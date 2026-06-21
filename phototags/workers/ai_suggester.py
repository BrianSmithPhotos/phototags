"""Background AI suggestion worker."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from phototags.services.ai_suggestion_service import (
    AiSuggestionError,
    AiSuggestionResult,
    AiSuggestionService,
)
from phototags.services.exif_service import ExifService, ExifToolReadError


@dataclass(slots=True)
class AiSuggestPayload:
    """AI result plus per-target metadata baselines for merge/apply."""

    representative_path: str
    target_paths: tuple[str, ...]
    suggestion: AiSuggestionResult
    base_keywords_by_path: dict[str, str]
    art_filter_by_path: dict[str, str]
    camera_by_path: dict[str, str]
    lens_by_path: dict[str, str]
    expand_to_group: bool = True


class AiSuggestSignals(QObject):
    """Signals emitted by AI suggestion worker."""

    suggested = Signal(object)
    failed = Signal(str, str)


class AiSuggestTask(QRunnable):
    """Generate AI suggestions without blocking the UI thread."""

    def __init__(
        self,
        *,
        representative_path: Path,
        target_paths: tuple[Path, ...],
        model_name: str,
        existing_keywords_by_path: dict[str, str],
        existing_keywords_text: str,
        existing_description: str,
        capture_context: str,
        location_context: str,
        ai_service: AiSuggestionService,
        exif_service: ExifService,
        signals: AiSuggestSignals,
        expand_to_group: bool = True,
    ) -> None:
        super().__init__()
        self.representative_path = representative_path
        self.target_paths = target_paths
        self.model_name = model_name
        self.existing_keywords_by_path = existing_keywords_by_path
        self.existing_keywords_text = existing_keywords_text
        self.existing_description = existing_description
        self.capture_context = capture_context
        self.location_context = location_context
        self.ai_service = ai_service
        self.exif_service = exif_service
        self.signals = signals
        self.expand_to_group = expand_to_group

    def run(self) -> None:
        """Run AI inference and emit success/failure."""
        try:
            suggestion = self.ai_service.suggest_for_image(
                image_path=self.representative_path,
                model=self.model_name,
                existing_keywords_text=self.existing_keywords_text,
                existing_description=self.existing_description,
                capture_context=self.capture_context,
                location_context=self.location_context,
            )
            base_keywords_by_path: dict[str, str] = {}
            art_filter_by_path: dict[str, str] = {}
            camera_by_path: dict[str, str] = {}
            lens_by_path: dict[str, str] = {}
            for target_path in self.target_paths:
                key = str(target_path)
                draft_keywords = self.existing_keywords_by_path.get(key, "").strip()
                if draft_keywords:
                    base_keywords_by_path[key] = draft_keywords
                    try:
                        _, art_filter, camera_model, lens_model = self._read_keywords_art_filter(target_path)
                    except (OSError, ValueError, ExifToolReadError, RuntimeError):
                        art_filter, camera_model, lens_model = "", "", ""
                    art_filter_by_path[key] = art_filter
                    camera_by_path[key] = camera_model
                    lens_by_path[key] = lens_model
                    continue

                try:
                    base_keywords, art_filter, camera_model, lens_model = self._read_keywords_art_filter(target_path)
                except (OSError, ValueError, ExifToolReadError, RuntimeError):
                    base_keywords, art_filter, camera_model, lens_model = "", "", "", ""
                base_keywords_by_path[key] = base_keywords
                art_filter_by_path[key] = art_filter
                camera_by_path[key] = camera_model
                lens_by_path[key] = lens_model

            payload = AiSuggestPayload(
                representative_path=str(self.representative_path),
                target_paths=tuple(str(path) for path in self.target_paths),
                suggestion=suggestion,
                base_keywords_by_path=base_keywords_by_path,
                art_filter_by_path=art_filter_by_path,
                camera_by_path=camera_by_path,
                lens_by_path=lens_by_path,
                expand_to_group=self.expand_to_group,
            )
            self.signals.suggested.emit(payload)
        except (OSError, ValueError, AiSuggestionError, RuntimeError) as exc:
            try:
                self.signals.failed.emit(str(self.representative_path), str(exc))
            except RuntimeError:
                return

    def _read_keywords_art_filter(self, image_path: Path) -> tuple[str, str, str, str]:
        """Read existing keywords and auto-keyword tokens for one target image."""
        metadata = self.exif_service.read_full_metadata(image_path)
        ui_data = self.exif_service.map_for_ui(metadata)
        return ui_data.keywords, ui_data.art_filter_token, ui_data.camera_model, ui_data.lens_model
