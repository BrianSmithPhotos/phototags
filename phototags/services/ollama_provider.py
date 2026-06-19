"""Ollama implementation of the AiProvider interface."""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from phototags.services.ai_provider import (
    AiProvider,
    AiSuggestionError,
    AiSuggestionEmptyResponseError,
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


def _read_optional_int_env(name: str, *, minimum: int = 1) -> int | None:
    """Read optional positive integer env var; return None when unset/invalid."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        parsed = int(raw)
    except ValueError:
        return None
    return parsed if parsed >= minimum else None


OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
OLLAMA_DEFAULT_MODEL = os.getenv("PHOTOTAGS_OLLAMA_MODEL", "qwen3.6:35b")
OLLAMA_TIMEOUT_SECONDS = _read_int_env("PHOTOTAGS_OLLAMA_TIMEOUT_SECONDS", 180, minimum=10)
OLLAMA_KEEP_ALIVE = os.getenv("PHOTOTAGS_OLLAMA_KEEP_ALIVE", "15m").strip()
OLLAMA_MAX_PREDICT = _read_optional_int_env("PHOTOTAGS_OLLAMA_MAX_PREDICT", minimum=32)
EMPTY_RESPONSE_RETRY_NUM_PREDICT = 1024

LOGGER = logging.getLogger(__name__)


class OllamaProvider(AiProvider):
    """Requests vision/chat completions from a local Ollama instance."""

    def __init__(self) -> None:
        self._vision_capability_cache: dict[str, bool] = {}

    def ensure_vision_capable(self, model: str) -> None:
        """Validate that selected Ollama model includes vision capability."""
        normalized_model = model.strip()
        if not normalized_model:
            raise AiSuggestionError("No Ollama model selected")

        cached = self._vision_capability_cache.get(normalized_model)
        if cached is not None:
            if not cached:
                raise AiSuggestionError(
                    f"Ollama model '{normalized_model}' does not support vision. "
                    "Choose a model with vision capability."
                )
            return

        tags_payload = self._ollama_tags()
        models = tags_payload.get("models")
        if not isinstance(models, list):
            raise AiSuggestionError("Invalid model list from Ollama /api/tags")

        matched_capabilities: list[str] | None = None
        for item in models:
            if not isinstance(item, dict):
                continue
            names = {
                self._to_text(item.get("name")).strip(),
                self._to_text(item.get("model")).strip(),
            }
            if normalized_model not in names:
                continue
            caps = item.get("capabilities")
            if isinstance(caps, list):
                matched_capabilities = [self._to_text(entry).strip().casefold() for entry in caps]
            else:
                matched_capabilities = []
            break

        if matched_capabilities is None:
            raise AiSuggestionError(
                f"Ollama model '{normalized_model}' was not found in /api/tags. "
                "Confirm the model is installed."
            )

        has_vision = "vision" in matched_capabilities
        self._vision_capability_cache[normalized_model] = has_vision
        if not has_vision:
            raise AiSuggestionError(
                f"Ollama model '{normalized_model}' does not support vision. "
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
        """Run one chat request, retrying once with a larger budget on empty content."""
        payload: dict[str, Any] = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt, "images": image_payloads},
            ],
            "options": {
                "temperature": 0.2,
            },
        }
        if not think:
            payload["think"] = False
        if OLLAMA_MAX_PREDICT is not None:
            payload["options"]["num_predict"] = OLLAMA_MAX_PREDICT
        if OLLAMA_KEEP_ALIVE:
            payload["keep_alive"] = OLLAMA_KEEP_ALIVE

        response = self._ollama_chat(payload=payload, request_label=request_label)
        try:
            return self._extract_message_content(response)
        except AiSuggestionEmptyResponseError:
            retry_label = f"{request_label}:empty-retry" if request_label else "empty-retry"
            retry_payload = self._payload_with_empty_response_retry_budget(
                payload=payload,
                response=response,
            )
            LOGGER.warning(
                "Ollama returned empty content [%s] (done_reason=%s); retrying once",
                request_label or "chat",
                self._to_text(response.get("done_reason")).strip() or "unknown",
            )
            retry_response = self._ollama_chat(payload=retry_payload, request_label=retry_label)
            return self._extract_message_content(retry_response)

    def _ollama_chat(self, *, payload: dict[str, Any], request_label: str = "") -> dict[str, Any]:
        """Execute one non-streaming chat request against local Ollama."""
        data = json.dumps(payload).encode("utf-8")
        payload_size_bytes = len(data)
        started = time.perf_counter()
        request = Request(
            OLLAMA_CHAT_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8")
        except URLError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if self._is_timeout_network_error(exc):
                LOGGER.warning(
                    "Ollama timeout [%s] after %dms (payload=%dB)",
                    request_label or "chat",
                    elapsed_ms,
                    payload_size_bytes,
                )
                raise AiSuggestionTimeoutError("Ollama request timed out") from exc
            LOGGER.warning(
                "Ollama network error [%s] after %dms (payload=%dB): %s",
                request_label or "chat",
                elapsed_ms,
                payload_size_bytes,
                exc,
            )
            raise AiSuggestionError(
                "Could not reach Ollama at http://127.0.0.1:11434. "
                "Ensure `ollama serve` is running."
            ) from exc
        except TimeoutError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            LOGGER.warning(
                "Ollama timeout [%s] after %dms (payload=%dB)",
                request_label or "chat",
                elapsed_ms,
                payload_size_bytes,
            )
            raise AiSuggestionTimeoutError("Ollama request timed out") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AiSuggestionError("Invalid JSON response from Ollama") from exc

        error_text = self._to_text(parsed.get("error"))
        if error_text:
            if self._is_timeout_text(error_text):
                raise AiSuggestionTimeoutError("Ollama request timed out")
            raise AiSuggestionError(error_text)
        return parsed

    def _ollama_tags(self) -> dict[str, Any]:
        """Read local Ollama installed model metadata from /api/tags."""
        request = Request(
            OLLAMA_TAGS_URL,
            headers={"Content-Type": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8")
        except URLError as exc:
            raise AiSuggestionError(
                "Could not reach Ollama at http://127.0.0.1:11434 while checking model capabilities."
            ) from exc
        except TimeoutError as exc:
            raise AiSuggestionError("Ollama /api/tags request timed out") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AiSuggestionError("Invalid JSON response from Ollama /api/tags") from exc

        return parsed

    def _extract_message_content(self, response: dict[str, Any]) -> str:
        """Extract assistant content from Ollama chat response."""
        message = response.get("message")
        if isinstance(message, dict):
            content = self._to_text(message.get("content")).strip()
            if content:
                return content
        elif isinstance(message, str):
            content = message.strip()
            if content:
                return content

        fallback_keys = ("response", "output", "output_text", "text")
        for key in fallback_keys:
            text = self._to_text(response.get(key)).strip()
            if text:
                return text

        choices = response.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                choice_message = choice.get("message")
                if isinstance(choice_message, dict):
                    text = self._to_text(choice_message.get("content")).strip()
                    if text:
                        return text
                text = self._to_text(choice.get("text")).strip()
                if text:
                    return text

        raise AiSuggestionEmptyResponseError("Empty suggestion response from Ollama")

    def _payload_with_empty_response_retry_budget(
        self,
        *,
        payload: dict[str, Any],
        response: dict[str, Any],
    ) -> dict[str, Any]:
        """Return payload copy with larger generation budget for empty-response retry."""
        retry_payload = dict(payload)
        options = payload.get("options")
        options_dict = dict(options) if isinstance(options, dict) else {}

        current_budget = self._int_or_none(options_dict.get("num_predict"))
        done_reason = self._to_text(response.get("done_reason")).strip().casefold()
        length_likely = done_reason in {"length", "max_tokens", "token_limit"}

        if current_budget is None:
            options_dict["num_predict"] = EMPTY_RESPONSE_RETRY_NUM_PREDICT
        elif length_likely:
            options_dict["num_predict"] = max(EMPTY_RESPONSE_RETRY_NUM_PREDICT, current_budget * 2)

        retry_payload["options"] = options_dict
        return retry_payload

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

    def _int_or_none(self, value: Any) -> int | None:
        """Return integer value when parseable, otherwise None."""
        if isinstance(value, int):
            return value
        text = self._to_text(value).strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None

    def _to_text(self, value: Any) -> str:
        """Convert arbitrary value to text."""
        if value is None:
            return ""
        return str(value)
