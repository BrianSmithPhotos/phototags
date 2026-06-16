"""Write Description + Keywords metadata using exiftool."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


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
            image_path=image_path,
            title=(cleaned_title if title is not None else None),
            description=cleaned_description,
            keywords=keywords,
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

    def _build_exiftool_write_command(
        self,
        *,
        image_path: Path,
        title: str | None,
        description: str,
        keywords: list[str],
    ) -> list[str]:
        """Construct exiftool write command."""
        command = ["exiftool"]
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
        command.append(str(image_path))
        return command

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
