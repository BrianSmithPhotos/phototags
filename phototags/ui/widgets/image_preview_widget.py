"""Center preview panel UI."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from phototags.ui.styles import (
    ACCENT_CYAN,
    BROWN_TEXT,
    BUTTON_DISABLED_BG,
    BUTTON_DISABLED_TEXT,
    DARK_TEAL,
    PANEL_BACKGROUND,
    PREVIEW_BACKGROUND,
    SALMON_SECONDARY,
    VARIANT_BUTTON_BG,
    VARIANT_BUTTON_BORDER,
    VARIANT_BUTTON_CHECKED_BG,
    VARIANT_BUTTON_CHECKED_TEXT,
)


class ImagePreviewWidget(QWidget):
    """Center panel showing selected image preview and actions."""

    variant_selected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_pixmap: QPixmap | None = None
        self._setting_zoom_programmatically = False
        self._auto_fit_on_resize = True
        self._variant_buttons: list[QPushButton] = []
        self._build_ui()

    def _build_ui(self) -> None:
        panel = QFrame()
        panel.setObjectName("previewPanel")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Image Preview")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(False)
        self.preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.preview_label = QLabel("Select a photo to preview")
        self.preview_label.setObjectName("previewLabel")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(1, 1)
        self.preview_scroll.setWidget(self.preview_label)
        layout.addWidget(self.preview_scroll, 1)

        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(8)

        zoom_text = QLabel("Zoom")
        zoom_row.addWidget(zoom_text)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(1, 400)
        self.zoom_slider.setValue(25)
        self.zoom_slider.setEnabled(False)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        zoom_row.addWidget(self.zoom_slider, 1)

        self.zoom_percent = QLabel("100%")
        zoom_row.addWidget(self.zoom_percent)

        self.fit_button = QPushButton("Fit")
        self.fit_button.setEnabled(False)
        self.fit_button.clicked.connect(self.fit_to_view)
        zoom_row.addWidget(self.fit_button)

        layout.addLayout(zoom_row)

        variant_heading_row = QHBoxLayout()
        variant_heading_row.setSpacing(8)

        self.variant_title = QLabel("Capture Set")
        self.variant_title.setObjectName("variantTitle")
        variant_heading_row.addWidget(self.variant_title)

        self.variant_status = QLabel("1 file")
        self.variant_status.setObjectName("variantStatus")
        variant_heading_row.addWidget(self.variant_status)
        variant_heading_row.addStretch(1)

        layout.addLayout(variant_heading_row)

        self.variant_scroll = QScrollArea()
        self.variant_scroll.setWidgetResizable(True)
        self.variant_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.variant_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.variant_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.variant_scroll.setMinimumHeight(64)
        self.variant_scroll.setMaximumHeight(64)

        self.variant_container = QWidget()
        self.variant_layout = QHBoxLayout(self.variant_container)
        self.variant_layout.setContentsMargins(0, 0, 0, 0)
        self.variant_layout.setSpacing(6)
        self.variant_layout.addStretch(1)

        self.variant_scroll.setWidget(self.variant_container)
        layout.addWidget(self.variant_scroll)

        skip_row = QHBoxLayout()
        skip_row.setSpacing(6)

        self.skip_single_button = QPushButton("Skip Image (Cmd+Backspace)")
        self.skip_single_button.setEnabled(False)
        skip_row.addWidget(self.skip_single_button, 1)

        self.skip_set_button = QPushButton("Skip Capture Set")
        self.skip_set_button.setEnabled(False)
        skip_row.addWidget(self.skip_set_button, 1)

        layout.addLayout(skip_row)

        self.setStyleSheet(
            f"""
            QFrame#previewPanel {{
                background: {PANEL_BACKGROUND};
                border: 1px solid {ACCENT_CYAN};
                border-radius: 8px;
            }}
            QLabel#panelTitle {{
                color: {DARK_TEAL};
                font-weight: 700;
                font-size: 15px;
            }}
            QLabel#previewLabel {{
                color: {BROWN_TEXT};
                border: 1px dashed {ACCENT_CYAN};
                border-radius: 6px;
                background: {PREVIEW_BACKGROUND};
            }}
            QLabel#variantTitle {{
                color: {DARK_TEAL};
                font-weight: 600;
                font-size: 12px;
            }}
            QLabel#variantStatus {{
                color: {BROWN_TEXT};
                font-size: 11px;
            }}
            QPushButton#variantButton {{
                background: {VARIANT_BUTTON_BG};
                color: {BROWN_TEXT};
                border: 1px solid {VARIANT_BUTTON_BORDER};
                border-radius: 6px;
                padding: 2px;
                font-weight: 500;
            }}
            QPushButton#variantButton:checked {{
                background: {VARIANT_BUTTON_CHECKED_BG};
                border: 1px solid {ACCENT_CYAN};
                color: {VARIANT_BUTTON_CHECKED_TEXT};
            }}
            QLabel, QSlider {{
                color: {BROWN_TEXT};
                font-size: 12px;
            }}
            QPushButton {{
                background: {SALMON_SECONDARY};
                color: white;
                padding: 8px 10px;
                border-radius: 6px;
                font-weight: 600;
            }}
            QPushButton:disabled {{
                background: {BUTTON_DISABLED_BG};
                color: {BUTTON_DISABLED_TEXT};
            }}
            """
        )

    def set_loading_state(self, filename: str) -> None:
        """Show loading state while preview is decoded in background."""
        self._base_pixmap = None
        self._auto_fit_on_resize = True
        self.zoom_slider.setEnabled(False)
        self.fit_button.setEnabled(False)
        self._set_zoom_value(25)
        self.zoom_percent.setText("25%")
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText(f"Loading {filename}...")

    def set_preview_pixmap(self, pixmap: QPixmap) -> None:
        """Display loaded image and reset zoom controls."""
        self._base_pixmap = pixmap
        self.zoom_slider.setEnabled(True)
        self.fit_button.setEnabled(True)
        self._auto_fit_on_resize = True
        self.fit_to_view()

    def set_variants(
        self,
        variant_paths: list[Path],
        selected_path: Path | None,
        thumbnails: dict[Path, QPixmap | None] | None = None,
    ) -> None:
        """Render capture-set variant thumbnails for quick in-group switching."""
        self._clear_variant_buttons()
        thumb_map = thumbnails or {}
        if not variant_paths:
            self.variant_status.setText("No files")
            self.variant_layout.addStretch(1)
            return

        selected_index = 1
        if selected_path is not None and selected_path in variant_paths:
            selected_index = variant_paths.index(selected_path) + 1

        if len(variant_paths) == 1:
            self.variant_status.setText("1 file")
        else:
            self.variant_status.setText(f"{selected_index}/{len(variant_paths)} selected")

        for path in variant_paths:
            button = QPushButton("")
            button.setObjectName("variantButton")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setChecked(selected_path is not None and path == selected_path)
            button.setFixedSize(82, 60)
            button.setToolTip(path.name)

            thumb = thumb_map.get(path)
            if thumb is not None and not thumb.isNull():
                button.setIcon(QIcon(thumb))
                button.setIconSize(QSize(72, 50))
            else:
                suffix = path.suffix.upper().replace(".", "") or "IMG"
                button.setText(suffix)

            button.clicked.connect(partial(self._on_variant_clicked, path))
            self.variant_layout.addWidget(button)
            self._variant_buttons.append(button)

        self.variant_layout.addStretch(1)

    def clear_preview(self, message: str = "Select a photo to preview") -> None:
        """Clear current image preview and show message."""
        self._base_pixmap = None
        self._auto_fit_on_resize = True
        self.zoom_slider.setEnabled(False)
        self.fit_button.setEnabled(False)
        self._set_zoom_value(25)
        self.zoom_percent.setText("25%")
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText(message)
        self.preview_label.adjustSize()
        self.set_variants([], None)

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        """Re-apply scaling when panel is resized."""
        if self._base_pixmap is not None and self._auto_fit_on_resize:
            self.fit_to_view()
        else:
            self._apply_zoom()
        super().resizeEvent(event)

    def _on_zoom_changed(self) -> None:
        """Handle slider changes from user interaction."""
        if not self._setting_zoom_programmatically:
            self._auto_fit_on_resize = False
        self._apply_zoom()

    def _on_variant_clicked(self, image_path: Path) -> None:
        """Emit selected variant path for parent window routing."""
        self.variant_selected.emit(image_path)

    def _clear_variant_buttons(self) -> None:
        """Remove existing variant controls from strip."""
        while self.variant_layout.count() > 0:
            item = self.variant_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._variant_buttons.clear()

    def _apply_zoom(self) -> None:
        """Scale current pixmap to slider-selected zoom, keeping the viewed point centered."""
        if self._base_pixmap is None:
            return

        h_bar = self.preview_scroll.horizontalScrollBar()
        v_bar = self.preview_scroll.verticalScrollBar()
        viewport = self.preview_scroll.viewport()
        old_pixmap = self.preview_label.pixmap()
        old_size = old_pixmap.size() if old_pixmap is not None else None

        center_frac_x = 0.5
        center_frac_y = 0.5
        if old_size is not None and old_size.width() > 0 and old_size.height() > 0:
            center_frac_x = (h_bar.value() + viewport.width() / 2) / old_size.width()
            center_frac_y = (v_bar.value() + viewport.height() / 2) / old_size.height()
            center_frac_x = max(0.0, min(center_frac_x, 1.0))
            center_frac_y = max(0.0, min(center_frac_y, 1.0))

        scale = self.zoom_slider.value() / 100.0
        scaled = self._base_pixmap.scaled(
            max(1, int(self._base_pixmap.width() * scale)),
            max(1, int(self._base_pixmap.height() * scale)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
        self.preview_label.resize(scaled.size())
        self.zoom_percent.setText(f"{self.zoom_slider.value()}%")

        h_bar.setValue(int(center_frac_x * scaled.width() - viewport.width() / 2))
        v_bar.setValue(int(center_frac_y * scaled.height() - viewport.height() / 2))

    def fit_to_view(self) -> None:
        """Set zoom to fit current preview viewport."""
        if self._base_pixmap is None:
            return
        self._auto_fit_on_resize = True
        self._set_zoom_value(self._fit_zoom_percent())
        self._apply_zoom()

    def _set_zoom_value(self, value: int) -> None:
        """Set slider value without disabling auto-fit state."""
        bounded = max(self.zoom_slider.minimum(), min(value, self.zoom_slider.maximum()))
        self._setting_zoom_programmatically = True
        self.zoom_slider.setValue(bounded)
        self._setting_zoom_programmatically = False

    def _fit_zoom_percent(self) -> int:
        """Calculate best fit zoom percentage for current viewport."""
        if self._base_pixmap is None:
            return 25

        view_width = self.preview_scroll.viewport().width()
        view_height = self.preview_scroll.viewport().height()
        if view_width <= 0 or view_height <= 0:
            return 25

        scale = min(
            view_width / float(self._base_pixmap.width()),
            view_height / float(self._base_pixmap.height()),
        )
        return int(max(1, min(round(scale * 100), 400)))
