"""Right metadata and actions panel UI."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from phototags.ui.styles import ACCENT_CYAN, BROWN_TEXT, DARK_TEAL, ORANGE_PRIMARY, PANEL_BACKGROUND, SALMON_SECONDARY


class MetadataPanel(QWidget):
    """Right panel for metadata, rename preview, and process action."""

    TECHNICAL_WIDE_VALUE_WIDTH = 360
    TECHNICAL_VALUE_HEIGHT = 26
    PANEL_FIXED_WIDTH = TECHNICAL_WIDE_VALUE_WIDTH + 160

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_exif_dump = ""
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
        self.setFixedWidth(self.PANEL_FIXED_WIDTH)

        title = QLabel("Metadata & Actions")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(8)

        self.title_edit = QTextEdit()
        self.title_edit.setMinimumHeight(54)
        self.title_edit.setPlaceholderText("Auto-set from filename stem in Part 5")
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

        ai_heading = QLabel("AI Suggestions (Ollama)")
        ai_heading.setObjectName("subHeading")
        layout.addWidget(ai_heading)

        self.suggest_button = QPushButton("Suggest Description + Keywords")
        self.suggest_button.setEnabled(False)
        layout.addWidget(self.suggest_button)

        self.suggested_keywords_view = QTextEdit()
        self.suggested_keywords_view.setReadOnly(True)
        self.suggested_keywords_view.setMinimumHeight(62)
        self.suggested_keywords_view.setPlaceholderText(
            "AI-suggested keywords appear here. Review and add to Keywords when ready."
        )
        layout.addWidget(self.suggested_keywords_view)

        self.apply_suggested_keywords_button = QPushButton("Add Suggested -> Keywords")
        self.apply_suggested_keywords_button.setEnabled(False)
        layout.addWidget(self.apply_suggested_keywords_button)

        self.ai_status = QLabel("")
        self.ai_status.setObjectName("statusLabel")
        layout.addWidget(self.ai_status)

        technical_heading = QLabel("Technical (Read-Only)")
        technical_heading.setObjectName("subHeading")
        layout.addWidget(technical_heading)

        technical_grid = QGridLayout()
        technical_grid.setContentsMargins(0, 0, 0, 0)
        technical_grid.setHorizontalSpacing(8)
        technical_grid.setVerticalSpacing(5)
        technical_grid.setColumnStretch(2, 3)
        technical_grid.setColumnStretch(5, 2)

        self.camera_value = self._create_meta_value_label(self.TECHNICAL_WIDE_VALUE_WIDTH)
        self.lens_type_value = self._create_meta_value_label(self.TECHNICAL_WIDE_VALUE_WIDTH)
        self._add_technical_field(
            technical_grid,
            row=0,
            start_column=0,
            label_text="Camera",
            value_label=self.camera_value,
            value_span=4,
        )
        self._add_technical_field(
            technical_grid,
            row=1,
            start_column=0,
            label_text="Lens Type",
            value_label=self.lens_type_value,
            value_span=4,
        )

        self.aperture_value = self._create_meta_value_label()
        self.shutter_speed_value = self._create_meta_value_label()
        self._add_technical_field(
            technical_grid,
            row=2,
            start_column=0,
            label_text="Aperture",
            value_label=self.aperture_value,
        )
        self._add_technical_field(
            technical_grid,
            row=2,
            start_column=3,
            label_text="Shutter Speed",
            value_label=self.shutter_speed_value,
        )

        self.focal_length_value = self._create_meta_value_label()
        self.focus_distance_value = self._create_meta_value_label()
        self._add_technical_field(
            technical_grid,
            row=3,
            start_column=0,
            label_text="Focal Length",
            value_label=self.focal_length_value,
        )
        self._add_technical_field(
            technical_grid,
            row=3,
            start_column=3,
            label_text="Focus Distance",
            value_label=self.focus_distance_value,
        )

        self.captured_at_value = self._create_meta_value_label()
        self.iso_value = self._create_meta_value_label()
        self._add_technical_field(
            technical_grid,
            row=4,
            start_column=0,
            label_text="Captured At",
            value_label=self.captured_at_value,
        )
        self._add_technical_field(
            technical_grid,
            row=4,
            start_column=3,
            label_text="ISO",
            value_label=self.iso_value,
        )
        layout.addLayout(technical_grid)

        rename_heading = QLabel("Rename Preview")
        rename_heading.setObjectName("subHeading")
        layout.addWidget(rename_heading)

        location_label = QLabel("Batch Location")
        location_label.setObjectName("fieldHelp")
        layout.addWidget(location_label)

        self.location_edit = QLineEdit()
        self.location_edit.setPlaceholderText("Applies to all files in current batch until changed")
        layout.addWidget(self.location_edit)

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
        layout.addStretch(1)

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
            QLabel#fieldHelp {{
                color: {BROWN_TEXT};
                font-size: 11px;
            }}
            QLabel#technicalLabel {{
                color: {BROWN_TEXT};
                font-size: 11px;
            }}
            QLabel#technicalColon {{
                color: {BROWN_TEXT};
                font-size: 11px;
            }}
            QLabel, QLineEdit, QTextEdit {{
                color: {BROWN_TEXT};
                font-size: 12px;
            }}
            QLabel#metaValue {{
                color: {BROWN_TEXT};
                font-size: 12px;
                padding: 0px;
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

    def _create_meta_value_label(self, fixed_width: int | None = None) -> QLabel:
        """Create a fixed-height read-only metadata value label."""
        label = QLabel("")
        label.setObjectName("metaValue")
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setMinimumHeight(20)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if fixed_width is not None:
            label.setMinimumWidth(fixed_width)
        return label

    def _add_technical_field(
        self,
        grid: QGridLayout,
        *,
        row: int,
        start_column: int,
        label_text: str,
        value_label: QLabel,
        value_span: int = 1,
    ) -> None:
        """Add one technical metadata field to the compact aligned grid."""
        label = QLabel(label_text)
        label.setObjectName("technicalLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        colon = QLabel(":")
        colon.setObjectName("technicalColon")
        colon.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        value_label.setMinimumWidth(max(88, value_label.minimumWidth()))

        grid.addWidget(label, row, start_column)
        grid.addWidget(colon, row, start_column + 1)
        grid.addWidget(value_label, row, start_column + 2, 1, value_span)

    def set_metadata_fields(
        self,
        *,
        title: str,
        description: str,
        keywords: str,
        camera: str,
        lens_type: str,
        aperture: str,
        shutter_speed: str,
        focal_length: str,
        focus_distance: str,
        captured_at: str,
        iso: str,
    ) -> None:
        """Populate editable and read-only metadata fields."""
        self.title_edit.setPlainText(title)
        self.description_edit.setPlainText(description)
        self.keywords_edit.setPlainText(keywords)
        self.camera_value.setText(camera)
        self.lens_type_value.setText(lens_type)
        self.aperture_value.setText(aperture)
        self.shutter_speed_value.setText(shutter_speed)
        self.focal_length_value.setText(focal_length)
        self.focus_distance_value.setText(focus_distance)
        self.captured_at_value.setText(captured_at)
        self.iso_value.setText(iso)

    def set_exif_dump(self, dump_text: str) -> None:
        """Store EXIF dump text for potential future debug surfaces."""
        self._last_exif_dump = dump_text

    def clear_metadata(self, message: str = "") -> None:
        """Clear all metadata fields."""
        self.set_metadata_fields(
            title="",
            description="",
            keywords="",
            camera="",
            lens_type="",
            aperture="",
            shutter_speed="",
            focal_length="",
            focus_distance="",
            captured_at="",
            iso="",
        )
        self._last_exif_dump = message
        self.clear_ai_suggestions()
        self.set_suggest_button_enabled(False)
        self.set_save_button_enabled(False)
        self.set_process_button_enabled(False)
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

    def set_process_button_enabled(self, enabled: bool) -> None:
        """Enable/disable process action."""
        self.process_button.setEnabled(enabled)

    def set_suggest_button_enabled(self, enabled: bool) -> None:
        """Enable/disable AI suggestion action."""
        self.suggest_button.setEnabled(enabled)

    def set_apply_suggested_keywords_enabled(self, enabled: bool) -> None:
        """Enable/disable apply-suggested-keywords action."""
        self.apply_suggested_keywords_button.setEnabled(enabled)

    def set_save_status(self, message: str, is_error: bool = False) -> None:
        """Set status line under metadata save actions."""
        self.save_status.setText(message)
        color = "#c84d3a" if is_error else BROWN_TEXT
        self.save_status.setStyleSheet(f"color: {color}; font-size: 11px;")

    def set_ai_status(self, message: str, is_error: bool = False) -> None:
        """Set status line for AI suggestion actions."""
        self.ai_status.setText(message)
        color = "#c84d3a" if is_error else BROWN_TEXT
        self.ai_status.setStyleSheet(f"color: {color}; font-size: 11px;")

    def location_text(self) -> str:
        """Return current rename location value."""
        return self.location_edit.text()

    def rename_preview_text(self) -> str:
        """Return generated filename preview text."""
        return self.rename_preview.text().strip()

    def set_suggested_keywords(self, text: str) -> None:
        """Set AI suggested keywords text."""
        self.suggested_keywords_view.setPlainText(text)

    def suggested_keywords_text(self) -> str:
        """Return current suggested keywords text."""
        return self.suggested_keywords_view.toPlainText()

    def clear_ai_suggestions(self) -> None:
        """Clear AI suggestion output."""
        self.suggested_keywords_view.setPlainText("")
        self.set_apply_suggested_keywords_enabled(False)
        self.set_ai_status("")

    def set_rename_preview(self, filename: str) -> None:
        """Set generated filename preview text."""
        self.rename_preview.setText(filename)
