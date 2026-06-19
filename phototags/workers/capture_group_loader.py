"""Background capture grouping loader."""

from __future__ import annotations

from pathlib import Path

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
    """Compute capture groups in filename-ordered batches without blocking the UI thread.

    Batching lets the UI apply grouping for the first files in a folder as soon as
    their batch resolves, rather than waiting for the whole folder's EXIF reads to
    finish before showing any stacked sets.
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
        """Run capture grouping batch by batch, emitting a signal per batch."""
        batches = batch_image_paths(self.image_paths)
        last_index = len(batches) - 1
        for index, batch in enumerate(batches):
            try:
                result = self.service.build_groups(batch)
            except (OSError, ValueError, CaptureGroupError, RuntimeError) as exc:
                try:
                    self.signals.failed.emit(str(self.folder_path), str(exc))
                except RuntimeError:
                    return
                return
            try:
                self.signals.loaded.emit(str(self.folder_path), result, index == last_index)
            except RuntimeError:
                return
