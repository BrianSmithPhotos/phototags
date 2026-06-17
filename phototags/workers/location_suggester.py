"""Background GPS suggestion worker backed by timeline cache."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from phototags.services.timeline_location_service import GpsSuggestion, TimelineLocationError, TimelineLocationService


class LocationSuggestSignals(QObject):
    """Signals emitted by timeline GPS suggestion worker."""

    suggested = Signal(str, object)
    failed = Signal(str, str)


class LocationSuggestTask(QRunnable):
    """Run timeline-backed GPS lookup without blocking the UI thread."""

    def __init__(
        self,
        *,
        image_path: Path,
        captured_at: str,
        service: TimelineLocationService,
        signals: LocationSuggestSignals,
    ) -> None:
        super().__init__()
        self.image_path = image_path
        self.captured_at = captured_at
        self.service = service
        self.signals = signals

    def run(self) -> None:
        """Lookup nearest GPS sample for the selected image capture time."""
        try:
            suggestion: GpsSuggestion | None = self.service.suggest_for_capture(self.captured_at)
            self.signals.suggested.emit(str(self.image_path), suggestion)
        except (OSError, ValueError, TimelineLocationError, RuntimeError) as exc:
            try:
                self.signals.failed.emit(str(self.image_path), str(exc))
            except RuntimeError:
                return
