import io
import json
import socket
from urllib.error import HTTPError, URLError

import pytest

from phototags.services import openrouter_provider as openrouter_provider_module
from phototags.services.ai_provider import (
    AiSuggestionEmptyResponseError,
    AiSuggestionError,
    AiSuggestionTimeoutError,
)
from phototags.services.openrouter_provider import OpenRouterProvider


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def _patch_urlopen(monkeypatch: pytest.MonkeyPatch, fake_urlopen) -> None:
    monkeypatch.setattr(openrouter_provider_module, "urlopen", fake_urlopen)


def _fake_http_error(status: int, body: dict | str) -> HTTPError:
    raw = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body.encode("utf-8")
    return HTTPError(
        url="https://openrouter.ai/api/v1/chat/completions",
        code=status,
        msg="error",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(raw),
    )


# ---------------------------------------------------------------------------
# _extract_message_content
# ---------------------------------------------------------------------------

def test_extract_message_content_reads_choices_message_content() -> None:
    provider = OpenRouterProvider()
    response = {"choices": [{"message": {"content": "A swan on a lake."}}]}

    assert provider._extract_message_content(response) == "A swan on a lake."


def test_extract_message_content_skips_non_dict_choices_entries() -> None:
    provider = OpenRouterProvider()
    response = {"choices": ["invalid", {"message": {"content": "A swan on a lake."}}]}

    assert provider._extract_message_content(response) == "A swan on a lake."


def test_extract_message_content_raises_when_choices_is_absent() -> None:
    provider = OpenRouterProvider()
    with pytest.raises(AiSuggestionEmptyResponseError):
        provider._extract_message_content({})


def test_extract_message_content_raises_when_all_choices_have_empty_content() -> None:
    provider = OpenRouterProvider()
    response = {"choices": [{"message": {"content": "  "}}]}

    with pytest.raises(AiSuggestionEmptyResponseError):
        provider._extract_message_content(response)


# ---------------------------------------------------------------------------
# _error_message_from_body
# ---------------------------------------------------------------------------

def test_error_message_from_body_extracts_error_message_field() -> None:
    provider = OpenRouterProvider()
    body = json.dumps({"error": {"message": "Invalid API key"}})

    assert provider._error_message_from_body(body) == "Invalid API key"


def test_error_message_from_body_returns_empty_for_invalid_json() -> None:
    provider = OpenRouterProvider()

    assert provider._error_message_from_body("not json") == ""


def test_error_message_from_body_returns_empty_when_error_key_absent() -> None:
    provider = OpenRouterProvider()
    body = json.dumps({"unrelated": "field"})

    assert provider._error_message_from_body(body) == ""


def test_error_message_from_body_returns_empty_when_error_is_not_a_dict() -> None:
    provider = OpenRouterProvider()
    body = json.dumps({"error": "string error"})

    assert provider._error_message_from_body(body) == ""


# ---------------------------------------------------------------------------
# _is_timeout_network_error
# ---------------------------------------------------------------------------

def test_is_timeout_network_error_true_for_timeout_error_reason() -> None:
    provider = OpenRouterProvider()
    exc = URLError(reason=TimeoutError("timed out"))

    assert provider._is_timeout_network_error(exc) is True


def test_is_timeout_network_error_true_for_socket_timeout_reason() -> None:
    provider = OpenRouterProvider()
    exc = URLError(reason=socket.timeout("timed out"))

    assert provider._is_timeout_network_error(exc) is True


def test_is_timeout_network_error_true_for_timed_out_string_reason() -> None:
    provider = OpenRouterProvider()
    exc = URLError(reason="Connection timed out")

    assert provider._is_timeout_network_error(exc) is True


def test_is_timeout_network_error_false_for_connection_refused() -> None:
    provider = OpenRouterProvider()
    exc = URLError(reason="Connection refused")

    assert provider._is_timeout_network_error(exc) is False


