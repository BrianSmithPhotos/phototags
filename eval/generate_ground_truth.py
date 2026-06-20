"""One-off helper: populate eval/ground_truth.json from a model, as a starting draft.

Calls AiSuggestionService directly (no Qt) against every image in eval/images/
and writes its description/keywords into eval/ground_truth.json, leaving any
existing non-empty entries untouched so hand-corrected ground truth is never
overwritten by a re-run.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

EVAL_DIR = Path(__file__).resolve().parent
IMAGES_DIR = EVAL_DIR / "images"
GROUND_TRUTH_PATH = EVAL_DIR / "ground_truth.json"
MODEL = "openrouter:google/gemini-3.5-flash"

sys.path.insert(0, str(EVAL_DIR.parent))

from phototags.services.ai_suggestion_service import AiSuggestionError, AiSuggestionService  # noqa: E402


def main() -> None:
    ground_truth: dict[str, dict[str, object]] = json.loads(GROUND_TRUTH_PATH.read_text())
    service = AiSuggestionService()

    image_paths = sorted(p for p in IMAGES_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".orf"})
    for image_path in image_paths:
        entry = ground_truth.get(image_path.name)
        if entry and (entry.get("description") or entry.get("keywords")):
            print(f"skip (already populated): {image_path.name}")
            continue

        try:
            result = service.suggest_for_image(image_path=image_path, model=MODEL)
        except AiSuggestionError as exc:
            print(f"FAILED: {image_path.name}: {exc}")
            continue

        ground_truth[image_path.name] = {
            "description": result.description,
            "keywords": [keyword.casefold() for keyword in result.keywords],
        }
        print(f"ok: {image_path.name}: {result.description}")

    GROUND_TRUTH_PATH.write_text(json.dumps(ground_truth, indent=2) + "\n")


if __name__ == "__main__":
    main()
