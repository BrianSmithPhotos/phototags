"""Compute capture groups for ORF/JPG variants in one folder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import re
import subprocess
from typing import Any

from phototags.services.exiftool_path import EXIFTOOL_PATH

GROUP_READ_TAGS: tuple[str, ...] = (
    "DateTimeOriginal",
    "CreateDate",
)
GROUP_READ_CHUNK_SIZE = 250
DEFAULT_GROUP_BATCH_SIZE = 50


@dataclass(slots=True)
class CaptureGroup:
    """Represents one grouped capture set with one or more member files."""

    group_id: str
    representative_path: Path
    members: tuple[Path, ...]
    strategy: str
    key_text: str


@dataclass(slots=True)
class CaptureGroupingResult:
    """Capture grouping output including reverse index and debug summary."""

    groups: tuple[CaptureGroup, ...]
    by_path: dict[Path, CaptureGroup]
    debug_text: str


@dataclass(slots=True)
class _CaptureRecord:
    """Normalized metadata fields used only during grouping."""

    path: Path
    captured_at: datetime | None
    captured_second_key: str


class CaptureGroupError(RuntimeError):
    """Raised when grouping metadata cannot be read or parsed."""


def batch_image_paths(
    image_paths: list[Path], batch_size: int = DEFAULT_GROUP_BATCH_SIZE
) -> list[list[Path]]:
    """Split filename-sorted paths into batches without splitting same-stem pairs.

    Files are sorted by name, so a same-shot JPG+RAW pair (for example
    P1010001.JPG and P1010001.ORF) sit adjacent. A batch boundary that would fall
    between such a pair is pushed forward by one file instead, so each batch's
    EXIF-based grouping never has to merge across batch lines for the common
    one-JPG-one-RAW case. Same-second bursts of unrelated stems can still rarely
    straddle a boundary; that risk already exists in the single-pass grouping this
    replaces and is unchanged by batching.
    """
    if not image_paths:
        return []

    sorted_paths = sorted(image_paths, key=lambda item: item.name.casefold())
    total = len(sorted_paths)
    batches: list[list[Path]] = []
    start = 0
    while start < total:
        end = min(start + batch_size, total)
        while end < total and sorted_paths[end - 1].stem.casefold() == sorted_paths[end].stem.casefold():
            end += 1
        batches.append(sorted_paths[start:end])
        start = end
    return batches


class CaptureGroupService:
    """Build capture groups from EXIF capture date/time metadata."""

    def build_groups(self, image_paths: list[Path]) -> CaptureGroupingResult:
        """Return grouped capture sets for provided files.

        Args:
            image_paths: Files in one folder to group.

        Returns:
            CaptureGroupingResult with deterministic group/member ordering.
        """
        if not image_paths:
            return CaptureGroupingResult(groups=tuple(), by_path={}, debug_text="")

        metadata_by_path = self.read_metadata_for_paths(image_paths)
        return self.build_groups_from_metadata(image_paths, metadata_by_path)

    def build_groups_from_metadata(
        self, image_paths: list[Path], metadata_by_path: dict[Path, dict[str, Any]]
    ) -> CaptureGroupingResult:
        """Compute capture groups from already-read EXIF metadata (no I/O).

        Grouping must see every file that shares a capture timestamp in one pass —
        a set sharing one timestamp (for example an Art Filter Bracket, where every
        frame is a different render of the same shot) is otherwise split if some of
        its files were grouped separately before the rest had been read. Callers
        that read metadata in I/O batches for responsiveness (see
        `CaptureGroupLoadTask`) should call this with the full set of paths read so
        far each time, not just the latest batch.
        """
        if not image_paths:
            return CaptureGroupingResult(groups=tuple(), by_path={}, debug_text="")

        records = [
            self._record_for_path(path=path, metadata=metadata_by_path.get(path, {}))
            for path in sorted(image_paths, key=lambda item: item.name.casefold())
        ]

        groups: list[tuple[list[_CaptureRecord], str, str]] = []
        datetime_buckets: dict[str, list[_CaptureRecord]] = {}
        missing_datetime: list[_CaptureRecord] = []
        for record in records:
            if not record.captured_second_key:
                missing_datetime.append(record)
                continue
            datetime_buckets.setdefault(record.captured_second_key, []).append(record)

        for key in sorted(datetime_buckets):
            bucket = datetime_buckets[key]
            groups.append((bucket, "datetime-second", f"dt={key}"))

        for record in missing_datetime:
            groups.append(([record], "missing-datetime", record.path.name))

        finalized = self._finalize_groups(groups)
        by_path: dict[Path, CaptureGroup] = {}
        for group in finalized:
            for path in group.members:
                by_path[path] = group

        debug_lines = [
            f"{group.group_id} [{group.strategy}] {group.key_text}: "
            + ", ".join(member.name for member in group.members)
            for group in finalized
        ]
        return CaptureGroupingResult(
            groups=tuple(finalized),
            by_path=by_path,
            debug_text="\n".join(debug_lines),
        )

    def read_metadata_for_paths(self, image_paths: list[Path]) -> dict[Path, dict[str, Any]]:
        """Read grouping tags from exiftool in chunks."""
        metadata_by_path: dict[Path, dict[str, Any]] = {}
        sorted_paths = sorted(image_paths, key=lambda item: item.name.casefold())

        for start in range(0, len(sorted_paths), GROUP_READ_CHUNK_SIZE):
            chunk = sorted_paths[start : start + GROUP_READ_CHUNK_SIZE]
            command = [
                EXIFTOOL_PATH,
                "-j",
                "-s",
                "-q",
                "-q",
                *[f"-{tag}" for tag in GROUP_READ_TAGS],
                *[str(path) for path in chunk],
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=90,
            )
            if result.returncode != 0:
                message = result.stderr.strip() or "Unknown exiftool error"
                raise CaptureGroupError(message)

            try:
                parsed = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise CaptureGroupError(f"Invalid exiftool JSON while grouping: {exc}") from exc

            if not isinstance(parsed, list):
                raise CaptureGroupError("Unexpected exiftool grouping payload")

            for entry in parsed:
                if not isinstance(entry, dict):
                    continue
                source_text = self._to_text(entry.get("SourceFile")).strip()
                if not source_text:
                    continue
                source_path = Path(source_text)
                metadata_by_path[source_path] = entry

        return metadata_by_path

    def _record_for_path(self, *, path: Path, metadata: dict[str, Any]) -> _CaptureRecord:
        """Map one file's grouping fields into normalized grouping record."""
        captured_at_text = self._first_text(metadata, ("DateTimeOriginal", "CreateDate"))

        record = _CaptureRecord(
            path=path,
            captured_at=self._parse_datetime(captured_at_text),
            captured_second_key=self._captured_second_key(captured_at_text),
        )
        return record

    def _finalize_groups(self, grouped: list[tuple[list[_CaptureRecord], str, str]]) -> list[CaptureGroup]:
        """Return stable, deterministic CaptureGroup objects."""
        ordered_groups = sorted(
            grouped,
            key=lambda item: min(record.path.name.casefold() for record in item[0]),
        )

        finalized: list[CaptureGroup] = []
        for index, (records, strategy, key_text) in enumerate(ordered_groups, start=1):
            member_paths = [record.path for record in records]
            representative = self._pick_representative(member_paths)
            ordered_members = self._ordered_members(member_paths, representative)
            finalized.append(
                CaptureGroup(
                    group_id=f"grp-{index:04d}",
                    representative_path=representative,
                    members=tuple(ordered_members),
                    strategy=strategy,
                    key_text=key_text,
                )
            )
        return finalized

    def _pick_representative(self, paths: list[Path]) -> Path:
        """Pick representative file for one capture group: first JPG by filename, else first file.

        Filename order matches camera capture order (e.g. OM System Art Filter
        Bracket shoots the plain/Off-filter render first), which gives a more
        representative preview than picking by file size — art-filter renders
        (grain, dramatic tone, monochrome) often compress to a larger file than
        the plain render of the same shot.
        """
        jpg_candidates = [path for path in paths if path.suffix.casefold() in {".jpg", ".jpeg"}]
        candidates = jpg_candidates or paths
        return min(candidates, key=lambda path: path.name.casefold())

    def _ordered_members(self, paths: list[Path], representative: Path) -> list[Path]:
        """Order group members with representative first, then deterministic fallback order."""
        ordered = sorted(paths, key=self._member_sort_key)
        if representative in ordered:
            ordered.remove(representative)
            ordered.insert(0, representative)
        return ordered

    def _member_sort_key(self, path: Path) -> tuple[int, str]:
        """Sort by preferred render type then filename."""
        suffix = path.suffix.casefold()
        if suffix in {".jpg", ".jpeg"}:
            return (0, path.name.casefold())
        if suffix == ".orf":
            return (1, path.name.casefold())
        return (2, path.name.casefold())

    def _captured_second_key(self, captured_at_text: str) -> str:
        """Return a normalized YYYY:MM:DD HH:MM:SS key for grouping."""
        parsed = self._parse_datetime(captured_at_text)
        if parsed is not None:
            return parsed.strftime("%Y:%m:%d %H:%M:%S")

        text = captured_at_text.strip()
        if not text:
            return ""
        match = re.search(r"\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}", text)
        if not match:
            return ""
        return match.group(0)

    def _parse_datetime(self, value: str) -> datetime | None:
        """Parse EXIF date/time text into datetime when possible."""
        text = value.strip()
        if not text:
            return None
        for fmt in ("%Y:%m:%d %H:%M:%S%z", "%Y:%m:%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    def _first_text(self, metadata: dict[str, Any], keys: tuple[str, ...]) -> str:
        """Return first non-empty text from key candidates."""
        for key in keys:
            if key not in metadata:
                continue
            text = self._to_text(metadata[key]).strip()
            if text:
                return text
        return ""

    def _to_text(self, value: Any) -> str:
        """Convert metadata value into text."""
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        if value is None:
            return ""
        return str(value)