# ---------------------------------------------------------------------------
# _is_timeout_text
# ---------------------------------------------------------------------------

def test_is_timeout_text_true_for_timed_out() -> None:
    assert OpenRouterProvider()._is_timeout_text("request timed out") is True


def test_is_timeout_text_true_for_timeout() -> None:
    assert OpenRouterProvider()._is_timeout_text("upstream timeout") is True


def test_is_timeout_text_is_case_insensitive() -> None:
    assert OpenRouterProvider()._is_timeout_text("Timed Out") is True


def test_is_timeout_text_false_for_unrelated_error() -> None:
    assert OpenRouterProvider()._is_timeout_text("rate limit exceeded") is False


# ---------------------------------------------------------------------------
# _usage_from_response
# ---------------------------------------------------------------------------

def test_usage_from_response_extracts_all_fields() -> None:
    provider = OpenRouterProvider()
    response = {
        "usage": {
            "cost": 0.0012,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "completion_tokens_details": {"reasoning_tokens": 20},
        }
    }

    usage = provider._usage_from_response(response)

    assert usage["cost_usd"] == 0.0012
    assert usage["prompt_tokens"] == 100
    assert usage["completion_tokens"] == 50
    assert usage["reasoning_tokens"] == 20


def test_usage_from_response_returns_nones_when_usage_absent() -> None:
    provider = OpenRouterProvider()
    usage = provider._usage_from_response({})

    assert usage["cost_usd"] is None
    assert usage["prompt_tokens"] is None
    assert usage["completion_tokens"] is None
    assert usage["reasoning_tokens"] is None


