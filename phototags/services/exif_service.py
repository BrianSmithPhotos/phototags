"""EXIF read helpers backed by exiftool."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any

EXIFTOOL_READ_COMMAND = ("exiftool", "-j", "-G1", "-a", "-s")


@dataclass(slots=True)
class ExifUiData:
    """Subset of EXIF metadata mapped to current UI fields."""

    title: str
    description: str
    keywords: str
    camera: str
    camera_model: str
    lens_type: str
    lens_model: str
    aperture: str
    focal_length: str
    focus_distance: str
    captured_at: str
    art_filter_token: str


class ExifToolReadError(RuntimeError):
    """Raised when exiftool metadata read fails."""


class ExifService:
    """Read and map metadata using exiftool JSON output."""

    def read_full_metadata(self, image_path: Path) -> dict[str, Any]:
        """Read complete grouped EXIF metadata for one file.

        Args:
            image_path: File path to inspect.

        Returns:
            Full metadata dictionary from exiftool.

        Raises:
            ExifToolReadError: If exiftool fails or returns invalid JSON.
        """
        command = [*EXIFTOOL_READ_COMMAND, str(image_path)]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or "Unknown exiftool error"
            raise ExifToolReadError(message)

        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ExifToolReadError(f"Invalid JSON output: {exc}") from exc

        if not parsed or not isinstance(parsed, list):
            raise ExifToolReadError("No metadata returned by exiftool")

        first = parsed[0]
        if not isinstance(first, dict):
            raise ExifToolReadError("Unexpected metadata shape from exiftool")
        return first

    def map_for_ui(self, metadata: dict[str, Any]) -> ExifUiData:
        """Extract current UI field values from full metadata."""
        return ExifUiData(
            title=self._first_text(
                metadata,
                (
                    "XMP:Title",
                    "XMP-dc:Title",
                    "IPTC:ObjectName",
                    "IFD0:ImageDescription",
                    "EXIF:ImageDescription",
                    "QuickTime:Title",
                ),
            ),
            description=self._first_text(
                metadata,
                (
                    "XMP:Description",
                    "XMP-dc:Description",
                    "IPTC:Caption-Abstract",
                    "EXIF:UserComment",
                    "IFD0:ImageDescription",
                    "EXIF:ImageDescription",
                ),
            ),
            keywords=self._keywords_text(metadata),
            camera=self._camera_make_model_text(metadata),
            camera_model=self._first_text(
                metadata,
                (
                    "IFD0:Model",
                    "EXIF:Model",
                    "Composite:Model",
                    "MakerNotes:Model",
                ),
            ),
            lens_type=self._first_text(
                metadata,
                (
                    "Olympus:LensType",
                    "Composite:LensID",
                    "ExifIFD:LensModel",
                    "IFD0:LensModel",
                    "Olympus:LensModel",
                    "ExifIFD:LensInfo",
                ),
            ),
            lens_model=self._first_text(
                metadata,
                (
                    "ExifIFD:LensModel",
                    "Olympus:LensModel",
                    "IFD0:LensModel",
                    "Composite:LensID",
                    "ExifIFD:LensInfo",
                ),
            ),
            aperture=self._format_aperture(
                self._first_text(
                    metadata,
                    (
                        "Composite:Aperture",
                        "ExifIFD:FNumber",
                        "EXIF:FNumber",
                    ),
                )
            ),
            focal_length=self._first_text(
                metadata,
                (
                    "ExifIFD:FocalLength",
                    "EXIF:FocalLength",
                    "Composite:FocalLength",
                    "Composite:FocalLength35efl",
                ),
            ),
            focus_distance=self._first_text(
                metadata,
                (
                    "Olympus:FocusDistance",
                    "Composite:FocusDistance",
                ),
            ),
            captured_at=self._first_text(
                metadata,
                (
                    "ExifIFD:DateTimeOriginal",
                    "EXIF:DateTimeOriginal",
                    "ExifIFD:CreateDate",
                    "EXIF:CreateDate",
                    "QuickTime:CreateDate",
                ),
            ),
            art_filter_token=self._art_filter_token(metadata),
        )

    def format_full_dump(self, metadata: dict[str, Any]) -> str:
        """Return pretty JSON dump for debug viewer."""
        return json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False)

    def _first_text(self, metadata: dict[str, Any], keys: tuple[str, ...]) -> str:
        """Return first non-empty text value for candidate keys."""
        for key in keys:
            if key not in metadata:
                continue
            text = self._to_text(metadata[key]).strip()
            if text:
                return text
        return ""

    def _keywords_text(self, metadata: dict[str, Any]) -> str:
        """Normalize keywords/tags into comma-delimited text for UI editing."""
        candidates = (
            "XMP:Subject",
            "XMP-dc:Subject",
            "IPTC:Keywords",
            "XMP:TagsList",
            "Composite:Keywords",
            "Keys:Keywords",
        )
        for key in candidates:
            if key not in metadata:
                continue
            value = metadata[key]
            if isinstance(value, list):
                cleaned = [self._to_text(item).strip() for item in value if self._to_text(item).strip()]
                if cleaned:
                    return ", ".join(cleaned)
            text = self._to_text(value).strip()
            if text:
                return text
        return ""

    def _camera_make_model_text(self, metadata: dict[str, Any]) -> str:
        """Return combined camera make+model text when available."""
        make = self._first_text(
            metadata,
            (
                "IFD0:Make",
                "EXIF:Make",
            ),
        )
        model = self._first_text(
            metadata,
            (
                "IFD0:Model",
                "EXIF:Model",
                "Composite:Model",
                "MakerNotes:Model",
            ),
        )
        if make and model:
            return f"{make} {model}"
        return make or model

    def _art_filter_token(self, metadata: dict[str, Any]) -> str:
        """Return filename token for ArtFilter/stacking states."""
        art_effect = self._first_text(
            metadata,
            (
                "Olympus:ArtFilterEffect",
                "EXIF:ArtFilterEffect",
                "MakerNotes:ArtFilterEffect",
            ),
        )
        first = self._first_semicolon_text(art_effect)
        if first and first.casefold() != "off":
            return first

        picture_mode = self._first_text(
            metadata,
            (
                "Olympus:PictureMode",
                "EXIF:PictureMode",
            ),
        )
        picture_first = self._first_semicolon_text(picture_mode)
        if "profile" in picture_first.casefold():
            return picture_first

        stacked = self._first_text(
            metadata,
            (
                "Olympus:StackedImage",
                "Olympus:StackedImages",
                "EXIF:StackedImage",
            ),
        )
        stacked_first = self._first_semicolon_text(stacked)
        if stacked_first and stacked_first.casefold() != "no":
            return stacked_first

        multiple_exposure = self._first_text(
            metadata,
            (
                "Olympus:MultipleExposureMode",
                "EXIF:MultipleExposureMode",
            ),
        )
        if multiple_exposure.casefold().startswith("on"):
            return "MultipleExposure"

        return ""

    def _format_aperture(self, aperture_text: str) -> str:
        """Normalize aperture display to f/<value> format."""
        text = aperture_text.strip()
        if not text:
            return ""
        lower = text.lower()
        if lower.startswith("f/"):
            return text
        try:
            value = float(text)
            if value.is_integer():
                return f"f/{int(value)}"
            return f"f/{value:g}"
        except ValueError:
            return f"f/{text}"

    def _first_semicolon_text(self, value: str) -> str:
        """Return first segment before ';' and trim whitespace."""
        if not value:
            return ""
        return value.split(";")[0].strip()

    def _to_text(self, value: Any) -> str:
        """Convert metadata value into display text."""
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        if value is None:
            return ""
        return str(value)
