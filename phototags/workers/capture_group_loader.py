"""Background capture grouping loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal

from phototags.services.capture_group_service import (
    CaptureGroupError,
    CaptureGroupService,
    batch_image_paths,
)


class CaptureGroupLoadSignals(QObject):
    """Signals emitted by capture grouping worker."""

    loaded = Signal(str, object, bool)
    failed = Signal(str, str)


class CaptureGroupLoadTask(QRunnable):
    """Read EXIF grouping metadata in filename-ordered batches without blocking the UI thread.

    Batching the EXIF reads lets the UI apply grouping for the first files in a
    folder as soon as their batch resolves, rather than waiting for the whole
    folder's EXIF reads to finish before showing any stacked sets. Grouping itself
    is recomputed from the full accumulated metadata after every batch (cheap, no
    extra I/O) rather than per batch in isolation, so a set sharing one timestamp
    is never split just because its files landed in different batches.
    """

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
        """Read EXIF metadata batch by batch, emitting full cumulative grouping each time."""
        batches = batch_image_paths(self.image_paths)
        last_index = len(batches) - 1
        accumulated_metadata: dict[Path, dict[str, Any]] = {}
        processed_paths: list[Path] = []
        for index, batch in enumerate(batches):
            try:
                batch_metadata = self.service.read_metadata_for_paths(batch)
            except (OSError, ValueError, CaptureGroupError, RuntimeError) as exc:
                try:
                    self.signals.failed.emit(str(self.folder_path), str(exc))
                except RuntimeError:
                    return
                return
            accumulated_metadata.update(batch_metadata)
            processed_paths.extend(batch)
            result = self.service.build_groups_from_metadata(processed_paths, accumulated_metadata)
            try:
                self.signals.loaded.emit(str(self.folder_path), result, index == last_index)
            except RuntimeError:
                return
