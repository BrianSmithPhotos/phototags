"""Background elevation lookup worker."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from phototags.services.elevation_lookup_service import ElevationLookupError, ElevationLookupService


class ElevationLookupSignals(QObject):
    """Signals emitted by elevation lookup worker."""

    looked_up = Signal(str, float)
    failed = Signal(str, str)


class ElevationLookupTask(QRunnable):
    """Lookup altitude without blocking the UI thread."""

    def __init__(
        self,
        *,
        image_path: Path,
        latitude: float,
        longitude: float,
        service: ElevationLookupService,
        signals: ElevationLookupSignals,
    ) -> None:
        super().__init__()
        self.image_path = image_path
        self.latitude = latitude
        self.longitude = longitude
        self.service = service
        self.signals = signals

    def run(self) -> None:
        """Lookup altitude and emit success/failure."""
        try:
            altitude_m = self.service.lookup_altitude_m(
                latitude=self.latitude,
                longitude=self.longitude,
            )
            self.signals.looked_up.emit(str(self.image_path), altitude_m)
        except (OSError, ValueError, ElevationLookupError, RuntimeError) as exc:
            try:
                self.signals.failed.emit(str(self.image_path), str(exc))
            except RuntimeError:
                return
