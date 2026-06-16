"""Main window composition for MacPhotoMaster."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QCloseEvent, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QSplitter, QWidget

from phototags.services.ai_suggestion_service import AiSuggestionResult, AiSuggestionService
from phototags.services.exif_service import ExifService, ExifUiData
from phototags.services.metadata_write_service import MetadataWriteResult, MetadataWriteService
from phototags.services.process_move_service import ProcessMoveResult, ProcessMoveService
from phototags.services.rename_service import RenameContext, RenameService
from phototags.ui.widgets.image_preview_widget import ImagePreviewWidget
from phototags.ui.widgets.metadata_panel import MetadataPanel
from phototags.ui.widgets.source_panel import SourcePanel
from phototags.workers.exif_loader import ExifLoadSignals, ExifLoadTask
from phototags.workers.image_loader import ImageLoadSignals, ImageLoadTask
from phototags.workers.ai_suggester import AiSuggestSignals, AiSuggestTask
from phototags.workers.metadata_writer import MetadataSaveSignals, MetadataSaveTask
from phototags.workers.process_mover import ProcessMoveSignals, ProcessMoveTask

PREVIEW_MAX_EDGE = 2800
THUMBNAIL_WORKERS = 4
DESTINATION_ROOT = Path("/Users/bsmi067/Pictures/DxO")


class MainWindow(QMainWindow):
    """Single-window app shell with source, preview, and metadata panels."""

    def __init__(self, source_dir: Path) -> None:
        super().__init__()
        self._ai_suggestion_service = AiSuggestionService()
        self._exif_service = ExifService()
        self._metadata_write_service = MetadataWriteService()
        self._rename_service = RenameService()
        self._process_move_service = ProcessMoveService(
            metadata_write_service=self._metadata_write_service,
            rename_service=self._rename_service,
        )
        self._thumbnail_pool = QThreadPool(self)
        self._thumbnail_pool.setMaxThreadCount(THUMBNAIL_WORKERS)
        self._preview_pool = QThreadPool(self)
        self._preview_pool.setMaxThreadCount(1)
        self._exif_pool = QThreadPool(self)
        self._exif_pool.setMaxThreadCount(1)
        self._metadata_write_pool = QThreadPool(self)
        self._metadata_write_pool.setMaxThreadCount(1)
        self._ai_pool = QThreadPool(self)
        self._ai_pool.setMaxThreadCount(1)
        self._process_pool = QThreadPool(self)
        self._process_pool.setMaxThreadCount(1)
        self._preview_request_id = 0
        self._preview_job_id = 0
        self._active_preview_jobs: dict[int, tuple[ImageLoadTask, ImageLoadSignals]] = {}
        self._exif_request_id = 0
        self._exif_job_id = 0
        self._active_exif_jobs: dict[int, tuple[ExifLoadTask, ExifLoadSignals]] = {}
        self._metadata_write_request_id = 0
        self._metadata_write_job_id = 0
        self._active_metadata_write_jobs: dict[int, tuple[MetadataSaveTask, MetadataSaveSignals]] = {}
        self._ai_request_id = 0
        self._ai_job_id = 0
        self._active_ai_jobs: dict[int, tuple[AiSuggestTask, AiSuggestSignals]] = {}
        self._process_request_id = 0
        self._process_job_id = 0
        self._active_process_jobs: dict[int, tuple[ProcessMoveTask, ProcessMoveSignals]] = {}
        self._ai_inflight = False
        self._process_inflight = False
        self._selected_image_path: Path | None = None
        self._current_exif_ui_data: ExifUiData | None = None
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
        self.source_panel.photo_selected.connect(self._on_photo_selected)
        self.metadata_panel.save_button.clicked.connect(self._on_save_metadata_clicked)
        self.metadata_panel.process_button.clicked.connect(self._on_process_clicked)
        self.metadata_panel.suggest_button.clicked.connect(self._on_ai_suggest_clicked)
        self.metadata_panel.apply_suggested_keywords_button.clicked.connect(
            self._on_apply_suggested_keywords_clicked
        )
        self.metadata_panel.location_edit.textChanged.connect(self._update_rename_preview)
        self.preview_panel.delete_button.clicked.connect(self._on_skip_selected)
        self._skip_shortcut = QShortcut(QKeySequence("Meta+Backspace"), self)
        self._skip_shortcut.activated.connect(self._on_skip_selected)
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
        self._selected_image_path = image_path
        if image_path is None:
            self._current_exif_ui_data = None
            self.preview_panel.clear_preview("No supported files in this folder")
            self.metadata_panel.clear_metadata("No file selected")
            self.metadata_panel.set_rename_preview("")
            self.preview_panel.delete_button.setEnabled(False)
            self.metadata_panel.set_suggest_button_enabled(False)
            self.metadata_panel.set_process_button_enabled(False)
            return

        self._preview_request_id += 1
        request_id = self._preview_request_id
        self.preview_panel.set_loading_state(image_path.name)

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
        self.metadata_panel.set_save_button_enabled(not self._process_inflight and not self._ai_inflight)
        self.metadata_panel.set_process_button_enabled(
            not self._process_inflight and not self._ai_inflight
        )
        self.metadata_panel.set_suggest_button_enabled(not self._process_inflight and not self._ai_inflight)
        self.preview_panel.delete_button.setEnabled(not self._process_inflight and not self._ai_inflight)
        self.metadata_panel.set_save_status("")
        self._update_rename_preview()

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
        _image_path: str,
        ui_data: ExifUiData,
        dump_text: str,
    ) -> None:
        """Populate right panel metadata fields and full dump."""
        self._finish_exif_job(job_id)
        if request_id != self._exif_request_id:
            return
        self.metadata_panel.set_metadata_fields(
            title=ui_data.title,
            description=ui_data.description,
            keywords=ui_data.keywords,
            camera=ui_data.camera,
            lens_type=ui_data.lens_type,
            aperture=ui_data.aperture,
            shutter_speed=ui_data.shutter_speed,
            focal_length=ui_data.focal_length,
            focus_distance=ui_data.focus_distance,
            captured_at=ui_data.captured_at_display,
            iso=ui_data.iso,
        )
        self._current_exif_ui_data = ui_data
        self.metadata_panel.set_exif_dump(dump_text)
        self._update_rename_preview()

    def _on_exif_failed(
        self,
        request_id: int,
        job_id: int,
        image_path: str,
        error: str,
    ) -> None:
        """Show EXIF load errors in debug panel."""
        self._finish_exif_job(job_id)
        if request_id != self._exif_request_id:
            return
        self._current_exif_ui_data = None
        self.metadata_panel.clear_metadata(
            f"Failed to read EXIF for {Path(image_path).name}\n\n{error}"
        )
        self.metadata_panel.set_rename_preview("")
        self.metadata_panel.set_suggest_button_enabled(False)

    def _on_save_metadata_clicked(self) -> None:
        """Persist description and keywords for selected file."""
        if self._selected_image_path is None:
            self.metadata_panel.set_save_status("No file selected", is_error=True)
            return
        if self._process_inflight:
            self.metadata_panel.set_save_status("Process already running...", is_error=True)
            return
        if self._ai_inflight:
            self.metadata_panel.set_save_status("AI suggestions running...", is_error=True)
            return

        image_path = self._selected_image_path
        description = self.metadata_panel.description_text()
        keywords_text = self.metadata_panel.keywords_text()

        self._metadata_write_request_id += 1
        request_id = self._metadata_write_request_id
        self._metadata_write_job_id += 1
        job_id = self._metadata_write_job_id

        self.metadata_panel.set_save_button_enabled(False)
        self.metadata_panel.set_save_status("Saving description + keywords...")

        signals = MetadataSaveSignals()
        signals.saved.connect(partial(self._on_metadata_saved, request_id, job_id))
        signals.failed.connect(partial(self._on_metadata_save_failed, request_id, job_id))

        task = MetadataSaveTask(
            image_path=image_path,
            description=description,
            keywords_text=keywords_text,
            service=self._metadata_write_service,
            signals=signals,
        )
        self._active_metadata_write_jobs[job_id] = (task, signals)
        self._metadata_write_pool.start(task)

    def _on_metadata_saved(
        self,
        request_id: int,
        job_id: int,
        image_path: str,
        result: MetadataWriteResult,
    ) -> None:
        """Handle successful metadata write completion."""
        self._finish_metadata_write_job(job_id)
        if request_id != self._metadata_write_request_id:
            return

        self.metadata_panel.keywords_edit.setPlainText(", ".join(result.keywords))
        self.metadata_panel.description_edit.setPlainText(result.description)
        self.metadata_panel.set_save_button_enabled(not self._process_inflight and not self._ai_inflight)
        self.metadata_panel.set_save_status("Saved description + keywords")
        self._start_exif_load(Path(image_path))

    def _on_metadata_save_failed(
        self,
        request_id: int,
        job_id: int,
        _image_path: str,
        error: str,
    ) -> None:
        """Show metadata save error to user."""
        self._finish_metadata_write_job(job_id)
        if request_id != self._metadata_write_request_id:
            return
        self.metadata_panel.set_save_button_enabled(not self._process_inflight and not self._ai_inflight)
        self.metadata_panel.set_save_status(f"Save failed: {error}", is_error=True)

    def _on_ai_suggest_clicked(self) -> None:
        """Request AI description and keyword suggestions for selected image."""
        if self._selected_image_path is None:
            self.metadata_panel.set_ai_status("No file selected", is_error=True)
            return
        if self._process_inflight:
            self.metadata_panel.set_ai_status("Process already running...", is_error=True)
            return
        if self._ai_inflight:
            self.metadata_panel.set_ai_status("AI suggestions already running...", is_error=True)
            return

        image_path = self._selected_image_path
        self._ai_request_id += 1
        request_id = self._ai_request_id
        self._ai_job_id += 1
        job_id = self._ai_job_id

        self._ai_inflight = True
        self.metadata_panel.set_suggest_button_enabled(False)
        self.metadata_panel.set_apply_suggested_keywords_enabled(False)
        self.metadata_panel.set_save_button_enabled(False)
        self.metadata_panel.set_process_button_enabled(False)
        self.preview_panel.delete_button.setEnabled(False)
        self.metadata_panel.set_ai_status("Generating AI suggestions...")

        signals = AiSuggestSignals()
        signals.suggested.connect(partial(self._on_ai_suggested, request_id, job_id))
        signals.failed.connect(partial(self._on_ai_suggest_failed, request_id, job_id))

        task = AiSuggestTask(
            image_path=image_path,
            existing_keywords_text=self.metadata_panel.keywords_text(),
            existing_description=self.metadata_panel.description_text(),
            capture_context=self._capture_context(),
            service=self._ai_suggestion_service,
            signals=signals,
        )
        self._active_ai_jobs[job_id] = (task, signals)
        self._ai_pool.start(task)

    def _on_ai_suggested(
        self,
        request_id: int,
        job_id: int,
        image_path: str,
        result: AiSuggestionResult,
    ) -> None:
        """Apply AI suggestions to UI fields."""
        self._finish_ai_job(job_id)
        if request_id != self._ai_request_id:
            return

        self._ai_inflight = False
        if self._selected_image_path is None or str(self._selected_image_path) != image_path:
            has_selection = self._selected_image_path is not None
            self.metadata_panel.set_suggest_button_enabled(has_selection and not self._process_inflight)
            self.metadata_panel.set_apply_suggested_keywords_enabled(
                has_selection
                and not self._process_inflight
                and bool(self.metadata_panel.suggested_keywords_text().strip())
            )
            self.metadata_panel.set_save_button_enabled(has_selection and not self._process_inflight)
            self.metadata_panel.set_process_button_enabled(has_selection and not self._process_inflight)
            self.preview_panel.delete_button.setEnabled(has_selection and not self._process_inflight)
            return

        self.metadata_panel.description_edit.setPlainText(result.description)
        self.metadata_panel.set_suggested_keywords(", ".join(result.keywords))
        self.metadata_panel.set_apply_suggested_keywords_enabled(bool(result.keywords))
        self.metadata_panel.set_suggest_button_enabled(True)
        self.metadata_panel.set_save_button_enabled(True)
        self.metadata_panel.set_process_button_enabled(True)
        self.preview_panel.delete_button.setEnabled(True)
        self.metadata_panel.set_ai_status("AI suggestions ready")

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
        has_selection = self._selected_image_path is not None
        self.metadata_panel.set_suggest_button_enabled(has_selection and not self._process_inflight)
        self.metadata_panel.set_apply_suggested_keywords_enabled(
            has_selection
            and not self._process_inflight
            and bool(self.metadata_panel.suggested_keywords_text().strip())
        )
        self.metadata_panel.set_save_button_enabled(has_selection and not self._process_inflight)
        self.metadata_panel.set_process_button_enabled(has_selection and not self._process_inflight)
        self.preview_panel.delete_button.setEnabled(has_selection and not self._process_inflight)
        self.metadata_panel.set_ai_status(f"AI suggestion failed: {error}", is_error=True)

    def _on_apply_suggested_keywords_clicked(self) -> None:
        """Merge suggested keywords into editable keywords field."""
        suggested = self._parse_keywords(self.metadata_panel.suggested_keywords_text())
        if not suggested:
            self.metadata_panel.set_ai_status("No suggested keywords to add", is_error=True)
            return
        existing = self._parse_keywords(self.metadata_panel.keywords_text())
        merged = self._merge_keywords(existing, suggested)
        self.metadata_panel.keywords_edit.setPlainText(", ".join(merged))
        self.metadata_panel.set_ai_status("Suggested keywords added to Keywords")

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

    def _on_process_clicked(self) -> None:
        """Copy selected file to destination tree and write metadata."""
        if self._selected_image_path is None:
            self.metadata_panel.set_save_status("No file selected", is_error=True)
            return
        if self._process_inflight:
            self.metadata_panel.set_save_status("Process already running...", is_error=True)
            return
        if self._ai_inflight:
            self.metadata_panel.set_save_status("AI suggestions running...", is_error=True)
            return

        proposed_filename = self.metadata_panel.rename_preview_text()
        if not proposed_filename:
            self.metadata_panel.set_save_status("No filename preview available", is_error=True)
            return

        image_path = self._selected_image_path
        captured_at = self._current_exif_ui_data.captured_at if self._current_exif_ui_data else ""
        description = self.metadata_panel.description_text()
        keywords_text = self.metadata_panel.keywords_text()
        title = Path(proposed_filename).stem

        self._process_request_id += 1
        request_id = self._process_request_id
        self._process_job_id += 1
        job_id = self._process_job_id

        self._process_inflight = True
        self.metadata_panel.set_save_button_enabled(False)
        self.metadata_panel.set_process_button_enabled(False)
        self.metadata_panel.set_suggest_button_enabled(False)
        self.metadata_panel.set_apply_suggested_keywords_enabled(False)
        self.preview_panel.delete_button.setEnabled(False)
        self.metadata_panel.set_save_status("Processing and copying file...")

        signals = ProcessMoveSignals()
        signals.completed.connect(partial(self._on_process_completed, request_id, job_id))
        signals.failed.connect(partial(self._on_process_failed, request_id, job_id))

        task = ProcessMoveTask(
            source_path=image_path,
            destination_root=DESTINATION_ROOT,
            proposed_filename=proposed_filename,
            captured_at=captured_at,
            title=title,
            description=description,
            keywords_text=keywords_text,
            service=self._process_move_service,
            signals=signals,
        )
        self._active_process_jobs[job_id] = (task, signals)
        self._process_pool.start(task)

    def _on_process_completed(
        self,
        request_id: int,
        job_id: int,
        source_path: str,
        result: ProcessMoveResult,
    ) -> None:
        """Handle successful process-and-copy completion."""
        self._finish_process_job(job_id)
        if request_id != self._process_request_id:
            return

        self._process_inflight = False
        self.metadata_panel.title_edit.setPlainText(result.metadata_result.title)
        self.metadata_panel.description_edit.setPlainText(result.metadata_result.description)
        self.metadata_panel.keywords_edit.setPlainText(", ".join(result.metadata_result.keywords))
        self.source_panel.mark_skipped(Path(source_path))
        self.metadata_panel.set_save_status(f"Copied to {result.destination_path}")

    def _on_process_failed(
        self,
        request_id: int,
        job_id: int,
        _source_path: str,
        error: str,
    ) -> None:
        """Show process-and-copy errors and restore controls."""
        self._finish_process_job(job_id)
        if request_id != self._process_request_id:
            return
        self._process_inflight = False
        has_selection = self._selected_image_path is not None
        self.metadata_panel.set_save_button_enabled(has_selection)
        self.metadata_panel.set_process_button_enabled(has_selection)
        self.metadata_panel.set_suggest_button_enabled(has_selection)
        self.metadata_panel.set_apply_suggested_keywords_enabled(
            has_selection and bool(self.metadata_panel.suggested_keywords_text().strip())
        )
        self.preview_panel.delete_button.setEnabled(has_selection)
        self.metadata_panel.set_save_status(f"Process failed: {error}", is_error=True)

    def _on_skip_selected(self) -> None:
        """Skip selected file for this session without deleting from SD."""
        if self._selected_image_path is None:
            return
        if self._process_inflight or self._ai_inflight:
            return
        skipped_path = self._selected_image_path
        self.source_panel.mark_skipped(skipped_path)
        self.metadata_panel.set_save_status(f"Skipped {skipped_path.name}")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Stop thread pools cleanly before window teardown."""
        self._ai_pool.clear()
        self._process_pool.clear()
        self._metadata_write_pool.clear()
        self._exif_pool.clear()
        self._preview_pool.clear()
        self._thumbnail_pool.clear()
        self._ai_pool.waitForDone()
        self._process_pool.waitForDone()
        self._metadata_write_pool.waitForDone()
        self._exif_pool.waitForDone()
        self._preview_pool.waitForDone()
        self._thumbnail_pool.waitForDone()
        super().closeEvent(event)

    def _finish_preview_job(self, job_id: int) -> None:
        """Release references for completed preview tasks."""
        self._active_preview_jobs.pop(job_id, None)

    def _finish_exif_job(self, job_id: int) -> None:
        """Release references for completed EXIF tasks."""
        self._active_exif_jobs.pop(job_id, None)

    def _finish_metadata_write_job(self, job_id: int) -> None:
        """Release references for completed metadata save tasks."""
        self._active_metadata_write_jobs.pop(job_id, None)

    def _finish_ai_job(self, job_id: int) -> None:
        """Release references for completed AI suggestion tasks."""
        self._active_ai_jobs.pop(job_id, None)

    def _finish_process_job(self, job_id: int) -> None:
        """Release references for completed process-and-copy tasks."""
        self._active_process_jobs.pop(job_id, None)

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
