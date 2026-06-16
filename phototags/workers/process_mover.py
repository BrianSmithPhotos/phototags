"""Background process-and-copy worker."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from phototags.services.process_move_service import ProcessMoveError, ProcessMoveService


class ProcessMoveSignals(QObject):
    """Signals emitted by process-and-copy worker."""

    completed = Signal(str, object)
    failed = Signal(str, str)


class ProcessMoveTask(QRunnable):
    """Run process-and-copy flow without blocking UI."""

    def __init__(
        self,
        *,
        source_path: Path,
        destination_root: Path,
        proposed_filename: str,
        captured_at: str,
        title: str,
        description: str,
        keywords_text: str,
        service: ProcessMoveService,
        signals: ProcessMoveSignals,
    ) -> None:
        super().__init__()
        self.source_path = source_path
        self.destination_root = destination_root
        self.proposed_filename = proposed_filename
        self.captured_at = captured_at
        self.title = title
        self.description = description
        self.keywords_text = keywords_text
        self.service = service
        self.signals = signals

    def run(self) -> None:
        """Execute process flow and emit success/failure."""
        try:
            result = self.service.process_and_copy(
                source_path=self.source_path,
                destination_root=self.destination_root,
                proposed_filename=self.proposed_filename,
                captured_at=self.captured_at,
                title=self.title,
                description=self.description,
                keywords_text=self.keywords_text,
            )
            self.signals.completed.emit(str(self.source_path), result)
        except (OSError, ValueError, ProcessMoveError, RuntimeError) as exc:
            try:
                self.signals.failed.emit(str(self.source_path), str(exc))
            except RuntimeError:
                return
