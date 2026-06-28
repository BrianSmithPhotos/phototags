import io
import json
import socket
from urllib.error import URLError

import pytest

from phototags.services import ollama_provider as ollama_provider_module
from phototags.services.ai_provider import (
    AiSuggestionEmptyResponseError,
    AiSuggestionError,
    AiSuggestionTimeoutError,
)
from phototags.services.ollama_provider import OllamaProvider


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
    monkeypatch.setattr(ollama_provider_module, "urlopen", fake_urlopen)


# ---------------------------------------------------------------------------
# _extract_message_content — fallback chain
# ---------------------------------------------------------------------------

def test_extract_message_content_reads_message_dict_content() -> None:
    provider = OllamaProvider()
    response = {"message": {"content": "A swan on a lake."}}

    assert provider._extract_message_content(response) == "A swan on a lake."


def test_extract_message_content_reads_message_string() -> None:
    provider = OllamaProvider()
    response = {"message": "A swan on a lake."}

    assert provider._extract_message_content(response) == "A swan on a lake."


def test_extract_message_content_falls_back_to_response_key() -> None:
    provider = OllamaProvider()
    response = {"response": "A swan on a lake."}

    assert provider._extract_message_content(response) == "A swan on a lake."


def test_extract_message_content_falls_back_to_output_key() -> None:
    provider = OllamaProvider()
    response = {"output": "A swan on a lake."}

    assert provider._extract_message_content(response) == "A swan on a lake."


def test_extract_message_content_falls_back_to_choices_message_content() -> None:
    provider = OllamaProvider()
    response = {"choices": [{"message": {"content": "A swan on a lake."}}]}

    assert provider._extract_message_content(response) == "A swan on a lake."


def test_extract_message_content_falls_back_to_choices_text() -> None:
    provider = OllamaProvider()
    response = {"choices": [{"text": "A swan on a lake."}]}

    assert provider._extract_message_content(response) == "A swan on a lake."


def test_extract_message_content_skips_empty_message_content_and_falls_back() -> None:
    provider = OllamaProvider()
    # Empty message content should not count; fall through to response key.
    response = {"message": {"content": "  "}, "response": "A swan on a lake."}

    assert provider._extract_message_content(response) == "A swan on a lake."


def test_extract_message_content_raises_when_all_paths_are_empty() -> None:
    provider = OllamaProvider()
    with pytest.raises(AiSuggestionEmptyResponseError):
        provider._extract_message_content({})


# ---------------------------------------------------------------------------
# _payload_with_empty_response_retry_budget
# ---------------------------------------------------------------------------

def test_retry_budget_sets_num_predict_when_none_in_options() -> None:
    provider = OllamaProvider()
    payload = {"options": {}}
    retry = provider._payload_with_empty_response_retry_budget(payload=payload, response={})

    assert retry["options"]["num_predict"] == 1024


def test_retry_budget_doubles_existing_budget_when_truncated_by_length() -> None:
    provider = OllamaProvider()
    payload = {"options": {"num_predict": 600}}
    response = {"done_reason": "length"}

    retry = provider._payload_with_empty_response_retry_budget(payload=payload, response=response)

    assert retry["options"]["num_predict"] == 1200  # 600 * 2


def test_retry_budget_uses_floor_of_1024_when_doubled_budget_is_smaller() -> None:
    provider = OllamaProvider()
    payload = {"options": {"num_predict": 256}}
    response = {"done_reason": "length"}

    retry = provider._payload_with_empty_response_retry_budget(payload=payload, response=response)

    assert retry["options"]["num_predict"] == 1024  # max(1024, 256*2=512) → 1024


def test_retry_budget_does_not_change_budget_when_not_truncated() -> None:
    provider = OllamaProvider()
    payload = {"options": {"num_predict": 2048}}
    response = {"done_reason": "stop"}

    retry = provider._payload_with_empty_response_retry_budget(payload=payload, response=response)

    # Not truncated, budget exists → no change.
    assert retry["options"]["num_predict"] == 2048


def test_retry_budget_creates_options_dict_when_absent() -> None:
    provider = OllamaProvider()
    payload: dict = {}
    retry = provider._payload_with_empty_response_retry_budget(payload=payload, response={})

    assert retry["options"]["num_predict"] == 1024


# ---------------------------------------------------------------------------
# _is_timeout_network_error
# ---------------------------------------------------------------------------

