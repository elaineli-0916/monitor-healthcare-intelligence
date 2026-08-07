#!/usr/bin/env python3
"""Convert human-corrected review CSV into gold_labels.jsonl for calibration.

Usage:
  1. Open gold_review.csv and fill in the 'corrected_l2' column.
  2. Run: python3 convert_review_to_gold.py [--input gold_review.csv] [--output gold_labels.jsonl]

The output gold_labels.jsonl replaces LLM silver labels with human-verified gold labels.
Each correction has confidence=1.0 and label_source='human_gold'.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

REVIEW_FILE = Path(__file__).parent.parent / "references" / "gold_review.csv"
GOLD_OUTPUT = Path(__file__).parent.parent / "references" / "gold_labels.jsonl"


def parent_for(label: str) -> str:
    if label == "其他/综合" or label.startswith("其他"):
        return "其他/综合"
    prefix = label.split(".", 1)[0]
    mapping = {
        "1": "1. 创新药",
        "2": "2. 医疗器械",
        "3": "3. 医疗服务",
        "4": "4. 消费医疗与医美",
    }
    return mapping.get(prefix, "其他/综合")


def convert(csv_path: Path, output_path: Path) -> dict:
    rows_written = 0
    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        with open(output_path, 'w', encoding='utf-8') as out:
            for row in reader:
                corrected = (row.get('corrected_l2', '') or '').strip()
                if not corrected:
                    continue
                article_id = row.get('id', '').strip()
                title = row.get('title', '').strip()
                summary = (row.get('summary', '') or '')[:800]
                out.write(json.dumps({
                    "sample_index": rows_written,
                    "id": article_id,
                    "title": title,
                    "summary": summary,
                    "source": "",
                    "current_level_1_category": parent_for(row.get('l2_category', '')),
                    "current_level_2_category": row.get('l2_category', ''),
                    "level_1_category": parent_for(corrected),
                    "level_2_category": corrected,
                    "is_other": corrected in ("其他/综合", "其他"),
                    "confidence": 1.0,
                    "reason": f"人工修正：从 {row.get('l2_category','?')} → {corrected}",
                    "evidence": title,
                    "label_source": "human_gold",
                    "split": "test",
                    "schema_version": "1.0",
                }, ensure_ascii=False) + '\n')
                rows_written += 1
    return {"status": "ok", "gold_labels": rows_written}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=REVIEW_FILE)
    parser.add_argument('--output', type=Path, default=GOLD_OUTPUT)
    args = parser.parse_args()
    result = convert(args.input.resolve(), args.output.resolve())
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
