"""Right metadata and actions panel UI."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from phototags.ui.styles import ACCENT_CYAN, BROWN_TEXT, DARK_TEAL, ORANGE_PRIMARY, PANEL_BACKGROUND, SALMON_SECONDARY


class MetadataPanel(QWidget):
    """Right panel for metadata, rename preview, and process action."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        panel = QFrame()
        panel.setObjectName("metadataPanel")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Metadata & Actions")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(8)

        self.title_edit = QLineEdit()
        self.description_edit = QTextEdit()
        self.description_edit.setMinimumHeight(90)
        self.keywords_edit = QTextEdit()
        self.keywords_edit.setMinimumHeight(84)
        self.keywords_edit.setPlaceholderText(
            "Comma-delimited keywords (10+ is fine), e.g. bird, heron, wetland"
        )

        form.addRow("Title", self.title_edit)
        form.addRow("Description", self.description_edit)
        form.addRow("Keywords", self.keywords_edit)
        layout.addLayout(form)

        technical_heading = QLabel("Technical (Read-Only)")
        technical_heading.setObjectName("subHeading")
        layout.addWidget(technical_heading)

        technical_form = QFormLayout()
        technical_form.setSpacing(6)
        technical_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        technical_form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        technical_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        technical_form.setHorizontalSpacing(10)

        self.camera_value = QLabel("")
        self.camera_value.setObjectName("metaValue")
        self.camera_value.setMinimumWidth(360)
        self.lens_type_value = QLabel("")
        self.lens_type_value.setObjectName("metaValue")
        self.lens_type_value.setMinimumWidth(360)
        self.aperture_value = QLabel("")
        self.aperture_value.setObjectName("metaValue")
        self.focal_length_value = QLabel("")
        self.focal_length_value.setObjectName("metaValue")
        self.focus_distance_value = QLabel("")
        self.focus_distance_value.setObjectName("metaValue")
        self.captured_at_value = QLabel("")
        self.captured_at_value.setObjectName("metaValue")

        technical_form.addRow("Camera", self.camera_value)
        technical_form.addRow("Lens Type", self.lens_type_value)
        technical_form.addRow("Aperture", self.aperture_value)
        technical_form.addRow("Focal Length", self.focal_length_value)
        technical_form.addRow("Focus Distance", self.focus_distance_value)
        technical_form.addRow("Captured At", self.captured_at_value)
        layout.addLayout(technical_form)

        rename_heading = QLabel("Rename Preview")
        rename_heading.setObjectName("subHeading")
        layout.addWidget(rename_heading)

        self.rename_preview = QLineEdit()
        self.rename_preview.setReadOnly(True)
        self.rename_preview.setPlaceholderText("Filename preview appears in Part 5")
        layout.addWidget(self.rename_preview)

        self.save_button = QPushButton("Save Description + Keywords")
        self.save_button.setEnabled(False)
        layout.addWidget(self.save_button)

        self.process_button = QPushButton("Process & Move")
        self.process_button.setEnabled(False)
        layout.addWidget(self.process_button)

        self.save_status = QLabel("")
        self.save_status.setObjectName("statusLabel")
        layout.addWidget(self.save_status)

        debug_heading = QLabel("EXIF Dump (Debug)")
        debug_heading.setObjectName("subHeading")
        layout.addWidget(debug_heading)

        self.exif_dump_view = QPlainTextEdit()
        self.exif_dump_view.setReadOnly(True)
        self.exif_dump_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.exif_dump_view.setMinimumHeight(220)
        self.exif_dump_view.setPlaceholderText(
            "Full EXIF JSON dump for selected image appears here."
        )
        layout.addWidget(self.exif_dump_view, 1)

        self.setStyleSheet(
            f"""
            QFrame#metadataPanel {{
                background: {PANEL_BACKGROUND};
                border: 1px solid {ACCENT_CYAN};
                border-radius: 8px;
            }}
            QLabel#panelTitle {{
                color: {DARK_TEAL};
                font-weight: 700;
                font-size: 15px;
            }}
            QLabel#subHeading {{
                color: {ORANGE_PRIMARY};
                font-weight: 700;
                margin-top: 4px;
            }}
            QLabel, QLineEdit, QTextEdit {{
                color: {BROWN_TEXT};
                font-size: 12px;
            }}
            QLabel#metaValue {{
                color: {BROWN_TEXT};
                font-size: 12px;
                background: #f6f3f1;
                border: 1px solid #dfd8d1;
                border-radius: 5px;
                padding: 4px 6px;
            }}
            QPlainTextEdit {{
                color: {BROWN_TEXT};
                font-size: 11px;
                font-family: Menlo, Monaco, monospace;
            }}
            QLabel#statusLabel {{
                color: {BROWN_TEXT};
                font-size: 11px;
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

    def set_metadata_fields(
        self,
        *,
        title: str,
        description: str,
        keywords: str,
        camera: str,
        lens_type: str,
        aperture: str,
        focal_length: str,
        focus_distance: str,
        captured_at: str,
    ) -> None:
        """Populate editable and read-only metadata fields."""
        self.title_edit.setText(title)
        self.description_edit.setPlainText(description)
        self.keywords_edit.setPlainText(keywords)
        self.camera_value.setText(camera)
        self.lens_type_value.setText(lens_type)
        self.aperture_value.setText(aperture)
        self.focal_length_value.setText(focal_length)
        self.focus_distance_value.setText(focus_distance)
        self.captured_at_value.setText(captured_at)

    def set_exif_dump(self, dump_text: str) -> None:
        """Populate full EXIF debug dump."""
        self.exif_dump_view.setPlainText(dump_text)

    def clear_metadata(self, message: str = "") -> None:
        """Clear all metadata fields and debug text."""
        self.set_metadata_fields(
            title="",
            description="",
            keywords="",
            camera="",
            lens_type="",
            aperture="",
            focal_length="",
            focus_distance="",
            captured_at="",
        )
        self.exif_dump_view.setPlainText(message)
        self.set_save_button_enabled(False)
        self.set_save_status("")

    def description_text(self) -> str:
        """Return current description editor text."""
        return self.description_edit.toPlainText()

    def keywords_text(self) -> str:
        """Return current keywords editor text."""
        return self.keywords_edit.toPlainText()

    def set_save_button_enabled(self, enabled: bool) -> None:
        """Enable/disable metadata save action."""
        self.save_button.setEnabled(enabled)

    def set_save_status(self, message: str, is_error: bool = False) -> None:
        """Set status line under metadata save actions."""
        self.save_status.setText(message)
        color = "#c84d3a" if is_error else BROWN_TEXT
        self.save_status.setStyleSheet(f"color: {color}; font-size: 11px;")
