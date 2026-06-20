"""Print a summary table comparing every judged candidate model.

Reads eval/results/<model>.json (cost/time) and eval/results/judged/<model>.json
(judge scores), prints one row per model sorted by mean judge score (accuracy +
completeness).
"""

from __future__ import annotations

import json
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"
JUDGED_DIR = RESULTS_DIR / "judged"


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize_model(result_file: Path) -> dict[str, object] | None:
    judged_file = JUDGED_DIR / result_file.name
    if not judged_file.exists():
        return None

    result_payload = json.loads(result_file.read_text())
    judged_payload = json.loads(judged_file.read_text())
    model = result_payload["model"]
    results = result_payload["results"]
    judged = judged_payload["judged"]

    error_count = sum(1 for entry in results.values() if entry.get("error"))
    total_count = len(results)
    elapsed_total = sum(entry.get("elapsed_seconds") or 0.0 for entry in results.values())
    cost_total = sum(entry.get("cost_usd") or 0.0 for entry in results.values())

    accuracy_scores = [score["accuracy"] for score in judged.values() if score.get("accuracy") is not None]
    completeness_scores = [score["completeness"] for score in judged.values() if score.get("completeness") is not None]

    return {
        "model": model,
        "avg_accuracy": mean(accuracy_scores),
        "avg_completeness": mean(completeness_scores),
        "error_rate": error_count / total_count if total_count else 0.0,
        "elapsed_total_s": elapsed_total,
        "cost_total_usd": cost_total,
    }


def main() -> None:
    rows = []
    for result_file in sorted(RESULTS_DIR.glob("*.json")):
        if result_file.parent != RESULTS_DIR:
            continue
        summary = summarize_model(result_file)
        if summary is not None:
            rows.append(summary)

    def sort_key(row: dict[str, object]) -> float:
        accuracy = row["avg_accuracy"] or 0.0
        completeness = row["avg_completeness"] or 0.0
        return -(accuracy + completeness)

    rows.sort(key=sort_key)

    header = f"{'model':<45} {'accuracy':>8} {'complete':>8} {'err%':>6} {'time(s)':>9} {'cost($)':>9}"
    print(header)
    print("-" * len(header))
    for row in rows:
        accuracy = f"{row['avg_accuracy']:.2f}" if row["avg_accuracy"] is not None else "n/a"
        completeness = f"{row['avg_completeness']:.2f}" if row["avg_completeness"] is not None else "n/a"
        print(
            f"{row['model']:<45} {accuracy:>8} {completeness:>8} "
            f"{row['error_rate'] * 100:>5.1f}% {row['elapsed_total_s']:>9.1f} {row['cost_total_usd']:>9.4f}"
        )


if __name__ == "__main__":
    main()
