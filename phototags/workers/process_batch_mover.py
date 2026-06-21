"""Background batch process-and-copy worker."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from phototags.services.auto_metadata import (
    description_with_art_filter_note,
    keywords_with_auto_tokens,
    sooc_token_for,
)
from phototags.services.exif_service import ExifService, ExifToolReadError, ExifUiData
from phototags.services.process_move_service import ProcessMoveError, ProcessMoveService
from phototags.services.rename_service import RenameContext, RenameService


@dataclass(slots=True)
class ProcessBatchItemOutcome:
    """One file outcome from a batch process run."""

    source_path: str
    destination_path: str
    error: str


@dataclass(slots=True)
class ProcessBatchResult:
    """Aggregate result for one batch process scope."""

    scope_label: str
    total_count: int
    success_count: int
    failure_count: int
    outcomes: list[ProcessBatchItemOutcome]


class ProcessBatchSignals(QObject):
    """Signals emitted by batch process worker."""

    completed = Signal(object)
    failed = Signal(str)


class ProcessBatchTask(QRunnable):
    """Run batch process-and-copy flow without blocking the UI thread."""

    def __init__(
        self,
        *,
        image_paths: tuple[Path, ...],
        scope_label: str,
        location_text: str,
        draft_by_path: dict[str, tuple[str, str, str, str, str]],
        destination_root: Path,
        exif_service: ExifService,
        rename_service: RenameService,
        process_move_service: ProcessMoveService,
        signals: ProcessBatchSignals,
    ) -> None:
        super().__init__()
        self.image_paths = image_paths
        self.scope_label = scope_label
        self.location_text = location_text
        self.draft_by_path = draft_by_path
        self.destination_root = destination_root
        self.exif_service = exif_service
        self.rename_service = rename_service
        self.process_move_service = process_move_service
        self.signals = signals

    def run(self) -> None:
        """Process all files in the batch and emit one aggregate result."""
        try:
            outcomes: list[ProcessBatchItemOutcome] = []
            for image_path in self.image_paths:
                outcome = self._process_one(image_path)
                outcomes.append(outcome)

            success_count = sum(1 for item in outcomes if not item.error)
            failure_count = len(outcomes) - success_count
            result = ProcessBatchResult(
                scope_label=self.scope_label,
                total_count=len(outcomes),
                success_count=success_count,
                failure_count=failure_count,
                outcomes=outcomes,
            )
            try:
                self.signals.completed.emit(result)
            except RuntimeError:
                return
        except (OSError, ValueError, RuntimeError) as exc:
            try:
                self.signals.failed.emit(str(exc))
            except RuntimeError:
                return

    def _process_one(self, image_path: Path) -> ProcessBatchItemOutcome:
        """Process one file and return success/failure outcome."""
        try:
            ui_data = self._read_exif_ui(image_path)
        except (OSError, ValueError, ExifToolReadError, RuntimeError) as exc:
            return ProcessBatchItemOutcome(
                source_path=str(image_path),
                destination_path="",
                error=f"EXIF read failed: {exc}",
            )

        draft = self.draft_by_path.get(str(image_path))
        if draft is not None:
            description = draft[0]
            keywords_source = draft[1]
            gps_latitude = draft[2]
            gps_longitude = draft[3]
            gps_altitude = draft[4]
        else:
            description = ui_data.description
            keywords_source = ui_data.keywords
            gps_latitude = ui_data.gps_latitude
            gps_longitude = ui_data.gps_longitude
            gps_altitude = ui_data.gps_altitude
        keywords_text = keywords_with_auto_tokens(
            keywords_source,
            art_filter_token=ui_data.art_filter_token,
            camera_token=ui_data.camera_model or ui_data.camera,
            lens_token=ui_data.lens_model or ui_data.lens_type,
            sooc_token=sooc_token_for(image_path),
        )
        description = description_with_art_filter_note(description, ui_data.art_filter_token)

        proposed_filename = self.rename_service.build_filename(
            RenameContext(
                source_path=image_path,
                captured_at=ui_data.captured_at,
                camera_model=ui_data.camera_model,
                lens_model=ui_data.lens_model,
                location=self.location_text,
                art_filter_token=ui_data.art_filter_token,
            )
        )
        title = Path(proposed_filename).stem

        try:
            result = self.process_move_service.process_and_copy(
                source_path=image_path,
                destination_root=self.destination_root,
                proposed_filename=proposed_filename,
                captured_at=ui_data.captured_at,
                title=title,
                description=description,
                keywords_text=keywords_text,
                gps_latitude=gps_latitude,
                gps_longitude=gps_longitude,
                gps_altitude=gps_altitude,
            )
        except (OSError, ValueError, ProcessMoveError, RuntimeError) as exc:
            return ProcessBatchItemOutcome(
                source_path=str(image_path),
                destination_path="",
                error=str(exc),
            )
        return ProcessBatchItemOutcome(
            source_path=str(image_path),
            destination_path=str(result.destination_path),
            error="",
        )

    def _read_exif_ui(self, image_path: Path) -> ExifUiData:
        """Read one file's EXIF and map it for downstream processing."""
        metadata = self.exif_service.read_full_metadata(image_path)
        return self.exif_service.map_for_ui(metadata)
