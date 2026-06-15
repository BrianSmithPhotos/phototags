"""Center preview panel UI."""

from __future__ import annotations

from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
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

from phototags.ui.styles import ACCENT_CYAN, BROWN_TEXT, DARK_TEAL, PANEL_BACKGROUND, SALMON_SECONDARY


class ImagePreviewWidget(QWidget):
    """Center panel showing selected image preview and actions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_pixmap: QPixmap | None = None
        self._setting_zoom_programmatically = False
        self._auto_fit_on_resize = True
        self._build_ui()

    def _build_ui(self) -> None:
        panel = QFrame()
        panel.setObjectName("previewPanel")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

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

        self.delete_button = QPushButton("Delete (Cmd+Backspace)")
        self.delete_button.setEnabled(False)
        layout.addWidget(self.delete_button)

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
                background: white;
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
                background: #d7ccc6;
                color: #f6f3f1;
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

    def _apply_zoom(self) -> None:
        """Scale current pixmap to slider-selected zoom."""
        if self._base_pixmap is None:
            return

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
