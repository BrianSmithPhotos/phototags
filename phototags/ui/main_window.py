"""Main window composition for MacPhotoMaster."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QSplitter, QWidget

from phototags.services.exif_service import ExifService, ExifUiData
from phototags.services.metadata_write_service import MetadataWriteResult, MetadataWriteService
from phototags.ui.widgets.image_preview_widget import ImagePreviewWidget
from phototags.ui.widgets.metadata_panel import MetadataPanel
from phototags.ui.widgets.source_panel import SourcePanel
from phototags.workers.exif_loader import ExifLoadSignals, ExifLoadTask
from phototags.workers.image_loader import ImageLoadSignals, ImageLoadTask
from phototags.workers.metadata_writer import MetadataSaveSignals, MetadataSaveTask

PREVIEW_MAX_EDGE = 2800
THUMBNAIL_WORKERS = 4


class MainWindow(QMainWindow):
    """Single-window app shell with source, preview, and metadata panels."""

    def __init__(self, source_dir: Path) -> None:
        super().__init__()
        self._exif_service = ExifService()
        self._metadata_write_service = MetadataWriteService()
        self._thumbnail_pool = QThreadPool(self)
        self._thumbnail_pool.setMaxThreadCount(THUMBNAIL_WORKERS)
        self._preview_pool = QThreadPool(self)
        self._preview_pool.setMaxThreadCount(1)
        self._exif_pool = QThreadPool(self)
        self._exif_pool.setMaxThreadCount(1)
        self._metadata_write_pool = QThreadPool(self)
        self._metadata_write_pool.setMaxThreadCount(1)
        self._preview_request_id = 0
        self._preview_job_id = 0
        self._active_preview_jobs: dict[int, tuple[ImageLoadTask, ImageLoadSignals]] = {}
        self._exif_request_id = 0
        self._exif_job_id = 0
        self._active_exif_jobs: dict[int, tuple[ExifLoadTask, ExifLoadSignals]] = {}
        self._metadata_write_request_id = 0
        self._metadata_write_job_id = 0
        self._active_metadata_write_jobs: dict[int, tuple[MetadataSaveTask, MetadataSaveSignals]] = {}
        self._selected_image_path: Path | None = None
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
            self.preview_panel.clear_preview("No supported files in this folder")
            self.metadata_panel.clear_metadata("No file selected")
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
        self.metadata_panel.set_save_button_enabled(True)
        self.metadata_panel.set_save_status("")

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
            focal_length=ui_data.focal_length,
            focus_distance=ui_data.focus_distance,
            captured_at=ui_data.captured_at,
        )
        self.metadata_panel.set_exif_dump(dump_text)

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
        self.metadata_panel.clear_metadata(
            f"Failed to read EXIF for {Path(image_path).name}\n\n{error}"
        )

    def _on_save_metadata_clicked(self) -> None:
        """Persist description and keywords for selected file."""
        if self._selected_image_path is None:
            self.metadata_panel.set_save_status("No file selected", is_error=True)
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
        self.metadata_panel.set_save_button_enabled(True)
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
        self.metadata_panel.set_save_button_enabled(True)
        self.metadata_panel.set_save_status(f"Save failed: {error}", is_error=True)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Stop thread pools cleanly before window teardown."""
        self._metadata_write_pool.clear()
        self._exif_pool.clear()
        self._preview_pool.clear()
        self._thumbnail_pool.clear()
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
