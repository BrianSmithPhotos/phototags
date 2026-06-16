"""Filename generation helpers for Part 5 rename workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re


INVALID_FILENAME_CHARS = set('\\/:*?"<>|')


@dataclass(slots=True)
class RenameContext:
    """Inputs required to generate a destination filename."""

    source_path: Path
    captured_at: str
    camera_model: str
    lens_model: str
    location: str
    art_filter_token: str


class RenameService:
    """Generate sanitized, collision-safe filenames from metadata."""

    def build_filename(self, context: RenameContext) -> str:
        """Build default filename pattern from source and metadata."""
        sequence = self._extract_sequence(context.source_path)
        short_date, time_str = self._date_time_parts(context.captured_at)
        location = self._sanitize_component(context.location)
        art_filter = self._sanitize_component(context.art_filter_token)
        camera = self._sanitize_component(context.camera_model) or "UnknownCamera"
        lens = self._sanitize_component(context.lens_model) or "UnknownLens"

        parts = [sequence]
        if location:
            parts.append(location)
        parts.extend([short_date, time_str])
        if art_filter:
            parts.append(art_filter)
        parts.extend([camera, lens])

        extension = context.source_path.suffix.lower() or ".jpg"
        return f"{'_'.join(parts)}{extension}"

    def ensure_unique_name(self, candidate: str, existing_names: set[str]) -> str:
        """Return unique filename by appending numeric suffix if needed."""
        if candidate not in existing_names:
            return candidate

        stem = Path(candidate).stem
        suffix = Path(candidate).suffix
        index = 1
        while True:
            next_candidate = f"{stem}_{index}{suffix}"
            if next_candidate not in existing_names:
                return next_candidate
            index += 1

    def _extract_sequence(self, source_path: Path) -> str:
        """Extract digits from source filename stem."""
        digits = "".join(ch for ch in source_path.stem if ch.isdigit())
        return digits or "0"

    def _date_time_parts(self, captured_at: str) -> tuple[str, str]:
        """Convert EXIF date text into filename date/time tokens."""
        if not captured_at:
            return "UnknownDate", "UnknownTime"

        for fmt in ("%Y:%m:%d %H:%M:%S%z", "%Y:%m:%d %H:%M:%S"):
            try:
                dt = datetime.strptime(captured_at, fmt)
                return dt.strftime("%Y%m%d"), dt.strftime("%H%M")
            except ValueError:
                continue
        return "UnknownDate", "UnknownTime"

    def _sanitize_component(self, value: str) -> str:
        """Sanitize one filename component."""
        text = value.strip()
        if not text:
            return ""

        replaced = "".join("-" if char in INVALID_FILENAME_CHARS else char for char in text)
        collapsed = re.sub(r"\s+", "-", replaced)
        collapsed = re.sub(r"-{2,}", "-", collapsed).strip("-.")
        return collapsed[:64]
