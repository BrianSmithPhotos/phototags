"""Background capture grouping loader."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from phototags.services.capture_group_service import CaptureGroupError, CaptureGroupService


class CaptureGroupLoadSignals(QObject):
    """Signals emitted by capture grouping worker."""

    loaded = Signal(str, object)
    failed = Signal(str, str)


class CaptureGroupLoadTask(QRunnable):
    """Compute capture groups without blocking the UI thread."""

    def __init__(
        self,
        *,
        folder_path: Path,
        image_paths: list[Path],
        service: CaptureGroupService,
        signals: CaptureGroupLoadSignals,
    ) -> None:
        super().__init__()
        self.folder_path = folder_path
        self.image_paths = image_paths
        self.service = service
        self.signals = signals

    def run(self) -> None:
        """Run capture grouping and emit success/failure signals."""
        try:
            result = self.service.build_groups(self.image_paths)
            self.signals.loaded.emit(str(self.folder_path), result)
        except (OSError, ValueError, CaptureGroupError, RuntimeError) as exc:
            try:
                self.signals.failed.emit(str(self.folder_path), str(exc))
            except RuntimeError:
                return
