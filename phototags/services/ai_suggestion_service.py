"""Generate AI metadata suggestions from local Ollama models."""

from __future__ import annotations

from dataclasses import dataclass
import base64
import io
import json
import logging
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from PIL import Image


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
MAX_IMAGE_EDGE = 1600
JPEG_QUALITY = 85
FALLBACK_CROP_SCALE = 0.72
FALLBACK_MIN_DIMENSION = 900
TIMEOUT_RETRY_CENTER_CROP_SCALE = 0.50
SUBJECT_NOUN_TOKENS = {
    "animal",
    "bear",
    "bird",
    "buck",
    "butterfly",
    "cat",
    "cormorant",
    "crane",
    "deer",
    "dog",
    "duck",
    "eagle",
    "egret",
    "falcon",
    "finch",
    "flower",
    "fox",
    "frog",
    "gull",
    "hawk",
    "heron",
    "ibis",
    "iris",
    "kingfisher",
    "lily",
    "mammal",
    "moth",
    "orchid",
    "otter",
    "owl",
    "pelican",
    "plant",
    "plover",
    "poppy",
    "rabbit",
    "raven",
    "robin",
    "rose",
    "sandpiper",
    "seal",
    "sparrow",
    "squirrel",
    "swallow",
    "tern",
    "tree",
    "warbler",
    "wildlife",
}
GENERIC_SUBJECT_TERMS = {
    "animal",
    "animals",
    "avian",
    "bird",
    "birds",
    "fauna",
    "flora",
    "flower",
    "flowers",
    "nature",
    "plant",
    "plants",
    "wildlife",
}
DOMAIN_HINT_TOKENS = {
    "animal",
    "animals",
    "avian",
    "bird",
    "birds",
    "fauna",
    "flora",
    "flower",
    "flowers",
    "plant",
    "plants",
    "species",
    "wildlife",
}
LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class AiSuggestionResult:
    """AI suggestion payload for metadata editing."""

    description: str
    keywords: list[str]
    refinement_attempted: bool = False
    refinement_applied: bool = False
    timeout_retry_attempted: bool = False
    timeout_retry_succeeded: bool = False


class AiSuggestionError(RuntimeError):
    """Raised when AI suggestion generation fails."""


class AiSuggestionTimeoutError(AiSuggestionError):
    """Raised when AI suggestion request times out."""


class AiSuggestionEmptyResponseError(AiSuggestionError):
    """Raised when AI suggestion response has no usable content."""


