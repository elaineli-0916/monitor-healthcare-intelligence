#!/usr/bin/env python3
"""Offline tests for the portable Healthcare intelligence runner."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo
import datetime as dt


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
MODULE_PATH = SCRIPT_DIR / "healthcare_intelligence.py"
SPEC = importlib.util.spec_from_file_location("healthcare_intelligence", MODULE_PATH)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


class ParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.timezone = ZoneInfo("Asia/Shanghai")
        self.now = dt.datetime(2026, 7, 23, 20, 30, tzinfo=self.timezone)

    def test_parse_absolute_and_relative_dates(self) -> None:
        absolute = monitor.parse_publish_time("发布于 2026-07-23 17:21", self.now, self.timezone)
        yesterday = monitor.parse_publish_time("昨天 21:57", self.now, self.timezone)
        hours = monitor.parse_publish_time("4小时前", self.now, self.timezone)
        self.assertEqual(absolute.isoformat(), "2026-07-23T17:21:00+08:00")
        self.assertEqual(yesterday.isoformat(), "2026-07-22T21:57:00+08:00")
        self.assertEqual(hours.isoformat(), "2026-07-23T16:30:00+08:00")

    def test_xq13_3_genetic_text_not_mistaken_as_date(self) -> None:
        result = monitor.parse_publish_time(
            "Xq13.3重复导致X连锁单纯性少毛症…… BioArtMED 昨天 20:00",
            self.now,
            self.timezone,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.isoformat(), "2026-07-22T20:00:00+08:00")

    def test_month_day_validated_before_construction(self) -> None:
        result = monitor.parse_publish_time(
            "某个版本 v13.3 已经发布，今天 15:30",
            self.now,
            self.timezone,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.isoformat(), "2026-07-23T15:30:00+08:00")

    def test_invalid_calendar_date_returns_none(self) -> None:
        result = monitor.parse_publish_time(
            "来源页面包含异常日期 2026-04-31 08:00",
            self.now,
            self.timezone,
        )
        self.assertIsNone(result)


    def test_risk_override_preserves_research_tag(self) -> None:
        category, tags = monitor.classify_item(
            "某创新药三期临床未达主要终点",
            "公司将重新评估后续临床试验。",
        )
        self.assertEqual(category, "风险事件")
        self.assertIn("创新药研发事件", tags)

    def test_bydrug_detail_ignores_navigation_text(self) -> None:
        content = """
        <html><head><title>测试标题医药新闻-ByDrug-一站式医药资源共享中心</title></head>
        <body>
          <nav>全球医疗健康投融资数据平台 医药政策 医疗器械</nav>
          <div class="top-container">
            <div class="title">Nature | 团队揭示免疫调控新机制</div>
            <div class="second-raw"><span class="text">2026-07-23 08:30</span>
              <a class="origin_link" href="https://mp.weixin.qq.com/s/example">查看原文</a>
            </div>
          </div>
          <div class="content"><div class="abstracts">研究发现一种新的免疫调控机制。</div></div>
        </body></html>
        """
        detail = monitor.parse_detail_page(
            content,
            "回退标题",
            "https://bydrug.pharmcube.com/news/detail/example",
        )
        self.assertEqual(detail["title"], "Nature | 团队揭示免疫调控新机制")
        self.assertEqual(detail["summary"], "研究发现一种新的免疫调控机制。")
        self.assertEqual(detail["time_text"], "2026-07-23 08:30")
        self.assertEqual(detail["original_url"], "https://mp.weixin.qq.com/s/example")
        category, _ = monitor.classify_item(detail["title"], detail["summary"])
        self.assertEqual(category, "学术与技术突破")

    def test_academic_team_cooperation_is_not_company_news(self) -> None:
        academic, _ = monitor.classify_item(
            "Nature | 甲团队与乙团队合作揭示免疫调控机制",
            "研究解析了蛋白结构。",
        )
        company, _ = monitor.classify_item(
            "某医药公司与某科技企业达成战略合作",
            "双方签署合作协议。",
        )
        self.assertEqual(academic, "学术与技术突破")
        self.assertEqual(company, "企业动态")

    def test_parse_werss_rss(self) -> None:
        feed = """
        <rss version="2.0"><channel><item>
          <title>某公司完成A轮融资</title>
          <link>https://mp.weixin.qq.com/s/example</link>
          <pubDate>Thu, 23 Jul 2026 17:21:00 +0800</pubDate>
          <description><![CDATA[<p>本轮资金用于产品研发。</p>]]></description>
        </item></channel></rss>
        """
        items = monitor.parse_werss_feed(feed, "https://werss.example/feed")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "某公司完成A轮融资")
        self.assertEqual(items[0]["feed_summary"], "本轮资金用于产品研发。")
        published = monitor.parse_publish_time(
            items[0]["context"], self.now, self.timezone
        )
        self.assertEqual(published.isoformat(), "2026-07-23T17:21:00+08:00")

    def test_conservative_merge_keeps_all_links(self) -> None:
        first = {
            "id": "a",
            "title": "元川微完成Pre-A轮数亿元融资，加速LPU芯片落地",
            "summary": "融资用于研发。",
            "published_at": "2026-07-23T17:21+08:00",
            "bydrug_url": "https://bydrug.example/a",
            "original_url": "https://original.example/a",
            "source_names": ["媒体"],
            "category": "一级市场投融资与投资事件",
            "tags": [],
            "trust": "B",
            "evidence": "secondary",
        }
        second = {
            **first,
            "id": "b",
            "title": "数亿元Pre-A轮融资完成，元川微推进LPU与芯片研发",
            "published_at": "2026-07-23T17:25+08:00",
            "bydrug_url": "https://bydrug.example/b",
            "original_url": "https://original.example/b",
            "source_names": ["公司官方"],
            "trust": "A",
            "evidence": "primary",
        }
        events = monitor.merge_items([first, second])
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0]["items"]), 2)
        self.assertEqual({link["url"] for link in events[0]["links"]}, {
            "https://bydrug.example/a",
            "https://original.example/a",
            "https://bydrug.example/b",
            "https://original.example/b",
        })
        self.assertEqual(events[0]["trust"], "A")
        self.assertEqual(events[0]["evidence"], "primary")


class OfflineEndToEndTests(unittest.TestCase):
    def make_runtime(self, root: Path) -> Path:
        config = json.loads((SKILL_ROOT / "assets" / "config.example.yaml").read_text())
        config["sources_file"] = str(SKILL_ROOT / "assets" / "fixtures" / "sources.md")
        config["output_dir"] = str(root / "runtime")
        config["ai"]["mode"] = "off"
        config["delivery"]["enabled"] = True
        config["delivery"]["recipients"] = ["reader@unit.test"]
        config["setup"]["sources_confirmed"] = True
        config["setup"]["answered_fields"] = sorted(
            monitor.required_setup_fields(config)
        )
        config_path = root / "config.yaml"
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        monitor.finalize_setup(config_path, confirmed_by_user=True)
        return config_path

    def test_incomplete_setup_blocks_collection_before_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = json.loads(
                (SKILL_ROOT / "assets" / "config.example.yaml").read_text()
            )
            config["sources_file"] = str(
                SKILL_ROOT / "assets" / "fixtures" / "sources.md"
            )
            config["output_dir"] = str(root / "runtime")
            config_path = root / "config.yaml"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "初始化未完成"):
                monitor.collect_run(
                    config_path,
                    fixture_dir=SKILL_ROOT / "assets" / "fixtures",
                    now_value="2026-07-23T20:30:00+08:00",
                )
            self.assertFalse((root / "runtime" / "raw").exists())

    def test_finalize_rejects_example_recipient(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = self.make_runtime(root)
            monitor.configure_workspace(
                config_path,
                ["delivery.recipients=[\"reader@example.com\"]"],
            )
            with self.assertRaisesRegex(RuntimeError, "示例邮箱"):
                monitor.finalize_setup(config_path, confirmed_by_user=True)

    def test_configure_relocks_confirmed_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = self.make_runtime(root)
            self.assertTrue(monitor.setup_status(config_path)["valid"])
            report = monitor.configure_workspace(
                config_path,
                ["collection_window_hours=24"],
            )
            self.assertFalse(report["completed"])
            with self.assertRaisesRegex(RuntimeError, "初始化未完成"):
                monitor.collect_run(
                    config_path,
                    fixture_dir=SKILL_ROOT / "assets" / "fixtures",
                    now_value="2026-07-23T20:30:00+08:00",
                )

    def test_manual_yaml_change_invalidates_confirmation_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = self.make_runtime(root)
            config = json.loads(config_path.read_text())
            config["collection_window_hours"] = 24
            config_path.write_text(json.dumps(config), encoding="utf-8")
            report = monitor.setup_status(config_path)
            self.assertFalse(report["valid"])
            self.assertIn("配置在用户确认后发生变化，必须重新确认", report["errors"])

    def test_source_registry_change_invalidates_confirmation_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources_path = root / "sources.md"
            sources_path.write_text(
                (SKILL_ROOT / "assets" / "fixtures" / "sources.md").read_text(),
                encoding="utf-8",
            )
            config_path = self.make_runtime(root)
            monitor.configure_workspace(
                config_path,
                [f"sources_file={sources_path}", "setup.sources_confirmed=true"],
            )
            monitor.finalize_setup(config_path, confirmed_by_user=True)
            sources_path.write_text(
                sources_path.read_text(encoding="utf-8") + "\n<!-- changed -->\n",
                encoding="utf-8",
            )
            report = monitor.setup_status(config_path)
            self.assertFalse(report["valid"])
            self.assertIn(
                "数据源范围在用户确认后发生变化，必须重新确认",
                report["errors"],
            )

    def test_fixture_run_writes_traceable_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = self.make_runtime(root)
            result = monitor.collect_run(
                config_path,
                fixture_dir=SKILL_ROOT / "assets" / "fixtures",
                now_value="2026-07-23T20:30:00+08:00",
            )
            self.assertEqual(result["status"], "healthy")
            self.assertEqual(result["sources_total"], 2)
            self.assertEqual(result["items"], 3)
            self.assertEqual(result["events"], 2)
            digest = Path(result["digest_path"]).read_text(encoding="utf-8")
            collected = Path(result["collected_path"]).read_text(encoding="utf-8")
            self.assertLess(
                digest.index("[风险事件]"),
                digest.index("[一级市场投融资与投资事件]"),
            )
            self.assertIn("合并条目数：2", digest)
            for url in (
                "https://example.com/original/finance-001",
                "https://example.com/original/finance-002",
                "https://example.com/original/risk-001",
            ):
                self.assertIn(url, digest)
            self.assertIn("仅供信息研究，不构成投资建议", digest)
            self.assertIn("来源链接", collected)

    def test_first_send_gate_and_outbox_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = self.make_runtime(root)
            digest_path = root / "digest.txt"
            digest_path.write_text("# 测试简报 — 2026-07-23\n", encoding="utf-8")
            blocked = monitor.deliver_digest(config_path, digest_path)
            self.assertEqual(blocked["status"], "approval-required")
            queued = monitor.deliver_digest(
                config_path,
                digest_path,
                confirm_first_send=True,
            )
            self.assertEqual(queued["status"], "queued-outbox")
            outbox = Path(json.loads(config_path.read_text())["output_dir"]) / "outbox"
            self.assertEqual(len(list(outbox.glob("*.json"))), 1)
            monitor.configure_workspace(
                config_path,
                ["delivery.recipients=[\"changed@unit.test\"]"],
            )
            monitor.finalize_setup(config_path, confirmed_by_user=True)
            changed = monitor.deliver_digest(config_path, digest_path)
            self.assertEqual(changed["status"], "approval-required")

    def test_critical_source_uses_werss_after_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = self.make_runtime(root)
            sources_path = root / "sources.md"
            sources_path.write_text(
                "\n".join(
                    [
                        "| Name | ByDrug URL | Source Type | Trust | Evidence | Enabled | Critical | WeRSS URL | Rating Status |",
                        "|---|---|---|---|---|---|---|---|---|",
                        "| 关键源 | https://fixture.local/missing | company_official | A | primary | true | true | https://fixture.local/feed | fixture |",
                    ]
                ),
                encoding="utf-8",
            )
            fixture_dir = root / "fixtures"
            fixture_dir.mkdir()
            (fixture_dir / "responses.json").write_text(
                json.dumps({"https://fixture.local/feed": "feed.xml"}),
                encoding="utf-8",
            )
            (fixture_dir / "feed.xml").write_text(
                """
                <rss version="2.0"><channel><item>
                  <title>某公司完成A轮融资</title>
                  <link>https://mp.weixin.qq.com/s/fallback</link>
                  <pubDate>Thu, 23 Jul 2026 17:21:00 +0800</pubDate>
                  <description>本轮资金用于产品研发。</description>
                </item></channel></rss>
                """,
                encoding="utf-8",
            )
            monitor.configure_workspace(
                config_path,
                [
                    "collection.failure_alert_after=1",
                    f"sources_file={sources_path}",
                    "setup.sources_confirmed=true",
                ],
            )
            monitor.finalize_setup(config_path, confirmed_by_user=True)
            result = monitor.collect_run(
                config_path,
                fixture_dir=fixture_dir,
                now_value="2026-07-23T20:30:00+08:00",
            )
            self.assertEqual(result["status"], "healthy")
            self.assertEqual(result["werss_fallback_sources"], ["关键源"])
            self.assertEqual(result["items"], 1)
            digest = Path(result["digest_path"]).read_text(encoding="utf-8")
            self.assertIn("https://mp.weixin.qq.com/s/fallback", digest)
            self.assertIn("WeRSS Feed", digest)


if __name__ == "__main__":
    unittest.main()
