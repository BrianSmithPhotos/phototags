"""Background metadata write worker."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from phototags.services.metadata_write_service import (
    MetadataWriteError,
    MetadataWriteService,
)


class MetadataSaveSignals(QObject):
    """Signals emitted by metadata save worker."""

    saved = Signal(str, object)
    failed = Signal(str, str)


class MetadataSaveTask(QRunnable):
    """Write description + keywords without blocking UI."""

    def __init__(
        self,
        image_path: Path,
        *,
        description: str,
        keywords_text: str,
        service: MetadataWriteService,
        signals: MetadataSaveSignals,
    ) -> None:
        super().__init__()
        self.image_path = image_path
        self.description = description
        self.keywords_text = keywords_text
        self.service = service
        self.signals = signals

    def run(self) -> None:
        """Persist metadata and emit success/failure."""
        try:
            result = self.service.write_description_keywords(
                self.image_path,
                description=self.description,
                keywords_text=self.keywords_text,
            )
            self.signals.saved.emit(str(self.image_path), result)
        except (OSError, ValueError, MetadataWriteError, RuntimeError) as exc:
            try:
                self.signals.failed.emit(str(self.image_path), str(exc))
            except RuntimeError:
                return
