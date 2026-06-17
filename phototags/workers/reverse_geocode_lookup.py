"""Background reverse geocode lookup worker."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from phototags.services.reverse_geocode_service import ReverseGeocodeError, ReverseGeocodeResult, ReverseGeocodeService


class ReverseGeocodeSignals(QObject):
    """Signals emitted by reverse geocode worker."""

    looked_up = Signal(str, object)
    failed = Signal(str, str)


class ReverseGeocodeTask(QRunnable):
    """Lookup reverse geocode location without blocking the UI thread."""

    def __init__(
        self,
        *,
        image_path: Path,
        latitude: float,
        longitude: float,
        service: ReverseGeocodeService,
        signals: ReverseGeocodeSignals,
    ) -> None:
        super().__init__()
        self.image_path = image_path
        self.latitude = latitude
        self.longitude = longitude
        self.service = service
        self.signals = signals

    def run(self) -> None:
        """Lookup location and emit success/failure."""
        try:
            result: ReverseGeocodeResult = self.service.lookup_location(
                latitude=self.latitude,
                longitude=self.longitude,
            )
            self.signals.looked_up.emit(str(self.image_path), result)
        except (OSError, ValueError, ReverseGeocodeError, RuntimeError) as exc:
            try:
                self.signals.failed.emit(str(self.image_path), str(exc))
            except RuntimeError:
                return
