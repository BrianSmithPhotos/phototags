"""Score every eval/results/<model>.json file against ground truth with a fixed judge.

Judge model is anthropic/claude-opus-4.5 via OpenRouter: not a candidate in
run_candidates.py, fixed (not swappable), and sees the actual image alongside ground
truth and the candidate's output so it can verify claims independently rather than
just diffing text.
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

sys.path.insert(0, str(EVAL_DIR.parent))

from phototags.services.ai_suggestion_service import AiSuggestionError, AiSuggestionService  # noqa: E402
from phototags.services.openrouter_provider import OpenRouterProvider  # noqa: E402

JUDGE_SYSTEM_PROMPT = (
    "You are an exacting photography metadata judge. "
    "Return only strict JSON with keys accuracy, completeness, and rationale."
)


def build_judge_prompt(
    *, ground_truth_description: str, ground_truth_keywords: list[str], candidate_description: str, candidate_keywords: list[str]
) -> str:
    return (
        "Compare a candidate AI-generated photo description/keywords against human "
        "ground truth, using the attached image to verify claims independently "
        "(e.g. treat a common name and its scientific name as equivalent, and credit "
        "correct identification even if phrased differently from ground truth).\n"
        "Score on a 1-5 scale:\n"
        "1) accuracy: is the candidate's subject identification and description "
        "factually correct given the image? Penalize wrong species/subject or "
        "invented details.\n"
        "2) completeness: does the candidate cover the same key facts as ground "
        "truth (subject, setting, notable detail)? Penalize missing or vague "
        "identification.\n"
        "3) rationale: one short sentence explaining the scores.\n"
        "4) Output only JSON in this exact shape:\n"
        '{"accuracy":3,"completeness":3,"rationale":"..."}\n'
        f"Ground truth description: {ground_truth_description}\n"
        f"Ground truth keywords: {', '.join(ground_truth_keywords)}\n"
        f"Candidate description: {candidate_description}\n"
        f"Candidate keywords: {', '.join(candidate_keywords)}\n"
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


def judge_one(
    *,
    service: AiSuggestionService,
    provider: OpenRouterProvider,
    image_path: Path,
    ground_truth_entry: dict[str, Any],
    candidate_entry: dict[str, Any],
) -> dict[str, Any]:
    image_bytes = service._read_previewable_image_bytes(image_path)  # noqa: SLF001
    image_payload = service._to_image_base64(image_bytes=image_bytes)  # noqa: SLF001
    prompt = build_judge_prompt(
        ground_truth_description=ground_truth_entry["description"],
        ground_truth_keywords=ground_truth_entry["keywords"],
        candidate_description=candidate_entry["description"],
        candidate_keywords=candidate_entry["keywords"],
    )
    content = provider.chat(
        model=JUDGE_MODEL,
        system_prompt=JUDGE_SYSTEM_PROMPT,
        user_prompt=prompt,
        image_payloads=[image_payload],
        request_label=f"{image_path.name}:judge",
    )
    payload = extract_json_object(content)
    return {
        "accuracy": payload.get("accuracy"),
        "completeness": payload.get("completeness"),
        "rationale": payload.get("rationale"),
    }


def main() -> None:
    JUDGED_DIR.mkdir(parents=True, exist_ok=True)
    ground_truth: dict[str, Any] = json.loads(GROUND_TRUTH_PATH.read_text())
    service = AiSuggestionService()
    provider = OpenRouterProvider()
    provider.ensure_vision_capable(JUDGE_MODEL)

    result_files = sorted(p for p in RESULTS_DIR.glob("*.json") if p.parent == RESULTS_DIR)
    for result_file in result_files:
        payload = json.loads(result_file.read_text())
        model = payload["model"]
        print(f"=== judging {model} ===")
        judged: dict[str, Any] = {}
        for image_name, candidate_entry in payload["results"].items():
            if candidate_entry.get("error"):
                judged[image_name] = {"accuracy": None, "completeness": None, "rationale": "candidate errored, skipped"}
                continue
            ground_truth_entry = ground_truth.get(image_name)
            if ground_truth_entry is None:
                print(f"  skip (no ground truth): {image_name}")
                continue
            try:
                score = judge_one(
                    service=service,
                    provider=provider,
                    image_path=IMAGES_DIR / image_name,
                    ground_truth_entry=ground_truth_entry,
                    candidate_entry=candidate_entry,
                )
            except AiSuggestionError as exc:
                print(f"  FAILED: {image_name}: {exc}")
                judged[image_name] = {"accuracy": None, "completeness": None, "rationale": f"judge error: {exc}"}
                continue
            judged[image_name] = score
            print(f"  {image_name}: accuracy={score['accuracy']} completeness={score['completeness']}")

        output_path = JUDGED_DIR / result_file.name
        output_path.write_text(json.dumps({"model": model, "judged": judged}, indent=2) + "\n")
        print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
