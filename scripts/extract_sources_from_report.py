#!/usr/bin/env python3
"""Extract the ByDrug source registry from the supplied HTML report."""

from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


CRITICAL_SOURCES = {"E药经理人", "米内网", "药渡", "赛柏蓝", "医药魔方"}

PRIMARY_KEYWORDS = (
    "国家药监局",
    "国家医保局",
    "国家卫健委",
    "药品审评中心",
    "医疗器械技术审评中心",
    "人民政府",
    "卫生健康委员会",
    "疾病预防控制中心",
    "证券交易所",
)
INSTITUTION_KEYWORDS = (
    "大学",
    "学院",
    "医院",
    "研究院",
    "研究所",
    "学会",
    "协会",
)


@dataclass
class SourceRow:
    name: str
    article_count: int
    latest: str
    url: str


class SourceTableParser(HTMLParser):
    """Read rows only from the table whose id is ``sourceTable``."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.table_depth = 0
        self.in_row = False
        self.in_cell = False
        self.current_cell: list[str] = []
        self.current_href = ""
        self.current_row: list[tuple[str, str]] = []
        self.rows: list[list[tuple[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "table" and attrs_dict.get("id") == "sourceTable":
            self.in_table = True
            self.table_depth = 1
            return
        if not self.in_table:
            return
        if tag == "table":
            self.table_depth += 1
        elif tag == "tr":
            self.in_row = True
            self.current_row = []
        elif tag in {"td", "th"} and self.in_row:
            self.in_cell = True
            self.current_cell = []
            self.current_href = ""
        elif tag == "a" and self.in_cell:
            self.current_href = attrs_dict.get("href") or ""

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.in_table:
            return
        if tag in {"td", "th"} and self.in_cell:
            text = " ".join("".join(self.current_cell).split())
            self.current_row.append((text, self.current_href))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.current_row:
                self.rows.append(self.current_row)
            self.in_row = False
        elif tag == "table":
            self.table_depth -= 1
            if self.table_depth == 0:
                self.in_table = False


def normalize_name(value: str) -> str:
    return re.sub(r"\s*目标\s*$", "", html.unescape(value)).strip()


def classify_source(name: str) -> tuple[str, str, str, str]:
    """Return source type, trust, evidence, and rating status."""
    if any(keyword in name for keyword in PRIMARY_KEYWORDS):
        return "government_or_regulator", "A", "primary", "provisional-rule"
    if any(keyword in name for keyword in INSTITUTION_KEYWORDS):
        return "research_or_medical_institution", "A", "primary", "needs-review"
    return "professional_media_or_database", "B", "secondary", "needs-review"


def extract_sources(report_path: Path) -> list[SourceRow]:
    parser = SourceTableParser()
    parser.feed(report_path.read_text(encoding="utf-8"))
    sources: list[SourceRow] = []
    for row in parser.rows:
        if len(row) < 5 or not row[0][0].strip().isdigit():
            continue
        name = normalize_name(row[1][0])
        count_text = row[2][0].replace(",", "").strip()
        count = int(count_text) if count_text.isdigit() else 0
        latest = row[3][0].strip() or "无文章"
        url = row[4][1].strip() or row[4][0].strip()
        if name and url:
            sources.append(SourceRow(name, count, latest, url))
    return sources


def escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def render_registry(sources: list[SourceRow], report_name: str) -> str:
    lines = [
        "# Healthcare Intelligence Sources",
        "",
        f"Generated from `{report_name}`. Snapshot rows: **{len(sources)}**.",
        "",
        "> The row count is a snapshot, not a product contract. Source ratings are",
        "> conservative initial estimates. Review rows marked `needs-review` before",
        "> relying on them for high-stakes claims. Edit `Enabled` and `Critical`",
        "> directly; the runner does not hardcode a source count.",
        "> `WeRSS URL` is optional and is used only for critical-source fallback.",
        "> It may reference `${WERSS_BASE_URL}` and `${WERSS_ACCESS_KEY}` from `.env`.",
        "",
        "| Name | ByDrug URL | Source Type | Trust | Evidence | Enabled | Critical | WeRSS URL | Rating Status | Snapshot Articles | Snapshot Latest |",
        "|---|---|---|---|---|---|---|---|---|---:|---|",
    ]
    for source in sources:
        source_type, trust, evidence, rating_status = classify_source(source.name)
        enabled = "true" if source.article_count > 0 else "false"
        critical = (
            "true"
            if any(
                source.name == critical_name or source.name.startswith(critical_name)
                for critical_name in CRITICAL_SOURCES
            )
            else "false"
        )
        values = [
            source.name,
            source.url,
            source_type,
            trust,
            evidence,
            enabled,
            critical,
            "",
            rating_status,
            str(source.article_count),
            source.latest,
        ]
        lines.append("| " + " | ".join(escape_cell(value) for value in values) + " |")
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Input HTML report")
    parser.add_argument("output", type=Path, help="Output Markdown registry")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    sources = extract_sources(args.report)
    if not sources:
        raise SystemExit("No rows found in table#sourceTable")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_registry(sources, args.report.name), encoding="utf-8")
    print(f"Wrote {len(sources)} sources to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