def test_usage_from_response_returns_none_reasoning_when_details_absent() -> None:
    provider = OpenRouterProvider()
    response = {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    usage = provider._usage_from_response(response)

    assert usage["reasoning_tokens"] is None


# ---------------------------------------------------------------------------
# ensure_vision_capable (mocked _openrouter_models)
# ---------------------------------------------------------------------------

def _models_payload(*model_ids_with_image: str) -> dict:
    """Build a minimal /models response with image modality for the given model IDs."""
    return {
        "data": [
            {
                "id": model_id,
                "architecture": {"input_modalities": ["text", "image"]},
            }
            for model_id in model_ids_with_image
        ]
    }


def test_ensure_vision_capable_passes_for_model_with_image_modality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenRouterProvider()
    monkeypatch.setattr(provider, "_openrouter_models", lambda: _models_payload("google/gemini-2.5-flash"))
    provider.ensure_vision_capable("google/gemini-2.5-flash")  # no exception


def test_ensure_vision_capable_raises_for_model_without_image_modality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenRouterProvider()
    monkeypatch.setattr(
        provider,
        "_openrouter_models",
        lambda: {"data": [{"id": "text-only-model", "architecture": {"input_modalities": ["text"]}}]},
    )

    with pytest.raises(AiSuggestionError, match="does not accept image input"):
        provider.ensure_vision_capable("text-only-model")


def test_ensure_vision_capable_raises_when_model_not_in_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenRouterProvider()
    monkeypatch.setattr(provider, "_openrouter_models", lambda: _models_payload("other/model"))

    with pytest.raises(AiSuggestionError, match="was not found"):
        provider.ensure_vision_capable("google/gemini-2.5-flash")


def test_ensure_vision_capable_raises_immediately_for_empty_model_name() -> None:
    provider = OpenRouterProvider()
    with pytest.raises(AiSuggestionError, match="No OpenRouter model selected"):
        provider.ensure_vision_capable("")


def test_ensure_vision_capable_uses_cache_and_skips_second_models_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def _fake_models() -> dict:
        nonlocal call_count
        call_count += 1
        return _models_payload("google/gemini-2.5-flash")

    provider = OpenRouterProvider()
    monkeypatch.setattr(provider, "_openrouter_models", _fake_models)
    provider.ensure_vision_capable("google/gemini-2.5-flash")
    provider.ensure_vision_capable("google/gemini-2.5-flash")

    assert call_count == 1


def test_ensure_vision_capable_cache_raises_without_models_call_for_non_vision_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenRouterProvider()
    provider._vision_capability_cache["text-only-model"] = False

    call_count = 0

    def _fake_models() -> dict:
        nonlocal call_count
        call_count += 1
        return {"data": []}

    monkeypatch.setattr(provider, "_openrouter_models", _fake_models)

    with pytest.raises(AiSuggestionError, match="does not accept image input"):
        provider.ensure_vision_capable("text-only-model")
    assert call_count == 0


# ---------------------------------------------------------------------------
# _openrouter_chat — network paths (mocked urlopen + env var)
# ---------------------------------------------------------------------------

def test_openrouter_chat_raises_when_api_key_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    provider = OpenRouterProvider()

    with pytest.raises(AiSuggestionError, match="OPENROUTER_API_KEY is not set"):
        provider._openrouter_chat(body={})


def test_openrouter_chat_returns_parsed_response_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    payload = {"choices": [{"message": {"content": "A swan."}}]}
    _patch_urlopen(monkeypatch, lambda *a, **k: _FakeResponse(payload))
    provider = OpenRouterProvider()

    result = provider._openrouter_chat(body={})

    assert result == payload


def test_openrouter_chat_raises_error_from_http_error_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    http_err = _fake_http_error(401, {"error": {"message": "Invalid API key"}})

    def _raise(*a: object, **k: object) -> None:
        raise http_err

    _patch_urlopen(monkeypatch, _raise)
    provider = OpenRouterProvider()

    with pytest.raises(AiSuggestionError, match="Invalid API key"):
        provider._openrouter_chat(body={})


def test_openrouter_chat_raises_timeout_on_url_error_with_timeout_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def _raise(*a: object, **k: object) -> None:
        raise URLError(reason=TimeoutError("timed out"))

    _patch_urlopen(monkeypatch, _raise)
    provider = OpenRouterProvider()

    with pytest.raises(AiSuggestionTimeoutError):
        provider._openrouter_chat(body={})


def test_openrouter_chat_raises_error_on_non_timeout_url_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def _raise(*a: object, **k: object) -> None:
        raise URLError(reason="Connection refused")

    _patch_urlopen(monkeypatch, _raise)
    provider = OpenRouterProvider()

    with pytest.raises(AiSuggestionError, match="Could not reach the OpenRouter API"):
        provider._openrouter_chat(body={})


def test_openrouter_chat_raises_timeout_on_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def _raise(*a: object, **k: object) -> None:
        raise TimeoutError("timed out")

    _patch_urlopen(monkeypatch, _raise)
    provider = OpenRouterProvider()

    with pytest.raises(AiSuggestionTimeoutError):
        provider._openrouter_chat(body={})


def test_openrouter_chat_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    class _BadResponse:
        def read(self) -> bytes:
            return b"not json"

        def __enter__(self) -> "_BadResponse":
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

    _patch_urlopen(monkeypatch, lambda *a, **k: _BadResponse())
    provider = OpenRouterProvider()

    with pytest.raises(AiSuggestionError, match="Invalid JSON"):
        provider._openrouter_chat(body={})


def test_openrouter_chat_raises_error_for_error_dict_in_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    _patch_urlopen(
        monkeypatch,
        lambda *a, **k: _FakeResponse({"error": {"message": "model overloaded"}}),
    )
    provider = OpenRouterProvider()

    with pytest.raises(AiSuggestionError, match="model overloaded"):
        provider._openrouter_chat(body={})


def test_openrouter_chat_raises_timeout_when_error_message_contains_timeout_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    _patch_urlopen(
        monkeypatch,
        lambda *a, **k: _FakeResponse({"error": {"message": "upstream request timed out"}}),
    )
    provider = OpenRouterProvider()

    with pytest.raises(AiSuggestionTimeoutError):
        provider._openrouter_chat(body={})
