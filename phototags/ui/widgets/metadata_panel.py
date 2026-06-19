"""Right metadata and actions panel UI."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
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
    PANEL_FIXED_WIDTH = TECHNICAL_WIDE_VALUE_WIDTH + 200
    GPS_ALTITUDE_UNRELIABLE_COLOR = "#94867a"
    GPS_ALTITUDE_UNRELIABLE_BACKGROUND = "#f4eee7"

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

        self.ai_model_edit = QLineEdit()
        self.ai_model_edit.setPlaceholderText(
            "Model (e.g. gemma4:26b-mlx, or openrouter:google/gemini-2.5-flash)"
        )
        layout.addWidget(self.ai_model_edit)

        self.suggest_button = QPushButton("Suggest Description + Keywords")
        self.suggest_button.setEnabled(False)
        layout.addWidget(self.suggest_button)

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

        gps_heading = QLabel("GPS Enrichment")
        gps_heading.setObjectName("subHeading")
        layout.addWidget(gps_heading)

        gps_button_row = QHBoxLayout()
        gps_button_row.setSpacing(6)

        self.suggest_gps_button = QPushButton("Suggest GPS From Timeline")
        self.suggest_gps_button.setEnabled(False)
        self.suggest_gps_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        gps_button_row.addWidget(self.suggest_gps_button, 1)

        self.apply_gps_button = QPushButton("Apply Suggested GPS To Set")
        self.apply_gps_button.setEnabled(False)
        self.apply_gps_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        gps_button_row.addWidget(self.apply_gps_button, 1)

        layout.addLayout(gps_button_row)

        self.auto_altitude_lookup_check = QCheckBox("Auto lookup altitude when missing")
        self.auto_altitude_lookup_check.setChecked(False)
        layout.addWidget(self.auto_altitude_lookup_check)

        gps_form = QFormLayout()
        gps_form.setSpacing(6)
        self.gps_latitude_edit = QLineEdit()
        self.gps_latitude_edit.setPlaceholderText("Latitude")
        self.gps_longitude_edit = QLineEdit()
        self.gps_longitude_edit.setPlaceholderText("Longitude")
        self.gps_altitude_edit = QLineEdit()
        self.gps_altitude_edit.setPlaceholderText("Altitude meters (optional)")
        gps_form.addRow("Lat", self.gps_latitude_edit)
        gps_form.addRow("Lon", self.gps_longitude_edit)
        gps_form.addRow("Alt (m)", self.gps_altitude_edit)
        layout.addLayout(gps_form)

        self.lookup_altitude_button = QPushButton("Lookup Altitude For Set")
        self.lookup_altitude_button.setEnabled(False)
        layout.addWidget(self.lookup_altitude_button)

        self.gps_status = QLabel("")
        self.gps_status.setObjectName("statusLabel")
        self.gps_status.setWordWrap(True)
        self.gps_status.setMinimumHeight(34)
        layout.addWidget(self.gps_status)

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

        save_row = QHBoxLayout()
        save_row.setSpacing(6)

        self.save_single_button = QPushButton("Save Single")
        self.save_single_button.setEnabled(False)
        self.save_single_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        save_row.addWidget(self.save_single_button, 1)

        self.save_set_button = QPushButton("Save Capture Set")
        self.save_set_button.setEnabled(False)
        self.save_set_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        save_row.addWidget(self.save_set_button, 1)

        layout.addLayout(save_row)

        process_heading = QLabel("Process & Move")
        process_heading.setObjectName("subHeading")
        layout.addWidget(process_heading)

        process_row = QHBoxLayout()
        process_row.setSpacing(6)

        self.process_single_button = QPushButton("Single Image")
        self.process_single_button.setEnabled(False)
        self.process_single_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        process_row.addWidget(self.process_single_button, 1)

        self.process_set_button = QPushButton("Capture Set")
        self.process_set_button.setEnabled(False)
        self.process_set_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        process_row.addWidget(self.process_set_button, 1)

        self.process_session_button = QPushButton("Session")
        self.process_session_button.setEnabled(False)
        self.process_session_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        process_row.addWidget(self.process_session_button, 1)

        layout.addLayout(process_row)

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
        gps_latitude: str,
        gps_longitude: str,
        gps_altitude: str,
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
        self.set_gps_fields(
            latitude=gps_latitude,
            longitude=gps_longitude,
            altitude=gps_altitude,
        )

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
            gps_latitude="",
            gps_longitude="",
            gps_altitude="",
        )
        self._last_exif_dump = message
        self.clear_ai_suggestions()
        self.clear_gps_status()
        self.set_gps_lookup_button_enabled(False)
        self.set_gps_apply_button_enabled(False)
        self.set_lookup_altitude_button_enabled(False)
        self.set_suggest_button_enabled(False)
        self.set_save_buttons_enabled(False)
        self.set_process_buttons_enabled(False)
        self.set_save_status("")

    def description_text(self) -> str:
        """Return current description editor text."""
        return self.description_edit.toPlainText()

    def keywords_text(self) -> str:
        """Return current keywords editor text."""
        return self.keywords_edit.toPlainText()

    def set_save_buttons_enabled(self, enabled: bool) -> None:
        """Enable/disable metadata save actions."""
        self.save_single_button.setEnabled(enabled)
        self.save_set_button.setEnabled(enabled)

    def set_save_button_enabled(self, enabled: bool) -> None:
        """Backward-compatible wrapper for save button state."""
        self.set_save_buttons_enabled(enabled)

    def set_process_buttons_enabled(self, enabled: bool) -> None:
        """Enable/disable all process action buttons."""
        self.process_single_button.setEnabled(enabled)
        self.process_set_button.setEnabled(enabled)
        self.process_session_button.setEnabled(enabled)

    def set_suggest_button_enabled(self, enabled: bool) -> None:
        """Enable/disable AI suggestion action."""
        self.suggest_button.setEnabled(enabled)

    def set_gps_lookup_button_enabled(self, enabled: bool) -> None:
        """Enable/disable timeline GPS lookup action."""
        self.suggest_gps_button.setEnabled(enabled)

    def set_gps_apply_button_enabled(self, enabled: bool) -> None:
        """Enable/disable apply-suggested-GPS action."""
        self.apply_gps_button.setEnabled(enabled)

    def set_lookup_altitude_button_enabled(self, enabled: bool) -> None:
        """Enable/disable altitude lookup action."""
        self.lookup_altitude_button.setEnabled(enabled)

    def ai_model_name(self) -> str:
        """Return current Ollama model name from AI settings."""
        return self.ai_model_edit.text().strip()

    def set_ai_model_name(self, model_name: str) -> None:
        """Set Ollama model name in AI settings input."""
        self.ai_model_edit.setText(model_name.strip())

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

    def set_gps_status(self, message: str, is_error: bool = False) -> None:
        """Set status line for GPS enrichment actions."""
        self.gps_status.setText(message)
        color = "#c84d3a" if is_error else BROWN_TEXT
        self.gps_status.setStyleSheet(f"color: {color}; font-size: 11px;")

    def clear_gps_status(self) -> None:
        """Clear GPS enrichment status text."""
        self.set_gps_status("")

    def location_text(self) -> str:
        """Return current rename location value."""
        return self.location_edit.text()

    def rename_preview_text(self) -> str:
        """Return generated filename preview text."""
        return self.rename_preview.text().strip()

    def gps_latitude_text(self) -> str:
        """Return current GPS latitude text."""
        return self.gps_latitude_edit.text().strip()

    def gps_longitude_text(self) -> str:
        """Return current GPS longitude text."""
        return self.gps_longitude_edit.text().strip()

    def gps_altitude_text(self) -> str:
        """Return current GPS altitude text."""
        return self.gps_altitude_edit.text().strip()

    def auto_altitude_lookup_enabled(self) -> bool:
        """Return whether auto altitude lookup is enabled."""
        return self.auto_altitude_lookup_check.isChecked()

    def set_gps_fields(
        self,
        *,
        latitude: str,
        longitude: str,
        altitude: str,
    ) -> None:
        """Set editable GPS fields."""
        self.gps_latitude_edit.setText(latitude)
        self.gps_longitude_edit.setText(longitude)
        self.gps_altitude_edit.setText(altitude)
        self.set_gps_altitude_unreliable(False)

    def set_gps_altitude_unreliable(self, unreliable: bool, source_type: str = "") -> None:
        """Dim altitude field when value comes from a less-reliable timeline source."""
        if unreliable:
            self.gps_altitude_edit.setStyleSheet(
                (
                    f"color: {self.GPS_ALTITUDE_UNRELIABLE_COLOR}; "
                    f"background: {self.GPS_ALTITUDE_UNRELIABLE_BACKGROUND};"
                )
            )
            source = source_type.strip() or "timeline"
            self.gps_altitude_edit.setToolTip(
                f"Altitude from {source} source is approximate and may be inaccurate."
            )
            return
        self.gps_altitude_edit.setStyleSheet("")
        self.gps_altitude_edit.setToolTip("")

    def clear_ai_suggestions(self) -> None:
        """Clear AI suggestion output."""
        self.set_ai_status("")

    def set_rename_preview(self, filename: str) -> None:
        """Set generated filename preview text."""
        self.rename_preview.setText(filename)
