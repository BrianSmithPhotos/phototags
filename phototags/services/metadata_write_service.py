"""Write Description + Keywords metadata using exiftool."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from phototags.services.exiftool_path import EXIFTOOL_PATH


@dataclass(slots=True)
class MetadataWriteResult:
    """Normalized metadata values that were written."""

    title: str
    description: str
    keywords: list[str]


class MetadataWriteError(RuntimeError):
    """Raised when metadata write fails."""


class MetadataWriteService:
    """Persist metadata edits with rollback support."""

    def write_description_keywords(
        self,
        image_path: Path,
        *,
        title: str | None = None,
        description: str,
        keywords_text: str,
        gps_latitude: str | None = None,
        gps_longitude: str | None = None,
        gps_altitude: str | None = None,
    ) -> MetadataWriteResult:
        """Write title, description, and keywords to IPTC/XMP tags.

        Title is written to IPTC Object Name and XMP dc:Title.
        Description is written to IPTC caption (primary) and mirrored to XMP description.
        Keywords are normalized and written to IPTC keywords and XMP subject.
        """
        cleaned_title = title.strip() if title is not None else ""
        cleaned_description = description.strip()
        keywords = self._normalize_keywords(keywords_text)

        command = self._build_exiftool_write_command(
            image_paths=[image_path],
            title=(cleaned_title if title is not None else None),
            description=cleaned_description,
            keywords=keywords,
            gps_latitude=gps_latitude,
            gps_longitude=gps_longitude,
            gps_altitude=gps_altitude,
        )
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=12,
        )
        backup_path = Path(f"{image_path}_original")

        if result.returncode != 0:
            self._restore_backup_if_present(image_path=image_path, backup_path=backup_path)
            message = result.stderr.strip() or result.stdout.strip() or "Unknown exiftool write error"
            raise MetadataWriteError(message)

        self._cleanup_backup(backup_path)
        return MetadataWriteResult(
            title=cleaned_title,
            description=cleaned_description,
            keywords=keywords,
        )

    def write_description_keywords_for_paths(
        self,
        image_paths: list[Path],
        *,
        description: str,
        keywords_text: str,
        gps_latitude: str | None = None,
        gps_longitude: str | None = None,
        gps_altitude: str | None = None,
    ) -> dict[Path, MetadataWriteResult | MetadataWriteError]:
        """Write identical description/keywords/GPS values to many files in one exiftool call.

        Batching only amortizes exiftool's per-process startup cost across the
        group — every path receives the exact same tag values, so only call this
        with files already known to want an identical result (e.g. a capture set
        whose auto-generated keywords happen to match). No title support: callers
        that need a per-file title (renaming/process) have per-file-unique values
        by construction and get no benefit from batching, so they should keep
        using `write_description_keywords` per file.

        On any failure (or timeout) this restores backups for the whole group and
        falls back to writing each file individually via
        `write_description_keywords`, preserving today's per-file rollback/error
        behavior rather than guessing which of several files in one exiftool
        invocation actually failed.
        """
        cleaned_description = description.strip()
        keywords = self._normalize_keywords(keywords_text)

        command = self._build_exiftool_write_command(
            image_paths=image_paths,
            title=None,
            description=cleaned_description,
            keywords=keywords,
            gps_latitude=gps_latitude,
            gps_longitude=gps_longitude,
            gps_altitude=gps_altitude,
        )
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=12 * len(image_paths),
            )
        except subprocess.TimeoutExpired:
            result = None

        if result is not None and result.returncode == 0:
            for image_path in image_paths:
                self._cleanup_backup(Path(f"{image_path}_original"))
            return {
                image_path: MetadataWriteResult(
                    title="", description=cleaned_description, keywords=keywords
                )
                for image_path in image_paths
            }

        for image_path in image_paths:
            self._restore_backup_if_present(
                image_path=image_path, backup_path=Path(f"{image_path}_original")
            )

        results: dict[Path, MetadataWriteResult | MetadataWriteError] = {}
        for image_path in image_paths:
            try:
                results[image_path] = self.write_description_keywords(
                    image_path,
                    description=description,
                    keywords_text=keywords_text,
                    gps_latitude=gps_latitude,
                    gps_longitude=gps_longitude,
                    gps_altitude=gps_altitude,
                )
            except MetadataWriteError as exc:
                results[image_path] = exc
        return results

    def _build_exiftool_write_command(
        self,
        *,
        image_paths: list[Path],
        title: str | None,
        description: str,
        keywords: list[str],
        gps_latitude: str | None,
        gps_longitude: str | None,
        gps_altitude: str | None,
    ) -> list[str]:
        """Construct an exiftool write command applying the same tag values to one or more files."""
        normalized_gps = self._normalize_gps_values(
            gps_latitude=gps_latitude,
            gps_longitude=gps_longitude,
            gps_altitude=gps_altitude,
        )
        command = [EXIFTOOL_PATH]
        if title is not None:
            command.extend(
                [
                    f"-IPTC:ObjectName={title}",
                    f"-XMP-dc:Title={title}",
                ]
            )
        command.extend(
            [
                f"-IPTC:Caption-Abstract={description}",
                f"-XMP-dc:Description={description}",
                "-IPTC:Keywords=",
                "-XMP-dc:Subject=",
            ]
        )
        for keyword in keywords:
            command.append(f"-IPTC:Keywords={keyword}")
            command.append(f"-XMP-dc:Subject={keyword}")
        if normalized_gps is not None:
            latitude, longitude, altitude = normalized_gps
            command.extend(
                [
                    f"-GPSLatitude={latitude}",
                    f"-GPSLatitudeRef={'N' if latitude >= 0 else 'S'}",
                    f"-GPSLongitude={longitude}",
                    f"-GPSLongitudeRef={'E' if longitude >= 0 else 'W'}",
                ]
            )
            if altitude is not None:
                command.extend(
                    [
                        f"-GPSAltitude={altitude}",
                        f"-GPSAltitudeRef={'0' if altitude >= 0 else '1'}",
                    ]
                )
        command.extend(str(image_path) for image_path in image_paths)
        return command

    def _normalize_gps_values(
        self,
        *,
        gps_latitude: str | None,
        gps_longitude: str | None,
        gps_altitude: str | None,
    ) -> tuple[float, float, float | None] | None:
        """Validate and normalize GPS values for write command arguments."""
        lat_text = (gps_latitude or "").strip()
        lon_text = (gps_longitude or "").strip()
        alt_text = (gps_altitude or "").strip()

        if not lat_text and not lon_text and not alt_text:
            return None
        if not lat_text or not lon_text:
            raise MetadataWriteError("GPS latitude and longitude must both be provided")

        try:
            latitude = float(lat_text)
            longitude = float(lon_text)
        except ValueError as exc:
            raise MetadataWriteError("GPS latitude/longitude must be numeric") from exc
        if latitude < -90 or latitude > 90:
            raise MetadataWriteError("GPS latitude must be between -90 and 90")
        if longitude < -180 or longitude > 180:
            raise MetadataWriteError("GPS longitude must be between -180 and 180")

        altitude: float | None = None
        if alt_text:
            try:
                altitude = float(alt_text)
            except ValueError as exc:
                raise MetadataWriteError("GPS altitude must be numeric") from exc
        return latitude, longitude, altitude

    def _normalize_keywords(self, keywords_text: str) -> list[str]:
        """Parse comma-delimited keywords and remove duplicates."""
        parts = keywords_text.replace("\n", ",").split(",")
        normalized: list[str] = []
        seen: set[str] = set()
        for part in parts:
            keyword = part.strip()
            if not keyword:
                continue
            key = keyword.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(keyword)
        return normalized

    def _cleanup_backup(self, backup_path: Path) -> None:
        """Remove exiftool backup file if it exists."""
        if backup_path.exists():
            try:
                backup_path.unlink()
            except OSError:
                return

    def _restore_backup_if_present(self, *, image_path: Path, backup_path: Path) -> None:
        """Restore original file from exiftool backup if available."""
        if not backup_path.exists():
            return
        try:
            if image_path.exists():
                image_path.unlink()
            backup_path.replace(image_path)
        except OSError:
            return
