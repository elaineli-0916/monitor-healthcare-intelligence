#!/usr/bin/env python3
"""Evaluate the classifier against held-out LLM silver labels."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from classification_engine import ClassificationEngine, DEFAULT_SILVER_PATH


def safe_divide(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def macro_f1(gold: list[str], predicted: list[str]) -> float:
    labels = sorted(set(gold) | set(predicted))
    values = []
    for label in labels:
        true_positive = sum(
            expected == label and actual == label
            for expected, actual in zip(gold, predicted)
        )
        false_positive = sum(
            expected != label and actual == label
            for expected, actual in zip(gold, predicted)
        )
        false_negative = sum(
            expected == label and actual != label
            for expected, actual in zip(gold, predicted)
        )
        precision = safe_divide(true_positive, true_positive + false_positive)
        recall = safe_divide(true_positive, true_positive + false_negative)
        values.append(
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
    return sum(values) / len(values) if values else 0.0


def evaluate(
    engine: ClassificationEngine, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    predictions = []
    for row in rows:
        result = engine.classify(
            str(row.get("title", "")),
            str(row.get("summary", "")),
            list(row.get("tags") or []),
        )
        predictions.append({**row, "prediction": result.to_dict()})

    gold_level_1 = [str(row["level_1_category"]) for row in rows]
    gold_level_2 = [str(row["level_2_category"]) for row in rows]
    predicted_level_1 = [
        str(row["prediction"]["level_1_category"]) for row in predictions
    ]
    predicted_level_2 = [
        str(row["prediction"]["level_2_category"]) for row in predictions
    ]
    other = engine.other_label
    other_true_positive = sum(
        expected == other and actual == other
        for expected, actual in zip(gold_level_2, predicted_level_2)
    )
    other_false_positive = sum(
        expected != other and actual == other
        for expected, actual in zip(gold_level_2, predicted_level_2)
    )
    other_false_negative = sum(
        expected == other and actual != other
        for expected, actual in zip(gold_level_2, predicted_level_2)
    )

    return {
        "label_source": "llm_silver",
        "split": "test",
        "rows": len(rows),
        "level_1": {
            "accuracy": safe_divide(
                sum(a == b for a, b in zip(gold_level_1, predicted_level_1)),
                len(rows),
            ),
            "macro_f1": macro_f1(gold_level_1, predicted_level_1),
        },
        "level_2": {
            "accuracy": safe_divide(
                sum(a == b for a, b in zip(gold_level_2, predicted_level_2)),
                len(rows),
            ),
            "macro_f1": macro_f1(gold_level_2, predicted_level_2),
        },
        "other": {
            "gold": sum(label == other for label in gold_level_2),
            "predicted": sum(label == other for label in predicted_level_2),
            "precision": safe_divide(
                other_true_positive,
                other_true_positive + other_false_positive,
            ),
            "recall": safe_divide(
                other_true_positive,
                other_true_positive + other_false_negative,
            ),
            "false_positive": other_false_positive,
            "false_negative": other_false_negative,
        },
        "methods": dict(
            Counter(
                row["prediction"]["classification_method"]
                for row in predictions
            )
        ),
        "errors": [
            {
                "id": row.get("id", ""),
                "title": row.get("title", ""),
                "expected": row["level_2_category"],
                "predicted": row["prediction"]["level_2_category"],
                "method": row["prediction"]["classification_method"],
                "confidence": row["prediction"]["classification_confidence"],
            }
            for row in predictions
            if row["level_2_category"]
            != row["prediction"]["level_2_category"]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--silver", type=Path, default=DEFAULT_SILVER_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in args.silver.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    test_rows = [row for row in rows if row.get("split") == "test"]
    report = evaluate(
        ClassificationEngine(enable_llm=False),
        test_rows,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
