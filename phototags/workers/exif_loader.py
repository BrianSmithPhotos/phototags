"""Background EXIF metadata loader."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from phototags.services.exif_service import ExifService, ExifToolReadError


class ExifLoadSignals(QObject):
    """Signals emitted by EXIF read worker."""

    loaded = Signal(str, object, str)
    failed = Signal(str, str)


class ExifLoadTask(QRunnable):
    """Load EXIF metadata in background to keep UI responsive."""

    def __init__(
        self,
        image_path: Path,
        signals: ExifLoadSignals,
        service: ExifService,
    ) -> None:
        super().__init__()
        self.image_path = image_path
        self.signals = signals
        self.service = service

    def run(self) -> None:
        """Read metadata and emit mapped UI data plus full debug dump."""
        try:
            metadata = self.service.read_full_metadata(self.image_path)
            ui_data = self.service.map_for_ui(metadata)
            dump_text = self.service.format_full_dump(metadata)
            self.signals.loaded.emit(str(self.image_path), ui_data, dump_text)
        except (OSError, ValueError, ExifToolReadError, RuntimeError) as exc:
            try:
                self.signals.failed.emit(str(self.image_path), str(exc))
            except RuntimeError:
                return
