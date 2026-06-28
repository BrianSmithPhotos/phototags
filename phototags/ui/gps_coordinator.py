"""GPS / geocode / altitude orchestration extracted from MainWindow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Callable, TYPE_CHECKING

from PySide6.QtCore import QThreadPool

from phototags.services.auto_metadata import merge_keywords, parse_keywords
from phototags.services.elevation_lookup_service import ElevationLookupService
from phototags.services.exif_service import ExifUiData
from phototags.services.reverse_geocode_service import ReverseGeocodeResult, ReverseGeocodeService
from phototags.services.timeline_location_service import GpsSuggestion, TimelineLocationService
from phototags.services.timeline_sync_service import TimelineSyncService
from phototags.workers.elevation_lookup import ElevationLookupSignals, ElevationLookupTask
from phototags.workers.location_suggester import LocationSuggestSignals, LocationSuggestTask
from phototags.workers.reverse_geocode_lookup import ReverseGeocodeSignals, ReverseGeocodeTask
from phototags.workers.timeline_sync import TimelineSyncSignals, TimelineSyncTask

if TYPE_CHECKING:
    from phototags.ui.main_window import MetadataDraft


@dataclass
class GpsContext:
    """Read/write hooks GpsCoordinator needs into MainWindow's state and UI."""

    selected_image_path: Callable[[], Path | None]
    metadata_drafts: dict[Path, "MetadataDraft"]
    group_by_path: Callable[[], dict]
    multi_selected_paths: Callable[[], tuple[Path, ...]]
    set_gps_status: Callable[..., None]
    clear_gps_status: Callable[[], None]
    set_gps_fields: Callable[..., None]
    gps_latitude_text: Callable[[], str]
    gps_longitude_text: Callable[[], str]
    gps_altitude_text: Callable[[], str]
    set_lookup_altitude_button_enabled: Callable[[bool], None]
    restore_action_controls: Callable[[], None]
    sync_current_draft: Callable[[], None]
    ensure_draft_for_path: Callable[[Path], "MetadataDraft | None"]
    is_manual_multi_target: Callable[[Path], bool]
    expand_to_capture_groups: Callable[[tuple[Path, ...]], tuple[Path, ...]]
    get_representative_for: Callable[[Path | None], Path | None]
    current_exif_ui_data: Callable[[], ExifUiData | None]
    suppress_metadata_sync: Callable[[bool], None]
    keywords_edit_set_text: Callable[[str], None]
    gps_altitude_edit_set_text: Callable[[str], None]


