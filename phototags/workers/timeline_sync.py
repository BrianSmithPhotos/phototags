"""Background worker that syncs Timeline.json from Google Drive on startup."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from phototags.services.timeline_sync_service import TimelineSyncService


class TimelineSyncSignals(QObject):
    """Signals emitted by the Timeline.json Google Drive sync worker."""

    synced = Signal(bool)
    failed = Signal(str)


class TimelineSyncTask(QRunnable):
    """Copy a fresher Timeline.json from Google Drive without blocking the UI thread."""

    def __init__(self, *, service: TimelineSyncService, signals: TimelineSyncSignals) -> None:
        super().__init__()
        self.service = service
        self.signals = signals

    def run(self) -> None:
        """Run the freshness check and copy on a background thread."""
        try:
            copied = self.service.sync_if_fresher()
            self.signals.synced.emit(copied)
        except OSError as exc:
            try:
                self.signals.failed.emit(str(exc))
            except RuntimeError:
                return
