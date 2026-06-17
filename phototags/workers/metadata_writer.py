"""Background metadata write worker."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from phototags.services.exif_service import ExifService, ExifToolReadError, ExifUiData
from phototags.services.metadata_write_service import (
    MetadataWriteResult,
    MetadataWriteError,
    MetadataWriteService,
)


class MetadataSaveSignals(QObject):
    """Signals emitted by metadata save worker."""

    saved = Signal(str, object)
    failed = Signal(str, str)


class MetadataSaveTask(QRunnable):
    """Write description + keywords without blocking UI."""

    def __init__(
        self,
        image_path: Path,
        *,
        description: str,
        keywords_text: str,
        service: MetadataWriteService,
        signals: MetadataSaveSignals,
    ) -> None:
        super().__init__()
        self.image_path = image_path
        self.description = description
        self.keywords_text = keywords_text
        self.service = service
        self.signals = signals

    def run(self) -> None:
        """Persist metadata and emit success/failure."""
        try:
            result = self.service.write_description_keywords(
                self.image_path,
                description=self.description,
                keywords_text=self.keywords_text,
            )
            self.signals.saved.emit(str(self.image_path), result)
        except (OSError, ValueError, MetadataWriteError, RuntimeError) as exc:
            try:
                self.signals.failed.emit(str(self.image_path), str(exc))
            except RuntimeError:
                return


@dataclass(slots=True)
class MetadataBatchItemOutcome:
    """One file outcome from batch metadata save."""

    image_path: str
    description: str
    keywords: list[str]
    error: str


@dataclass(slots=True)
class MetadataBatchSaveResult:
    """Aggregate result for one scoped metadata save."""

    scope_label: str
    total_count: int
    success_count: int
    failure_count: int
    outcomes: list[MetadataBatchItemOutcome]


class MetadataBatchSaveSignals(QObject):
    """Signals emitted by batch metadata save worker."""

    completed = Signal(object)
    failed = Signal(str)


class MetadataBatchSaveTask(QRunnable):
    """Write description + keywords for a scope of files without blocking UI."""

    def __init__(
        self,
        *,
        image_paths: tuple[Path, ...],
        scope_label: str,
        draft_by_path: dict[str, tuple[str, str]],
        exif_service: ExifService,
        metadata_write_service: MetadataWriteService,
        signals: MetadataBatchSaveSignals,
    ) -> None:
        super().__init__()
        self.image_paths = image_paths
        self.scope_label = scope_label
        self.draft_by_path = draft_by_path
        self.exif_service = exif_service
        self.metadata_write_service = metadata_write_service
        self.signals = signals

    def run(self) -> None:
        """Persist metadata for all files in this save scope."""
        try:
            outcomes: list[MetadataBatchItemOutcome] = []
            for image_path in self.image_paths:
                outcome = self._save_one(image_path)
                outcomes.append(outcome)

            success_count = sum(1 for outcome in outcomes if not outcome.error)
            failure_count = len(outcomes) - success_count
            result = MetadataBatchSaveResult(
                scope_label=self.scope_label,
                total_count=len(outcomes),
                success_count=success_count,
                failure_count=failure_count,
                outcomes=outcomes,
            )
            try:
                self.signals.completed.emit(result)
            except RuntimeError:
                return
        except (OSError, ValueError, RuntimeError) as exc:
            try:
                self.signals.failed.emit(str(exc))
            except RuntimeError:
                return

    def _save_one(self, image_path: Path) -> MetadataBatchItemOutcome:
        """Persist metadata for one file and return outcome."""
        try:
            ui_data = self._read_exif_ui(image_path)
        except (OSError, ValueError, ExifToolReadError, RuntimeError) as exc:
            return MetadataBatchItemOutcome(
                image_path=str(image_path),
                description="",
                keywords=[],
                error=f"EXIF read failed: {exc}",
            )

        draft = self.draft_by_path.get(str(image_path))
        if draft is not None:
            description = draft[0]
            keywords_source = draft[1]
        else:
            description = ui_data.description
            keywords_source = ui_data.keywords

        keywords_text = self._keywords_with_auto_tokens(
            keywords_source,
            ui_data.art_filter_token,
            ui_data.camera_model or ui_data.camera,
            ui_data.lens_model or ui_data.lens_type,
        )

        try:
            result = self.metadata_write_service.write_description_keywords(
                image_path,
                description=description,
                keywords_text=keywords_text,
            )
        except (OSError, ValueError, MetadataWriteError, RuntimeError) as exc:
            return MetadataBatchItemOutcome(
                image_path=str(image_path),
                description=description,
                keywords=self._parse_keywords(keywords_text),
                error=str(exc),
            )
        return self._success_outcome(image_path=image_path, result=result)

    def _read_exif_ui(self, image_path: Path) -> ExifUiData:
        """Read one file's EXIF and map to UI metadata."""
        metadata = self.exif_service.read_full_metadata(image_path)
        return self.exif_service.map_for_ui(metadata)

    def _success_outcome(
        self,
        *,
        image_path: Path,
        result: MetadataWriteResult,
    ) -> MetadataBatchItemOutcome:
        """Build success outcome from normalized write result."""
        return MetadataBatchItemOutcome(
            image_path=str(image_path),
            description=result.description,
            keywords=list(result.keywords),
            error="",
        )

    def _keywords_with_auto_tokens(
        self,
        keywords_text: str,
        art_filter_token: str,
        camera_token: str,
        lens_token: str,
    ) -> str:
        """Append art/camera/lens tokens with case-insensitive de-duplication."""
        keywords = self._parse_keywords(keywords_text)
        auto_tokens = [art_filter_token.strip(), camera_token.strip(), lens_token.strip()]
        merged = self._merge_keywords(keywords, [token for token in auto_tokens if token])
        return ", ".join(merged)

    def _parse_keywords(self, text: str) -> list[str]:
        """Split comma/newline-delimited keywords into normalized list."""
        values = [part.strip() for part in text.replace("\n", ",").split(",")]
        return [value for value in values if value]

    def _merge_keywords(self, existing: list[str], incoming: list[str]) -> list[str]:
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
