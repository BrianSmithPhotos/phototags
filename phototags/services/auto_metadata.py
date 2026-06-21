"""Deterministic auto-keyword/description rules applied at save/process time."""

from __future__ import annotations

from pathlib import Path

SOOC_JPEG_SUFFIXES = {".jpg", ".jpeg"}


def parse_keywords(text: str) -> list[str]:
    """Split comma/newline-delimited keywords into a normalized list."""
    values = [part.strip() for part in text.replace("\n", ",").split(",")]
    return [value for value in values if value]


def merge_keywords(existing: list[str], incoming: list[str]) -> list[str]:
    """Merge keyword lists preserving order and removing case-insensitive duplicates."""
    merged: list[str] = []
    seen: set[str] = set()
    for keyword in [*existing, *incoming]:
        lowered = keyword.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        merged.append(keyword)
    return merged


def sooc_token_for(image_path: Path) -> str:
    """Return the 'sooc' (straight out of camera) keyword for JPEGs, else empty."""
    return "sooc" if image_path.suffix.lower() in SOOC_JPEG_SUFFIXES else ""


def keywords_with_auto_tokens(
    keywords_text: str,
    *,
    art_filter_token: str,
    camera_token: str,
    lens_token: str,
    sooc_token: str,
) -> str:
    """Append art-filter/camera/lens/sooc tokens with case-insensitive de-duplication."""
    keywords = parse_keywords(keywords_text)
    auto_tokens = [
        art_filter_token.strip(),
        camera_token.strip(),
        lens_token.strip(),
        sooc_token.strip(),
    ]
    merged = merge_keywords(keywords, [token for token in auto_tokens if token])
    return ", ".join(merged)


def description_with_art_filter_note(description: str, art_filter_token: str) -> str:
    """Append an 'In camera effect <filter>.' note, skipping if already present."""
    token = art_filter_token.strip()
    if not token:
        return description
    note = f"In camera effect {token}."
    if note in description:
        return description
    if not description.strip():
        return note
    return f"{description} {note}"
