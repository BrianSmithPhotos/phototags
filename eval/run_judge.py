"""Score every eval/results/<model>.json file against ground truth with a fixed judge.

Judge model is anthropic/claude-opus-4.5 via OpenRouter: not a candidate in
run_candidates.py, fixed (not swappable), and sees the actual image alongside ground
truth and every candidate's output so it can verify claims independently rather than
just diffing text.

One judge call per image scores every candidate model at once (image sent once
instead of once per candidate) — cuts judge calls from (models x images) down to
just (images), and avoids paying for the same image's tokens once per candidate.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
IMAGES_DIR = EVAL_DIR / "images"
RESULTS_DIR = EVAL_DIR / "results"
JUDGED_DIR = RESULTS_DIR / "judged"
GROUND_TRUTH_PATH = EVAL_DIR / "ground_truth.json"

JUDGE_MODEL = "anthropic/claude-opus-4.5"

# Restrict judging to this subset of candidate model ids (must match the "model"
# field in eval/results/<model>.json). Empty list means judge every candidate.
JUDGE_ONLY: list[str] = []

sys.path.insert(0, str(EVAL_DIR.parent))

from phototags.services.ai_suggestion_service import AiSuggestionError, AiSuggestionService  # noqa: E402
from phototags.services.openrouter_provider import OpenRouterProvider  # noqa: E402

JUDGE_SYSTEM_PROMPT = (
    "You are an exacting photography metadata judge. "
    "Return only strict JSON with one entry per candidate id."
)


def build_judge_prompt(
    *,
    ground_truth_description: str,
    ground_truth_keywords: list[str],
    candidates: dict[str, dict[str, Any]],
) -> str:
    candidates_text = "\n".join(
        f"- id: {candidate_id}\n"
        f"  description: {entry['description']}\n"
        f"  keywords: {', '.join(entry['keywords'])}"
        for candidate_id, entry in candidates.items()
    )
    candidate_ids = ", ".join(f'"{candidate_id}"' for candidate_id in candidates)
    return (
        "Compare each candidate AI-generated photo description/keywords against "
        "human ground truth, using the attached image to verify claims "
        "independently (e.g. treat a common name and its scientific name as "
        "equivalent, and credit correct identification even if phrased "
        "differently from ground truth).\n"
        "Score each candidate independently on a 1-5 scale:\n"
        "1) accuracy: is the candidate's subject identification and description "
        "factually correct given the image? Penalize wrong species/subject or "
        "invented details.\n"
        "2) completeness: does the candidate cover the same key facts as ground "
        "truth (subject, setting, notable detail)? Penalize missing or vague "
        "identification.\n"
        "3) rationale: one short sentence explaining that candidate's scores.\n"
        "4) Output only JSON in this exact shape, one entry per candidate id:\n"
        '{"<id>":{"accuracy":3,"completeness":3,"rationale":"..."}}\n'
        f"Ground truth description: {ground_truth_description}\n"
        f"Ground truth keywords: {', '.join(ground_truth_keywords)}\n"
        f"Candidates ({candidate_ids}):\n{candidates_text}\n"
    )


def extract_json_object(content: str) -> dict[str, Any]:
    """Decode JSON object from judge response, including code-fenced replies."""
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise AiSuggestionError("Judge response did not contain valid JSON")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise AiSuggestionError("Judge JSON payload is not an object")
    return parsed


def judge_image(
    *,
    service: AiSuggestionService,
    provider: OpenRouterProvider,
    image_path: Path,
    ground_truth_entry: dict[str, Any],
    candidates: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Score every candidate's output for one image in a single judge call."""
    image_bytes = service._read_previewable_image_bytes(image_path)  # noqa: SLF001
    image_payload = service._to_image_base64(image_bytes=image_bytes)  # noqa: SLF001
    prompt = build_judge_prompt(
        ground_truth_description=ground_truth_entry["description"],
        ground_truth_keywords=ground_truth_entry["keywords"],
        candidates=candidates,
    )
    content = provider.chat(
        model=JUDGE_MODEL,
        system_prompt=JUDGE_SYSTEM_PROMPT,
        user_prompt=prompt,
        image_payloads=[image_payload],
        request_label=f"{image_path.name}:judge",
    )
    payload = extract_json_object(content)
    scores: dict[str, dict[str, Any]] = {}
    for candidate_id in candidates:
        entry = payload.get(candidate_id)
        if not isinstance(entry, dict):
            scores[candidate_id] = {"accuracy": None, "completeness": None, "rationale": "missing from judge response"}
            continue
        scores[candidate_id] = {
            "accuracy": entry.get("accuracy"),
            "completeness": entry.get("completeness"),
            "rationale": entry.get("rationale"),
        }
    return scores


def main() -> None:
    JUDGED_DIR.mkdir(parents=True, exist_ok=True)
    ground_truth: dict[str, Any] = json.loads(GROUND_TRUTH_PATH.read_text())
    service = AiSuggestionService()
    provider = OpenRouterProvider()
    provider.ensure_vision_capable(JUDGE_MODEL)

    result_files = sorted(p for p in RESULTS_DIR.glob("*.json") if p.parent == RESULTS_DIR)
    payloads_by_model: dict[str, dict[str, Any]] = {}
    result_file_by_model: dict[str, Path] = {}
    for result_file in result_files:
        payload = json.loads(result_file.read_text())
        if JUDGE_ONLY and payload["model"] not in JUDGE_ONLY:
            continue
        payloads_by_model[payload["model"]] = payload
        result_file_by_model[payload["model"]] = result_file

    judged_by_model: dict[str, dict[str, Any]] = {model: {} for model in payloads_by_model}

    for image_name, ground_truth_entry in ground_truth.items():
        candidates: dict[str, dict[str, Any]] = {}
        for model, payload in payloads_by_model.items():
            entry = payload["results"].get(image_name)
            if entry is None or entry.get("error"):
                continue
            candidates[model] = entry

        if not candidates:
            print(f"=== {image_name} === skip (no usable candidate output)")
            continue

        print(f"=== {image_name} === judging {len(candidates)} candidates")
        try:
            scores = judge_image(
                service=service,
                provider=provider,
                image_path=IMAGES_DIR / image_name,
                ground_truth_entry=ground_truth_entry,
                candidates=candidates,
            )
        except AiSuggestionError as exc:
            print(f"  FAILED: {exc}")
            for model in candidates:
                judged_by_model[model][image_name] = {"accuracy": None, "completeness": None, "rationale": f"judge error: {exc}"}
            continue

        for model, score in scores.items():
            judged_by_model[model][image_name] = score
            print(f"  {model}: accuracy={score['accuracy']} completeness={score['completeness']}")

        for model, payload in payloads_by_model.items():
            entry = payload["results"].get(image_name)
            if entry is not None and entry.get("error") and model not in scores:
                judged_by_model[model][image_name] = {"accuracy": None, "completeness": None, "rationale": "candidate errored, skipped"}

    for model in payloads_by_model:
        output_path = JUDGED_DIR / result_file_by_model[model].name
        output_path.write_text(json.dumps({"model": model, "judged": judged_by_model[model]}, indent=2) + "\n")
        print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