def test_is_timeout_network_error_true_for_timeout_error_reason() -> None:
    provider = OllamaProvider()
    exc = URLError(reason=TimeoutError("timed out"))

    assert provider._is_timeout_network_error(exc) is True


def test_is_timeout_network_error_true_for_socket_timeout_reason() -> None:
    provider = OllamaProvider()
    exc = URLError(reason=socket.timeout("timed out"))

    assert provider._is_timeout_network_error(exc) is True


def test_is_timeout_network_error_true_for_timed_out_string_reason() -> None:
    provider = OllamaProvider()
    exc = URLError(reason="Connection timed out")

    assert provider._is_timeout_network_error(exc) is True


def test_is_timeout_network_error_false_for_connection_refused() -> None:
    provider = OllamaProvider()
    exc = URLError(reason="Connection refused")

    assert provider._is_timeout_network_error(exc) is False


# ---------------------------------------------------------------------------
# _is_timeout_text
# ---------------------------------------------------------------------------

def test_is_timeout_text_true_for_timed_out() -> None:
    assert OllamaProvider()._is_timeout_text("request timed out") is True


def test_is_timeout_text_true_for_timeout() -> None:
    assert OllamaProvider()._is_timeout_text("context deadline exceeded (timeout)") is True


def test_is_timeout_text_is_case_insensitive() -> None:
    assert OllamaProvider()._is_timeout_text("Timed Out") is True


def test_is_timeout_text_false_for_unrelated_error() -> None:
    assert OllamaProvider()._is_timeout_text("model not found") is False


# ---------------------------------------------------------------------------
# ensure_vision_capable (mocked _ollama_tags)
# ---------------------------------------------------------------------------

def test_ensure_vision_capable_passes_for_model_with_vision_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OllamaProvider()
    monkeypatch.setattr(
        provider,
        "_ollama_tags",
        lambda: {"models": [{"name": "mymodel", "capabilities": ["vision", "tools"]}]},
    )
    provider.ensure_vision_capable("mymodel")  # no exception


def test_ensure_vision_capable_raises_for_model_without_vision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OllamaProvider()
    monkeypatch.setattr(
        provider,
        "_ollama_tags",
        lambda: {"models": [{"name": "mymodel", "capabilities": ["tools"]}]},
    )
    with pytest.raises(AiSuggestionError, match="does not support vision"):
        provider.ensure_vision_capable("mymodel")


def test_ensure_vision_capable_raises_when_model_not_in_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OllamaProvider()
    monkeypatch.setattr(
        provider,
        "_ollama_tags",
        lambda: {"models": [{"name": "other-model", "capabilities": ["vision"]}]},
    )
    with pytest.raises(AiSuggestionError, match="was not found"):
        provider.ensure_vision_capable("mymodel")


def test_ensure_vision_capable_raises_immediately_for_empty_model_name() -> None:
    provider = OllamaProvider()
    with pytest.raises(AiSuggestionError, match="No Ollama model selected"):
        provider.ensure_vision_capable("")


def test_ensure_vision_capable_uses_cache_and_skips_second_tags_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def _fake_tags() -> dict:
        nonlocal call_count
        call_count += 1
        return {"models": [{"name": "mymodel", "capabilities": ["vision"]}]}

    provider = OllamaProvider()
    monkeypatch.setattr(provider, "_ollama_tags", _fake_tags)
    provider.ensure_vision_capable("mymodel")
    provider.ensure_vision_capable("mymodel")

    assert call_count == 1


def test_ensure_vision_capable_cache_raises_without_tags_call_when_model_has_no_vision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OllamaProvider()
    # Prime the cache with False (no vision).
    provider._vision_capability_cache["mymodel"] = False

    call_count = 0

    def _fake_tags() -> dict:
        nonlocal call_count
        call_count += 1
        return {"models": []}

    monkeypatch.setattr(provider, "_ollama_tags", _fake_tags)

    with pytest.raises(AiSuggestionError, match="does not support vision"):
        provider.ensure_vision_capable("mymodel")
    assert call_count == 0


# ---------------------------------------------------------------------------
# chat — empty-response retry logic (mocked _ollama_chat)
# ---------------------------------------------------------------------------

def _make_ollama_response(content: str = "", done_reason: str = "stop") -> dict:
    return {"message": {"content": content}, "done_reason": done_reason, "eval_count": 10, "prompt_eval_count": 5}


