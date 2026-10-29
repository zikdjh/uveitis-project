"""Summarize frozen OCT errors by class, source group, and patient.

This script reads existing prediction files only. It does not load a model,
run inference, update checkpoints, or use test rows for training.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "model" / "training" / "datasets" / "training" / "manifest.csv"
DEFAULT_CANDIDATE = (
    ROOT
    / "model"
    / "training"
    / "assets"
    / "qwen3.5-4b"
    / "eval-oct-step20-vs-step100-20261025-01"
    / "step20"
    / "predictions.json"
)
DEFAULT_BASELINE = DEFAULT_CANDIDATE.with_name("..") / "step100" / "predictions.json"
DEFAULT_OUTPUT = (
    ROOT
    / "model"
    / "training"
    / "assets"
    / "qwen3.5-4b"
    / "eval-oct-step20-vs-step100-20261025-01"
    / "error-analysis"
    / "step20-source-analysis.json"
)


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _source_group_key(
    dataset: str,
    label: str,
    source_group: str,
    source_image: str,
) -> str:
    leaf = Path(source_image).name
    if dataset == "13_zhanglab_oct":
        match = re.match(r"^[A-Za-z]+-(\d+)-", leaf)
        if match:
            return f"13:{label}:patient:{match.group(1)}"
    return f"{dataset}:{label}:source:{source_group or leaf}"


def _metrics(items: list[dict]) -> dict:
    labels = [item["expected"] for item in items]
    predictions = [item["predicted"] for item in items]
    classes = sorted(set(labels))
    per_class: dict[str, dict] = {}
    f1_scores: list[float] = []
    for label in classes:
        tp = sum(a == label and p == label for a, p in zip(labels, predictions))
        fp = sum(a != label and p == label for a, p in zip(labels, predictions))
        fn = sum(a == label and p != label for a, p in zip(labels, predictions))
        denominator = 2 * tp + fp + fn
        f1 = 2 * tp / denominator if denominator else 0.0
        f1_scores.append(f1)
        per_class[label] = {
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "f1": f1,
            "support": sum(a == label for a in labels),
        }
    matrix = {
        actual: {
            predicted: sum(
                a == actual and p == predicted
                for a, p in zip(labels, predictions)
            )
            for predicted in classes
        }
        for actual in classes
    }
    return {
        "samples": len(items),
        "accuracy": sum(a == p for a, p in zip(labels, predictions)) / len(items),
        "macro_f1": sum(f1_scores) / len(f1_scores),
        "json_valid_rate": sum(p is not None for p in predictions) / len(items),
        "per_class": per_class,
        "confusion_matrix": matrix,
    }


def _load_manifest(path: Path) -> dict[tuple[str, str], dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    return {(row["task"], row["image"]): row for row in rows}


def _load_predictions(path: Path) -> list[dict]:
    value = _read_json(path)
    if not isinstance(value, list):
        raise ValueError(f"Predictions must be a JSON list: {path}")
    return value


def _index_predictions(rows: list[dict]) -> dict[tuple[str, str], dict]:
    return {(row["task"], row["image"]): row for row in rows}


def _group_error_rows(items: list[dict], limit: int = 20) -> list[dict]:
    grouped: dict[str, dict] = {}
    for item in items:
        key = item["group_key"]
        group = grouped.setdefault(
            key,
            {
                "group_key": key,
                "dataset": item["dataset"],
                "expected": item["expected"],
                "samples": 0,
                "errors": 0,
                "confusions": Counter(),
                "images": [],
            },
        )
        group["samples"] += 1
        if item["predicted"] != item["expected"]:
            group["errors"] += 1
            group["confusions"][f"{item['expected']}->{item['predicted']}"] += 1
            group["images"].append(item["image"])

    values = []
    for group in grouped.values():
        values.append(
            {
                "group_key": group["group_key"],
                "dataset": group["dataset"],
                "expected": group["expected"],
                "samples": group["samples"],
                "errors": group["errors"],
                "accuracy": 1 - group["errors"] / group["samples"],
                "confusions": dict(sorted(group["confusions"].items())),
                "images": group["images"],
            }
        )
    values.sort(key=lambda row: (-row["errors"], -row["samples"], row["group_key"]))
    return values[:limit]


def _comparison(candidate: list[dict], baseline: list[dict]) -> dict:
    candidate_by_key = _index_predictions(candidate)
    baseline_by_key = _index_predictions(baseline)
    shared_keys = sorted(candidate_by_key.keys() & baseline_by_key.keys())
    by_class: dict[str, Counter] = defaultdict(Counter)
    by_group: dict[str, Counter] = defaultdict(Counter)
    for key in shared_keys:
        cand = candidate_by_key[key]
        base = baseline_by_key[key]
        if cand["predicted"] == cand["expected"] and base["predicted"] != base["expected"]:
            outcome = "candidate_improved"
        elif cand["predicted"] != cand["expected"] and base["predicted"] == base["expected"]:
            outcome = "candidate_regressed"
        elif cand["predicted"] == cand["expected"]:
            outcome = "both_correct"
        else:
            outcome = "both_wrong"
        by_class[cand["expected"]][outcome] += 1
        by_group[cand["group_key"]][outcome] += 1

    group_rows = []
    for group_key, counts in by_group.items():
        net = counts["candidate_improved"] - counts["candidate_regressed"]
        group_rows.append(
            {
                "group_key": group_key,
                "net_correctness_delta": net,
                "candidate_improved": counts["candidate_improved"],
                "candidate_regressed": counts["candidate_regressed"],
                "both_correct": counts["both_correct"],
                "both_wrong": counts["both_wrong"],
            }
        )
    group_rows.sort(
        key=lambda row: (
            -abs(row["net_correctness_delta"]),
            row["group_key"],
        )
    )
    return {
        "shared_samples": len(shared_keys),
        "by_class": {label: dict(sorted(counts.items())) for label, counts in sorted(by_class.items())},
        "top_changed_groups": group_rows[:20],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-predictions", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--baseline-predictions", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = _load_manifest(args.manifest)
    candidate = _load_predictions(args.candidate_predictions)
    baseline = _load_predictions(args.baseline_predictions)

    enriched = []
    missing_manifest = []
    for prediction in candidate:
        key = (prediction["task"], prediction["image"])
        manifest_row = manifest.get(key)
        if manifest_row is None:
            missing_manifest.append(prediction["image"])
            continue
        enriched.append(
            {
                **prediction,
                "source_group": manifest_row["source_group"],
                "group_key": _source_group_key(
                    prediction["dataset"],
                    prediction["expected"],
                    manifest_row["source_group"],
                    manifest_row["source_image"],
                ),
            }
        )
    if missing_manifest:
        raise ValueError(f"Predictions missing from manifest: {missing_manifest[:3]}")

    overall = _metrics(enriched)
    error_pairs = Counter(
        f"{item['expected']}->{item['predicted']}"
        for item in enriched
        if item["predicted"] != item["expected"]
    )
    per_actual = {
        label: {
            "samples": sum(item["expected"] == label for item in enriched),
            "errors": sum(
                item["expected"] == label and item["predicted"] != label
                for item in enriched
            ),
            "confusions": dict(
                sorted(
                    Counter(
                        item["predicted"]
                        for item in enriched
                        if item["expected"] == label and item["predicted"] != label
                    ).items()
                )
            ),
        }
        for label in sorted({item["expected"] for item in enriched})
    }

    grouped = defaultdict(list)
    for item in enriched:
        grouped[item["group_key"]].append(item)
    groups_with_errors = sum(
        any(item["predicted"] != item["expected"] for item in items)
        for items in grouped.values()
    )
    top_errors = _group_error_rows(enriched)
    top_error_sum = sum(row["errors"] for row in top_errors[:10])

    analysis = {
        "status": "ok",
        "generated_at": datetime.now(UTC).isoformat(),
        "candidate_predictions": str(args.candidate_predictions),
        "baseline_predictions": str(args.baseline_predictions),
        "manifest": str(args.manifest),
        "overall": overall,
        "error_pairs": dict(sorted(error_pairs.items(), key=lambda item: (-item[1], item[0]))),
        "per_actual": per_actual,
        "groups": {
            "total": len(grouped),
            "with_errors": groups_with_errors,
            "clean": len(grouped) - groups_with_errors,
            "top_10_error_share": top_error_sum / sum(error_pairs.values())
            if error_pairs
            else 0.0,
            "largest_error_groups": top_errors,
        },
        "candidate_vs_baseline": _comparison(enriched, baseline),
        "limitations": [
            "This is a grouped same-source split, not patient-isolated external validation.",
            "The source analysis uses existing frozen predictions and does not rerun inference.",
            "A clean patient group in this split does not establish clinical generalization.",
        ],
    }
    _write_json(args.output, analysis)
    print(json.dumps(analysis, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
