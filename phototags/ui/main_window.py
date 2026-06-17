"""Main window composition for MacPhotoMaster."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
import os
from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QCloseEvent, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QSplitter, QWidget

from phototags.services.ai_suggestion_service import OLLAMA_DEFAULT_MODEL, AiSuggestionService
from phototags.services.capture_group_service import CaptureGroup, CaptureGroupingResult, CaptureGroupService
from phototags.services.elevation_lookup_service import ElevationLookupService
from phototags.services.exif_service import ExifService, ExifUiData
from phototags.services.metadata_write_service import MetadataWriteService
from phototags.services.process_move_service import ProcessMoveService
from phototags.services.rename_service import RenameContext, RenameService
from phototags.services.timeline_location_service import GpsSuggestion, TimelineLocationService
from phototags.ui.widgets.image_preview_widget import ImagePreviewWidget
from phototags.ui.widgets.metadata_panel import MetadataPanel
from phototags.ui.widgets.source_panel import SourcePanel
from phototags.workers.capture_group_loader import CaptureGroupLoadSignals, CaptureGroupLoadTask
from phototags.workers.elevation_lookup import ElevationLookupSignals, ElevationLookupTask
from phototags.workers.exif_loader import ExifLoadSignals, ExifLoadTask
from phototags.workers.image_loader import ImageLoadSignals, ImageLoadTask
from phototags.workers.location_suggester import LocationSuggestSignals, LocationSuggestTask
from phototags.workers.ai_suggester import AiSuggestPayload, AiSuggestSignals, AiSuggestTask
from phototags.workers.metadata_writer import (
    MetadataBatchSaveResult,
    MetadataBatchSaveSignals,
    MetadataBatchSaveTask,
)
from phototags.workers.process_batch_mover import ProcessBatchResult, ProcessBatchSignals, ProcessBatchTask

PREVIEW_MAX_EDGE = 2800
THUMBNAIL_WORKERS = 4
DESTINATION_ROOT = Path("/Users/bsmi067/Pictures/DxO")
GROUP_DEBUG_ENABLED = os.getenv("PHOTOTAGS_GROUP_DEBUG", "").strip().casefold() in {"1", "true", "yes"}


@dataclass(slots=True)
class MetadataDraft:
    """In-memory editable metadata draft for one source image."""

    description: str
    keywords: str
    gps_latitude: str
    gps_longitude: str
    gps_altitude: str


class MainWindow(QMainWindow):
    """Single-window app shell with source, preview, and metadata panels."""

    def __init__(self, source_dir: Path) -> None:
        super().__init__()
        self._ai_suggestion_service = AiSuggestionService()
        self._capture_group_service = CaptureGroupService()
        self._elevation_lookup_service = ElevationLookupService()
        self._exif_service = ExifService()
        self._metadata_write_service = MetadataWriteService()
        self._rename_service = RenameService()
        self._timeline_location_service = TimelineLocationService()
        self._process_move_service = ProcessMoveService(
            metadata_write_service=self._metadata_write_service,
            rename_service=self._rename_service,
        )
        self._thumbnail_pool = QThreadPool(self)
        self._thumbnail_pool.setMaxThreadCount(THUMBNAIL_WORKERS)
        self._group_pool = QThreadPool(self)
        self._group_pool.setMaxThreadCount(1)
        self._preview_pool = QThreadPool(self)
        self._preview_pool.setMaxThreadCount(1)
        self._exif_pool = QThreadPool(self)
        self._exif_pool.setMaxThreadCount(1)
        self._metadata_write_pool = QThreadPool(self)
        self._metadata_write_pool.setMaxThreadCount(1)
        self._location_pool = QThreadPool(self)
        self._location_pool.setMaxThreadCount(1)
        self._altitude_pool = QThreadPool(self)
        self._altitude_pool.setMaxThreadCount(1)
        self._ai_pool = QThreadPool(self)
        self._ai_pool.setMaxThreadCount(1)
        self._process_pool = QThreadPool(self)
        self._process_pool.setMaxThreadCount(1)
        self._group_request_id = 0
        self._group_job_id = 0
        self._active_group_jobs: dict[int, tuple[CaptureGroupLoadTask, CaptureGroupLoadSignals]] = {}
        self._capture_groups: tuple[CaptureGroup, ...] = tuple()
        self._group_by_path: dict[Path, CaptureGroup] = {}
        self._preview_request_id = 0
        self._preview_job_id = 0
        self._active_preview_jobs: dict[int, tuple[ImageLoadTask, ImageLoadSignals]] = {}
        self._exif_request_id = 0
        self._exif_job_id = 0
        self._active_exif_jobs: dict[int, tuple[ExifLoadTask, ExifLoadSignals]] = {}
        self._metadata_write_request_id = 0
        self._metadata_write_job_id = 0
        self._active_metadata_write_jobs: dict[int, tuple[MetadataBatchSaveTask, MetadataBatchSaveSignals]] = {}
        self._location_request_id = 0
        self._location_job_id = 0
        self._active_location_jobs: dict[int, tuple[LocationSuggestTask, LocationSuggestSignals]] = {}
        self._altitude_request_id = 0
        self._altitude_job_id = 0
        self._active_altitude_jobs: dict[int, tuple[ElevationLookupTask, ElevationLookupSignals]] = {}
        self._ai_request_id = 0
        self._ai_job_id = 0
        self._active_ai_jobs: dict[int, tuple[AiSuggestTask, AiSuggestSignals]] = {}
        self._process_request_id = 0
        self._process_job_id = 0
        self._active_process_jobs: dict[int, tuple[ProcessBatchTask, ProcessBatchSignals]] = {}
        self._ai_inflight = False
        self._save_inflight = False
        self._process_inflight = False
        self._selected_image_path: Path | None = None
        self._current_exif_ui_data: ExifUiData | None = None
        self._metadata_drafts: dict[Path, MetadataDraft] = {}
        self._gps_suggestions: dict[Path, GpsSuggestion] = {}
        self._embedded_gps_by_path: dict[Path, bool] = {}
        self._embedded_altitude_by_path: dict[Path, bool] = {}
        self._gps_altitude_unreliable_by_path: dict[Path, bool] = {}
        self._gps_altitude_source_by_path: dict[Path, str] = {}
        self._altitude_target_paths: tuple[Path, ...] = tuple()
        self._suppress_metadata_sync = False
        self.setWindowTitle("MacPhotoMaster")
        self.resize(1460, 900)
        self.setMinimumSize(1180, 720)
        self._build_ui(source_dir=source_dir)

    def _build_ui(self, source_dir: Path) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)

        self.source_panel = SourcePanel(
            source_dir=source_dir,
            thread_pool=self._thumbnail_pool,
        )
        self.preview_panel = ImagePreviewWidget()
        self.metadata_panel = MetadataPanel()
        self.source_panel.folder_selected.connect(self._on_folder_selected)
        self.source_panel.photo_selected.connect(self._on_photo_selected)
        self.source_panel.thumbnail_loaded.connect(self._on_thumbnail_loaded)
        self.preview_panel.variant_selected.connect(self._on_variant_selected)
        self.metadata_panel.save_single_button.clicked.connect(self._on_save_single_clicked)
        self.metadata_panel.save_set_button.clicked.connect(self._on_save_set_clicked)
        self.metadata_panel.process_single_button.clicked.connect(self._on_process_single_clicked)
        self.metadata_panel.process_set_button.clicked.connect(self._on_process_set_clicked)
        self.metadata_panel.process_session_button.clicked.connect(self._on_process_session_clicked)
        self.metadata_panel.suggest_button.clicked.connect(self._on_ai_suggest_clicked)
        self.metadata_panel.suggest_gps_button.clicked.connect(self._on_gps_suggest_clicked)
        self.metadata_panel.apply_gps_button.clicked.connect(self._on_gps_apply_clicked)
        self.metadata_panel.lookup_altitude_button.clicked.connect(self._on_lookup_altitude_clicked)
        self.metadata_panel.location_edit.textChanged.connect(self._update_rename_preview)
        self.metadata_panel.description_edit.textChanged.connect(self._on_metadata_edited)
        self.metadata_panel.keywords_edit.textChanged.connect(self._on_metadata_edited)
        self.metadata_panel.gps_latitude_edit.textChanged.connect(self._on_metadata_edited)
        self.metadata_panel.gps_longitude_edit.textChanged.connect(self._on_metadata_edited)
        self.metadata_panel.gps_altitude_edit.textChanged.connect(self._on_metadata_edited)
        self.metadata_panel.gps_altitude_edit.textEdited.connect(self._on_altitude_manually_edited)
        self.metadata_panel.set_ai_model_name(OLLAMA_DEFAULT_MODEL)
        self.preview_panel.skip_single_button.clicked.connect(self._on_skip_single_selected)
        self.preview_panel.skip_set_button.clicked.connect(self._on_skip_set_selected)
        self._skip_shortcut = QShortcut(QKeySequence("Meta+Backspace"), self)
        self._skip_shortcut.activated.connect(self._on_skip_single_selected)
        self._on_folder_selected(self.source_panel.current_folder)
        if self.source_panel.selected_path is not None:
            self._on_photo_selected(self.source_panel.selected_path)

        splitter.addWidget(self.source_panel)
        splitter.addWidget(self.preview_panel)
        splitter.addWidget(self.metadata_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 3)

        layout.addWidget(splitter)

    def _on_photo_selected(self, image_path: Path | None) -> None:
        """Start background preview loading for selected photo."""
        self._sync_current_draft()
        self._selected_image_path = image_path
        if image_path is None:
            self._current_exif_ui_data = None
            self.preview_panel.clear_preview("No supported files in this folder")
            self.preview_panel.set_variants([], None)
            self.metadata_panel.clear_metadata("No file selected")
            self.metadata_panel.set_rename_preview("")
            self.preview_panel.skip_single_button.setEnabled(False)
            self.preview_panel.skip_set_button.setEnabled(False)
            self.metadata_panel.set_suggest_button_enabled(False)
            self.metadata_panel.set_process_buttons_enabled(False)
            self.metadata_panel.set_gps_lookup_button_enabled(False)
            self.metadata_panel.set_gps_apply_button_enabled(False)
            self.metadata_panel.set_lookup_altitude_button_enabled(False)
            self.metadata_panel.clear_gps_status()
            return

        self._preview_request_id += 1
        request_id = self._preview_request_id
        self.preview_panel.set_loading_state(image_path.name)
        self._refresh_variant_strip(image_path)

        self._preview_job_id += 1
        job_id = self._preview_job_id
        signals = ImageLoadSignals()
        signals.loaded.connect(partial(self._on_preview_loaded, request_id, job_id))
        signals.failed.connect(partial(self._on_preview_failed, request_id, job_id))

        task = ImageLoadTask(
            image_path=image_path,
            signals=signals,
            max_edge=PREVIEW_MAX_EDGE,
        )
        self._active_preview_jobs[job_id] = (task, signals)
        self._preview_pool.start(task)

        self._start_exif_load(image_path=image_path)
        self.metadata_panel.clear_ai_suggestions()
        self.metadata_panel.clear_gps_status()
        self.metadata_panel.set_gps_apply_button_enabled(False)
        self._restore_metadata_action_controls()
        self.metadata_panel.set_save_status("")
        self._update_rename_preview()

    def _on_folder_selected(self, folder_path: Path) -> None:
        """Start background capture grouping for the selected folder."""
        image_paths = self.source_panel.current_image_paths
        self._capture_groups = tuple()
        self._group_by_path = {}
        self.source_panel.set_group_sizes({})

        if not image_paths:
            self.preview_panel.set_variants([], None)
            return

        self._group_request_id += 1
        request_id = self._group_request_id
        self._group_job_id += 1
        job_id = self._group_job_id

        signals = CaptureGroupLoadSignals()
        signals.loaded.connect(partial(self._on_groups_loaded, request_id, job_id))
        signals.failed.connect(partial(self._on_groups_failed, request_id, job_id))

        task = CaptureGroupLoadTask(
            folder_path=folder_path,
            image_paths=image_paths,
            service=self._capture_group_service,
            signals=signals,
        )
        self._active_group_jobs[job_id] = (task, signals)
        self._group_pool.start(task)

    def _start_exif_load(self, image_path: Path) -> None:
        """Start background EXIF load for selected image."""
        self._exif_request_id += 1
        request_id = self._exif_request_id
        self.metadata_panel.set_exif_dump("Loading EXIF metadata...")

        self._exif_job_id += 1
        job_id = self._exif_job_id

        signals = ExifLoadSignals()
        signals.loaded.connect(partial(self._on_exif_loaded, request_id, job_id))
        signals.failed.connect(partial(self._on_exif_failed, request_id, job_id))

        task = ExifLoadTask(
            image_path=image_path,
            signals=signals,
            service=self._exif_service,
        )
        self._active_exif_jobs[job_id] = (task, signals)
        self._exif_pool.start(task)

    def _on_preview_loaded(
        self,
        request_id: int,
        job_id: int,
        _image_path: str,
        data: bytes,
        _width: int,
        _height: int,
    ) -> None:
        """Apply loaded preview if it belongs to latest selection."""
        self._finish_preview_job(job_id)
        if request_id != self._preview_request_id:
            return

        pixmap = QPixmap()
        pixmap.loadFromData(data, "PNG")
        if pixmap.isNull():
            self.preview_panel.clear_preview("Unable to decode selected image")
            return
        self.preview_panel.set_preview_pixmap(pixmap)

    def _on_thumbnail_loaded(self, image_path: Path) -> None:
        """Refresh variant strip when source thumbnails become available."""
        selected = self._selected_image_path
        if selected is None:
            return
        group = self._group_by_path.get(selected)
        if group is None:
            if image_path == selected:
                self._refresh_variant_strip(selected)
            return
        if image_path in group.members:
            self._refresh_variant_strip(selected)

    def _on_preview_failed(
        self,
        request_id: int,
        job_id: int,
        image_path: str,
        _error: str,
    ) -> None:
        """Show decode fallback for preview failures."""
        self._finish_preview_job(job_id)
        if request_id != self._preview_request_id:
            return
        self.preview_panel.clear_preview(f"No preview available for {Path(image_path).name}")

    def _on_exif_loaded(
        self,
        request_id: int,
        job_id: int,
        image_path: str,
        ui_data: ExifUiData,
        dump_text: str,
    ) -> None:
        """Populate right panel metadata fields and full dump."""
        self._finish_exif_job(job_id)
        if request_id != self._exif_request_id:
            return
        path_obj = Path(image_path)
        draft = self._metadata_drafts.get(path_obj)
        keywords_source = draft.keywords if draft is not None else ui_data.keywords
        keywords_text = self._keywords_with_auto_tokens(
            keywords_source,
            ui_data.art_filter_token,
            ui_data.camera_model,
            ui_data.lens_model,
        )
        description_text = draft.description if draft is not None else ui_data.description
        gps_latitude_text = draft.gps_latitude if draft is not None else ui_data.gps_latitude
        gps_longitude_text = draft.gps_longitude if draft is not None else ui_data.gps_longitude
        gps_altitude_text = draft.gps_altitude if draft is not None else ui_data.gps_altitude
        altitude_unreliable = self._gps_altitude_unreliable_by_path.get(path_obj, False)
        altitude_source = self._gps_altitude_source_by_path.get(path_obj, "")

        self._suppress_metadata_sync = True
        try:
            self.metadata_panel.set_metadata_fields(
                title=ui_data.title,
                description=description_text,
                keywords=keywords_text,
                camera=ui_data.camera,
                lens_type=ui_data.lens_type,
                aperture=ui_data.aperture,
                shutter_speed=ui_data.shutter_speed,
                focal_length=ui_data.focal_length,
                focus_distance=ui_data.focus_distance,
                captured_at=ui_data.captured_at_display,
                iso=ui_data.iso,
                gps_latitude=gps_latitude_text,
                gps_longitude=gps_longitude_text,
                gps_altitude=gps_altitude_text,
            )
            self.metadata_panel.set_gps_altitude_unreliable(
                altitude_unreliable and bool(gps_altitude_text.strip()),
                source_type=altitude_source,
            )
        finally:
            self._suppress_metadata_sync = False
        self._current_exif_ui_data = ui_data
        self._embedded_gps_by_path[path_obj] = bool(ui_data.gps_latitude.strip() and ui_data.gps_longitude.strip())
        self._embedded_altitude_by_path[path_obj] = bool(ui_data.gps_altitude.strip())
        self.metadata_panel.set_exif_dump(dump_text)
        self._metadata_drafts[path_obj] = MetadataDraft(
            description=description_text,
            keywords=keywords_text,
            gps_latitude=gps_latitude_text,
            gps_longitude=gps_longitude_text,
            gps_altitude=gps_altitude_text,
        )
        if self._selected_has_embedded_gps():
            self._gps_suggestions.pop(path_obj, None)
            self._gps_altitude_unreliable_by_path[path_obj] = False
            self._gps_altitude_source_by_path.pop(path_obj, None)
            self.metadata_panel.set_gps_altitude_unreliable(False)
            self.metadata_panel.set_gps_status("Existing EXIF GPS found; timeline suggestion skipped")
        else:
            self._start_gps_suggest(image_path=path_obj, captured_at=ui_data.captured_at)
        self._restore_metadata_action_controls()
        self._update_rename_preview()

    def _on_groups_loaded(
        self,
        request_id: int,
        job_id: int,
        folder_path: str,
        result: CaptureGroupingResult,
    ) -> None:
        """Apply capture grouping result to current UI state."""
        self._finish_group_job(job_id)
        if request_id != self._group_request_id:
            return
        if Path(folder_path) != self.source_panel.current_folder:
            return

        self._capture_groups = result.groups
        self._group_by_path = result.by_path
        group_sizes = {path: len(group.members) for path, group in self._group_by_path.items()}
        self.source_panel.set_group_sizes(group_sizes)
        self._refresh_variant_strip(self._selected_image_path)

        if GROUP_DEBUG_ENABLED and result.debug_text:
            print("Capture grouping debug:")
            print(result.debug_text)

    def _on_groups_failed(
        self,
        request_id: int,
        job_id: int,
        folder_path: str,
        error: str,
    ) -> None:
        """Handle grouping failure while keeping normal selection workflow active."""
        self._finish_group_job(job_id)
        if request_id != self._group_request_id:
            return
        if Path(folder_path) != self.source_panel.current_folder:
            return

        self._capture_groups = tuple()
        self._group_by_path = {}
        self.source_panel.set_group_sizes({})
        self._refresh_variant_strip(self._selected_image_path)
        self.metadata_panel.set_save_status(f"Grouping failed: {error}", is_error=True)

    def _on_exif_failed(
        self,
        request_id: int,
        job_id: int,
        image_path: str,
        error: str,
    ) -> None:
        """Show EXIF load errors in metadata area."""
        self._finish_exif_job(job_id)
        if request_id != self._exif_request_id:
            return
        self._current_exif_ui_data = None
        self.metadata_panel.clear_metadata(
            f"Failed to read EXIF for {Path(image_path).name}\n\n{error}"
        )
        self.metadata_panel.set_rename_preview("")
        self.metadata_panel.set_suggest_button_enabled(False)
        self.metadata_panel.set_gps_lookup_button_enabled(False)
        self.metadata_panel.set_gps_apply_button_enabled(False)
        self.metadata_panel.set_lookup_altitude_button_enabled(False)

    def _on_save_single_clicked(self) -> None:
        """Persist description + keywords only for selected file."""
        selected = self._selected_image_path
        if selected is None:
            self.metadata_panel.set_save_status("No file selected", is_error=True)
            return
        self._start_save_scope("single image", [selected])

    def _on_save_set_clicked(self) -> None:
        """Persist description + keywords for all files in selected capture set."""
        selected = self._selected_image_path
        if selected is None:
            self.metadata_panel.set_save_status("No file selected", is_error=True)
            return
        group = self._group_by_path.get(selected)
        paths = list(group.members) if group is not None else [selected]
        self._start_save_scope("capture set", paths)

    def _start_save_scope(self, scope_label: str, paths: list[Path]) -> None:
        """Start one background save job for selected scope."""
        if self._save_inflight:
            self.metadata_panel.set_save_status("Save already running...", is_error=True)
            return
        if self._process_inflight:
            self.metadata_panel.set_save_status("Process already running...", is_error=True)
            return
        if self._ai_inflight:
            self.metadata_panel.set_save_status("AI suggestions running...", is_error=True)
            return
        unique_paths = self._dedupe_paths(paths)
        if not unique_paths:
            self.metadata_panel.set_save_status("No files to save", is_error=True)
            return

        self._sync_current_draft()
        draft_snapshot = {
            str(path): (
                draft.description,
                draft.keywords,
                draft.gps_latitude,
                draft.gps_longitude,
                draft.gps_altitude,
            )
            for path, draft in self._metadata_drafts.items()
        }

        self._metadata_write_request_id += 1
        request_id = self._metadata_write_request_id
        self._metadata_write_job_id += 1
        job_id = self._metadata_write_job_id

        self._save_inflight = True
        self.metadata_panel.set_save_buttons_enabled(False)
        self.metadata_panel.set_process_buttons_enabled(False)
        self.metadata_panel.set_suggest_button_enabled(False)
        self.metadata_panel.set_gps_lookup_button_enabled(False)
        self.metadata_panel.set_gps_apply_button_enabled(False)
        self.metadata_panel.set_lookup_altitude_button_enabled(False)
        self.preview_panel.skip_single_button.setEnabled(False)
        self.preview_panel.skip_set_button.setEnabled(False)
        self.metadata_panel.set_save_status(
            f"Saving description + keywords for {len(unique_paths)} file(s) ({scope_label})..."
        )

        signals = MetadataBatchSaveSignals()
        signals.completed.connect(partial(self._on_metadata_batch_saved, request_id, job_id))
        signals.failed.connect(partial(self._on_metadata_batch_save_failed, request_id, job_id))

        task = MetadataBatchSaveTask(
            image_paths=tuple(unique_paths),
            scope_label=scope_label,
            draft_by_path=draft_snapshot,
            exif_service=self._exif_service,
            metadata_write_service=self._metadata_write_service,
            signals=signals,
        )
        self._active_metadata_write_jobs[job_id] = (task, signals)
        self._metadata_write_pool.start(task)

    def _on_metadata_batch_saved(
        self,
        request_id: int,
        job_id: int,
        result: MetadataBatchSaveResult,
    ) -> None:
        """Handle successful completion for scoped metadata save."""
        self._finish_metadata_write_job(job_id)
        if request_id != self._metadata_write_request_id:
            return

        self._save_inflight = False
        selected = self._selected_image_path
        selected_saved = False
        selected_keywords = ""
        selected_description = ""
        for item in result.outcomes:
            if item.error:
                continue
            image_path = Path(item.image_path)
            keywords_text = ", ".join(item.keywords)
            existing_draft = self._metadata_drafts.get(image_path)
            self._metadata_drafts[image_path] = MetadataDraft(
                description=item.description,
                keywords=keywords_text,
                gps_latitude=(existing_draft.gps_latitude if existing_draft is not None else ""),
                gps_longitude=(existing_draft.gps_longitude if existing_draft is not None else ""),
                gps_altitude=(existing_draft.gps_altitude if existing_draft is not None else ""),
            )
            if selected is not None and image_path == selected:
                selected_saved = True
                selected_keywords = keywords_text
                selected_description = item.description

        if selected_saved:
            self._suppress_metadata_sync = True
            try:
                self.metadata_panel.keywords_edit.setPlainText(selected_keywords)
                self.metadata_panel.description_edit.setPlainText(selected_description)
            finally:
                self._suppress_metadata_sync = False

        self._restore_metadata_action_controls()
        if result.failure_count == 0:
            self.metadata_panel.set_save_status(
                f"Saved description + keywords for {result.success_count}/{result.total_count} files ({result.scope_label})"
            )
        else:
            first_failure = next((item for item in result.outcomes if item.error), None)
            failure_hint = ""
            if first_failure is not None:
                failure_hint = f" First failure: {Path(first_failure.image_path).name}."
            self.metadata_panel.set_save_status(
                (
                    f"Saved {result.success_count}/{result.total_count} files ({result.scope_label}); "
                    f"{result.failure_count} failed.{failure_hint}"
                ),
                is_error=True,
            )

        if selected is not None and selected_saved:
            self._start_exif_load(selected)

    def _on_metadata_batch_save_failed(
        self,
        request_id: int,
        job_id: int,
        error: str,
    ) -> None:
        """Show fatal scoped metadata save error to user."""
        self._finish_metadata_write_job(job_id)
        if request_id != self._metadata_write_request_id:
            return
        self._save_inflight = False
        self._restore_metadata_action_controls()
        self.metadata_panel.set_save_status(f"Save failed: {error}", is_error=True)

    def _on_ai_suggest_clicked(self) -> None:
        """Request AI description and keyword suggestions for selected image."""
        if self._selected_image_path is None:
            self.metadata_panel.set_ai_status("No file selected", is_error=True)
            return
        if self._save_inflight:
            self.metadata_panel.set_ai_status("Save already running...", is_error=True)
            return
        if self._process_inflight:
            self.metadata_panel.set_ai_status("Process already running...", is_error=True)
            return
        if self._ai_inflight:
            self.metadata_panel.set_ai_status("AI suggestions already running...", is_error=True)
            return

        self._sync_current_draft()
        selected_path = self._selected_image_path
        if selected_path is None:
            self.metadata_panel.set_ai_status("No file selected", is_error=True)
            return
        representative_path, target_paths = self._ai_targets_for(selected_path)
        model_name = self.metadata_panel.ai_model_name() or OLLAMA_DEFAULT_MODEL
        self.metadata_panel.set_ai_model_name(model_name)

        existing_keywords_by_path: dict[str, str] = {}
        for path in target_paths:
            draft = self._metadata_drafts.get(path)
            if draft is not None:
                existing_keywords_by_path[str(path)] = draft.keywords
                continue
            if path == selected_path:
                existing_keywords_by_path[str(path)] = self.metadata_panel.keywords_text()

        self._ai_request_id += 1
        request_id = self._ai_request_id
        self._ai_job_id += 1
        job_id = self._ai_job_id

        self._ai_inflight = True
        self.metadata_panel.set_suggest_button_enabled(False)
        self.metadata_panel.set_save_button_enabled(False)
        self.metadata_panel.set_process_buttons_enabled(False)
        self.metadata_panel.set_gps_lookup_button_enabled(False)
        self.metadata_panel.set_gps_apply_button_enabled(False)
        self.metadata_panel.set_lookup_altitude_button_enabled(False)
        self.preview_panel.skip_single_button.setEnabled(False)
        self.preview_panel.skip_set_button.setEnabled(False)
        if len(target_paths) > 1:
            self.metadata_panel.set_ai_status(
                f"Generating AI suggestions for {len(target_paths)}-image set..."
            )
        else:
            self.metadata_panel.set_ai_status("Generating AI suggestions...")

        signals = AiSuggestSignals()
        signals.suggested.connect(partial(self._on_ai_suggested, request_id, job_id))
        signals.failed.connect(partial(self._on_ai_suggest_failed, request_id, job_id))

        task = AiSuggestTask(
            representative_path=representative_path,
            target_paths=target_paths,
            model_name=model_name,
            existing_keywords_by_path=existing_keywords_by_path,
            existing_keywords_text=self.metadata_panel.keywords_text(),
            existing_description=self.metadata_panel.description_text(),
            capture_context=self._capture_context(),
            ai_service=self._ai_suggestion_service,
            exif_service=self._exif_service,
            signals=signals,
        )
        self._active_ai_jobs[job_id] = (task, signals)
        self._ai_pool.start(task)

    def _on_ai_suggested(
        self,
        request_id: int,
        job_id: int,
        payload: AiSuggestPayload,
    ) -> None:
        """Apply AI suggestions to all target files as editable drafts."""
        self._finish_ai_job(job_id)
        if request_id != self._ai_request_id:
            return

        self._ai_inflight = False
        for path_text in payload.target_paths:
            path_obj = Path(path_text)
            base_keywords = payload.base_keywords_by_path.get(path_text, "")
            art_filter = payload.art_filter_by_path.get(path_text, "")
            camera_model = payload.camera_by_path.get(path_text, "")
            lens_model = payload.lens_by_path.get(path_text, "")
            with_art_filter = self._keywords_with_auto_tokens(
                base_keywords,
                art_filter,
                camera_model,
                lens_model,
            )
            merged_keywords = self._merge_keywords(
                self._parse_keywords(with_art_filter),
                payload.suggestion.keywords,
            )
            existing_draft = self._metadata_drafts.get(path_obj)
            self._metadata_drafts[path_obj] = MetadataDraft(
                description=payload.suggestion.description,
                keywords=", ".join(merged_keywords),
                gps_latitude=(existing_draft.gps_latitude if existing_draft is not None else ""),
                gps_longitude=(existing_draft.gps_longitude if existing_draft is not None else ""),
                gps_altitude=(existing_draft.gps_altitude if existing_draft is not None else ""),
            )

        selected_path = self._selected_image_path
        if selected_path is not None:
            selected_draft = self._metadata_drafts.get(selected_path)
            if selected_draft is not None:
                self._suppress_metadata_sync = True
                try:
                    self.metadata_panel.description_edit.setPlainText(selected_draft.description)
                    self.metadata_panel.keywords_edit.setPlainText(selected_draft.keywords)
                finally:
                    self._suppress_metadata_sync = False

        self._restore_metadata_action_controls()
        applied_count = len(payload.target_paths)
        refinement_note = ""
        if payload.suggestion.refinement_applied:
            refinement_note = "crop-refinement applied"
        elif payload.suggestion.refinement_attempted:
            refinement_note = "crop-refinement attempted"
        status_suffix = f"; {refinement_note}" if refinement_note else ""
        if applied_count > 1:
            self.metadata_panel.set_ai_status(
                f"AI suggestions applied to {applied_count} images; keywords auto-appended{status_suffix}"
            )
            return
        self.metadata_panel.set_ai_status(
            f"AI suggestions ready; keywords auto-appended{status_suffix}"
        )

    def _on_ai_suggest_failed(
        self,
        request_id: int,
        job_id: int,
        _image_path: str,
        error: str,
    ) -> None:
        """Handle AI suggestion errors."""
        self._finish_ai_job(job_id)
        if request_id != self._ai_request_id:
            return

        self._ai_inflight = False
        self._restore_metadata_action_controls()
        self.metadata_panel.set_ai_status(f"AI suggestion failed: {error}", is_error=True)

    def _on_gps_suggest_clicked(self) -> None:
        """Manually refresh GPS suggestion for currently selected image."""
        selected = self._selected_image_path
        if selected is None:
            self.metadata_panel.set_gps_status("No file selected", is_error=True)
            return
        if self._selected_has_embedded_gps():
            self.metadata_panel.set_gps_status(
                "Existing EXIF GPS found; timeline suggestion disabled to avoid overwrite"
            )
            return
        if self._save_inflight:
            self.metadata_panel.set_gps_status("Save already running...", is_error=True)
            return
        if self._process_inflight:
            self.metadata_panel.set_gps_status("Process already running...", is_error=True)
            return
        if self._ai_inflight:
            self.metadata_panel.set_gps_status("AI suggestions running...", is_error=True)
            return
        captured_at = self._current_exif_ui_data.captured_at if self._current_exif_ui_data else ""
        if not captured_at:
            self.metadata_panel.set_gps_status("Capture time is missing; cannot match timeline", is_error=True)
            return
        self._start_gps_suggest(image_path=selected, captured_at=captured_at)

    def _on_gps_apply_clicked(self) -> None:
        """Apply current timeline GPS suggestion into editable GPS fields for current set."""
        selected = self._selected_image_path
        if selected is None:
            self.metadata_panel.set_gps_status("No file selected", is_error=True)
            return
        if self._selected_has_embedded_gps():
            self.metadata_panel.set_gps_status(
                "Existing EXIF GPS found; apply is disabled to avoid overwrite"
            )
            return
        suggestion = self._gps_suggestions.get(selected)
        if suggestion is None:
            self.metadata_panel.set_gps_status("No GPS suggestion available", is_error=True)
            return

        self._sync_current_draft()
        target_paths = self._gps_target_paths(selected)
        timeline_altitude = suggestion.altitude_m
        altitude_unreliable = timeline_altitude is not None and suggestion.source_type != "GPS"
        latitude_text = f"{suggestion.latitude:.7f}"
        longitude_text = f"{suggestion.longitude:.7f}"
        altitude_text = "" if timeline_altitude is None else f"{timeline_altitude:.2f}"

        applied_paths: list[Path] = []
        skipped_embedded = 0
        skipped_unreadable = 0
        for path in target_paths:
            if self._path_has_embedded_gps(path):
                skipped_embedded += 1
                continue
            draft = self._ensure_draft_for_path(path)
            if draft is None:
                skipped_unreadable += 1
                continue
            draft.gps_latitude = latitude_text
            draft.gps_longitude = longitude_text
            draft.gps_altitude = altitude_text
            self._gps_altitude_unreliable_by_path[path] = altitude_unreliable
            if altitude_unreliable:
                self._gps_altitude_source_by_path[path] = suggestion.source_type
            else:
                self._gps_altitude_source_by_path.pop(path, None)
            applied_paths.append(path)

        if not applied_paths:
            self.metadata_panel.set_gps_status(
                "GPS apply skipped: no eligible files in capture set",
                is_error=True,
            )
            self._restore_metadata_action_controls()
            return

        self._suppress_metadata_sync = True
        try:
            self.metadata_panel.set_gps_fields(
                latitude=latitude_text,
                longitude=longitude_text,
                altitude=altitude_text,
            )
            self.metadata_panel.set_gps_altitude_unreliable(
                altitude_unreliable,
                source_type=suggestion.source_type,
            )
        finally:
            self._suppress_metadata_sync = False
        self._sync_current_draft()

        status_parts = [f"Applied GPS to {len(applied_paths)}/{len(target_paths)} file(s) in capture set"]
        if timeline_altitude is None:
            status_parts.append("timeline altitude missing")
        elif altitude_unreliable:
            status_parts.append(f"altitude from {suggestion.source_type} marked unreliable")
        if skipped_embedded:
            status_parts.append(f"{skipped_embedded} skipped (existing EXIF GPS)")
        if skipped_unreadable:
            status_parts.append(f"{skipped_unreadable} skipped (metadata unreadable)")
        self.metadata_panel.set_gps_status("; ".join(status_parts))
        self._restore_metadata_action_controls()
        if timeline_altitude is None and self.metadata_panel.auto_altitude_lookup_enabled():
            self._start_altitude_lookup(
                image_path=selected,
                latitude=suggestion.latitude,
                longitude=suggestion.longitude,
                target_paths=tuple(applied_paths),
                reason=f"Timeline altitude missing; looking up elevation for {len(applied_paths)} file(s)...",
            )

    def _on_lookup_altitude_clicked(self) -> None:
        """Lookup and fill missing altitude for current capture set."""
        selected = self._selected_image_path
        if selected is None:
            self.metadata_panel.set_gps_status("No file selected", is_error=True)
            return
        if self._save_inflight:
            self.metadata_panel.set_gps_status("Save already running...", is_error=True)
            return
        if self._process_inflight:
            self.metadata_panel.set_gps_status("Process already running...", is_error=True)
            return
        if self._ai_inflight:
            self.metadata_panel.set_gps_status("AI suggestions running...", is_error=True)
            return

        latitude, longitude = self._current_gps_lat_lon()
        if latitude is None or longitude is None:
            self.metadata_panel.set_gps_status(
                "Latitude and longitude must be numeric before altitude lookup",
                is_error=True,
            )
            return

        self._sync_current_draft()
        target_paths = self._gps_target_paths(selected)
        eligible_paths: list[Path] = []
        skipped_embedded_altitude = 0
        skipped_unreadable = 0
        already_has_altitude = 0
        for path in target_paths:
            if self._path_has_embedded_altitude(path):
                skipped_embedded_altitude += 1
                continue
            draft = self._ensure_draft_for_path(path)
            if draft is None:
                skipped_unreadable += 1
                continue
            if draft.gps_altitude.strip():
                already_has_altitude += 1
                continue
            eligible_paths.append(path)

        if not eligible_paths:
            self.metadata_panel.set_gps_status(
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

    def _start_gps_suggest(self, *, image_path: Path, captured_at: str) -> None:
        """Start one background timeline lookup for selected image capture time."""
        if not captured_at.strip():
            self.metadata_panel.set_gps_status("Capture time is missing; cannot match timeline")
            self.metadata_panel.set_gps_apply_button_enabled(False)
            return

        self._location_request_id += 1
        request_id = self._location_request_id
        self._location_job_id += 1
        job_id = self._location_job_id

        self.metadata_panel.set_gps_status("Looking up nearest GPS in timeline...")
        self.metadata_panel.set_gps_apply_button_enabled(False)

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

        self.metadata_panel.set_gps_status(reason)
        self.metadata_panel.set_lookup_altitude_button_enabled(False)
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
        if path_obj != self._selected_image_path:
            return

        targets = self._altitude_target_paths or (path_obj,)
        altitude_text = f"{altitude_m:.2f}"
        applied_count = 0
        skipped_existing = 0
        skipped_unreadable = 0
        selected_applied = False
        for path in targets:
            if self._path_has_embedded_altitude(path):
                skipped_existing += 1
                continue
            draft = self._ensure_draft_for_path(path)
            if draft is None:
                skipped_unreadable += 1
                continue
            if draft.gps_altitude.strip():
                continue
            draft.gps_altitude = altitude_text
            self._gps_altitude_unreliable_by_path[path] = False
            self._gps_altitude_source_by_path.pop(path, None)
            applied_count += 1
            if path == path_obj:
                selected_applied = True

        if selected_applied:
            self._suppress_metadata_sync = True
            try:
                self.metadata_panel.gps_altitude_edit.setText(altitude_text)
                self.metadata_panel.set_gps_altitude_unreliable(False)
            finally:
                self._suppress_metadata_sync = False
            self._sync_current_draft()

        if applied_count == 0:
            self.metadata_panel.set_gps_status("Altitude lookup returned, but no files needed updates")
        else:
            status_parts = [f"Altitude filled for {applied_count}/{len(targets)} file(s): {altitude_text} m"]
            if skipped_existing:
                status_parts.append(f"{skipped_existing} skipped (existing EXIF altitude)")
            if skipped_unreadable:
                status_parts.append(f"{skipped_unreadable} skipped (metadata unreadable)")
            self.metadata_panel.set_gps_status("; ".join(status_parts))
        self._restore_metadata_action_controls()

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
        if Path(image_path) != self._selected_image_path:
            return
        self.metadata_panel.set_gps_status(f"Altitude lookup failed: {error}", is_error=True)
        self._restore_metadata_action_controls()

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
            if path_obj == self._selected_image_path:
                self.metadata_panel.set_gps_status("No timeline record within 60 minutes of capture time")
                self._restore_metadata_action_controls()
            return

        self._gps_suggestions[path_obj] = suggestion
        if path_obj != self._selected_image_path:
            return

        matched_at = datetime.fromtimestamp(suggestion.matched_ts_utc, tz=timezone.utc)
        matched_at_text = matched_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        age_minutes = suggestion.age_seconds // 60
        age_seconds_remainder = suggestion.age_seconds % 60
        accuracy_text = (
            ""
            if suggestion.accuracy_m is None
            else f", accuracy {suggestion.accuracy_m:.0f}m"
        )
        self.metadata_panel.set_gps_status(
            (
                f"Nearest GPS {age_minutes}m {age_seconds_remainder}s away "
                f"({suggestion.source_type}{accuracy_text}); matched {matched_at_text}"
            )
        )
        self._restore_metadata_action_controls()

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
        if Path(image_path) != self._selected_image_path:
            return
        self._gps_suggestions.pop(Path(image_path), None)
        self.metadata_panel.set_gps_status(f"GPS lookup failed: {error}", is_error=True)
        self._restore_metadata_action_controls()

    def _on_metadata_edited(self) -> None:
        """Persist current editors into in-memory draft for selected image."""
        self._sync_current_draft()
        self._restore_metadata_action_controls()

    def _on_altitude_manually_edited(self, _: str) -> None:
        """Clear unreliable marker when user manually edits altitude."""
        if self._selected_image_path is None:
            return
        self._gps_altitude_unreliable_by_path[self._selected_image_path] = False
        self._gps_altitude_source_by_path.pop(self._selected_image_path, None)
        self.metadata_panel.set_gps_altitude_unreliable(False)

    def _sync_current_draft(self) -> None:
        """Capture editable fields for current selection into draft cache."""
        if self._suppress_metadata_sync:
            return
        if self._selected_image_path is None:
            return
        self._metadata_drafts[self._selected_image_path] = MetadataDraft(
            description=self.metadata_panel.description_text(),
            keywords=self.metadata_panel.keywords_text(),
            gps_latitude=self.metadata_panel.gps_latitude_text(),
            gps_longitude=self.metadata_panel.gps_longitude_text(),
            gps_altitude=self.metadata_panel.gps_altitude_text(),
        )

    def _ai_targets_for(self, selected_path: Path) -> tuple[Path, tuple[Path, ...]]:
        """Return representative and member list for AI apply scope."""
        group = self._group_by_path.get(selected_path)
        if group is None:
            return selected_path, (selected_path,)
        return group.representative_path, tuple(group.members)

    def _gps_target_paths(self, selected_path: Path) -> tuple[Path, ...]:
        """Return capture-set members for GPS/altitude apply actions."""
        group = self._group_by_path.get(selected_path)
        if group is None:
            return (selected_path,)
        return tuple(group.members)

    def _path_has_embedded_gps(self, path: Path) -> bool:
        """Return True when a file already has EXIF latitude and longitude."""
        if path == self._selected_image_path and self._current_exif_ui_data is not None:
            has_value = bool(
                self._current_exif_ui_data.gps_latitude.strip()
                and self._current_exif_ui_data.gps_longitude.strip()
            )
            self._embedded_gps_by_path[path] = has_value
            return has_value
        if path in self._embedded_gps_by_path:
            return self._embedded_gps_by_path[path]
        draft = self._ensure_draft_for_path(path)
        if draft is None:
            self._embedded_gps_by_path[path] = True
            return True
        return self._embedded_gps_by_path.get(path, False)

    def _path_has_embedded_altitude(self, path: Path) -> bool:
        """Return True when a file already has EXIF altitude."""
        if path == self._selected_image_path and self._current_exif_ui_data is not None:
            has_value = bool(self._current_exif_ui_data.gps_altitude.strip())
            self._embedded_altitude_by_path[path] = has_value
            return has_value
        if path in self._embedded_altitude_by_path:
            return self._embedded_altitude_by_path[path]
        draft = self._ensure_draft_for_path(path)
        if draft is None:
            self._embedded_altitude_by_path[path] = True
            return True
        return self._embedded_altitude_by_path.get(path, False)

    def _ensure_draft_for_path(self, path: Path) -> MetadataDraft | None:
        """Ensure draft exists for a path; return None when EXIF cannot be read."""
        existing = self._metadata_drafts.get(path)
        if existing is not None:
            return existing
        if path == self._selected_image_path and self._current_exif_ui_data is not None:
            draft = MetadataDraft(
                description=self.metadata_panel.description_text(),
                keywords=self.metadata_panel.keywords_text(),
                gps_latitude=self.metadata_panel.gps_latitude_text(),
                gps_longitude=self.metadata_panel.gps_longitude_text(),
                gps_altitude=self.metadata_panel.gps_altitude_text(),
            )
            self._metadata_drafts[path] = draft
            return draft
        try:
            metadata = self._exif_service.read_full_metadata(path)
            ui_data = self._exif_service.map_for_ui(metadata)
        except RuntimeError:
            return None
        self._embedded_gps_by_path[path] = bool(ui_data.gps_latitude.strip() and ui_data.gps_longitude.strip())
        self._embedded_altitude_by_path[path] = bool(ui_data.gps_altitude.strip())
        draft = MetadataDraft(
            description=ui_data.description,
            keywords=self._keywords_with_auto_tokens(
                ui_data.keywords,
                ui_data.art_filter_token,
                ui_data.camera_model,
                ui_data.lens_model,
            ),
            gps_latitude=ui_data.gps_latitude,
            gps_longitude=ui_data.gps_longitude,
            gps_altitude=ui_data.gps_altitude,
        )
        self._metadata_drafts[path] = draft
        return draft

    def _keywords_with_auto_tokens(
        self,
        keywords_text: str,
        art_filter_token: str,
        camera_token: str,
        lens_token: str,
    ) -> str:
        """Append art filter, camera, and lens tokens to comma-delimited keywords."""
        keywords = self._parse_keywords(keywords_text)
        auto_tokens = [art_filter_token.strip(), camera_token.strip(), lens_token.strip()]
        merged = self._merge_keywords(keywords, [token for token in auto_tokens if token])
        return ", ".join(merged)

    def _restore_metadata_action_controls(self) -> None:
        """Restore right-panel action enabled states based on app state."""
        has_selection = self._selected_image_path is not None
        allow_actions = (
            has_selection
            and not self._process_inflight
            and not self._ai_inflight
            and not self._save_inflight
        )
        allow_gps_actions = allow_actions and not self._selected_has_embedded_gps()
        self.metadata_panel.set_suggest_button_enabled(allow_actions)
        self.metadata_panel.set_save_button_enabled(allow_actions)
        self.metadata_panel.set_process_buttons_enabled(allow_actions)
        self.metadata_panel.set_gps_lookup_button_enabled(allow_gps_actions)
        has_suggestion = (
            self._selected_image_path is not None
            and self._selected_image_path in self._gps_suggestions
        )
        self.metadata_panel.set_gps_apply_button_enabled(allow_gps_actions and has_suggestion)
        lat_value, lon_value = self._current_gps_lat_lon()
        selected = self._selected_image_path
        lookup_target_paths = self._gps_target_paths(selected) if selected is not None else tuple()
        has_lookup_target = any(not self._path_has_embedded_altitude(path) for path in lookup_target_paths)
        self.metadata_panel.set_lookup_altitude_button_enabled(
            allow_actions
            and lat_value is not None
            and lon_value is not None
            and has_lookup_target
        )
        group = self._group_by_path.get(selected) if selected is not None else None
        has_capture_set = group is not None and len(group.members) > 1
        self.preview_panel.skip_single_button.setEnabled(allow_actions)
        self.preview_panel.skip_set_button.setEnabled(allow_actions and has_capture_set)

    def _selected_has_embedded_gps(self) -> bool:
        """Return True when selected image already contains EXIF lat/lon values."""
        data = self._current_exif_ui_data
        if data is None:
            return False
        return bool(data.gps_latitude.strip() and data.gps_longitude.strip())

    def _current_gps_lat_lon(self) -> tuple[float | None, float | None]:
        """Return numeric lat/lon from editable GPS fields when valid."""
        lat_text = self.metadata_panel.gps_latitude_text()
        lon_text = self.metadata_panel.gps_longitude_text()
        if not lat_text or not lon_text:
            return None, None
        try:
            return float(lat_text), float(lon_text)
        except ValueError:
            return None, None

    def _capture_context(self) -> str:
        """Return short camera/exposure context string for AI prompting."""
        data = self._current_exif_ui_data
        if data is None:
            return ""
        parts = [
            f"camera={data.camera}",
            f"lens={data.lens_type}",
            f"aperture={data.aperture}",
            f"shutter_speed={data.shutter_speed}",
            f"focal_length={data.focal_length}",
            f"focus_distance={data.focus_distance}",
            f"captured_at={data.captured_at_display}",
            f"iso={data.iso}",
        ]
        return "; ".join(part for part in parts if part and not part.endswith("="))

    def _parse_keywords(self, text: str) -> list[str]:
        """Split comma-delimited keywords into normalized list."""
        values = [part.strip() for part in text.replace("\n", ",").split(",")]
        return [value for value in values if value]

    def _merge_keywords(self, existing: list[str], suggested: list[str]) -> list[str]:
        """Merge keyword lists preserving order and removing case-insensitive duplicates."""
        merged: list[str] = []
        seen: set[str] = set()
        for keyword in [*existing, *suggested]:
            lowered = keyword.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            merged.append(keyword)
        return merged

    def _on_process_single_clicked(self) -> None:
        """Process and copy only the currently selected image."""
        selected = self._selected_image_path
        if selected is None:
            self.metadata_panel.set_save_status("No file selected", is_error=True)
            return
        self._start_process_scope("single image", [selected])

    def _on_process_set_clicked(self) -> None:
        """Process and copy all files in the current capture set."""
        selected = self._selected_image_path
        if selected is None:
            self.metadata_panel.set_save_status("No file selected", is_error=True)
            return
        group = self._group_by_path.get(selected)
        paths = list(group.members) if group is not None else [selected]
        self._start_process_scope("capture set", paths)

    def _on_process_session_clicked(self) -> None:
        """Process and copy all remaining files in the current session view."""
        paths = self.source_panel.current_image_paths
        if not paths:
            self.metadata_panel.set_save_status("No files available in current session", is_error=True)
            return
        self._start_process_scope("session", paths)

    def _start_process_scope(self, scope_label: str, paths: list[Path]) -> None:
        """Start one background batch process job for the requested scope."""
        if self._save_inflight:
            self.metadata_panel.set_save_status("Save already running...", is_error=True)
            return
        if self._process_inflight:
            self.metadata_panel.set_save_status("Process already running...", is_error=True)
            return
        if self._ai_inflight:
            self.metadata_panel.set_save_status("AI suggestions running...", is_error=True)
            return
        unique_paths = self._dedupe_paths(paths)
        if not unique_paths:
            self.metadata_panel.set_save_status("No files to process", is_error=True)
            return

        self._sync_current_draft()
        draft_snapshot = {
            str(path): (
                draft.description,
                draft.keywords,
                draft.gps_latitude,
                draft.gps_longitude,
                draft.gps_altitude,
            )
            for path, draft in self._metadata_drafts.items()
        }

        self._process_request_id += 1
        request_id = self._process_request_id
        self._process_job_id += 1
        job_id = self._process_job_id

        self._process_inflight = True
        self.metadata_panel.set_save_button_enabled(False)
        self.metadata_panel.set_process_buttons_enabled(False)
        self.metadata_panel.set_suggest_button_enabled(False)
        self.metadata_panel.set_gps_lookup_button_enabled(False)
        self.metadata_panel.set_gps_apply_button_enabled(False)
        self.metadata_panel.set_lookup_altitude_button_enabled(False)
        self.preview_panel.skip_single_button.setEnabled(False)
        self.preview_panel.skip_set_button.setEnabled(False)
        self.metadata_panel.set_save_status(
            f"Processing {len(unique_paths)} file(s) for {scope_label}..."
        )

        signals = ProcessBatchSignals()
        signals.completed.connect(partial(self._on_process_batch_completed, request_id, job_id))
        signals.failed.connect(partial(self._on_process_batch_failed, request_id, job_id))

        task = ProcessBatchTask(
            image_paths=tuple(unique_paths),
            scope_label=scope_label,
            location_text=self.metadata_panel.location_text(),
            draft_by_path=draft_snapshot,
            destination_root=DESTINATION_ROOT,
            exif_service=self._exif_service,
            rename_service=self._rename_service,
            process_move_service=self._process_move_service,
            signals=signals,
        )
        self._active_process_jobs[job_id] = (task, signals)
        self._process_pool.start(task)

    def _on_process_batch_completed(
        self,
        request_id: int,
        job_id: int,
        result: ProcessBatchResult,
    ) -> None:
        """Handle completion for a background batch process operation."""
        self._finish_process_job(job_id)
        if request_id != self._process_request_id:
            return

        self._process_inflight = False
        success_paths = [
            Path(item.source_path)
            for item in result.outcomes
            if not item.error
        ]
        if success_paths:
            self.source_panel.mark_skipped_many(success_paths)

        self._restore_metadata_action_controls()
        if result.failure_count == 0:
            self.metadata_panel.set_save_status(
                f"Processed {result.success_count}/{result.total_count} files for {result.scope_label}"
            )
            return

        first_failure = next((item for item in result.outcomes if item.error), None)
        failure_hint = ""
        if first_failure is not None:
            failure_hint = f" First failure: {Path(first_failure.source_path).name}."
        self.metadata_panel.set_save_status(
            (
                f"Processed {result.success_count}/{result.total_count} for {result.scope_label}; "
                f"{result.failure_count} failed.{failure_hint}"
            ),
            is_error=True,
        )

    def _on_process_batch_failed(
        self,
        request_id: int,
        job_id: int,
        error: str,
    ) -> None:
        """Handle fatal batch process errors."""
        self._finish_process_job(job_id)
        if request_id != self._process_request_id:
            return
        self._process_inflight = False
        self._restore_metadata_action_controls()
        self.metadata_panel.set_save_status(f"Process failed: {error}", is_error=True)

    def _dedupe_paths(self, paths: list[Path]) -> list[Path]:
        """Return unique paths preserving original order."""
        unique: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            unique.append(path)
        return unique

    def _on_skip_single_selected(self) -> None:
        """Skip selected file for this session without deleting from SD."""
        if self._selected_image_path is None:
            return
        if self._process_inflight or self._ai_inflight or self._save_inflight:
            return
        skipped_path = self._selected_image_path
        self.source_panel.mark_skipped(skipped_path)
        self.metadata_panel.set_save_status(f"Skipped {skipped_path.name}")

    def _on_skip_set_selected(self) -> None:
        """Skip all files in the selected capture set for this session."""
        selected = self._selected_image_path
        if selected is None:
            return
        if self._process_inflight or self._ai_inflight or self._save_inflight:
            return

        group = self._group_by_path.get(selected)
        if group is None or len(group.members) <= 1:
            self.source_panel.mark_skipped(selected)
            self.metadata_panel.set_save_status(f"Skipped {selected.name}")
            return

        self.source_panel.mark_skipped_many(list(group.members))
        self.metadata_panel.set_save_status(f"Skipped capture set ({len(group.members)} files)")

    def _on_variant_selected(self, image_path: Path) -> None:
        """Switch preview to selected capture-set variant."""
        if self._process_inflight or self._ai_inflight or self._save_inflight:
            return
        if image_path == self._selected_image_path:
            return
        selected = self.source_panel.select_path(image_path, emit_signal=True)
        if not selected:
            self._on_photo_selected(image_path)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Stop thread pools cleanly before window teardown."""
        self._group_pool.clear()
        self._location_pool.clear()
        self._altitude_pool.clear()
        self._ai_pool.clear()
        self._process_pool.clear()
        self._metadata_write_pool.clear()
        self._exif_pool.clear()
        self._preview_pool.clear()
        self._thumbnail_pool.clear()
        self._group_pool.waitForDone()
        self._location_pool.waitForDone()
        self._altitude_pool.waitForDone()
        self._ai_pool.waitForDone()
        self._process_pool.waitForDone()
        self._metadata_write_pool.waitForDone()
        self._exif_pool.waitForDone()
        self._preview_pool.waitForDone()
        self._thumbnail_pool.waitForDone()
        super().closeEvent(event)

    def _finish_group_job(self, job_id: int) -> None:
        """Release references for completed capture-group tasks."""
        self._active_group_jobs.pop(job_id, None)

    def _finish_preview_job(self, job_id: int) -> None:
        """Release references for completed preview tasks."""
        self._active_preview_jobs.pop(job_id, None)

    def _finish_exif_job(self, job_id: int) -> None:
        """Release references for completed EXIF tasks."""
        self._active_exif_jobs.pop(job_id, None)

    def _finish_metadata_write_job(self, job_id: int) -> None:
        """Release references for completed metadata save tasks."""
        self._active_metadata_write_jobs.pop(job_id, None)

    def _finish_location_job(self, job_id: int) -> None:
        """Release references for completed location suggestion tasks."""
        self._active_location_jobs.pop(job_id, None)

    def _finish_altitude_job(self, job_id: int) -> None:
        """Release references for completed altitude lookup tasks."""
        self._active_altitude_jobs.pop(job_id, None)

    def _finish_ai_job(self, job_id: int) -> None:
        """Release references for completed AI suggestion tasks."""
        self._active_ai_jobs.pop(job_id, None)

    def _finish_process_job(self, job_id: int) -> None:
        """Release references for completed process-and-copy tasks."""
        self._active_process_jobs.pop(job_id, None)

    def _refresh_variant_strip(self, selected_path: Path | None) -> None:
        """Refresh variant strip for current selection and grouping state."""
        if selected_path is None:
            self.preview_panel.set_variants([], None, {})
            return

        group = self._group_by_path.get(selected_path)
        if group is None:
            self.preview_panel.set_variants(
                [selected_path],
                selected_path,
                {selected_path: self.source_panel.thumbnail_for_path(selected_path)},
            )
            return
        members = list(group.members)
        thumbnails = {
            path: self.source_panel.thumbnail_for_path(path)
            for path in members
        }
        self.preview_panel.set_variants(members, selected_path, thumbnails)

    def _update_rename_preview(self) -> None:
        """Regenerate Part 5 filename preview and sync title field."""
        if self._selected_image_path is None:
            self.metadata_panel.set_rename_preview("")
            return

        context = RenameContext(
            source_path=self._selected_image_path,
            captured_at=(self._current_exif_ui_data.captured_at if self._current_exif_ui_data else ""),
            camera_model=(self._current_exif_ui_data.camera_model if self._current_exif_ui_data else ""),
            lens_model=(self._current_exif_ui_data.lens_model if self._current_exif_ui_data else ""),
            location=self.metadata_panel.location_text(),
            art_filter_token=(self._current_exif_ui_data.art_filter_token if self._current_exif_ui_data else ""),
        )
        candidate = self._rename_service.build_filename(context)

        existing = self._existing_names_for_folder(self._selected_image_path.parent)
        existing.discard(self._selected_image_path.name)
        unique_name = self._rename_service.ensure_unique_name(candidate, existing)

        self.metadata_panel.set_rename_preview(unique_name)
        self.metadata_panel.title_edit.setPlainText(Path(unique_name).stem)

    def _existing_names_for_folder(self, folder: Path) -> set[str]:
        """Return set of existing file names in folder."""
        try:
            return {entry.name for entry in folder.iterdir() if entry.is_file()}
        except OSError:
            return set()
