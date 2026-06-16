"""Copy processed images to destination library folders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
import shutil

from phototags.services.metadata_write_service import MetadataWriteResult, MetadataWriteService
from phototags.services.rename_service import RenameService

JPG_SUFFIXES = {".jpg", ".jpeg"}
HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(slots=True)
class ProcessMoveResult:
    """Result data for one successful process-and-copy operation."""

    source_path: Path
    destination_path: Path
    metadata_result: MetadataWriteResult


class ProcessMoveError(RuntimeError):
    """Raised when a process-and-copy operation fails."""


class ProcessMoveService:
    """Handle metadata write + verified copy to destination folders."""

    def __init__(
        self,
        *,
        metadata_write_service: MetadataWriteService | None = None,
        rename_service: RenameService | None = None,
    ) -> None:
        self._metadata_write_service = metadata_write_service or MetadataWriteService()
        self._rename_service = rename_service or RenameService()

    def process_and_copy(
        self,
        *,
        source_path: Path,
        destination_root: Path,
        proposed_filename: str,
        captured_at: str,
        title: str,
        description: str,
        keywords_text: str,
    ) -> ProcessMoveResult:
        """Copy source file to destination tree, then write metadata to destination."""
        if not source_path.exists():
            raise ProcessMoveError(f"Source file not found: {source_path}")

        destination_dir = self._destination_directory(
            destination_root=destination_root,
            captured_at=captured_at,
            source_path=source_path,
        )
        destination_dir.mkdir(parents=True, exist_ok=True)

        unique_filename = self._rename_service.ensure_unique_name(
            proposed_filename,
            {entry.name for entry in destination_dir.iterdir() if entry.is_file()},
        )
        destination_path = destination_dir / unique_filename

        try:
            shutil.copy2(source_path, destination_path)
            self._verify_copy(source_path=source_path, destination_path=destination_path)
            metadata_result = self._metadata_write_service.write_description_keywords(
                destination_path,
                title=title,
                description=description,
                keywords_text=keywords_text,
            )
        except OSError as exc:
            self._cleanup_destination(destination_path)
            raise ProcessMoveError(str(exc)) from exc
        except RuntimeError as exc:
            self._cleanup_destination(destination_path)
            raise ProcessMoveError(str(exc)) from exc

        return ProcessMoveResult(
            source_path=source_path,
            destination_path=destination_path,
            metadata_result=metadata_result,
        )

    def _destination_directory(
        self,
        *,
        destination_root: Path,
        captured_at: str,
        source_path: Path,
    ) -> Path:
        """Return destination path based on capture date and file type."""
        captured_dt = self._parse_captured_datetime(captured_at)
        if captured_dt is None:
            captured_dt = datetime.fromtimestamp(source_path.stat().st_mtime)

        month_folder = f"{captured_dt.month} {captured_dt.strftime('%B')}"
        day_folder = captured_dt.strftime("%d")
        destination = destination_root / month_folder / day_folder

        if source_path.suffix.lower() in JPG_SUFFIXES:
            return destination / "jpg"
        return destination

    def _parse_captured_datetime(self, captured_at: str) -> datetime | None:
        """Parse EXIF capture timestamp into datetime."""
        text = captured_at.strip()
        if not text:
            return None

        for fmt in ("%Y:%m:%d %H:%M:%S%z", "%Y:%m:%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    def _verify_copy(self, *, source_path: Path, destination_path: Path) -> None:
        """Verify copied file content before reporting success."""
        source_stat = source_path.stat()
        destination_stat = destination_path.stat()
        if source_stat.st_size != destination_stat.st_size:
            raise ProcessMoveError(
                f"Copy verification failed for {source_path.name}: size mismatch "
                f"({source_stat.st_size} != {destination_stat.st_size})"
            )

        source_hash = self._sha256(source_path)
        destination_hash = self._sha256(destination_path)
        if source_hash != destination_hash:
            raise ProcessMoveError(
                f"Copy verification failed for {source_path.name}: checksum mismatch"
            )

    def _sha256(self, path: Path) -> str:
        """Return SHA-256 digest for a file."""
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                block = handle.read(HASH_CHUNK_SIZE)
                if not block:
                    break
                digest.update(block)
        return digest.hexdigest()

    def _cleanup_destination(self, destination_path: Path) -> None:
        """Delete incomplete destination file after errors."""
        try:
            if destination_path.exists():
                destination_path.unlink()
        except OSError:
            return
