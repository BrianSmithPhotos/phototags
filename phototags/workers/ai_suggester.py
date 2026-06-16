"""Background AI suggestion worker."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from phototags.services.ai_suggestion_service import (
    AiSuggestionError,
    AiSuggestionService,
)


class AiSuggestSignals(QObject):
    """Signals emitted by AI suggestion worker."""

    suggested = Signal(str, object)
    failed = Signal(str, str)


class AiSuggestTask(QRunnable):
    """Generate AI suggestions without blocking the UI thread."""

    def __init__(
        self,
        *,
        image_path: Path,
        existing_keywords_text: str,
        existing_description: str,
        capture_context: str,
        service: AiSuggestionService,
        signals: AiSuggestSignals,
    ) -> None:
        super().__init__()
        self.image_path = image_path
        self.existing_keywords_text = existing_keywords_text
        self.existing_description = existing_description
        self.capture_context = capture_context
        self.service = service
        self.signals = signals

    def run(self) -> None:
        """Run AI inference and emit success/failure."""
        try:
            result = self.service.suggest_for_image(
                image_path=self.image_path,
                existing_keywords_text=self.existing_keywords_text,
                existing_description=self.existing_description,
                capture_context=self.capture_context,
            )
            self.signals.suggested.emit(str(self.image_path), result)
        except (OSError, ValueError, AiSuggestionError, RuntimeError) as exc:
            try:
                self.signals.failed.emit(str(self.image_path), str(exc))
            except RuntimeError:
                return
