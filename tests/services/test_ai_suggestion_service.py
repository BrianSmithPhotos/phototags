import io
from pathlib import Path
import subprocess

import pytest
from PIL import Image

from phototags.services import ai_suggestion_service as ai_suggestion_service_module
from phototags.services.ai_provider import AiProvider, AiSuggestionEmptyResponseError, AiSuggestionError
from phototags.services.ai_suggestion_service import AiSuggestionResult, AiSuggestionService

# These methods are pure parsing/decision logic with no provider calls, so a
# placeholder provider (never invoked by the methods under test) is enough.
_SERVICE = AiSuggestionService(provider=object())


class _FakeProvider(AiProvider):
    """Records chat() calls and returns a scripted sequence of responses/exceptions."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def ensure_vision_capable(self, model: str) -> None:
        return None

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
        self.calls.append({"model": model, "image_payloads": image_payloads, "think": think})
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _make_jpeg_bytes(size: tuple[int, int] = (64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color="red").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_extract_json_object_parses_plain_json() -> None:
    payload = _SERVICE._extract_json_object('{"description": "a dog", "keywords": ["dog"]}')

    assert payload == {"description": "a dog", "keywords": ["dog"]}


def test_extract_json_object_strips_code_fence() -> None:
    content = '```json\n{"description": "a dog", "keywords": ["dog"]}\n```'

    payload = _SERVICE._extract_json_object(content)

    assert payload == {"description": "a dog", "keywords": ["dog"]}


def test_extract_json_object_extracts_braces_from_surrounding_prose() -> None:
    content = 'Sure, here you go: {"description": "a dog", "keywords": ["dog"]} Hope that helps!'

    payload = _SERVICE._extract_json_object(content)

    assert payload == {"description": "a dog", "keywords": ["dog"]}


def test_normalize_keywords_dedupes_case_insensitively_preserving_first_casing() -> None:
    normalized = _SERVICE._normalize_keywords(["Dog", "dog", "Cat"])

    assert normalized == ["Dog", "Cat"]


def test_normalize_keywords_splits_comma_separated_string() -> None:
    normalized = _SERVICE._normalize_keywords("dog, cat,  bird ")

    assert normalized == ["dog", "cat", "bird"]


def test_normalize_keywords_returns_empty_list_for_unsupported_type() -> None:
    assert _SERVICE._normalize_keywords(None) == []
    assert _SERVICE._normalize_keywords(42) == []


def test_merge_keywords_preserves_primary_order_and_drops_secondary_duplicates() -> None:
    merged = _SERVICE._merge_keywords(["dog", "park"], ["cat", "Dog", "tree"])

    assert merged == ["dog", "park", "cat", "tree"]


def test_needs_subject_crop_refinement_true_when_keyword_subject_not_in_description() -> None:
    result = AiSuggestionResult(description="A bird perched on a branch.", keywords=["snowy egret", "branch"])

    assert _SERVICE._needs_subject_crop_refinement(result) is True


def test_needs_subject_crop_refinement_false_when_description_already_names_subject() -> None:
    result = AiSuggestionResult(description="A snowy egret perched on a branch.", keywords=["snowy egret", "branch"])

    assert _SERVICE._needs_subject_crop_refinement(result) is False


def test_needs_subject_crop_refinement_false_when_no_subject_candidates() -> None:
    result = AiSuggestionResult(description="A scenic overlook at sunset.", keywords=["sunset", "overlook"])

    assert _SERVICE._needs_subject_crop_refinement(result) is False


def test_description_mentions_subject_matches_whole_word_only() -> None:
    assert _SERVICE._description_mentions_subject("A dog runs in the park.", ["dog"]) is True
    assert _SERVICE._description_mentions_subject("A dogwood tree in bloom.", ["dog"]) is False


def test_description_mentions_subject_falls_back_to_last_token_of_multiword_candidate() -> None:
    # "egret" alone should match even though the full candidate phrase is "snowy egret".
    assert _SERVICE._description_mentions_subject("An egret stands in shallow water.", ["snowy egret"]) is True


def test_suggest_for_image_returns_primary_result_without_refinement(tmp_path: Path) -> None:
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(_make_jpeg_bytes())
    provider = _FakeProvider(['{"description": "A scenic overlook.", "keywords": ["overlook", "sunset"]}'])
    service = AiSuggestionService(provider=provider)

    result = service.suggest_for_image(image_path=image_path, model="test-model")

    assert result.description == "A scenic overlook."
    assert result.keywords == ["overlook", "sunset"]
    assert result.refinement_attempted is False
    assert len(provider.calls) == 1


def test_suggest_for_image_retries_with_center_crop_after_timeout(tmp_path: Path) -> None:
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(_make_jpeg_bytes())
    provider = _FakeProvider(
        [
            ai_suggestion_service_module.AiSuggestionTimeoutError("timed out"),
            '{"description": "A scenic overlook.", "keywords": ["overlook"]}',
        ]
    )
    service = AiSuggestionService(provider=provider)

    result = service.suggest_for_image(image_path=image_path, model="test-model")

    assert result.description == "A scenic overlook."
    assert result.timeout_retry_attempted is True
    assert result.timeout_retry_succeeded is True
    assert len(provider.calls) == 2
    assert provider.calls[1]["think"] is False


def test_suggest_for_image_raises_when_retry_also_returns_empty(tmp_path: Path) -> None:
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(_make_jpeg_bytes())
    provider = _FakeProvider(
        [
            AiSuggestionEmptyResponseError("empty"),
            AiSuggestionEmptyResponseError("still empty"),
        ]
    )
    service = AiSuggestionService(provider=provider)

    with pytest.raises(AiSuggestionError, match="empty content after retry"):
        service.suggest_for_image(image_path=image_path, model="test-model")


def test_read_previewable_image_bytes_reads_jpeg_directly(tmp_path: Path) -> None:
    image_path = tmp_path / "photo.jpg"
    jpeg_bytes = _make_jpeg_bytes()
    image_path.write_bytes(jpeg_bytes)
    service = AiSuggestionService(provider=object())

    assert service._read_previewable_image_bytes(image_path) == jpeg_bytes


def test_read_previewable_image_bytes_extracts_orf_preview_via_exiftool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jpeg_bytes = _make_jpeg_bytes()
    monkeypatch.setattr(
        ai_suggestion_service_module.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(args=[], returncode=0, stdout=jpeg_bytes, stderr=b""),
    )
    service = AiSuggestionService(provider=object())

    assert service._read_previewable_image_bytes(tmp_path / "photo.orf") == jpeg_bytes


def test_read_previewable_image_bytes_raises_when_exiftool_finds_no_preview(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        ai_suggestion_service_module.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(args=[], returncode=1, stdout=b"", stderr=b"No PreviewImage"),
    )
    service = AiSuggestionService(provider=object())

    with pytest.raises(AiSuggestionError, match="No PreviewImage"):
        service._read_previewable_image_bytes(tmp_path / "photo.orf")
