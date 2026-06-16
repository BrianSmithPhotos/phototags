"""Generate AI metadata suggestions from local Ollama models."""

from __future__ import annotations

from dataclasses import dataclass
import base64
import io
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from PIL import Image

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_DEFAULT_MODEL = os.getenv("PHOTOTAGS_OLLAMA_MODEL", "llava")
OLLAMA_TIMEOUT_SECONDS = 90
MAX_IMAGE_EDGE = 1600
JPEG_QUALITY = 85


@dataclass(slots=True)
class AiSuggestionResult:
    """AI suggestion payload for metadata editing."""

    description: str
    keywords: list[str]


class AiSuggestionError(RuntimeError):
    """Raised when AI suggestion generation fails."""


class AiSuggestionService:
    """Request local AI suggestions from Ollama."""

    def suggest_for_image(
        self,
        *,
        image_path: Path,
        model: str = OLLAMA_DEFAULT_MODEL,
        existing_keywords_text: str = "",
        existing_description: str = "",
        capture_context: str = "",
    ) -> AiSuggestionResult:
        """Generate description and keyword suggestions for one image."""
        image_b64 = self._image_base64(image_path)
        prompt = self._build_prompt(
            existing_keywords_text=existing_keywords_text,
            existing_description=existing_description,
            capture_context=capture_context,
        )
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
                    "images": [image_b64],
                },
            ],
            "options": {
                "temperature": 0.2,
            },
        }

        response = self._ollama_chat(payload=payload)
        content = self._extract_message_content(response)
        return self._parse_result(content)

    def _build_prompt(
        self,
        *,
        existing_keywords_text: str,
        existing_description: str,
        capture_context: str,
    ) -> str:
        """Build deterministic prompt for description and keyword suggestions."""
        return (
            "Analyze the photo and produce metadata suggestions.\n"
            "Requirements:\n"
            "1) description: one concise sentence, max 30 words.\n"
            "2) keywords: 10 to 15 short keywords, lowercase strings.\n"
            "3) If birds, flowers, animals, or landmarks are visible, include likely "
            "common names and scientific names where possible.\n"
            "4) Do not include duplicates.\n"
            "5) Output only JSON in this exact shape:\n"
            '{"description":"...","keywords":["k1","k2"]}\n'
            f"Existing keywords (optional context): {existing_keywords_text or '(none)'}\n"
            f"Existing description (optional context): {existing_description or '(none)'}\n"
            f"Capture context (optional): {capture_context or '(none)'}\n"
        )

    def _ollama_chat(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute one non-streaming chat request against local Ollama."""
        data = json.dumps(payload).encode("utf-8")
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
            raise AiSuggestionError(
                "Could not reach Ollama at http://127.0.0.1:11434. "
                "Ensure `ollama serve` is running."
            ) from exc
        except TimeoutError as exc:
            raise AiSuggestionError("Ollama request timed out") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AiSuggestionError("Invalid JSON response from Ollama") from exc

        error_text = self._to_text(parsed.get("error"))
        if error_text:
            raise AiSuggestionError(error_text)
        return parsed

    def _extract_message_content(self, response: dict[str, Any]) -> str:
        """Extract assistant content from Ollama chat response."""
        message = response.get("message")
        if not isinstance(message, dict):
            raise AiSuggestionError("Missing `message` payload from Ollama")
        content = self._to_text(message.get("content")).strip()
        if not content:
            raise AiSuggestionError("Empty suggestion response from Ollama")
        return content

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

    def _image_base64(self, image_path: Path) -> str:
        """Load a viewable image payload for Ollama vision inference."""
        image_bytes = self._read_previewable_image_bytes(image_path)
        optimized = self._to_web_jpeg(image_bytes=image_bytes)
        return base64.b64encode(optimized).decode("ascii")

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

    def _to_text(self, value: Any) -> str:
        """Convert arbitrary value to text."""
        if value is None:
            return ""
        return str(value)
