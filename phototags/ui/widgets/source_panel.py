"""Source browser panel UI."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from PySide6.QtCore import QDir, QFileInfo, QThreadPool, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFileSystemModel,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from phototags.ui.styles import ACCENT_CYAN, BROWN_TEXT, DARK_TEAL, PANEL_BACKGROUND
from phototags.workers.image_loader import ImageLoadSignals, ImageLoadTask

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".orf"}
THUMBNAIL_MAX_EDGE = 220


class ThumbnailTile(QFrame):
    """Single thumbnail tile in the source grid."""

    clicked = Signal(object)

    def __init__(self, image_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image_path = image_path
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("thumbnailTile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(156, 168)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.thumb_label = QLabel("Loading...")
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setObjectName("thumbLabel")
        self.thumb_label.setFixedSize(140, 120)
        layout.addWidget(self.thumb_label, 0, Qt.AlignmentFlag.AlignCenter)

        self.name_label = QLabel(self.image_path.name)
        self.name_label.setWordWrap(True)
        self.name_label.setObjectName("nameLabel")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.name_label)

        self._apply_selected_style(selected=False)

    def mousePressEvent(self, event: object) -> None:  # noqa: N802
        """Emit selected image path when tile is clicked."""
        self.clicked.emit(self.image_path)
        super().mousePressEvent(event)

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        """Display scaled thumbnail image."""
        scaled = pixmap.scaled(
            140,
            120,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.thumb_label.setPixmap(scaled)
        self.thumb_label.setText("")

    def set_placeholder_text(self, text: str) -> None:
        """Display fallback text when thumbnail decoding fails."""
        self.thumb_label.setPixmap(QPixmap())
        self.thumb_label.setText(text)

    def set_selected(self, selected: bool) -> None:
        """Apply selected or normal tile styling."""
        self._apply_selected_style(selected=selected)

    def _apply_selected_style(self, selected: bool) -> None:
        if selected:
            border = ACCENT_CYAN
            bg = "#eefcfb"
        else:
            border = "#d6d2ce"
            bg = "white"

        self.setStyleSheet(
            f"""
            QFrame#thumbnailTile {{
                border: 2px solid {border};
                border-radius: 8px;
                background: {bg};
            }}
            QLabel#thumbLabel {{
                border: 1px solid #e8e4df;
                border-radius: 6px;
                color: {BROWN_TEXT};
                background: #f8f6f4;
                font-size: 11px;
            }}
            QLabel#nameLabel {{
                color: {BROWN_TEXT};
                font-size: 11px;
            }}
            """
        )


class SourcePanel(QWidget):
    """Left panel with folder browser and thumbnail grid."""

    photo_selected = Signal(object)
    folder_selected = Signal(object)

    def __init__(
        self,
        source_dir: Path,
        thread_pool: QThreadPool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._source_dir = source_dir
        self._thread_pool = thread_pool
        self._thumb_request_id = 0
        self._thumb_job_id = 0
        self._thumb_tiles: dict[str, ThumbnailTile] = {}
        self._selected_path: Path | None = None
        self._active_thumb_jobs: dict[int, tuple[ImageLoadTask, ImageLoadSignals]] = {}
        self._build_ui()
        self._set_source_path(source_dir)

    @property
    def source_dir(self) -> Path:
        """Return the currently selected source directory."""
        return self._source_dir

    @property
    def selected_path(self) -> Path | None:
        """Return selected image path for current folder."""
        return self._selected_path

    def _build_ui(self) -> None:
        panel = QFrame()
        panel.setObjectName("sourcePanel")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Source Browser")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("Select source folder...")
        path_row.addWidget(self.path_edit, 1)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._choose_folder)
        path_row.addWidget(browse_button)
        layout.addLayout(path_row)

        self.file_count_label = QLabel("0 files")
        self.file_count_label.setObjectName("supportText")
        layout.addWidget(self.file_count_label)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

        self.dir_model = QFileSystemModel(self)
        self.dir_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot)
        self.dir_model.setReadOnly(True)

        self.dir_tree = QTreeView()
        self.dir_tree.setModel(self.dir_model)
        self.dir_tree.setHeaderHidden(True)
        self.dir_tree.setAlternatingRowColors(True)
        self.dir_tree.clicked.connect(self._on_tree_clicked)
        for column in (1, 2, 3):
            self.dir_tree.hideColumn(column)
        splitter.addWidget(self.dir_tree)

        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.thumb_container = QWidget()
        self.thumb_grid = QGridLayout(self.thumb_container)
        self.thumb_grid.setContentsMargins(0, 0, 0, 0)
        self.thumb_grid.setSpacing(8)
        self.thumb_scroll.setWidget(self.thumb_container)
        splitter.addWidget(self.thumb_scroll)
        splitter.setSizes([300, 420])

        self.setStyleSheet(
            f"""
            QFrame#sourcePanel {{
                background: {PANEL_BACKGROUND};
                border: 1px solid {ACCENT_CYAN};
                border-radius: 8px;
            }}
            QLabel#panelTitle {{
                color: {DARK_TEAL};
                font-weight: 700;
                font-size: 15px;
            }}
            QLabel#supportText {{
                color: {BROWN_TEXT};
                font-size: 11px;
            }}
            QLineEdit, QTreeView, QPushButton {{
                color: {BROWN_TEXT};
                font-size: 12px;
            }}
            """
        )

    def _choose_folder(self) -> None:
        """Open folder picker and update selected source path."""
        selected_path = QFileDialog.getExistingDirectory(
            self,
            "Choose Source Folder",
            str(self._source_dir),
        )
        if not selected_path:
            return
        self._set_source_path(Path(selected_path))

    def _set_source_path(self, source_dir: Path) -> None:
        """Store source path and configure the directory tree root."""
        self._source_dir = source_dir
        self.path_edit.setText(str(source_dir))

        model_root_index = self.dir_model.setRootPath(str(source_dir))
        self.dir_tree.setRootIndex(model_root_index)
        self.dir_tree.setCurrentIndex(model_root_index)
        self._load_folder_images(source_dir)

    def _on_tree_clicked(self, model_index: object) -> None:
        """Refresh thumbnails for selected folder in tree."""
        folder_path = Path(self.dir_model.filePath(model_index))
        if folder_path.is_dir():
            self._load_folder_images(folder_path)

    def _load_folder_images(self, folder_path: Path) -> None:
        """Build thumbnail tiles and start background image decoding."""
        self.folder_selected.emit(folder_path)
        self._thumb_request_id += 1
        request_id = self._thumb_request_id
        self._selected_path = None
        self._thumb_tiles.clear()
        self._clear_grid()

        image_paths = self._find_supported_images(folder_path)
        self.file_count_label.setText(f"{len(image_paths)} files in {folder_path.name}")

        if not image_paths:
            empty = QLabel("No .jpg, .jpeg, or .orf files in this folder.")
            empty.setObjectName("supportText")
            self.thumb_grid.addWidget(empty, 0, 0)
            self.photo_selected.emit(None)
            return

        column_count = 2
        for index, image_path in enumerate(image_paths):
            row = index // column_count
            col = index % column_count
            tile = ThumbnailTile(image_path=image_path)
            tile.clicked.connect(self._on_tile_clicked)
            self._thumb_tiles[str(image_path)] = tile
            self.thumb_grid.addWidget(tile, row, col)
            self._start_thumbnail_load(image_path=image_path, request_id=request_id)

        self._set_selected_path(image_paths[0])
        self.photo_selected.emit(image_paths[0])

    def _find_supported_images(self, folder_path: Path) -> list[Path]:
        """Return sorted list of supported image files in folder."""
        try:
            files = [
                item
                for item in folder_path.iterdir()
                if item.is_file() and item.suffix.lower() in SUPPORTED_SUFFIXES
            ]
        except OSError:
            return []

        return sorted(files, key=lambda item: item.name.lower())

    def _clear_grid(self) -> None:
        """Remove and delete all existing grid widgets."""
        while self.thumb_grid.count() > 0:
            item = self.thumb_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _start_thumbnail_load(self, image_path: Path, request_id: int) -> None:
        """Launch a thumbnail worker for one file."""
        self._thumb_job_id += 1
        job_id = self._thumb_job_id
        signals = ImageLoadSignals()
        signals.loaded.connect(partial(self._on_thumbnail_loaded, request_id, job_id))
        signals.failed.connect(partial(self._on_thumbnail_failed, request_id, job_id))

        task = ImageLoadTask(
            image_path=image_path,
            signals=signals,
            max_edge=THUMBNAIL_MAX_EDGE,
        )
        self._active_thumb_jobs[job_id] = (task, signals)
        self._thread_pool.start(task)

    def _on_thumbnail_loaded(
        self,
        request_id: int,
        job_id: int,
        image_path: str,
        data: bytes,
        _width: int,
        _height: int,
    ) -> None:
        """Apply loaded thumbnail if request is still current."""
        self._finish_thumb_job(job_id)
        if request_id != self._thumb_request_id:
            return

        tile = self._thumb_tiles.get(image_path)
        if tile is None:
            return

        pixmap = QPixmap()
        pixmap.loadFromData(data, "PNG")
        tile.set_thumbnail(pixmap)

    def _on_thumbnail_failed(
        self,
        request_id: int,
        job_id: int,
        image_path: str,
        _error: str,
    ) -> None:
        """Show fallback for files Qt/Pillow cannot decode as thumbnails."""
        self._finish_thumb_job(job_id)
        if request_id != self._thumb_request_id:
            return

        tile = self._thumb_tiles.get(image_path)
        if tile is None:
            return

        extension = QFileInfo(image_path).suffix().upper() or "IMG"
        tile.set_placeholder_text(extension)

    def _on_tile_clicked(self, image_path: Path) -> None:
        """Set active tile and emit selected image path."""
        self._set_selected_path(image_path)
        self.photo_selected.emit(image_path)

    def _set_selected_path(self, image_path: Path) -> None:
        """Update tile selection state and store active path."""
        self._selected_path = image_path
        selected = str(image_path)
        for path_text, tile in self._thumb_tiles.items():
            tile.set_selected(path_text == selected)

    def _finish_thumb_job(self, job_id: int) -> None:
        """Release references for completed thumbnail tasks."""
        self._active_thumb_jobs.pop(job_id, None)
