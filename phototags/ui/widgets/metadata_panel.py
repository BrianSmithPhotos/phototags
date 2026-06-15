"""Right metadata and actions panel UI."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
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

        rename_heading = QLabel("Rename Preview")
        rename_heading.setObjectName("subHeading")
        layout.addWidget(rename_heading)

        self.rename_preview = QLineEdit()
        self.rename_preview.setReadOnly(True)
        self.rename_preview.setPlaceholderText("Filename preview appears in Part 5")
        layout.addWidget(self.rename_preview)

        self.process_button = QPushButton("Process & Move")
        self.process_button.setEnabled(False)
        layout.addWidget(self.process_button)

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
            QLabel, QLineEdit, QTextEdit {{
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