class GpsCoordinator:
    """Owns timeline/GPS, reverse-geocode, and altitude orchestration off the Qt main thread."""

    def __init__(self, ctx: GpsContext) -> None:
        self._ctx = ctx

        self._elevation_lookup_service = ElevationLookupService()
        self._reverse_geocode_service = ReverseGeocodeService()
        self._timeline_location_service = TimelineLocationService()
        self._timeline_sync_service = TimelineSyncService(
            local_path=self._timeline_location_service.timeline_path
        )
        self._active_timeline_sync_job: tuple[TimelineSyncTask, TimelineSyncSignals] | None = None

        self._location_pool = QThreadPool()
        self._location_pool.setMaxThreadCount(1)
        self._altitude_pool = QThreadPool()
        self._altitude_pool.setMaxThreadCount(1)
        self._geocode_pool = QThreadPool()
        self._geocode_pool.setMaxThreadCount(1)

        self._gps_suggestions: dict[Path, GpsSuggestion] = {}
        self._embedded_gps_by_path: dict[Path, bool] = {}
        self._embedded_altitude_by_path: dict[Path, bool] = {}
        self._altitude_target_paths: tuple[Path, ...] = tuple()
        self._geocode_target_paths: tuple[Path, ...] = tuple()
        self._location_context_by_path: dict[Path, str] = {}
        # Tracks capture-set representatives that received GPS auto-apply this session
        # so re-focusing the same set doesn't trigger a second apply.
        self._gps_auto_applied_paths: set[Path] = set()
        # Tracks representatives that received reverse-geocode auto-lookup this session
        # (covers both timeline-applied GPS and images with pre-existing embedded GPS).
        self._geocode_auto_applied_paths: set[Path] = set()

        self._location_request_id = 0
        self._location_job_id = 0
        self._active_location_jobs: dict[int, tuple[LocationSuggestTask, LocationSuggestSignals]] = {}
        self._altitude_request_id = 0
        self._altitude_job_id = 0
        self._active_altitude_jobs: dict[int, tuple[ElevationLookupTask, ElevationLookupSignals]] = {}
        self._geocode_request_id = 0
        self._geocode_job_id = 0
        self._active_geocode_jobs: dict[int, tuple[ReverseGeocodeTask, ReverseGeocodeSignals]] = {}

    # -- pools, for closeEvent teardown --

    @property
    def pools(self) -> tuple[QThreadPool, ...]:
        return (self._location_pool, self._altitude_pool, self._geocode_pool)

    # -- timeline sync --

    def start_timeline_sync(self) -> None:
        """Check Google Drive for a fresher Timeline.json export and copy it in if found."""
        signals = TimelineSyncSignals()
        signals.synced.connect(self._on_timeline_sync_finished)
        signals.failed.connect(self._on_timeline_sync_failed)
        task = TimelineSyncTask(service=self._timeline_sync_service, signals=signals)
        self._active_timeline_sync_job = (task, signals)
        self._location_pool.start(task)

    def _on_timeline_sync_finished(self, copied: bool) -> None:
        self._active_timeline_sync_job = None
        if copied:
            self._ctx.set_gps_status("Timeline.json updated from Google Drive.")

    def _on_timeline_sync_failed(self, error: str) -> None:
        self._active_timeline_sync_job = None
        self._ctx.set_gps_status(f"Timeline.json sync from Google Drive failed: {error}", is_error=True)

    # -- entry points called from MainWindow --

    def on_exif_loaded(self, path_obj: Path, ui_data: ExifUiData) -> None:
        """Kick off GPS suggest or existing-GPS geocode/altitude lookups after EXIF load."""
        if self._selected_has_embedded_gps():
            self._gps_suggestions.pop(path_obj, None)
            representative = self._ctx.get_representative_for(path_obj)
            if representative is not None and representative not in self._geocode_auto_applied_paths:
                self._geocode_auto_applied_paths.add(representative)
                lat, lon = self._current_gps_lat_lon()
                if lat is not None and lon is not None:
                    target_paths = self._gps_target_paths(path_obj)
                    self._start_reverse_geocode(
                        image_path=path_obj,
                        latitude=lat,
                        longitude=lon,
                        target_paths=target_paths,
                        reason="Existing GPS found; looking up city/county/state...",
                    )
                    self._start_altitude_lookup(
                        image_path=path_obj,
                        latitude=lat,
                        longitude=lon,
                        target_paths=target_paths,
                        reason=f"Looking up elevation for {len(target_paths)} file(s)...",
                    )
                else:
                    self._ctx.set_gps_status("Existing EXIF GPS found; coordinates could not be parsed")
            else:
                self._ctx.set_gps_status("Existing EXIF GPS found; location already looked up")
        else:
            self._start_gps_suggest(image_path=path_obj, captured_at=ui_data.captured_at)

    def catchup_for_group(self, selected: Path | None) -> None:
        """Propagate a GPS suggestion to group members that missed the auto-apply.

        The GPS auto-apply in _on_gps_suggested calls _gps_target_paths, which
        uses _group_by_path.  If _on_groups_loaded has not yet fired at that
        point, the group is unknown and GPS is applied only to the selected image.
        This method is called from MainWindow whenever grouping data changes; it
        finds any such under-applied GPS and fills in the missing members.
        """
        if selected is None:
            return
        suggestion = self._gps_suggestions.get(selected)
        if suggestion is None:
            return
        representative = self._ctx.get_representative_for(selected)
        if representative is None or representative not in self._gps_auto_applied_paths:
            return
        group = self._ctx.group_by_path().get(selected)
        if group is None or len(group.members) <= 1:
            return
        latitude_text = f"{suggestion.latitude:.7f}"
        longitude_text = f"{suggestion.longitude:.7f}"
        for member in group.members:
            if member == selected:
                continue
            if self._path_has_embedded_gps(member, probe=False):
                continue
            draft = self._ctx.metadata_drafts.get(member)
            if draft is None:
                draft = self._ctx.ensure_draft_for_path(member)
            if draft is None:
                continue
            if draft.gps_latitude or draft.gps_longitude:
                continue
            draft.gps_latitude = latitude_text
            draft.gps_longitude = longitude_text
            draft.gps_altitude = ""

    # -- timeline GPS suggest --

    def _start_gps_suggest(self, *, image_path: Path, captured_at: str) -> None:
        """Start one background timeline lookup for selected image capture time."""
        if not captured_at.strip():
            self._ctx.set_gps_status("Capture time is missing; cannot match timeline")
            return

        self._location_request_id += 1
        request_id = self._location_request_id
        self._location_job_id += 1
        job_id = self._location_job_id

        self._ctx.set_gps_status("Looking up nearest GPS in timeline...")

        signals = LocationSuggestSignals()
        signals.suggested.connect(partial(self._on_gps_suggested, request_id, job_id))
        signals.failed.connect(partial(self._on_gps_suggest_failed, request_id, job_id))

        task = LocationSuggestTask(
            image_path=image_path,
            captured_at=captured_at,
            service=self._timeline_location_service,
            signals=signals,
        )
        self._active_location_jobs[job_id] = (task, signals)
        self._location_pool.start(task)

    def _on_gps_suggested(
        self,
        request_id: int,
        job_id: int,
        image_path: str,
        suggestion: GpsSuggestion | None,
    ) -> None:
        """Apply timeline GPS lookup result for selected image."""
        self._finish_location_job(job_id)
        if request_id != self._location_request_id:
            return

        path_obj = Path(image_path)
        if suggestion is None:
            self._gps_suggestions.pop(path_obj, None)
            if path_obj == self._ctx.selected_image_path():
                self._ctx.set_gps_status("No timeline record within 60 minutes of capture time")
                self._ctx.restore_action_controls()
            return

        self._gps_suggestions[path_obj] = suggestion
        if path_obj != self._ctx.selected_image_path():
            return

        # Auto-apply GPS on first focus for this set in the current session.
        # The guard prevents re-applying when the user navigates back to the same set.
        representative = self._ctx.get_representative_for(path_obj)
        if representative is not None and representative not in self._gps_auto_applied_paths:
            self._gps_auto_applied_paths.add(representative)
            self.on_gps_apply_clicked()
            return  # on_gps_apply_clicked calls restore_action_controls

        matched_at = datetime.fromtimestamp(suggestion.matched_ts_utc, tz=timezone.utc)
        matched_at_text = matched_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        age_minutes = suggestion.age_seconds // 60
        age_seconds_remainder = suggestion.age_seconds % 60
        accuracy_text = (
            ""
            if suggestion.accuracy_m is None
            else f", accuracy {suggestion.accuracy_m:.0f}m"
        )
        self._ctx.set_gps_status(
            (
                f"Nearest GPS {age_minutes}m {age_seconds_remainder}s away "
                f"({suggestion.source_type}{accuracy_text}); matched {matched_at_text}"
            )
        )
        self._ctx.restore_action_controls()

    def _on_gps_suggest_failed(
        self,
        request_id: int,
        job_id: int,
        image_path: str,
        error: str,
    ) -> None:
        """Handle GPS timeline lookup errors."""
        self._finish_location_job(job_id)
        if request_id != self._location_request_id:
            return
        if Path(image_path) != self._ctx.selected_image_path():
            return
        self._gps_suggestions.pop(Path(image_path), None)
        self._ctx.set_gps_status(f"GPS lookup failed: {error}", is_error=True)
        self._ctx.restore_action_controls()

    # -- apply suggested GPS --

    def on_gps_apply_clicked(self) -> None:
        """Apply current timeline GPS suggestion into editable GPS fields for current set."""
        selected = self._ctx.selected_image_path()
        if selected is None:
            self._ctx.set_gps_status("No file selected", is_error=True)
            return
        if self._selected_has_embedded_gps():
            self._ctx.set_gps_status(
                "Existing EXIF GPS found; apply is disabled to avoid overwrite"
            )
            return
        suggestion = self._gps_suggestions.get(selected)
        if suggestion is None:
            self._ctx.set_gps_status("No GPS suggestion available", is_error=True)
            return

        self._ctx.sync_current_draft()
        target_paths = self._gps_target_paths(selected)
        latitude_text = f"{suggestion.latitude:.7f}"
        longitude_text = f"{suggestion.longitude:.7f}"

        applied_paths: list[Path] = []
        skipped_embedded = 0
        skipped_unreadable = 0
        for path in target_paths:
            if self._path_has_embedded_gps(path, probe=True):
                skipped_embedded += 1
                continue
            draft = self._ctx.ensure_draft_for_path(path)
            if draft is None:
                skipped_unreadable += 1
                continue
            draft.gps_latitude = latitude_text
            draft.gps_longitude = longitude_text
            draft.gps_altitude = ""
            applied_paths.append(path)

        if not applied_paths:
            self._ctx.set_gps_status(
                "GPS apply skipped: no eligible files in capture set",
                is_error=True,
            )
            self._ctx.restore_action_controls()
            return

        self._ctx.suppress_metadata_sync(True)
        try:
            self._ctx.set_gps_fields(
                latitude=latitude_text,
                longitude=longitude_text,
                altitude="",
            )
        finally:
            self._ctx.suppress_metadata_sync(False)
        self._ctx.sync_current_draft()

        status_parts = [f"Applied GPS to {len(applied_paths)}/{len(target_paths)} file(s) in capture set"]
        if skipped_embedded:
            status_parts.append(f"{skipped_embedded} skipped (existing EXIF GPS)")
        if skipped_unreadable:
            status_parts.append(f"{skipped_unreadable} skipped (metadata unreadable)")
        self._ctx.set_gps_status("; ".join(status_parts))
        self._ctx.restore_action_controls()
        representative = self._ctx.get_representative_for(selected)
        if representative is not None:
            self._geocode_auto_applied_paths.add(representative)
        self._start_reverse_geocode(
            image_path=selected,
            latitude=suggestion.latitude,
            longitude=suggestion.longitude,
            target_paths=target_paths,
            reason=f"Looking up city/county/state for {len(target_paths)} file(s)...",
        )
        # Timeline altitude (phone GPS/WIFI sensor noise) is unreliable even when
        # tagged "GPS" source, so altitude always comes from USGS elevation lookup
        # instead of whatever (if anything) the timeline export reported.
        self._start_altitude_lookup(
            image_path=selected,
            latitude=suggestion.latitude,
            longitude=suggestion.longitude,
            target_paths=tuple(applied_paths),
            reason=f"Looking up elevation for {len(applied_paths)} file(s)...",
        )

    # -- lookup altitude button --

    def on_lookup_altitude_clicked(
        self,
        *,
        save_inflight: bool,
        process_inflight: bool,
        ai_inflight: bool,
    ) -> None:
        """Lookup and fill missing altitude for current capture set."""
        selected = self._ctx.selected_image_path()
        if selected is None:
            self._ctx.set_gps_status("No file selected", is_error=True)
            return
        if save_inflight:
            self._ctx.set_gps_status("Save already running...", is_error=True)
            return
        if process_inflight:
            self._ctx.set_gps_status("Process already running...", is_error=True)
            return
        if ai_inflight:
            self._ctx.set_gps_status("AI suggestions running...", is_error=True)
            return

        latitude, longitude = self._current_gps_lat_lon()
        if latitude is None or longitude is None:
            self._ctx.set_gps_status(
                "Latitude and longitude must be numeric before altitude lookup",
                is_error=True,
            )
            return

        self._ctx.sync_current_draft()
        target_paths = self._gps_target_paths(selected)
        eligible_paths: list[Path] = []
        skipped_embedded_altitude = 0
        skipped_unreadable = 0
        already_has_altitude = 0
        for path in target_paths:
            if self._path_has_embedded_altitude(path, probe=True):
                skipped_embedded_altitude += 1
                continue
            draft = self._ctx.ensure_draft_for_path(path)
            if draft is None:
                skipped_unreadable += 1
                continue
            if draft.gps_altitude.strip():
                already_has_altitude += 1
                continue
            eligible_paths.append(path)

        if not eligible_paths:
            self._ctx.set_gps_status(
                "Altitude lookup skipped: no files need altitude updates"
            )
            return

        self._start_altitude_lookup(
            image_path=selected,
            latitude=latitude,
            longitude=longitude,
            target_paths=tuple(eligible_paths),
            reason=(
                f"Looking up altitude for {len(eligible_paths)} file(s)"
                + ("" if skipped_embedded_altitude == 0 else f" ({skipped_embedded_altitude} already had EXIF altitude)")
                + ("" if already_has_altitude == 0 else f" ({already_has_altitude} already had edited altitude)")
                + ("" if skipped_unreadable == 0 else f" ({skipped_unreadable} metadata unreadable)")
                + "..."
            ),
        )
        self._start_reverse_geocode(
            image_path=selected,
            latitude=latitude,
            longitude=longitude,
            target_paths=target_paths,
            reason=f"Looking up city/county/state for {len(target_paths)} file(s)...",
        )

    # -- altitude lookup --

    def _start_altitude_lookup(
        self,
        *,
        image_path: Path,
        latitude: float,
        longitude: float,
        target_paths: tuple[Path, ...] | None = None,
        reason: str,
    ) -> None:
        """Start background elevation lookup for one coordinate pair."""
        self._altitude_request_id += 1
        request_id = self._altitude_request_id
        self._altitude_job_id += 1
        job_id = self._altitude_job_id

        self._ctx.set_gps_status(reason)
        self._ctx.set_lookup_altitude_button_enabled(False)
        self._altitude_target_paths = tuple(target_paths or (image_path,))

        signals = ElevationLookupSignals()
        signals.looked_up.connect(partial(self._on_altitude_looked_up, request_id, job_id))
        signals.failed.connect(partial(self._on_altitude_lookup_failed, request_id, job_id))

        task = ElevationLookupTask(
            image_path=image_path,
            latitude=latitude,
            longitude=longitude,
            service=self._elevation_lookup_service,
            signals=signals,
        )
        self._active_altitude_jobs[job_id] = (task, signals)
        self._altitude_pool.start(task)

    def _on_altitude_looked_up(
        self,
        request_id: int,
        job_id: int,
        image_path: str,
        altitude_m: float,
    ) -> None:
        """Apply looked-up altitude for current capture set."""
        self._finish_altitude_job(job_id)
        if request_id != self._altitude_request_id:
            return

        path_obj = Path(image_path)
        if path_obj != self._ctx.selected_image_path():
            return

        targets = self._altitude_target_paths or (path_obj,)
        altitude_text = f"{altitude_m:.2f}"
        applied_count = 0
        skipped_existing = 0
        skipped_unreadable = 0
        selected_applied = False
        for path in targets:
            if self._path_has_embedded_altitude(path, probe=True):
                skipped_existing += 1
                continue
            draft = self._ctx.ensure_draft_for_path(path)
            if draft is None:
                skipped_unreadable += 1
                continue
            if draft.gps_altitude.strip():
                continue
            draft.gps_altitude = altitude_text
            applied_count += 1
            if path == path_obj:
                selected_applied = True

        if selected_applied:
            self._ctx.suppress_metadata_sync(True)
            try:
                self._ctx.gps_altitude_edit_set_text(altitude_text)
            finally:
                self._ctx.suppress_metadata_sync(False)
            self._ctx.sync_current_draft()

        if applied_count == 0:
            self._ctx.set_gps_status("Altitude lookup returned, but no files needed updates")
        else:
            status_parts = [f"Altitude filled for {applied_count}/{len(targets)} file(s): {altitude_text} m"]
            if skipped_existing:
                status_parts.append(f"{skipped_existing} skipped (existing EXIF altitude)")
            if skipped_unreadable:
                status_parts.append(f"{skipped_unreadable} skipped (metadata unreadable)")
            self._ctx.set_gps_status("; ".join(status_parts))
        self._ctx.restore_action_controls()

    def _on_altitude_lookup_failed(
        self,
        request_id: int,
        job_id: int,
        image_path: str,
        error: str,
    ) -> None:
        """Handle elevation lookup errors."""
        self._finish_altitude_job(job_id)
        if request_id != self._altitude_request_id:
            return
        if Path(image_path) != self._ctx.selected_image_path():
            return
        self._ctx.set_gps_status(f"Altitude lookup failed: {error}", is_error=True)
        self._ctx.restore_action_controls()

    # -- reverse geocode --

    def _start_reverse_geocode(
        self,
        *,
        image_path: Path,
        latitude: float,
        longitude: float,
        target_paths: tuple[Path, ...],
        reason: str,
    ) -> None:
        """Start background reverse geocode lookup for one coordinate pair."""
        if not target_paths:
            return
        self._geocode_request_id += 1
        request_id = self._geocode_request_id
        self._geocode_job_id += 1
        job_id = self._geocode_job_id

        self._ctx.set_gps_status(reason)
        self._geocode_target_paths = target_paths

        signals = ReverseGeocodeSignals()
        signals.looked_up.connect(partial(self._on_reverse_geocoded, request_id, job_id))
        signals.failed.connect(partial(self._on_reverse_geocode_failed, request_id, job_id))

        task = ReverseGeocodeTask(
            image_path=image_path,
            latitude=latitude,
            longitude=longitude,
            service=self._reverse_geocode_service,
            signals=signals,
        )
        self._active_geocode_jobs[job_id] = (task, signals)
        self._geocode_pool.start(task)

    def _on_reverse_geocoded(
        self,
        request_id: int,
        job_id: int,
        image_path: str,
        location: ReverseGeocodeResult,
    ) -> None:
        """Apply reverse geocode keywords/context to target drafts."""
        self._finish_geocode_job(job_id)
        if request_id != self._geocode_request_id:
            return

        path_obj = Path(image_path)
        if path_obj != self._ctx.selected_image_path():
            return

        tokens = location.keyword_tokens()
        if not tokens:
            self._ctx.set_gps_status("Reverse geocode returned no location keywords")
            return

        targets = self._geocode_target_paths or (path_obj,)
        applied_count = 0
        skipped_unreadable = 0
        selected_updated = False
        for path in targets:
            draft = self._ctx.ensure_draft_for_path(path)
            if draft is None:
                skipped_unreadable += 1
                continue
            merged_keywords = merge_keywords(
                parse_keywords(draft.keywords),
                tokens,
            )
            draft.keywords = ", ".join(merged_keywords)
            self._location_context_by_path[path] = location.context_text()
            applied_count += 1
            if path == path_obj:
                selected_updated = True

        if selected_updated:
            selected_draft = self._ctx.metadata_drafts.get(path_obj)
            if selected_draft is not None:
                self._ctx.suppress_metadata_sync(True)
                try:
                    self._ctx.keywords_edit_set_text(selected_draft.keywords)
                finally:
                    self._ctx.suppress_metadata_sync(False)
                self._ctx.sync_current_draft()

        if applied_count == 0:
            self._ctx.set_gps_status("Reverse geocode completed, but no files were updated")
            return

        summary = ", ".join(tokens)
        status_parts = [f"Added location keywords to {applied_count}/{len(targets)} file(s): {summary}"]
        if skipped_unreadable:
            status_parts.append(f"{skipped_unreadable} skipped (metadata unreadable)")
        self._ctx.set_gps_status("; ".join(status_parts))

    def _on_reverse_geocode_failed(
        self,
        request_id: int,
        job_id: int,
        image_path: str,
        error: str,
    ) -> None:
        """Handle reverse geocode errors without interrupting GPS edits."""
        self._finish_geocode_job(job_id)
        if request_id != self._geocode_request_id:
            return
        if Path(image_path) != self._ctx.selected_image_path():
            return
        self._ctx.set_gps_status(f"Reverse geocode failed: {error}", is_error=True)

    # -- embedded-GPS/altitude probing --

    def _path_has_embedded_gps(self, path: Path, *, probe: bool = False) -> bool:
        """Return True when a file already has EXIF latitude and longitude."""
        current_exif = self._ctx.current_exif_ui_data()
        if path == self._ctx.selected_image_path() and current_exif is not None:
            has_value = bool(
                current_exif.gps_latitude.strip()
                and current_exif.gps_longitude.strip()
            )
            self._embedded_gps_by_path[path] = has_value
            return has_value
        if path in self._embedded_gps_by_path:
            return self._embedded_gps_by_path[path]
        if not probe:
            return False
        draft = self._ctx.ensure_draft_for_path(path)
        if draft is None:
            self._embedded_gps_by_path[path] = True
            return True
        return self._embedded_gps_by_path.get(path, False)

    def _path_has_embedded_altitude(self, path: Path, *, probe: bool = False) -> bool:
        """Return True when a file already has EXIF altitude."""
        current_exif = self._ctx.current_exif_ui_data()
        if path == self._ctx.selected_image_path() and current_exif is not None:
            has_value = bool(current_exif.gps_altitude.strip())
            self._embedded_altitude_by_path[path] = has_value
            return has_value
        if path in self._embedded_altitude_by_path:
            return self._embedded_altitude_by_path[path]
        if not probe:
            return False
        draft = self._ctx.ensure_draft_for_path(path)
        if draft is None:
            self._embedded_altitude_by_path[path] = True
            return True
        return self._embedded_altitude_by_path.get(path, False)

    def path_has_embedded_altitude(self, path: Path, *, probe: bool = False) -> bool:
        """Public wrapper used by MainWindow to check embedded altitude for a path."""
        return self._path_has_embedded_altitude(path, probe=probe)

    def set_embedded_gps(self, path: Path, has_gps: bool) -> None:
        """Record embedded-GPS state for a path (called after a fresh EXIF read)."""
        self._embedded_gps_by_path[path] = has_gps

    def set_embedded_altitude(self, path: Path, has_altitude: bool) -> None:
        """Record embedded-altitude state for a path (called after a fresh EXIF read)."""
        self._embedded_altitude_by_path[path] = has_altitude

    def _selected_has_embedded_gps(self) -> bool:
        """Return True when selected image already contains EXIF lat/lon values."""
        data = self._ctx.current_exif_ui_data()
        if data is None:
            return False
        return bool(data.gps_latitude.strip() and data.gps_longitude.strip())

    # -- target path / context helpers --

    def gps_target_paths(self, selected_path: Path) -> tuple[Path, ...]:
        """Public wrapper for _gps_target_paths."""
        return self._gps_target_paths(selected_path)

    def _gps_target_paths(self, selected_path: Path) -> tuple[Path, ...]:
        """Return capture-set members for GPS/altitude apply actions.

        A manual multi-selection (cmd-click/shift-click in the left nav) takes
        priority over capture-group membership when active, same as
        `_ai_targets_for`. Per-file embedded-GPS/altitude checks in the callers
        (`on_gps_apply_clicked`, altitude lookup) already skip any file that
        has its own real GPS, so this is safe even across files that may span
        different locations.
        """
        if self._ctx.is_manual_multi_target(selected_path):
            return self._ctx.expand_to_capture_groups(self._ctx.multi_selected_paths())
        group = self._ctx.group_by_path().get(selected_path)
        if group is None:
            return (selected_path,)
        return tuple(group.members)

    def current_gps_lat_lon(self) -> tuple[float | None, float | None]:
        """Public wrapper for _current_gps_lat_lon."""
        return self._current_gps_lat_lon()

    def _current_gps_lat_lon(self) -> tuple[float | None, float | None]:
        """Return numeric lat/lon from editable GPS fields when valid."""
        lat_text = self._ctx.gps_latitude_text()
        lon_text = self._ctx.gps_longitude_text()
        if not lat_text or not lon_text:
            return None, None
        try:
            return float(lat_text), float(lon_text)
        except ValueError:
            return None, None

    def location_context_for_paths(self, target_paths: tuple[Path, ...]) -> str:
        """Return merged reverse-geocode context text for AI prompting."""
        contexts: list[str] = []
        seen: set[str] = set()
        for path in target_paths:
            context = self._location_context_by_path.get(path, "").strip()
            if not context:
                continue
            key = context.casefold()
            if key in seen:
                continue
            seen.add(key)
            contexts.append(context)
        return " | ".join(contexts)

    # -- job bookkeeping --

    def _finish_location_job(self, job_id: int) -> None:
        """Release references for completed location suggestion tasks."""
        self._active_location_jobs.pop(job_id, None)

    def _finish_altitude_job(self, job_id: int) -> None:
        """Release references for completed altitude lookup tasks."""
        self._active_altitude_jobs.pop(job_id, None)

    def _finish_geocode_job(self, job_id: int) -> None:
        """Release references for completed reverse-geocode tasks."""
        self._active_geocode_jobs.pop(job_id, None)
