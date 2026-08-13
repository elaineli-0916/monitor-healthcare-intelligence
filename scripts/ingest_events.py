#!/usr/bin/env python3
"""Merge agent-extracted events (financing/regulatory/clinical) into the payload, then persist + re-render."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import daily_intelligence


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def merge_events(payload: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    by_article_id: dict[str, dict[str, Any]] = {}
    for event in events:
        article_id = event.get("article_id")
        if article_id:
            by_article_id[article_id] = event

    enriched = 0
    for article in payload.get("articles", []):
        event = by_article_id.get(article.get("id"))
        if not event:
            continue
        family = event.get("family")
        company = event.get("company")
        article["companies"] = [company] if company else []

        if family == "financing":
            article["event_type"] = event.get("type", "融资")
            article["investors"] = event.get("counterparty") or []
            article["track"] = event.get("track", "")
            article["amount_text"] = event.get("amount", "")
            article["financing_round"] = event.get("round_asset", "")
        elif family == "regulatory":
            article["event_type"] = "监管获批"
            article["product_name"] = event.get("product", "")
            article["indication"] = event.get("indication", "")
            article["regulator"] = event.get("regulator", "")
            article["decision"] = event.get("decision", "")
        elif family == "clinical":
            article["event_type"] = "临床研发"
            article["product_name"] = event.get("asset", "")
            article["indication"] = event.get("indication", "")
            article["trial_id"] = event.get("trial_id", "")
            article["clinical_phase"] = event.get("phase", "")
            article["clinical_outcome"] = event.get("status", "")
        enriched += 1

    print(f"merged events: {enriched}/{len(events)}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, default=daily_intelligence.DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--date")
    parser.add_argument("--watchlist", type=Path)
    parser.add_argument("--coverage-threshold", type=float, default=0.95)
    parser.add_argument("--top-signals", type=int, default=10)
    args = parser.parse_args(argv)

    events_doc = load_json(args.events)
    events = events_doc.get("events", []) if isinstance(events_doc, dict) else events_doc
    payload = load_json(args.input)
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")

    merged = merge_events(payload, events)

    report_date = (
        dt.date.fromisoformat(args.date)
        if args.date
        else dt.date.fromisoformat(events_doc.get("report_date", dt.date.today().isoformat()))
    )
    runtime_root = args.runtime_root.expanduser().resolve()
    database = args.database or runtime_root / "intelligence" / "healthcare_intelligence.sqlite3"
    report_dir = args.report_dir or runtime_root / "reports"
    watchlist = args.watchlist
    if watchlist is None and (runtime_root / "watchlist.json").exists():
        watchlist = runtime_root / "watchlist.json"

    result = daily_intelligence.process_payload(
        merged,
        database_path=database,
        report_dir=report_dir,
        report_date=report_date,
        watchlist_path=watchlist,
        coverage_threshold=args.coverage_threshold,
        top_limit=max(5, min(args.top_signals, 10)),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
