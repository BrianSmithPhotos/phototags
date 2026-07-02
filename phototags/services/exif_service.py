"""EXIF read helpers backed by exiftool."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from phototags.services.exiftool_path import EXIFTOOL_PATH

EXIFTOOL_READ_COMMAND = (EXIFTOOL_PATH, "-j", "-G1", "-a", "-s")
EXIFTOOL_READ_CHUNK_SIZE = 50


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
    shutter_speed: str
    focal_length: str
    focus_distance: str
    captured_at: str
    captured_at_display: str
    iso: str
    gps_latitude: str
    gps_longitude: str
    gps_altitude: str
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

    def read_full_metadata_for_paths(
        self, image_paths: list[Path]
    ) -> dict[Path, dict[str, Any] | ExifToolReadError]:
        """Read complete grouped EXIF metadata for many files, batching exiftool calls.

        exiftool's per-invocation cost is dominated by process/Perl-interpreter
        startup, not by the actual file read, so reading N files one at a time is
        roughly N times slower than reading them in one call (~15x measured on a
        20-file sample). Requests are chunked (`EXIFTOOL_READ_CHUNK_SIZE`) so one
        exiftool invocation's runtime/output stays bounded for large sessions.

        Each path maps to either its metadata dict or the `ExifToolReadError` that
        occurred reading it, so one unreadable or slow file in a chunk falls back
        to an individual `read_full_metadata` retry instead of failing every other
        file batched alongside it.
        """
        metadata_by_path: dict[Path, dict[str, Any] | ExifToolReadError] = {}
        for start in range(0, len(image_paths), EXIFTOOL_READ_CHUNK_SIZE):
            chunk = image_paths[start : start + EXIFTOOL_READ_CHUNK_SIZE]
            chunk_metadata = self._read_chunk(chunk)
            for image_path in chunk:
                match = chunk_metadata.get(str(image_path))
                if match is not None:
                    metadata_by_path[image_path] = match
                    continue
                try:
                    metadata_by_path[image_path] = self.read_full_metadata(image_path)
                except ExifToolReadError as exc:
                    metadata_by_path[image_path] = exc
        return metadata_by_path

    def _read_chunk(self, chunk: list[Path]) -> dict[str, dict[str, Any]]:
        """Best-effort batched read for one chunk, keyed by exiftool's SourceFile.

        Any path missing from the returned dict (nonzero exit, invalid JSON, or a
        timeout) is retried individually by the caller, so this never raises.
        """
        command = [*EXIFTOOL_READ_COMMAND, *[str(path) for path in chunk]]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=8 * len(chunk),
            )
        except subprocess.TimeoutExpired:
            return {}

        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, list):
            return {}

        by_source: dict[str, dict[str, Any]] = {}
        for entry in parsed:
            if isinstance(entry, dict) and isinstance(entry.get("SourceFile"), str):
                by_source[entry["SourceFile"]] = entry
        return by_source

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
            shutter_speed=self._first_text(
                metadata,
                (
                    "Composite:ShutterSpeed",
                    "ExifIFD:ExposureTime",
                    "EXIF:ExposureTime",
                ),
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
            captured_at_display=self._format_captured_at_display(
                self._first_text(
                    metadata,
                    (
                        "ExifIFD:DateTimeOriginal",
                        "EXIF:DateTimeOriginal",
                        "ExifIFD:CreateDate",
                        "EXIF:CreateDate",
                        "QuickTime:CreateDate",
                    ),
                )
            ),
            iso=self._first_text(
                metadata,
                (
                    "ExifIFD:ISO",
                    "EXIF:ISO",
                    "MakerNotes:ISO",
                    "Composite:ISO",
                ),
            ),
            gps_latitude=self._gps_coordinate_text(
                metadata=metadata,
                coordinate_keys=(
                    "Composite:GPSLatitude",
                    "GPS:GPSLatitude",
                    "EXIF:GPSLatitude",
                ),
                ref_keys=(
                    "GPS:GPSLatitudeRef",
                    "EXIF:GPSLatitudeRef",
                    "Composite:GPSLatitudeRef",
                ),
                is_latitude=True,
            ),
            gps_longitude=self._gps_coordinate_text(
                metadata=metadata,
                coordinate_keys=(
                    "Composite:GPSLongitude",
                    "GPS:GPSLongitude",
                    "EXIF:GPSLongitude",
                ),
                ref_keys=(
                    "GPS:GPSLongitudeRef",
                    "EXIF:GPSLongitudeRef",
                    "Composite:GPSLongitudeRef",
                ),
                is_latitude=False,
            ),
            gps_altitude=self._gps_altitude_text(metadata),
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

    def _gps_coordinate_text(
        self,
        *,
        metadata: dict[str, Any],
        coordinate_keys: tuple[str, ...],
        ref_keys: tuple[str, ...],
        is_latitude: bool,
    ) -> str:
        """Return decimal GPS coordinate text for UI editing/saving."""
        coordinate_text = self._first_text(metadata, coordinate_keys)
        if not coordinate_text:
            return ""
        ref_text = self._first_text(metadata, ref_keys)

        try:
            value = float(coordinate_text)
            return f"{value:.7f}"
        except ValueError:
            pass

        parsed = self._parse_dms_coordinate(
            coordinate_text=coordinate_text,
            ref_text=ref_text,
            is_latitude=is_latitude,
        )
        if parsed is None:
            return coordinate_text
        return f"{parsed:.7f}"

    def _parse_dms_coordinate(
        self,
        *,
        coordinate_text: str,
        ref_text: str,
        is_latitude: bool,
    ) -> float | None:
        """Parse DMS GPS text into signed decimal degrees."""
        pattern = (
            r"^\s*([+-]?\d+(?:\.\d+)?)\s*deg(?:rees?)?\s*"
            r"(\d+(?:\.\d+)?)?'\s*"
            r"(\d+(?:\.\d+)?)?\"?\s*([NSEW])?\s*$"
        )
        match = re.match(pattern, coordinate_text, flags=re.IGNORECASE)
        if match is None:
            decimal_match = re.match(
                r"^\s*([+-]?\d+(?:\.\d+)?)\s*([NSEW])?\s*$",
                coordinate_text,
                flags=re.IGNORECASE,
            )
            if decimal_match is None:
                return None
            degrees = float(decimal_match.group(1))
            minutes = 0.0
            seconds = 0.0
            suffix = (decimal_match.group(2) or "").upper()
        else:
            degrees = float(match.group(1))
            minutes = float(match.group(2)) if match.group(2) else 0.0
            seconds = float(match.group(3)) if match.group(3) else 0.0
            suffix = (match.group(4) or "").upper()
        hemisphere = suffix or ref_text.strip().upper()

        absolute = abs(degrees) + (minutes / 60.0) + (seconds / 3600.0)
        signed = -absolute if degrees < 0 else absolute

        if hemisphere:
            if hemisphere in {"S", "W"}:
                signed = -abs(absolute)
            elif hemisphere in {"N", "E"}:
                signed = abs(absolute)

        if is_latitude and (signed < -90.0 or signed > 90.0):
            return None
        if not is_latitude and (signed < -180.0 or signed > 180.0):
            return None
        return signed

    def _gps_altitude_text(self, metadata: dict[str, Any]) -> str:
        """Return numeric GPS altitude text when available."""
        altitude_text = self._first_text(
            metadata,
            (
                "Composite:GPSAltitude",
                "GPS:GPSAltitude",
                "EXIF:GPSAltitude",
            ),
        )
        if not altitude_text:
            return ""
        try:
            value = float(altitude_text)
            return f"{value:.2f}"
        except ValueError:
            match = re.search(r"[-+]?\d+(?:\.\d+)?", altitude_text)
            if match is None:
                return altitude_text
            return match.group(0)

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

    def _format_captured_at_display(self, captured_at_text: str) -> str:
        """Return longer, human-readable capture date/time for UI display."""
        text = captured_at_text.strip()
        if not text:
            return ""

        for fmt in ("%Y:%m:%d %H:%M:%S%z", "%Y:%m:%d %H:%M:%S"):
            try:
                dt = datetime.strptime(text, fmt)
                return dt.strftime("%a, %b %d, %Y %H:%M:%S")
            except ValueError:
                continue
        return text

    def _to_text(self, value: Any) -> str:
        """Convert metadata value into display text."""
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        if value is None:
            return ""
        return str(value)
