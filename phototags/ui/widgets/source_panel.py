"""Source browser panel UI."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from PySide6.QtCore import QDir, QFileInfo, QThreadPool, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
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
    QStyle,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from phototags.ui.styles import (
    ACCENT_CYAN,
    BROWN_TEXT,
    DARK_TEAL,
    PANEL_BACKGROUND,
    THUMB_PLACEHOLDER_BG,
    THUMB_PLACEHOLDER_BORDER,
    TILE_BG_DEFAULT,
    TILE_BG_SELECTED,
    TILE_BORDER,
    is_dark_mode_enabled,
    set_dark_mode_enabled,
)
from phototags.workers.image_loader import ImageLoadSignals, ImageLoadTask

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".orf"}
THUMBNAIL_MAX_EDGE = 220
GRID_COLUMN_COUNT = 2
THUMBNAIL_TILE_WIDTH = 156
THUMBNAIL_TILE_HEIGHT = 168
GRID_SPACING = 8
PANEL_CONTENT_MARGIN = 12
PANEL_FRAME_BORDER = 1


class ThumbnailTile(QFrame):
    """Single thumbnail tile in the source grid."""

    clicked = Signal(object, object)

    def __init__(self, image_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image_path = image_path
        self._group_size = 1
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("thumbnailTile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(THUMBNAIL_TILE_WIDTH, THUMBNAIL_TILE_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.thumb_label = QLabel("Loading...")
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setObjectName("thumbLabel")
        self.thumb_label.setFixedSize(140, 120)
        layout.addWidget(self.thumb_label, 0, Qt.AlignmentFlag.AlignCenter)

        self.name_label = QLabel("")
        self.name_label.setWordWrap(True)
        self.name_label.setObjectName("nameLabel")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.name_label)
        self.set_group_size(1)

        self._apply_selected_style(selected=False)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Emit selected image path and click modifiers when tile is clicked."""
        self.clicked.emit(self.image_path, event.modifiers())
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

    def set_group_size(self, size: int) -> None:
        """Update filename caption with grouped set size."""
        bounded = max(1, size)
        self._group_size = bounded
        if bounded > 1:
            self.name_label.setText(f"{self.image_path.name}\n[{bounded} in set]")
            return
        self.name_label.setText(self.image_path.name)

    def set_selected(self, selected: bool) -> None:
        """Apply selected or normal tile styling."""
        self._apply_selected_style(selected=selected)

    def _apply_selected_style(self, selected: bool) -> None:
        if selected:
            border = ACCENT_CYAN
            bg = TILE_BG_SELECTED
        else:
            border = TILE_BORDER
            bg = TILE_BG_DEFAULT

        self.setStyleSheet(
            f"""
            QFrame#thumbnailTile {{
                border: 2px solid {border};
                border-radius: 8px;
                background: {bg};
            }}
            QLabel#thumbLabel {{
                border: 1px solid {THUMB_PLACEHOLDER_BORDER};
                border-radius: 6px;
                color: {BROWN_TEXT};
                background: {THUMB_PLACEHOLDER_BG};
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
    thumbnail_loaded = Signal(object)
    selection_changed = Signal(object)

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
        self._multi_selected_paths: set[Path] = set()
        self._range_anchor_path: Path | None = None
        self._current_folder: Path = source_dir
        self._current_image_paths: list[Path] = []
        self._group_sizes: dict[Path, int] = {}
        self._thumbnail_pixmaps: dict[Path, QPixmap] = {}
        self._skipped_paths: set[Path] = set()
        self._active_thumb_jobs: dict[int, tuple[ImageLoadTask, ImageLoadSignals]] = {}
        self._stacked_enabled = True
        self._non_representative_paths: set[Path] = set()
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

    @property
    def current_folder(self) -> Path:
        """Return current folder shown in the thumbnail grid."""
        return self._current_folder

    @property
    def current_image_paths(self) -> list[Path]:
        """Return image paths currently displayed in the thumbnail grid."""
        return list(self._current_image_paths)

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

        count_row = QHBoxLayout()
        count_row.setSpacing(8)

        self.file_count_label = QLabel("0 files")
        self.file_count_label.setObjectName("supportText")
        count_row.addWidget(self.file_count_label, 1)

        self.stacked_checkbox = QCheckBox("Stacked?")
        self.stacked_checkbox.setChecked(True)
        self.stacked_checkbox.toggled.connect(self._on_stacked_toggled)
        count_row.addWidget(self.stacked_checkbox)

        self.dark_mode_checkbox = QCheckBox("Dark Mode")
        self.dark_mode_checkbox.setChecked(is_dark_mode_enabled())
        self.dark_mode_checkbox.toggled.connect(self._on_dark_mode_toggled)
        count_row.addWidget(self.dark_mode_checkbox)
        layout.addLayout(count_row)

        self.dark_mode_hint = QLabel("")
        self.dark_mode_hint.setObjectName("supportText")
        layout.addWidget(self.dark_mode_hint)

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
        self.thumb_grid.setSpacing(GRID_SPACING)
        self.thumb_scroll.setWidget(self.thumb_container)
        splitter.addWidget(self.thumb_scroll)
        splitter.setSizes([110, 610])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self._apply_panel_max_width()

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
            QLineEdit, QPushButton, QCheckBox {{
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
        self._current_folder = folder_path
        self._thumb_request_id += 1
        request_id = self._thumb_request_id
        self._selected_path = None
        self._multi_selected_paths = set()
        self._range_anchor_path = None
        self._thumb_tiles.clear()
        self._group_sizes = {}
        self._thumbnail_pixmaps = {}
        self._non_representative_paths = set()
        self._clear_grid()

        image_paths = self._find_supported_images(folder_path)
        self._current_image_paths = image_paths
        self.folder_selected.emit(folder_path)
        self.file_count_label.setText(f"{len(image_paths)} files in {folder_path.name}")

        if not image_paths:
            empty = QLabel("No .jpg, .jpeg, or .orf files in this folder.")
            empty.setObjectName("supportText")
            self.thumb_grid.addWidget(empty, 0, 0)
            self.photo_selected.emit(None)
            return

        for image_path in image_paths:
            tile = ThumbnailTile(image_path=image_path)
            tile.set_group_size(self._group_sizes.get(image_path, 1))
            tile.clicked.connect(self._on_tile_clicked)
            self._thumb_tiles[str(image_path)] = tile
            self._start_thumbnail_load(image_path=image_path, request_id=request_id)
        self._relayout_grid()

        self._set_selected_path(image_paths[0])
        self.photo_selected.emit(image_paths[0])

    def _find_supported_images(self, folder_path: Path) -> list[Path]:
        """Return sorted list of supported image files in folder."""
        try:
            files = [
                item
                for item in folder_path.iterdir()
                if item.is_file()
                and item.suffix.lower() in SUPPORTED_SUFFIXES
                and not item.name.startswith(".")
                and item not in self._skipped_paths
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
        path_obj = Path(image_path)
        self._thumbnail_pixmaps[path_obj] = pixmap
        tile.set_thumbnail(pixmap)
        self.thumbnail_loaded.emit(path_obj)

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

    def _on_tile_clicked(self, image_path: Path, modifiers: Qt.KeyboardModifier) -> None:
        """Update selection per click modifiers, then emit selection signals.

        Cmd-click (Qt auto-maps this to ControlModifier on macOS) toggles one tile
        in/out of the multi-selection. Shift-click selects the contiguous range
        between the last click and this one. A plain click resets to single-select.
        """
        is_cmd = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        is_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if is_shift and self._range_anchor_path is not None:
            self._multi_selected_paths = self._range_between(self._range_anchor_path, image_path)
        elif is_cmd:
            if image_path in self._multi_selected_paths:
                self._multi_selected_paths.discard(image_path)
            else:
                self._multi_selected_paths.add(image_path)
            self._range_anchor_path = image_path
        else:
            self._multi_selected_paths = {image_path}
            self._range_anchor_path = image_path

        self._selected_path = image_path
        self._apply_multi_selection_style()
        self._update_file_count_label()
        self.photo_selected.emit(image_path)
        self.selection_changed.emit(self._ordered_selection())

    def _range_between(self, anchor_path: Path, image_path: Path) -> set[Path]:
        """Return the contiguous set of visible paths between anchor and image_path."""
        visible_paths = self._visible_paths()
        if anchor_path not in visible_paths or image_path not in visible_paths:
            return {image_path}
        start = visible_paths.index(anchor_path)
        end = visible_paths.index(image_path)
        low, high = min(start, end), max(start, end)
        return set(visible_paths[low : high + 1])

    def _ordered_selection(self) -> tuple[Path, ...]:
        """Return the current multi-selection in on-screen display order."""
        return tuple(path for path in self._current_image_paths if path in self._multi_selected_paths)

    def _apply_multi_selection_style(self) -> None:
        """Restyle every tile to reflect current multi-selection membership."""
        for path_text, tile in self._thumb_tiles.items():
            tile.set_selected(Path(path_text) in self._multi_selected_paths)

    def _update_file_count_label(self) -> None:
        """Refresh the file count label, appending a multi-selection hint when active."""
        count = len(self._current_image_paths)
        base = f"{count} files in {self._current_folder.name}"
        selected_count = len(self._multi_selected_paths)
        if selected_count > 1:
            base += f" — {selected_count} selected"
        self.file_count_label.setText(base)

    def _set_selected_path(self, image_path: Path) -> None:
        """Set a single active path programmatically, collapsing any multi-selection."""
        self._selected_path = image_path
        self._multi_selected_paths = {image_path}
        self._range_anchor_path = image_path
        self._apply_multi_selection_style()
        self._update_file_count_label()
        self.selection_changed.emit(self._ordered_selection())

    def _finish_thumb_job(self, job_id: int) -> None:
        """Release references for completed thumbnail tasks."""
        self._active_thumb_jobs.pop(job_id, None)

    def set_group_sizes(self, group_sizes: dict[Path, int]) -> None:
        """Apply grouped set-size hints to current thumbnail captions."""
        self._group_sizes = dict(group_sizes)
        for path_text, tile in self._thumb_tiles.items():
            tile.set_group_size(self._group_sizes.get(Path(path_text), 1))

    def set_capture_group_membership(self, non_representative_paths: set[Path]) -> None:
        """Record which currently-displayed files are non-representative capture-set members.

        When "Stacked?" is on, these are hidden from the grid so only one tile per
        capture set is shown; the full set remains reachable via the preview panel's
        variant strip.
        """
        self._non_representative_paths = set(non_representative_paths)
        self._apply_panel_max_width()
        self._relayout_grid()

    def _on_stacked_toggled(self, checked: bool) -> None:
        """Re-layout the grid when the user toggles stacked capture-set display."""
        self._stacked_enabled = checked
        self._apply_panel_max_width()
        self._relayout_grid()

    def _on_dark_mode_toggled(self, checked: bool) -> None:
        """Persist the dark-mode preference; styling itself only applies on next launch."""
        set_dark_mode_enabled(checked)
        self.dark_mode_hint.setText("Restart MacPhotoMaster to apply the new theme.")

    def _visible_paths(self) -> list[Path]:
        """Return paths to display given current stacked/grouping state."""
        if self._stacked_enabled and self._non_representative_paths:
            return [
                path
                for path in self._current_image_paths
                if path not in self._non_representative_paths
            ]
        return list(self._current_image_paths)

    def _visible_column_count(self) -> int:
        """Return 1 when stacking is actually hiding non-representative tiles, else the full grid width.

        Stacking only collapses to one tile per capture set once grouping data has
        resolved enough to know which paths are non-representative; until then (or
        if a folder has no multi-file capture sets at all) every photo is visible,
        so the 2-column grid applies regardless of the "Stacked?" checkbox state.
        """
        if self._stacked_enabled and self._non_representative_paths:
            return 1
        return GRID_COLUMN_COUNT

    def _apply_panel_max_width(self) -> None:
        """Cap panel width to fit exactly one thumbnail column when stacking is in effect.

        Stacked mode collapses to one tile per capture set, so the left column
        should not be wider than a single thumbnail; any extra space a user drags
        into this column instead flows to the middle preview panel, since
        QSplitter gives slack to siblings once a child hits its maximumWidth.
        Showing the full 2-column grid (un-stacked, or stacking not yet resolved)
        widens the cap to fit that.
        """
        scrollbar_extent = self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        margins = 2 * PANEL_CONTENT_MARGIN + 2 * PANEL_FRAME_BORDER
        column_count = self._visible_column_count()
        columns_width = column_count * THUMBNAIL_TILE_WIDTH + (column_count - 1) * GRID_SPACING
        self.setMaximumWidth(columns_width + scrollbar_extent + margins)

    def _relayout_grid(self) -> None:
        """Show/hide and re-flow existing tiles without re-decoding any thumbnails.

        Newly created tiles have no parent yet (see `_load_folder_images`), so
        `addWidget` must reparent them into the grid before `setVisible` runs —
        calling `setVisible(True)` on a still-parentless widget makes Qt treat it
        as its own top-level native window, which is enormously expensive once
        hundreds of tiles do it on the first layout pass.
        """
        visible_paths = self._visible_paths()
        visible_keys = {str(path) for path in visible_paths}
        column_count = self._visible_column_count()

        for tile in self._thumb_tiles.values():
            self.thumb_grid.removeWidget(tile)

        for index, image_path in enumerate(visible_paths):
            tile = self._thumb_tiles.get(str(image_path))
            if tile is not None:
                self.thumb_grid.addWidget(tile, index // column_count, index % column_count)

        for key, tile in self._thumb_tiles.items():
            tile.setVisible(key in visible_keys)

    def select_path(self, image_path: Path, *, emit_signal: bool = True) -> bool:
        """Select a file tile programmatically when it exists in current grid."""
        key = str(image_path)
        if key not in self._thumb_tiles:
            return False
        self._set_selected_path(image_path)
        if emit_signal:
            self.photo_selected.emit(image_path)
        return True

    def thumbnail_for_path(self, image_path: Path) -> QPixmap | None:
        """Return loaded thumbnail pixmap for a given image path when available."""
        return self._thumbnail_pixmaps.get(image_path)

    def mark_skipped(self, image_path: Path) -> None:
        """Hide a file from the current session without touching disk."""
        self._skipped_paths.add(image_path)
        self._remove_from_session([image_path])

    def mark_skipped_many(self, image_paths: list[Path]) -> None:
        """Hide many files from the current session without touching disk."""
        if not image_paths:
            return
        self._skipped_paths.update(image_paths)
        self._remove_from_session(image_paths)

    def _remove_from_session(self, image_paths: list[Path]) -> None:
        """Remove specific tiles from the visible grid without reloading the folder.

        Avoids re-triggering thumbnail decoding for every remaining file, which a
        full folder reload would do.
        """
        removed_keys = {str(path) for path in image_paths}
        self._current_image_paths = [
            path for path in self._current_image_paths if str(path) not in removed_keys
        ]

        was_selected = self._selected_path is not None and str(self._selected_path) in removed_keys

        for key in removed_keys:
            tile = self._thumb_tiles.pop(key, None)
            if tile is not None:
                self.thumb_grid.removeWidget(tile)
                tile.deleteLater()
            self._thumbnail_pixmaps.pop(Path(key), None)
            self._group_sizes.pop(Path(key), None)

        removed_paths = {Path(key) for key in removed_keys}
        self._multi_selected_paths -= removed_paths
        if self._range_anchor_path in removed_paths:
            self._range_anchor_path = None
        self._non_representative_paths -= removed_paths
        self._update_file_count_label()

        if not self._current_image_paths:
            self._clear_grid()
            empty = QLabel("No .jpg, .jpeg, or .orf files in this folder.")
            empty.setObjectName("supportText")
            self.thumb_grid.addWidget(empty, 0, 0)
            self._selected_path = None
            self._multi_selected_paths = set()
            self._range_anchor_path = None
            self.photo_selected.emit(None)
            return

        self._relayout_grid()
        self._apply_multi_selection_style()

        if was_selected:
            next_path = self._current_image_paths[0]
            self._set_selected_path(next_path)
            self.photo_selected.emit(next_path)
        else:
            self.selection_changed.emit(self._ordered_selection())

    def reload_current_folder(self) -> None:
        """Reload thumbnails for the current folder path."""
        self._load_folder_images(self._current_folder)