def test_chat_returns_content_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OllamaProvider()
    response = _make_ollama_response("A swan on a lake.")
    monkeypatch.setattr(provider, "_ollama_chat", lambda *, payload, request_label="": response)

    result = provider.chat(
        model="mymodel",
        system_prompt="",
        user_prompt="",
        image_payloads=[],
    )

    assert result == "A swan on a lake."


def test_chat_retries_on_empty_content_and_returns_retry_result(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OllamaProvider()
    responses = [
        _make_ollama_response("", done_reason="length"),
        _make_ollama_response("Retry result."),
    ]

    def _fake_chat(*, payload: dict, request_label: str = "") -> dict:
        return responses.pop(0)

    monkeypatch.setattr(provider, "_ollama_chat", _fake_chat)

    result = provider.chat(
        model="mymodel",
        system_prompt="",
        user_prompt="",
        image_payloads=[],
    )

    assert result == "Retry result."


def test_chat_raises_when_retry_also_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OllamaProvider()
    responses = [
        _make_ollama_response("", done_reason="length"),
        _make_ollama_response("", done_reason="length"),
    ]

    def _fake_chat(*, payload: dict, request_label: str = "") -> dict:
        return responses.pop(0)

    monkeypatch.setattr(provider, "_ollama_chat", _fake_chat)

    with pytest.raises(AiSuggestionEmptyResponseError):
        provider.chat(
            model="mymodel",
            system_prompt="",
            user_prompt="",
            image_payloads=[],
        )


def test_chat_populates_last_usage_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OllamaProvider()
    response = {"message": {"content": "A photo."}, "prompt_eval_count": 42, "eval_count": 18, "total_duration": 999}
    monkeypatch.setattr(provider, "_ollama_chat", lambda *, payload, request_label="": response)

    provider.chat(model="mymodel", system_prompt="", user_prompt="", image_payloads=[])

    assert provider.last_usage == {
        "cost_usd": 0.0,
        "prompt_tokens": 42,
        "completion_tokens": 18,
        "total_duration_ns": 999,
    }


# ---------------------------------------------------------------------------
# _ollama_chat — network paths (mocked urlopen)
# ---------------------------------------------------------------------------

def test_ollama_chat_returns_parsed_response_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OllamaProvider()
    payload = {"message": {"content": "A swan."}}
    _patch_urlopen(monkeypatch, lambda *a, **k: _FakeResponse(payload))

    result = provider._ollama_chat(payload={})

    assert result == payload


def test_ollama_chat_raises_timeout_on_url_error_with_timeout_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OllamaProvider()

    def _raise(*a: object, **k: object) -> None:
        raise URLError(reason=TimeoutError("timed out"))

    _patch_urlopen(monkeypatch, _raise)

    with pytest.raises(AiSuggestionTimeoutError):
        provider._ollama_chat(payload={})


def test_ollama_chat_raises_error_on_non_timeout_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OllamaProvider()

    def _raise(*a: object, **k: object) -> None:
        raise URLError(reason="Connection refused")

    _patch_urlopen(monkeypatch, _raise)

    with pytest.raises(AiSuggestionError, match="Could not reach Ollama"):
        provider._ollama_chat(payload={})


def test_ollama_chat_raises_timeout_on_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OllamaProvider()

    def _raise(*a: object, **k: object) -> None:
        raise TimeoutError("timed out")

    _patch_urlopen(monkeypatch, _raise)

    with pytest.raises(AiSuggestionTimeoutError):
        provider._ollama_chat(payload={})


def test_ollama_chat_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OllamaProvider()

    class _BadResponse:
        def read(self) -> bytes:
            return b"not json"

        def __enter__(self) -> "_BadResponse":
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

    _patch_urlopen(monkeypatch, lambda *a, **k: _BadResponse())

    with pytest.raises(AiSuggestionError, match="Invalid JSON"):
        provider._ollama_chat(payload={})


def test_ollama_chat_raises_on_error_field_in_response(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OllamaProvider()
    _patch_urlopen(monkeypatch, lambda *a, **k: _FakeResponse({"error": "model not found"}))

    with pytest.raises(AiSuggestionError, match="model not found"):
        provider._ollama_chat(payload={})


def test_ollama_chat_raises_timeout_when_error_field_contains_timeout_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OllamaProvider()
    _patch_urlopen(monkeypatch, lambda *a, **k: _FakeResponse({"error": "context deadline exceeded (timed out)"}))

    with pytest.raises(AiSuggestionTimeoutError):
        provider._ollama_chat(payload={})
