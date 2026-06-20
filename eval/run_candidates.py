"""Run every candidate model in MODELS against eval/images/ and capture results.

Calls AiSuggestionService directly (no Qt), same approach as generate_ground_truth.py.
For each model, writes eval/results/<safe-model-name>.json with description, keywords,
elapsed time, and token/cost usage per image. Models run sequentially (one fully
completes before the next starts) to avoid GPU contention between local Ollama models
and to keep per-model progress/cost easy to watch live.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

EVAL_DIR = Path(__file__).resolve().parent
IMAGES_DIR = EVAL_DIR / "images"
RESULTS_DIR = EVAL_DIR / "results"

MODELS = [
    "ollama:qwen3.6:35b",
    "ollama:gemma4:12b",
    "ollama:qwen2.5vl:72b",
    "ollama:mistral-medium-3.5:latest",
    "ollama:qwen3.5:latest",
    "ollama:llama3.2-vision:11b",
    "ollama:moondream:latest",
    "openrouter:google/gemini-2.5-flash",
    "openrouter:google/gemini-3.5-flash",
    "openrouter:google/gemini-2.5-pro",
    "openrouter:openai/gpt-4o-mini",
    "openrouter:openai/gpt-5.1",
    "openrouter:anthropic/claude-opus-4.6",
    "openrouter:anthropic/claude-sonnet-4.5",
    "openrouter:qwen/qwen2.5-vl-72b-instruct",
]

sys.path.insert(0, str(EVAL_DIR.parent))

from phototags.services.ai_suggestion_service import AiSuggestionError, AiSuggestionService  # noqa: E402


def safe_model_name(model: str) -> str:
    """Turn a 'provider:model/id' string into a filesystem-safe file stem."""
    return model.replace(":", "_").replace("/", "_")


def run_model(service: AiSuggestionService, model: str, image_paths: list[Path]) -> dict[str, object]:
    """Run one model against every image and return its results payload."""
    results: dict[str, object] = {}
    for image_path in image_paths:
        started = time.perf_counter()
        try:
            result = service.suggest_for_image(image_path=image_path, model=model)
        except AiSuggestionError as exc:
            elapsed = time.perf_counter() - started
            print(f"  FAILED: {image_path.name}: {exc}")
            results[image_path.name] = {
                "description": None,
                "keywords": None,
                "elapsed_seconds": elapsed,
                "cost_usd": None,
                "prompt_tokens": None,
                "completion_tokens": None,
                "error": str(exc),
            }
            continue

        elapsed = time.perf_counter() - started
        provider, _ = service._resolve_provider_and_model(model)
        usage = provider.last_usage or {}
        results[image_path.name] = {
            "description": result.description,
            "keywords": [keyword.casefold() for keyword in result.keywords],
            "elapsed_seconds": elapsed,
            "cost_usd": usage.get("cost_usd"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "error": None,
        }
        print(f"  ok ({elapsed:.1f}s): {image_path.name}: {result.description}")
    return results


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    image_paths = sorted(p for p in IMAGES_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".orf"})
    service = AiSuggestionService()

    for model in MODELS:
        print(f"=== {model} ===")
        output_path = RESULTS_DIR / f"{safe_model_name(model)}.json"
        results = run_model(service, model, image_paths)
        output_path.write_text(json.dumps({"model": model, "results": results}, indent=2) + "\n")
        print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