class AiSuggestionService:
    """Request local AI suggestions from Ollama."""

    def __init__(self) -> None:
        self._vision_capability_cache: dict[str, bool] = {}

    def suggest_for_image(
        self,
        *,
        image_path: Path,
        model: str = OLLAMA_DEFAULT_MODEL,
        existing_keywords_text: str = "",
        existing_description: str = "",
        capture_context: str = "",
        location_context: str = "",
    ) -> AiSuggestionResult:
        """Generate description and keyword suggestions for one image."""
        self._ensure_model_supports_vision(model)
        source_image_bytes = self._read_previewable_image_bytes(image_path)
        prompt = self._build_primary_prompt(
            existing_keywords_text=existing_keywords_text,
            existing_description=existing_description,
            capture_context=capture_context,
            location_context=location_context,
        )
        timeout_retry_attempted = False
        timeout_retry_succeeded = False
        request_label_prefix = image_path.name
        try:
            primary = self._suggest_from_image_bytes(
                model=model,
                prompt=prompt,
                image_bytes=source_image_bytes,
                request_label=f"{request_label_prefix}:primary",
            )
        except (AiSuggestionTimeoutError, AiSuggestionEmptyResponseError) as exc:
            timeout_retry_attempted = isinstance(exc, AiSuggestionTimeoutError)
            center_crop_payload = self._center_crop_payload(
                image_bytes=source_image_bytes,
                scale=TIMEOUT_RETRY_CENTER_CROP_SCALE,
            )
            if center_crop_payload is None:
                raise
            reason_label = (
                "timed out"
                if isinstance(exc, AiSuggestionTimeoutError)
                else "returned empty content"
            )
            LOGGER.warning(
                "Ollama primary request %s for %s; retrying with %.0f%% center crop",
                reason_label,
                image_path.name,
                TIMEOUT_RETRY_CENTER_CROP_SCALE * 100,
            )
            try:
                primary = self._suggest_from_base64_payloads(
                    model=model,
                    prompt=prompt,
                    image_payloads=[center_crop_payload],
                    request_label=f"{request_label_prefix}:timeout-center-crop",
                )
            except AiSuggestionEmptyResponseError as inner_exc:
                raise AiSuggestionError(
                    "Ollama returned empty content after retry and center-crop fallback. "
                    "Try a different model, or set PHOTOTAGS_OLLAMA_MAX_PREDICT=1024."
                ) from inner_exc
            if isinstance(exc, AiSuggestionTimeoutError):
                timeout_retry_succeeded = True
        if not self._needs_subject_crop_refinement(primary):
            return self._result_with_debug_flags(
                primary,
                attempted=False,
                applied=False,
                timeout_retry_attempted=timeout_retry_attempted,
                timeout_retry_succeeded=timeout_retry_succeeded,
            )

        crop_payloads = self._subject_focus_crop_payloads(image_bytes=source_image_bytes)
        if not crop_payloads:
            return self._result_with_debug_flags(
                primary,
                attempted=True,
                applied=False,
                timeout_retry_attempted=timeout_retry_attempted,
                timeout_retry_succeeded=timeout_retry_succeeded,
            )

        refinement_prompt = self._build_crop_refinement_prompt(
            primary_result=primary,
            existing_keywords_text=existing_keywords_text,
            existing_description=existing_description,
            capture_context=capture_context,
            location_context=location_context,
        )
        try:
            refined = self._suggest_from_base64_payloads(
                model=model,
                prompt=refinement_prompt,
                image_payloads=crop_payloads,
                request_label=f"{request_label_prefix}:subject-refinement",
            )
        except AiSuggestionError:
            return self._result_with_debug_flags(
                primary,
                attempted=True,
                applied=False,
                timeout_retry_attempted=timeout_retry_attempted,
                timeout_retry_succeeded=timeout_retry_succeeded,
            )
        merged, refinement_applied = self._merge_primary_refined(primary=primary, refined=refined)
        return self._result_with_debug_flags(
            merged,
            attempted=True,
            applied=refinement_applied,
            timeout_retry_attempted=timeout_retry_attempted,
            timeout_retry_succeeded=timeout_retry_succeeded,
        )

    def _build_primary_prompt(
        self,
        *,
        existing_keywords_text: str,
        existing_description: str,
        capture_context: str,
        location_context: str,
    ) -> str:
        """Build deterministic prompt for description and keyword suggestions."""
        return (
            "Analyze the photo and produce metadata suggestions.\n"
            "Requirements:\n"
            "1) description: one concise sentence, max 30 words.\n"
            "2) keywords: 10 to 15 short keywords, lowercase strings.\n"
            "3) If birds, flowers, animals, or landmarks are visible, include likely "
            "common names and scientific names where possible.\n"
            "4) If an animal, bird, plant, or flower is visible, description must explicitly "
            "name the most "
            "specific likely subject (for example: snowy egret), not only generic terms "
            "like bird, animal, plant, or flower.\n"
            "5) If uncertain on species, use 'likely <species>' in the description rather "
            "than omitting identification.\n"
            "6) Do not include duplicates.\n"
            "7) Do not describe the image as monochrome, black-and-white, or grayscale "
            "unless you are very confident there is effectively no color information.\n"
            "8) If colors are subtle or dull, describe that as muted/low-saturation color "
            "instead of monochrome.\n"
            "9) Output only JSON in this exact shape:\n"
            '{"description":"...","keywords":["k1","k2"]}\n'
            "10) If location context is provided, use it to improve likely wildlife/plant "
            "identification and habitat plausibility.\n"
            "11) If location context strongly helps, you may include city/county/state in "
            "the description while keeping it concise.\n"
            f"Existing keywords (optional context): {existing_keywords_text or '(none)'}\n"
            f"Existing description (optional context): {existing_description or '(none)'}\n"
            f"Capture context (optional): {capture_context or '(none)'}\n"
            f"Location context (optional): {location_context or '(none)'}\n"
        )

    def _build_crop_refinement_prompt(
        self,
        *,
        primary_result: AiSuggestionResult,
        existing_keywords_text: str,
        existing_description: str,
        capture_context: str,
        location_context: str,
    ) -> str:
        """Build fallback prompt for crop-focused subject refinement."""
        return (
            "You are reviewing cropped regions from the same photo to refine subject identification.\n"
            "Prior full-image result may have missed subject specificity.\n"
            "Requirements:\n"
            "1) description: one concise sentence, max 30 words.\n"
            "2) If an animal, bird, plant, or flower is visible, description must include "
            "the most specific likely identity.\n"
            "3) If uncertain, use 'likely <species>' language instead of a generic label.\n"
            "4) keywords: 10 to 15 short keywords, lowercase strings, include scientific names "
            "where possible.\n"
            "5) Use location context to prefer locally plausible species when provided.\n"
            "6) Output only JSON in this exact shape:\n"
            '{"description":"...","keywords":["k1","k2"]}\n'
            f"Prior description: {primary_result.description}\n"
            f"Prior keywords: {', '.join(primary_result.keywords)}\n"
            f"Existing keywords (optional context): {existing_keywords_text or '(none)'}\n"
            f"Existing description (optional context): {existing_description or '(none)'}\n"
            f"Capture context (optional): {capture_context or '(none)'}\n"
            f"Location context (optional): {location_context or '(none)'}\n"
        )

    def _suggest_from_image_bytes(
        self,
        *,
        model: str,
        prompt: str,
        image_bytes: bytes,
        request_label: str = "",
    ) -> AiSuggestionResult:
        """Run one suggestion request from raw image bytes."""
        image_payload = self._to_image_base64(image_bytes=image_bytes)
        return self._suggest_from_base64_payloads(
            model=model,
            prompt=prompt,
            image_payloads=[image_payload],
            request_label=request_label,
        )

    def _suggest_from_base64_payloads(
        self,
        *,
        model: str,
        prompt: str,
        image_payloads: list[str],
        request_label: str = "",
    ) -> AiSuggestionResult:
        """Run one suggestion request from prepared base64 image payloads."""
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a photography metadata assistant. "
                        "Return only strict JSON with keys description and keywords."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                    "images": image_payloads,
                },
            ],
            "options": {
                "temperature": 0.2,
            },
        }
        if OLLAMA_MAX_PREDICT is not None:
            payload["options"]["num_predict"] = OLLAMA_MAX_PREDICT
        if OLLAMA_KEEP_ALIVE:
            payload["keep_alive"] = OLLAMA_KEEP_ALIVE

        response = self._ollama_chat(payload=payload, request_label=request_label)
        try:
            content = self._extract_message_content(response)
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
            content = self._extract_message_content(retry_response)
        return self._parse_result(content)

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

    def _ensure_model_supports_vision(self, model: str) -> None:
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

    def _parse_result(self, content: str) -> AiSuggestionResult:
        """Parse JSON result from model response text."""
        payload = self._extract_json_object(content)

        description = self._to_text(payload.get("description")).strip()
        if not description:
            raise AiSuggestionError("AI response did not include a description")

        keywords = self._normalize_keywords(payload.get("keywords"))
        if not keywords:
            raise AiSuggestionError("AI response did not include keywords")

        return AiSuggestionResult(description=description, keywords=keywords)

    def _extract_json_object(self, content: str) -> dict[str, Any]:
        """Decode JSON object, including code-fenced model responses."""
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise AiSuggestionError("AI response did not contain valid JSON")

        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise AiSuggestionError("AI JSON payload could not be parsed") from exc
        if not isinstance(parsed, dict):
            raise AiSuggestionError("AI JSON payload is not an object")
        return parsed

    def _normalize_keywords(self, raw_keywords: Any) -> list[str]:
        """Normalize AI keywords into deduplicated list."""
        if isinstance(raw_keywords, str):
            values = [part.strip() for part in raw_keywords.replace("\n", ",").split(",")]
        elif isinstance(raw_keywords, list):
            values = [self._to_text(item).strip() for item in raw_keywords]
        else:
            values = []

        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = value.strip().strip(",")
            if not cleaned:
                continue
            lowered = cleaned.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(cleaned)
        return normalized

    def _needs_subject_crop_refinement(self, result: AiSuggestionResult) -> bool:
        """Return True when keyword subjects are not represented in description."""
        subject_candidates = self._subject_candidates_from_keywords(result.keywords)
        if not subject_candidates:
            return False
        return not self._description_mentions_subject(result.description, subject_candidates)

    def _subject_candidates_from_keywords(self, keywords: list[str]) -> list[str]:
        """Extract likely subject-identification keyword candidates."""
        normalized_keywords = [self._normalized_phrase(keyword) for keyword in keywords]
        domain_hint_present = any(
            any(token in DOMAIN_HINT_TOKENS for token in keyword.split())
            for keyword in normalized_keywords
            if keyword
        )
        candidates: list[str] = []
        seen: set[str] = set()
        for normalized in normalized_keywords:
            if not normalized or normalized in GENERIC_SUBJECT_TERMS:
                continue
            tokens = normalized.split()
            is_scientific = len(tokens) == 2 and all(token.isalpha() for token in tokens)
            last_token = tokens[-1] if tokens else ""
            has_subject_noun = last_token in SUBJECT_NOUN_TOKENS or normalized in SUBJECT_NOUN_TOKENS
            if is_scientific and not domain_hint_present:
                is_scientific = False
            if not is_scientific and not has_subject_noun:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            candidates.append(normalized)
        return candidates

    def _description_mentions_subject(self, description: str, candidates: list[str]) -> bool:
        """Return True when description references one of candidate subjects."""
        text = self._normalized_phrase(description)
        if not text:
            return False
        for candidate in candidates:
            if self._contains_phrase(text, candidate):
                return True
            tokens = candidate.split()
            if len(tokens) > 1 and tokens[-1] in SUBJECT_NOUN_TOKENS:
                if self._contains_phrase(text, tokens[-1]):
                    return True
        return False

    def _contains_phrase(self, text: str, phrase: str) -> bool:
        """Check phrase containment using word-boundary matching."""
        if not phrase:
            return False
        pattern = r"\b" + re.escape(phrase) + r"\b"
        return re.search(pattern, text) is not None

    def _merge_primary_refined(
        self,
        *,
        primary: AiSuggestionResult,
        refined: AiSuggestionResult,
    ) -> tuple[AiSuggestionResult, bool]:
        """Merge first-pass and crop-refined suggestion into one output."""
        primary_subjects = self._subject_candidates_from_keywords(primary.keywords)
        refined_subjects = self._subject_candidates_from_keywords(refined.keywords)
        combined_subjects = self._merge_keywords(primary_subjects, refined_subjects)
        description = primary.description
        description_replaced = False
        if combined_subjects and self._description_mentions_subject(refined.description, combined_subjects):
            description = refined.description
            description_replaced = True
        keywords = self._merge_keywords(primary.keywords, refined.keywords)
        keywords_changed = [item.casefold() for item in keywords] != [item.casefold() for item in primary.keywords]
        merged = AiSuggestionResult(description=description, keywords=keywords)
        return merged, (description_replaced or keywords_changed)

    def _result_with_debug_flags(
        self,
        result: AiSuggestionResult,
        *,
        attempted: bool,
        applied: bool,
        timeout_retry_attempted: bool,
        timeout_retry_succeeded: bool,
    ) -> AiSuggestionResult:
        """Copy suggestion result with debug flags."""
        return AiSuggestionResult(
            description=result.description,
            keywords=list(result.keywords),
            refinement_attempted=attempted,
            refinement_applied=applied,
            timeout_retry_attempted=timeout_retry_attempted,
            timeout_retry_succeeded=timeout_retry_succeeded,
        )

    def _merge_keywords(self, primary: list[str], secondary: list[str]) -> list[str]:
        """Merge keyword lists preserving order and removing duplicates."""
        merged: list[str] = []
        seen: set[str] = set()
        for keyword in [*primary, *secondary]:
            cleaned = keyword.strip()
            if not cleaned:
                continue
            lowered = cleaned.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            merged.append(cleaned)
        return merged

    def _image_base64(self, image_path: Path) -> str:
        """Load a viewable image payload for Ollama vision inference."""
        image_bytes = self._read_previewable_image_bytes(image_path)
        return self._to_image_base64(image_bytes=image_bytes)

    def _to_image_base64(self, *, image_bytes: bytes) -> str:
        """Encode bytes as a compact model-ready base64 JPEG."""
        optimized = self._to_web_jpeg(image_bytes=image_bytes)
        return base64.b64encode(optimized).decode("ascii")

    def _subject_focus_crop_payloads(self, *, image_bytes: bytes) -> list[str]:
        """Build deterministic crop payloads for fallback subject refinement."""
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                rgb = img.convert("RGB")
                width, height = rgb.size
                if min(width, height) < FALLBACK_MIN_DIMENSION:
                    return []

                crop_width = max(1, int(width * FALLBACK_CROP_SCALE))
                crop_height = max(1, int(height * FALLBACK_CROP_SCALE))
                center_left = max(0, (width - crop_width) // 2)
                center_top = max(0, (height - crop_height) // 2)
                max_left = max(0, width - crop_width)
                max_top = max(0, height - crop_height)

                anchors = [
                    (center_left, center_top),
                    (0, center_top),
                    (max_left, center_top),
                    (center_left, 0),
                    (center_left, max_top),
                ]

                payloads: list[str] = []
                seen_boxes: set[tuple[int, int, int, int]] = set()
                for left, top in anchors:
                    box = (
                        int(max(0, min(left, max_left))),
                        int(max(0, min(top, max_top))),
                        int(max(0, min(left, max_left))) + crop_width,
                        int(max(0, min(top, max_top))) + crop_height,
                    )
                    if box in seen_boxes:
                        continue
                    seen_boxes.add(box)
                    crop = rgb.crop(box)
                    payloads.append(self._to_image_base64(image_bytes=self._pil_to_jpeg_bytes(crop)))
                return payloads
        except OSError:
            return []

    def _center_crop_payload(self, *, image_bytes: bytes, scale: float) -> str | None:
        """Build a single center-crop payload for timeout retries."""
        bounded_scale = max(0.1, min(scale, 1.0))
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                rgb = img.convert("RGB")
                width, height = rgb.size
                if width <= 1 or height <= 1:
                    return None
                crop_width = max(1, int(width * bounded_scale))
                crop_height = max(1, int(height * bounded_scale))
                if crop_width >= width and crop_height >= height:
                    return None
                left = max(0, (width - crop_width) // 2)
                top = max(0, (height - crop_height) // 2)
                crop = rgb.crop((left, top, left + crop_width, top + crop_height))
                return self._to_image_base64(image_bytes=self._pil_to_jpeg_bytes(crop))
        except OSError:
            return None

    def _pil_to_jpeg_bytes(self, image: Image.Image) -> bytes:
        """Encode a PIL image to JPEG bytes without additional resizing."""
        output = io.BytesIO()
        image.save(
            output,
            format="JPEG",
            quality=JPEG_QUALITY,
            optimize=True,
        )
        return output.getvalue()

    def _read_previewable_image_bytes(self, image_path: Path) -> bytes:
        """Read source image or extract preview image from RAW."""
        if image_path.suffix.lower() in {".jpg", ".jpeg"}:
            return image_path.read_bytes()

        result = subprocess.run(
            ["exiftool", "-b", "-PreviewImage", str(image_path)],
            capture_output=True,
            check=False,
            timeout=12,
        )
        if result.returncode != 0 or not result.stdout:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            raise AiSuggestionError(
                message or f"Unable to extract preview image from {image_path.name}"
            )
        return result.stdout

    def _to_web_jpeg(self, *, image_bytes: bytes) -> bytes:
        """Resize/re-encode image to compact JPEG payload for model inference."""
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                converted = img.convert("RGB")
                converted.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
                output = io.BytesIO()
                converted.save(
                    output,
                    format="JPEG",
                    quality=JPEG_QUALITY,
                    optimize=True,
                )
                return output.getvalue()
        except OSError as exc:
            raise AiSuggestionError("Unable to decode image for AI suggestions") from exc

    def _normalized_phrase(self, value: str) -> str:
        """Normalize text for lightweight comparison checks."""
        lowered = value.casefold()
        cleaned = re.sub(r"[^a-z0-9 ]+", " ", lowered)
        return re.sub(r"\s+", " ", cleaned).strip()

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
