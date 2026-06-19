"""Provider abstraction for vision-capable chat backends used for AI suggestions.

Lets `AiSuggestionService` stay backend-agnostic (prompting, parsing, crop-refinement
logic) while swapping the actual HTTP/model backend (Ollama, OpenRouter, ...).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class AiSuggestionError(RuntimeError):
    """Raised when an AI provider request fails."""


class AiSuggestionTimeoutError(AiSuggestionError):
    """Raised when an AI provider request times out."""


class AiSuggestionEmptyResponseError(AiSuggestionError):
    """Raised when an AI provider returns no usable content."""


class AiProvider(ABC):
    """A vision-capable chat backend that can generate metadata suggestions."""

    @abstractmethod
    def ensure_vision_capable(self, model: str) -> None:
        """Raise AiSuggestionError if the model is unavailable or lacks vision support."""

    @abstractmethod
    def chat(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_payloads: list[str],
        request_label: str = "",
    ) -> str:
        """Send one chat request with base64 image payloads and return the raw text reply.

        Implementations own their own timeout/retry behavior and must raise
        AiSuggestionTimeoutError/AiSuggestionEmptyResponseError/AiSuggestionError
        rather than backend-specific exceptions.
        """
