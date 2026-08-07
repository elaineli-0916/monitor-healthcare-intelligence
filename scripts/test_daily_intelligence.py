#!/usr/bin/env python3
"""Offline tests for the SQLite event, signal, and daily report layer."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from daily_intelligence import (
    get_entity_history,
    get_event_evidence,
    process_payload,
    search_events,
)


REPORT_DATE = dt.date(2026, 7, 30)
NOW = dt.datetime(2026, 7, 30, 9, 5, tzinfo=dt.timezone(dt.timedelta(hours=8)))


def sample_payload(*, with_failure: bool = False) -> dict:
    failures = (
        [{"source": "EMA", "error_category": "连接超时", "error_detail": "timeout"}]
        if with_failure
        else []
    )
    return {
        "articles": [
            {
                "id": "funding-1",
                "title": "百济神州完成5亿美元战略融资",
                "summary": "本轮融资将用于推进肿瘤药物管线。",
                "source": "公司公告",
                "source_rating": "A",
                "source_type": "company",
                "publish_time": "2026-07-30 08:10",
                "source_url": "https://example.com/funding",
                "level_1_category": "1. 创新药",
                "level_2_category": "1. 创新药",
                "classification_method": "rule",
                "classification_confidence": 0.96,
                "event_type": "投融资",
                "companies": ["百济神州"],
                "products": [],
                "tags": [],
            },
            {
                "id": "approval-1",
                "title": "FDA批准新药Examplemab上市",
                "summary": "该药用于罕见病治疗。",
                "source": "FDA",
                "source_rating": "A",
                "source_type": "government",
                "publish_time": "2026-07-30 07:30",
                "url": "https://example.com/approval",
                "level_1_category": "1. 创新药",
                "level_2_category": "1.2 生物药（抗体/蛋白/核酸）",
                "classification_method": "semantic",
                "classification_confidence": 0.91,
                "event_type": "产品获批",
                "companies": [],
                "products": ["Examplemab"],
                "tags": [],
            },
            {
                "id": "clinical-1",
                "title": "ABC-101 III期临床未达主要终点",
                "summary": "公司将评估后续研发计划。",
                "source": "专业媒体",
                "source_rating": "B",
                "source_type": "media",
                "publish_time": "2026-07-29 19:20",
                "link": "https://example.com/clinical",
                "level_1_category": "1. 创新药",
                "level_2_category": "1.1 小分子创新药",
                "classification_method": "semantic_fallback",
                "classification_confidence": 0.78,
                "event_type": "临床试验",
                "companies": [],
                "products": ["ABC-101"],
                "tags": [],
            },
            {
                "id": "research-1",
                "title": "医疗行业年度研究综述",
                "summary": "行业结构回顾。",
                "source": "专业媒体",
                "source_rating": "B",
                "source_type": "media",
                "publish_time": "2026-07-29 12:00",
                "url": "https://example.com/research",
                "level_1_category": "其他/综合",
                "level_2_category": "其他/综合",
                "classification_method": "other",
                "classification_confidence": 0.85,
                "event_type": "行业研究",
                "companies": [],
                "products": [],
                "tags": [],
            },
        ],
        "failures": failures,
    }


class DailyIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.database = self.root / "intelligence.sqlite3"
        self.reports = self.root / "reports"
        self.watchlist = self.root / "watchlist.json"
        self.watchlist.write_text(
            json.dumps(
                {
                    "companies": ["百济神州"],
                    "drugs": ["Examplemab"],
                    "targets": [],
                    "technologies": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_payload(self, payload: dict | None = None) -> dict:
        return process_payload(
            payload or sample_payload(),
            database_path=self.database,
            report_dir=self.reports,
            report_date=REPORT_DATE,
            watchlist_path=self.watchlist,
            now=NOW,
        )

    def counts(self) -> dict[str, int]:
        connection = sqlite3.connect(self.database)
        try:
            return {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("articles", "events", "signals", "report_runs")
            }
        finally:
            connection.close()

    def test_three_signal_families_are_persisted(self) -> None:
        result = self.run_payload()
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["articles"], 4)
        self.assertEqual(result["events"], 3)
        connection = sqlite3.connect(self.database)
        try:
            families = {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT event_family FROM events"
                ).fetchall()
            }
        finally:
            connection.close()
        self.assertEqual(families, {"financing", "regulatory", "clinical"})

    def test_repeated_run_is_idempotent(self) -> None:
        self.run_payload()
        first = self.counts()
        self.run_payload()
        self.assertEqual(first, self.counts())
        self.assertEqual(
            first,
            {"articles": 4, "events": 3, "signals": 3, "report_runs": 1},
        )

    def test_watchlist_adds_full_weight(self) -> None:
        self.run_payload()
        connection = sqlite3.connect(self.database)
        try:
            scores = dict(
                connection.execute(
                    """
                    SELECT e.title, s.watchlist_score
                    FROM signals s JOIN events e ON e.id=s.event_id
                    """
                ).fetchall()
            )
        finally:
            connection.close()
        self.assertEqual(scores["百济神州完成5亿美元战略融资"], 25)
        self.assertEqual(scores["FDA批准新药Examplemab上市"], 25)
        self.assertEqual(scores["ABC-101 III期临床未达主要终点"], 0)

    def test_report_contains_required_sections_and_sources(self) -> None:
        result = self.run_payload()
        content = Path(result["report_path"]).read_text(encoding="utf-8")
        for heading in (
            "# 医疗健康行业每日情报｜2026-07-30",
            "## Top Signals",
            "## 关注名单命中",
            "## 融资交易事件",
            "## 监管获批事件",
            "## 临床研发事件",
            "## 趋势与结构",
            "## 待核实事项",
            "## 完整附录",
        ):
            self.assertIn(heading, content)
        top_section = content.split("## 关注名单命中", 1)[0]
        self.assertIn("融资交易", top_section)
        self.assertIn("监管获批", top_section)
        self.assertIn("临床研发", top_section)
        self.assertIn("https://example.com/approval", content)
        self.assertIn("历史基线不足", content)

    def test_source_failure_marks_report_partial(self) -> None:
        result = self.run_payload(sample_payload(with_failure=True))
        self.assertEqual(result["status"], "partial")
        self.assertLess(result["coverage"], 0.95)
        content = Path(result["report_path"]).read_text(encoding="utf-8")
        self.assertIn("本日报为 `partial`", content)
        self.assertIn("EMA", content)

    def test_event_fields_do_not_invent_missing_values(self) -> None:
        self.run_payload()
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT * FROM events WHERE event_family='clinical'"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(row["clinical_phase"], "III期")
        self.assertEqual(row["impact_direction"], "negative")
        self.assertIsNone(row["amount_text"])
        self.assertIsNone(row["regulator"])

    def test_reserved_event_and_evidence_interfaces(self) -> None:
        self.run_payload()
        events = search_events(self.database, query="Examplemab", family="regulatory")
        self.assertEqual(len(events), 1)
        evidence = get_event_evidence(self.database, events[0]["id"])
        self.assertEqual(evidence[0]["evidence_status"], "primary")
        history = get_entity_history(self.database, "Examplemab")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["event_family"], "regulatory")

    def test_default_run_never_sends_email(self) -> None:
        result = self.run_payload()
        self.assertEqual(result["mode"], "shadow")
        self.assertEqual(result["delivery"]["status"], "disabled")

    def test_nonmedical_and_research_noise_do_not_become_signals(self) -> None:
        payload = {
            "articles": [
                {
                    "id": "retail-ipo",
                    "title": "希音港股IPO新进展",
                    "summary": "经营业绩稳健增长。",
                    "source": "财经媒体",
                    "source_rating": "B",
                    "publish_time": "2026-07-30 08:00",
                    "url": "https://example.com/retail",
                    "level_1_category": "其他/综合",
                    "level_2_category": "其他/综合",
                    "event_type": "投融资",
                },
                {
                    "id": "clinical-report",
                    "title": "CAR-T全球临床数据深度分析报告",
                    "summary": "报告回顾既往临床试验数据。",
                    "source": "专业媒体",
                    "source_rating": "B",
                    "publish_time": "2026-07-30 08:00",
                    "url": "https://example.com/report",
                    "level_1_category": "1. 创新药",
                    "level_2_category": "1.3 细胞与基因治疗（CGT）",
                    "event_type": "临床试验",
                },
            ],
            "failures": [],
        }
        result = self.run_payload(payload)
        self.assertEqual(result["articles"], 2)
        self.assertEqual(result["events"], 0)
        self.assertEqual(result["signals"], 0)


if __name__ == "__main__":
    unittest.main()
