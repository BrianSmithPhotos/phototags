"""OpenRouter implementation of the AiProvider interface."""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from phototags.services.ai_provider import (
    AiProvider,
    AiSuggestionEmptyResponseError,
    AiSuggestionError,
    AiSuggestionTimeoutError,
)


def _read_int_env(name: str, default: int, *, minimum: int = 1) -> int:
    """Read positive integer env var with fallback to default."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed >= minimum else default


OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_DEFAULT_MODEL = os.getenv("PHOTOTAGS_OPENROUTER_MODEL", "google/gemini-2.5-flash")
OPENROUTER_TIMEOUT_SECONDS = _read_int_env("PHOTOTAGS_OPENROUTER_TIMEOUT_SECONDS", 120, minimum=10)

LOGGER = logging.getLogger(__name__)


class OpenRouterProvider(AiProvider):
    """Requests vision/chat completions from the OpenRouter API."""

    def __init__(self) -> None:
        self._vision_capability_cache: dict[str, bool] = {}

    def ensure_vision_capable(self, model: str) -> None:
        """Validate that selected OpenRouter model accepts image input."""
        normalized_model = model.strip()
        if not normalized_model:
            raise AiSuggestionError("No OpenRouter model selected")

        cached = self._vision_capability_cache.get(normalized_model)
        if cached is not None:
            if not cached:
                raise AiSuggestionError(
                    f"OpenRouter model '{normalized_model}' does not accept image input. "
                    "Choose a model with vision capability."
                )
            return

        models_payload = self._openrouter_models()
        models = models_payload.get("data")
        if not isinstance(models, list):
            raise AiSuggestionError("Invalid model list from OpenRouter /models")

        matched_modalities: list[str] | None = None
        for item in models:
            if not isinstance(item, dict):
                continue
            if self._to_text(item.get("id")).strip() != normalized_model:
                continue
            architecture = item.get("architecture")
            modalities = architecture.get("input_modalities") if isinstance(architecture, dict) else None
            matched_modalities = (
                [self._to_text(entry).strip().casefold() for entry in modalities]
                if isinstance(modalities, list)
                else []
            )
            break

        if matched_modalities is None:
            raise AiSuggestionError(
                f"OpenRouter model '{normalized_model}' was not found. Confirm the model id."
            )

        has_vision = "image" in matched_modalities
        self._vision_capability_cache[normalized_model] = has_vision
        if not has_vision:
            raise AiSuggestionError(
                f"OpenRouter model '{normalized_model}' does not accept image input. "
                "Choose a model with vision capability."
            )

    def chat(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_payloads: list[str],
        request_label: str = "",
        think: bool = True,
    ) -> str:
        """Run one chat completion request with base64 image payloads."""
        content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        for image_payload in image_payloads:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_payload}"},
                }
            )
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "temperature": 0.2,
        }
        if not think:
            # Not all routed models support a reasoning toggle; harmless no-op when ignored.
            body["reasoning"] = {"effort": "none", "exclude": True}

        response = self._openrouter_chat(body=body, request_label=request_label)
        return self._extract_message_content(response)

    def _openrouter_chat(self, *, body: dict[str, Any], request_label: str = "") -> dict[str, Any]:
        """Execute one chat completion request against the OpenRouter API."""
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise AiSuggestionError("OPENROUTER_API_KEY is not set")

        data = json.dumps(body).encode("utf-8")
        payload_size_bytes = len(data)
        started = time.perf_counter()
        request = Request(
            OPENROUTER_CHAT_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=OPENROUTER_TIMEOUT_SECONDS) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            error_body = exc.read().decode("utf-8", errors="replace")
            message = self._error_message_from_body(error_body) or str(exc)
            LOGGER.warning(
                "OpenRouter HTTP error [%s] after %dms (payload=%dB): %s",
                request_label or "chat",
                elapsed_ms,
                payload_size_bytes,
                message,
            )
            raise AiSuggestionError(f"OpenRouter request failed: {message}") from exc
        except URLError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if self._is_timeout_network_error(exc):
                LOGGER.warning(
                    "OpenRouter timeout [%s] after %dms (payload=%dB)",
                    request_label or "chat",
                    elapsed_ms,
                    payload_size_bytes,
                )
                raise AiSuggestionTimeoutError("OpenRouter request timed out") from exc
            LOGGER.warning(
                "OpenRouter network error [%s] after %dms (payload=%dB): %s",
                request_label or "chat",
                elapsed_ms,
                payload_size_bytes,
                exc,
            )
            raise AiSuggestionError("Could not reach the OpenRouter API.") from exc
        except TimeoutError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            LOGGER.warning(
                "OpenRouter timeout [%s] after %dms (payload=%dB)",
                request_label or "chat",
                elapsed_ms,
                payload_size_bytes,
            )
            raise AiSuggestionTimeoutError("OpenRouter request timed out") from exc

        try:
            parsed = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise AiSuggestionError("Invalid JSON response from OpenRouter") from exc

        error = parsed.get("error")
        if isinstance(error, dict):
            message = self._to_text(error.get("message")).strip()
            if self._is_timeout_text(message):
                raise AiSuggestionTimeoutError("OpenRouter request timed out")
            raise AiSuggestionError(message or "OpenRouter returned an error")
        return parsed

    def _openrouter_models(self) -> dict[str, Any]:
        """Read OpenRouter's model catalog, including input-modality capabilities."""
        request = Request(
            OPENROUTER_MODELS_URL,
            headers={"Content-Type": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=OPENROUTER_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8")
        except URLError as exc:
            raise AiSuggestionError(
                "Could not reach the OpenRouter API while checking model capabilities."
            ) from exc
        except TimeoutError as exc:
            raise AiSuggestionError("OpenRouter /models request timed out") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise AiSuggestionError("Invalid JSON response from OpenRouter /models") from exc

    def _extract_message_content(self, response: dict[str, Any]) -> str:
        """Extract assistant content from an OpenRouter chat completion response."""
        choices = response.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message")
                if isinstance(message, dict):
                    text = self._to_text(message.get("content")).strip()
                    if text:
                        return text
        raise AiSuggestionEmptyResponseError("Empty suggestion response from OpenRouter")

    def _error_message_from_body(self, body: str) -> str:
        """Extract an OpenRouter error message from a raw HTTP error response body."""
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return ""
        error = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(error, dict):
            return self._to_text(error.get("message")).strip()
        return ""

    def _is_timeout_network_error(self, exc: URLError) -> bool:
        """Return True when URLError wraps a timeout condition."""
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return True
        reason_text = self._to_text(reason).casefold()
        return "timed out" in reason_text or "timeout" in reason_text

    def _is_timeout_text(self, text: str) -> bool:
        """Return True when an error text likely indicates timeout."""
        lowered = text.casefold()
        return "timed out" in lowered or "timeout" in lowered

    def _to_text(self, value: Any) -> str:
        """Convert arbitrary value to text."""
        if value is None:
            return ""
        return str(value)
