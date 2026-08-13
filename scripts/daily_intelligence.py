#!/usr/bin/env python3
"""Persist healthcare events, score daily signals, and render a shadow report."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
# 不再从 skill 安装路径推断 runtime 目录；优先使用环境变量，其次使用当前目录
DEFAULT_RUNTIME_ROOT = Path(os.environ.get("HEALTHCARE_RUNTIME_ROOT", ".")).expanduser()
DEFAULT_DATABASE = DEFAULT_RUNTIME_ROOT / "intelligence" / "healthcare_intelligence.sqlite3"
DEFAULT_REPORT_DIR = DEFAULT_RUNTIME_ROOT / "reports"
DEFAULT_CONFIG = DEFAULT_RUNTIME_ROOT / "config.yaml"
DEFAULT_WATCHLIST = DEFAULT_RUNTIME_ROOT / "watchlist.json"
EXAMPLE_WATCHLIST = SKILL_ROOT / "assets" / "watchlist.example.json"
TIMEZONE = ZoneInfo("Asia/Shanghai")

FAMILY_LABELS = {
    "financing": "融资交易",
    "regulatory": "监管获批",
    "clinical": "临床研发",
}
FAMILY_EVENT_TYPES = {
    "投融资": "financing",
    "融资": "financing",
    "收购": "financing",
    "IPO": "financing",
    "并购": "financing",
    "合作授权": "financing",
    "注册申报": "regulatory",
    "产品获批": "regulatory",
    "临床试验": "clinical",
    "监管获批": "regulatory",
    "临床研发": "clinical",
}
FAMILY_PATTERNS = {
    "financing": re.compile(
        r"融资|领投|投资|并购|收购|募资|IPO|A轮|B轮|C轮|D轮|授权|许可|战略合作|license",
        re.IGNORECASE,
    ),
    "regulatory": re.compile(
        r"获批|批准|受理|申报|上市许可|NDA|BLA|NMPA|FDA|EMA|PMDA|CDE|注册证",
        re.IGNORECASE,
    ),
    "clinical": re.compile(
        r"临床|试验|入组|主要终点|次要终点|I期|II期|III期|Ⅰ期|Ⅱ期|Ⅲ期|phase\s*[123]",
        re.IGNORECASE,
    ),
}
MEDICAL_RELEVANCE_PATTERN = re.compile(
    r"药|医疗|医药|健康|生物|临床|患者|治疗|疾病|诊断|器械|疫苗|抗体|蛋白|"
    r"核酸|细胞|基因|肿瘤|制剂|疗法|医院|护理|康复|手术|医美|减重|视光|"
    r"口腔|生殖|听力|睡眠|营养保健|pharma|biotech|therapeutic|medical|"
    r"health|clinical|drug|diagnostic|device|therapy|hospital|patient",
    re.IGNORECASE,
)
OUT_OF_SCOPE_PATTERN = re.compile(
    r"宠物|兽药|兽医|农药|农化|农业|农林|作物|花生田",
    re.IGNORECASE,
)
RESEARCH_FORMAT_PATTERN = re.compile(
    r"深度分析|行业报告|研究报告|年度报告|盘点|综述|观点|一周动态|数据概览",
    re.IGNORECASE,
)
NEGATIVE_PATTERN = re.compile(
    r"失败|未达|终止|暂停|拒绝|撤回|召回|严重不良|警告信|处罚|退市",
    re.IGNORECASE,
)
POSITIVE_PATTERN = re.compile(
    r"获批|批准|达到主要终点|成功|完成融资|领投|突破|首次|首款|启动|入组完成",
    re.IGNORECASE,
)
PLACEHOLDER_PATTERN = re.compile(r"内容需人工审阅|后续解析|栏目占位")
AMOUNT_PATTERN = re.compile(
    r"(?P<currency>人民币|美元|美金|港元|欧元|RMB|CNY|USD|HKD|EUR|\$|￥)?\s*"
    r"(?P<amount>(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d+)?)\s*"
    r"(?P<unit>亿元|亿|万元|万|million|billion|M|B)"
    r"(?P<currency_suffix>人民币|美元|美金|港元|欧元|RMB|CNY|USD|HKD|EUR)?",
    re.IGNORECASE,
)
ROUND_PATTERN = re.compile(
    r"(?:Pre[- ]?)?[A-H][+]?轮|天使轮|种子轮|战略融资|IPO|Pre-IPO",
    re.IGNORECASE,
)
PHASE_PATTERN = re.compile(
    r"(?:I{1,3}|Ⅰ{1,3}|[一二三123])期(?:临床)?|phase\s*[123]",
    re.IGNORECASE,
)
REGULATOR_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:FDA|EMA|PMDA|TGA|MHRA|CDE|NMPA)(?![A-Za-z])",
    re.IGNORECASE,
)
DECISION_PATTERN = re.compile(r"获批|批准|受理|拒绝|撤回|暂停|上市许可|注册证")
SOURCE_RATING_POINTS = {"A": 15, "B": 10, "C": 5}
WATCHLIST_KEYS = {
    "companies": "company",
    "drugs": "drug",
    "targets": "target",
    "technologies": "technology",
}


SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    canonical_url TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_rating TEXT NOT NULL,
    source_type TEXT NOT NULL,
    published_at TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    level_1_category TEXT NOT NULL,
    level_2_category TEXT NOT NULL,
    classification_method TEXT NOT NULL,
    classification_confidence REAL NOT NULL,
    raw_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    watchlist INTEGER NOT NULL DEFAULT 0,
    UNIQUE(entity_type, normalized_name)
);

CREATE TABLE IF NOT EXISTS article_entities (
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    mention TEXT NOT NULL,
    PRIMARY KEY(article_id, entity_id)
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    event_family TEXT NOT NULL,
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    event_date TEXT NOT NULL,
    amount_text TEXT,
    financing_round TEXT,
    regulator TEXT,
    decision TEXT,
    clinical_phase TEXT,
    clinical_outcome TEXT,
    source_type TEXT NOT NULL DEFAULT 'auto',
    product_name TEXT,
    indication TEXT,
    approval_type TEXT,
    trial_id TEXT,
    trial_phase_detail TEXT,
    data_highlight TEXT,
    review_status TEXT,
    impact_direction TEXT NOT NULL,
    impact_horizon TEXT NOT NULL,
    confidence REAL NOT NULL,
    details_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_sources (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    evidence_status TEXT NOT NULL,
    source_rating TEXT NOT NULL,
    PRIMARY KEY(event_id, article_id)
);

CREATE TABLE IF NOT EXISTS event_entities (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    PRIMARY KEY(event_id, entity_id)
);

CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    report_date TEXT NOT NULL,
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    total_score INTEGER NOT NULL,
    materiality_score INTEGER NOT NULL,
    watchlist_score INTEGER NOT NULL,
    novelty_score INTEGER NOT NULL,
    evidence_score INTEGER NOT NULL,
    trend_score INTEGER NOT NULL,
    why_important TEXT NOT NULL,
    history_change TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(report_date, event_id)
);

CREATE TABLE IF NOT EXISTS report_runs (
    run_id TEXT PRIMARY KEY,
    report_date TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    coverage REAL NOT NULL,
    article_count INTEGER NOT NULL,
    event_count INTEGER NOT NULL,
    signal_count INTEGER NOT NULL,
    report_path TEXT NOT NULL,
    failures_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_date_family ON events(event_date, event_family);
CREATE INDEX IF NOT EXISTS idx_signals_date_score ON signals(report_date, total_score DESC);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(normalized_name);


CREATE TABLE IF NOT EXISTS monthly_reports (
    id TEXT PRIMARY KEY,
    report_month TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'draft',
    html_path TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    observations_text TEXT NOT NULL,
    reviewed_by TEXT,
    reviewed_at TEXT,
    published_at TEXT,
    created_at TEXT NOT NULL
);
"""


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_id(prefix: str, *parts: Any) -> str:
    joined = "\x1f".join(clean_text(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(joined.encode('utf-8')).hexdigest()[:24]}"


def canonical_url(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return text
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return text
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            parsed.query,
            "",
        )
    )


def markdown_text(value: Any) -> str:
    return clean_text(value).replace("|", "\\|").replace("\n", " ")


def parse_date(value: Any, fallback: dt.date) -> str:
    text = clean_text(value)
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    return match.group(0) if match else fallback.isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_watchlist(path: Path | None = None) -> dict[str, list[str]]:
    selected = path or (DEFAULT_WATCHLIST if DEFAULT_WATCHLIST.exists() else EXAMPLE_WATCHLIST)
    data = load_json(selected, {})
    if not isinstance(data, dict):
        raise ValueError("watchlist root must be an object")
    return {
        key: sorted(
            {
                clean_text(item)
                for item in data.get(key, [])
                if clean_text(item)
            },
            key=str.casefold,
        )
        for key in WATCHLIST_KEYS
    }


def connect_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    _migrate_monthly_report_schema(connection)
    return connection

_MONTHLY_REPORTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS monthly_reports (
    id TEXT PRIMARY KEY,
    report_month TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'draft',
    html_path TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    observations_text TEXT NOT NULL,
    reviewed_by TEXT,
    reviewed_at TEXT,
    published_at TEXT,
    created_at TEXT NOT NULL
);"""

_migration_schema_added = False

def _migrate_monthly_report_schema(conn: sqlite3.Connection) -> None:
    global _migration_schema_added
    existing = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
    new_event_cols = [
        ("source_type", "TEXT NOT NULL DEFAULT 'auto'"),
        ("product_name", "TEXT"),
        ("indication", "TEXT"),
        ("approval_type", "TEXT"),
        ("trial_id", "TEXT"),
        ("trial_phase_detail", "TEXT"),
        ("data_highlight", "TEXT"),
        ("review_status", "TEXT"),
        ("track", "TEXT"),
    ]
    for col, typedef in new_event_cols:
        if col not in existing:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col} {typedef}")
    if not _migration_schema_added:
        conn.executescript(_MONTHLY_REPORTS_SCHEMA)
        _migration_schema_added = True


def connect_readonly_database(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def normalize_article(article: dict[str, Any], report_date: dt.date) -> dict[str, Any]:
    url = canonical_url(
        article.get("source_url") or article.get("link") or article.get("url")
    )
    title = clean_text(article.get("title"))
    source = clean_text(article.get("source") or article.get("source_name") or "未知来源")
    article_id = clean_text(article.get("id")) or stable_id(
        "article", url or title, source, article.get("publish_time")
    )
    confidence = article.get("classification_confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        **article,
        "id": article_id,
        "title": title,
        "summary": clean_text(article.get("summary")),
        "source": source,
        "source_rating": clean_text(article.get("source_rating") or "B").upper(),
        "source_type": clean_text(article.get("source_type")),
        "url": url,
        "publish_time": clean_text(article.get("publish_time") or article.get("date")),
        "published_date": parse_date(
            article.get("publish_time") or article.get("date"), report_date
        ),
        "level_1_category": clean_text(
            article.get("level_1_category")
            or article.get("parent_category")
            or "其他/综合"
        ),
        "level_2_category": clean_text(
            article.get("level_2_category")
            or article.get("classification")
            or "其他/综合"
        ),
        "classification_method": clean_text(
            article.get("classification_method") or "legacy"
        ),
        "classification_confidence": max(0.0, min(1.0, confidence)),
        "event_type": clean_text(article.get("event_type")),
        "companies": [
            clean_text(item) for item in article.get("companies", []) if clean_text(item)
        ],
        "investors": [
            clean_text(item) for item in article.get("investors", []) if clean_text(item)
        ],
        "products": [
            clean_text(item) for item in article.get("products", []) if clean_text(item)
        ],
        "tags": [clean_text(item) for item in article.get("tags", []) if clean_text(item)],
        "track": clean_text(article.get("track")),
        "amount_text": clean_text(article.get("amount_text")),
        "financing_round": clean_text(article.get("financing_round")),
    }


def event_family(article: dict[str, Any]) -> str | None:
    # 事件识别以 agent 提取为准，不再用正则猜测事件类别。
    return FAMILY_EVENT_TYPES.get(article.get("event_type", ""))


def is_signal_candidate(article: dict[str, Any], family: str) -> bool:
    """Require both a healthcare boundary match and a concrete event action."""
    text = f"{article['title']} {article['summary']}"
    if PLACEHOLDER_PATTERN.search(text) or OUT_OF_SCOPE_PATTERN.search(text):
        return False
    if not MEDICAL_RELEVANCE_PATTERN.search(text):
        return False
    if RESEARCH_FORMAT_PATTERN.search(article["title"]):
        concrete_action = {
            "financing": re.compile(r"完成|获得|获|领投|签署|收购|并购|IPO", re.I),
            "regulatory": re.compile(r"获批|批准|受理|拒绝|撤回|暂停|上市许可", re.I),
            "clinical": re.compile(r"启动|入组|完成|达到|未达|揭盲|终止|暂停|结果", re.I),
        }[family]
        if not concrete_action.search(text):
            return False
    return True


def watchlist_matches(
    article: dict[str, Any], watchlist: dict[str, list[str]]
) -> list[tuple[str, str]]:
    haystack = f"{article['title']} {article['summary']}".casefold()
    matches: list[tuple[str, str]] = []
    for key, entity_type in WATCHLIST_KEYS.items():
        for name in watchlist.get(key, []):
            if name.casefold() in haystack:
                matches.append((entity_type, name))
    return matches


def article_entities(
    article: dict[str, Any], watchlist: dict[str, list[str]]
) -> list[tuple[str, str, bool]]:
    values: list[tuple[str, str, bool]] = []
    matched = {(entity_type, name) for entity_type, name in watchlist_matches(article, watchlist)}
    values.extend(("company", name, ("company", name) in matched) for name in article["companies"])
    values.extend(("investor", name, ("investor", name) in matched) for name in article.get("investors", []))
    values.extend(("drug", name, ("drug", name) in matched) for name in article["products"])
    values.extend((entity_type, name, True) for entity_type, name in matched)
    unique: dict[tuple[str, str], tuple[str, str, bool]] = {}
    for entity_type, name, is_watchlist in values:
        key = (entity_type, name.casefold())
        previous = unique.get(key)
        unique[key] = (
            entity_type,
            name,
            is_watchlist or bool(previous and previous[2]),
        )
    return list(unique.values())


def extract_event(article: dict[str, Any], family: str) -> dict[str, Any]:
    text = f"{article['title']} {article['summary']}"
    amount = article.get("amount_text") or (
        AMOUNT_PATTERN.search(text).group(0) if AMOUNT_PATTERN.search(text) else None
    )
    round_match = article.get("financing_round") or (
        ROUND_PATTERN.search(text).group(0) if ROUND_PATTERN.search(text) else None
    )
    regulator = article.get("regulator") or (
        REGULATOR_PATTERN.search(text).group(0) if REGULATOR_PATTERN.search(text) else None
    )
    decision = article.get("decision") or (
        DECISION_PATTERN.search(text).group(0) if DECISION_PATTERN.search(text) else None
    )
    phase = article.get("clinical_phase")
    if not phase and PHASE_PATTERN.search(text):
        phase = PHASE_PATTERN.search(text).group(0)
    phase_text = (
        re.sub(r"临床$", "", phase, flags=re.IGNORECASE) if phase else None
    )
    product_name = article.get("product_name")
    indication = article.get("indication")
    trial_id = article.get("trial_id")
    negative = bool(NEGATIVE_PATTERN.search(text))
    positive = bool(POSITIVE_PATTERN.search(text))
    clinical_outcome = article.get("clinical_outcome") or (
        NEGATIVE_PATTERN.search(text).group(0)
        if negative and family == "clinical"
        else POSITIVE_PATTERN.search(text).group(0)
        if positive and family == "clinical"
        else None
    )
    direction = "mixed" if negative and positive else "negative" if negative else "positive" if positive else "neutral"
    if family == "clinical":
        horizon = "中期" if phase_text and re.search(r"III|Ⅲ|三|3", phase_text, re.I) else "长期"
    elif family == "regulatory":
        horizon = "近期"
    else:
        horizon = "近期至中期"
    rating = article["source_rating"]
    base_confidence = {"A": 0.88, "B": 0.72, "C": 0.55}.get(rating, 0.60)
    classification_confidence = article["classification_confidence"]
    if classification_confidence:
        base_confidence = (base_confidence * 0.7) + (classification_confidence * 0.3)
    if PLACEHOLDER_PATTERN.search(text):
        base_confidence = min(base_confidence, 0.35)
    details = {
        "amount_text": amount if amount and family == "financing" else None,
        "financing_round": (
            round_match if round_match and family == "financing" else None
        ),
        "regulator": (regulator.upper() if regulator and family == "regulatory" else None),
        "decision": (decision if decision and family == "regulatory" else None),
        "product_name": (product_name if family in ("regulatory", "clinical") else None),
        "indication": (indication if family in ("regulatory", "clinical") else None),
        "trial_id": (trial_id if family == "clinical" else None),
        "clinical_phase": phase_text if family == "clinical" else None,
        "clinical_outcome": (clinical_outcome if family == "clinical" else None),
    }
    return {
        "id": stable_id("event", family, article["id"]),
        "event_family": family,
        "event_type": article["event_type"] or FAMILY_LABELS[family],
        "title": article["title"],
        "event_date": article["published_date"],
        "impact_direction": direction,
        "impact_horizon": horizon,
        "confidence": round(base_confidence, 4),
        **details,
    }


def evidence_status(article: dict[str, Any]) -> str:
    text = f"{article['title']} {article['summary']}"
    if PLACEHOLDER_PATTERN.search(text) or not article["url"]:
        return "unverified"
    if article["source_rating"] == "A" or article["source_type"] in {
        "government",
        "company",
        "exchange",
        "journal",
    }:
        return "primary"
    return "secondary"


def materiality_score(event: dict[str, Any], text: str) -> int:
    if event["event_family"] == "financing":
        score = 18
        if event["amount_text"]:
            score += 7
        if re.search(r"并购|收购|IPO|授权", text, re.I):
            score += 5
    elif event["event_family"] == "regulatory":
        score = 22
        if event["decision"] in {"获批", "批准", "拒绝", "上市许可", "注册证"}:
            score += 8
    else:
        score = 16
        if event["clinical_phase"]:
            score += 5
        if re.search(r"III|Ⅲ|三期|3期|主要终点|失败|终止", text, re.I):
            score += 9
    return min(score, 30)


def historical_context(
    connection: sqlite3.Connection,
    report_date: str,
    family_counts: Counter[str],
) -> dict[str, tuple[int, str]]:
    prior_days = connection.execute(
        """
        SELECT COUNT(DISTINCT report_date)
        FROM report_runs
        WHERE report_date < ? AND status IN ('healthy', 'partial')
        """,
        (report_date,),
    ).fetchone()[0]
    if prior_days < 7:
        return {
            family: (0, f"历史基线不足（已有 {prior_days} 个历史日报日，至少需要 7 日）")
            for family in FAMILY_LABELS
        }
    rows = connection.execute(
        """
        SELECT event_family, COUNT(*) AS total
        FROM events
        WHERE event_date >= date(?, '-30 day') AND event_date < ?
        GROUP BY event_family
        """,
        (report_date, report_date),
    ).fetchall()
    totals = {row["event_family"]: row["total"] for row in rows}
    result: dict[str, tuple[int, str]] = {}
    denominator = min(prior_days, 30)
    for family in FAMILY_LABELS:
        average = totals.get(family, 0) / denominator
        current = family_counts.get(family, 0)
        if average and current >= max(2, average * 1.5):
            result[family] = (
                10,
                f"今日 {current} 条，高于近 {denominator} 个历史日报日均值 {average:.1f}",
            )
        else:
            result[family] = (
                0,
                f"今日 {current} 条；近 {denominator} 个历史日报日均值 {average:.1f}",
            )
    return result


def why_important(
    event: dict[str, Any], entities: list[tuple[str, str, bool]], watched: bool
) -> str:
    detail = {
        "financing": "可能改变相关企业的资金可用性、交易边界或管线推进节奏",
        "regulatory": "可能直接影响产品商业化进度、可及市场或合规风险",
        "clinical": "可能改变研发成功概率、后续试验路径或管线时间表",
    }[event["event_family"]]
    names = "、".join(name for _, name, _ in entities[:3])
    prefix = f"涉及 {names}；" if names else ""
    watch = "命中关注名单；" if watched else ""
    return f"{watch}{prefix}{detail}。"


def persist_article(
    connection: sqlite3.Connection,
    article: dict[str, Any],
    entities: list[tuple[str, str, bool]],
    observed_at: str,
) -> list[str]:
    connection.execute(
        """
        INSERT INTO articles(
            id, canonical_url, title, summary, source_name, source_rating,
            source_type, published_at, collected_at, level_1_category,
            level_2_category, classification_method, classification_confidence,
            raw_json, first_seen_at, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            canonical_url=excluded.canonical_url,
            title=excluded.title,
            summary=excluded.summary,
            source_name=excluded.source_name,
            source_rating=excluded.source_rating,
            source_type=excluded.source_type,
            published_at=excluded.published_at,
            collected_at=excluded.collected_at,
            level_1_category=excluded.level_1_category,
            level_2_category=excluded.level_2_category,
            classification_method=excluded.classification_method,
            classification_confidence=excluded.classification_confidence,
            raw_json=excluded.raw_json,
            last_seen_at=excluded.last_seen_at
        """,
        (
            article["id"],
            article["url"],
            article["title"],
            article["summary"],
            article["source"],
            article["source_rating"],
            article["source_type"],
            article["publish_time"],
            clean_text(article.get("collected_at")) or observed_at,
            article["level_1_category"],
            article["level_2_category"],
            article["classification_method"],
            article["classification_confidence"],
            json.dumps(article, ensure_ascii=False, sort_keys=True),
            observed_at,
            observed_at,
        ),
    )
    entity_ids: list[str] = []
    for entity_type, name, is_watchlist in entities:
        normalized = name.casefold()
        entity_id = stable_id("entity", entity_type, normalized)
        connection.execute(
            """
            INSERT INTO entities(id, entity_type, canonical_name, normalized_name, watchlist)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(entity_type, normalized_name) DO UPDATE SET
                canonical_name=excluded.canonical_name,
                watchlist=MAX(entities.watchlist, excluded.watchlist)
            """,
            (entity_id, entity_type, name, normalized, int(is_watchlist)),
        )
        row = connection.execute(
            "SELECT id FROM entities WHERE entity_type=? AND normalized_name=?",
            (entity_type, normalized),
        ).fetchone()
        stored_entity_id = row["id"]
        entity_ids.append(stored_entity_id)
        connection.execute(
            """
            INSERT INTO article_entities(article_id, entity_id, mention)
            VALUES (?, ?, ?)
            ON CONFLICT(article_id, entity_id) DO UPDATE SET mention=excluded.mention
            """,
            (article["id"], stored_entity_id, name),
        )
    return entity_ids


def persist_event(
    connection: sqlite3.Connection,
    event: dict[str, Any],
    article: dict[str, Any],
    entities: list[tuple[str, str, bool]],
    entity_ids: list[str],
    observed_at: str,
) -> None:
    details = {
        key: event[key]
        for key in (
            "amount_text",
            "financing_round",
            "regulator",
            "decision",
            "clinical_phase",
            "clinical_outcome",
            "product_name",
            "indication",
            "trial_id",
        )
    }
    connection.execute(
        """
        INSERT INTO events(
            id, event_family, event_type, title, event_date, amount_text,
            financing_round, regulator, decision, clinical_phase,
            clinical_outcome, product_name, indication, trial_id,
            impact_direction, impact_horizon, confidence, track,
            details_json, first_seen_at, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            event_type=excluded.event_type,
            title=excluded.title,
            event_date=excluded.event_date,
            amount_text=excluded.amount_text,
            financing_round=excluded.financing_round,
            regulator=excluded.regulator,
            decision=excluded.decision,
            clinical_phase=excluded.clinical_phase,
            clinical_outcome=excluded.clinical_outcome,
            product_name=excluded.product_name,
            indication=excluded.indication,
            trial_id=excluded.trial_id,
            impact_direction=excluded.impact_direction,
            impact_horizon=excluded.impact_horizon,
            confidence=excluded.confidence,
            track=excluded.track,
            details_json=excluded.details_json,
            last_seen_at=excluded.last_seen_at
        """,
        (
            event["id"],
            event["event_family"],
            event["event_type"],
            event["title"],
            event["event_date"],
            event["amount_text"],
            event["financing_round"],
            event["regulator"],
            event["decision"],
            event["clinical_phase"],
            event["clinical_outcome"],
            event["product_name"],
            event["indication"],
            event["trial_id"],
            event["impact_direction"],
            event["impact_horizon"],
            event["confidence"],
            article.get("track"),
            json.dumps(details, ensure_ascii=False, sort_keys=True),
            observed_at,
            observed_at,
        ),
    )
    connection.execute(
        """
        INSERT INTO event_sources(event_id, article_id, evidence_status, source_rating)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(event_id, article_id) DO UPDATE SET
            evidence_status=excluded.evidence_status,
            source_rating=excluded.source_rating
        """,
        (event["id"], article["id"], evidence_status(article), article["source_rating"]),
    )
    for (entity_type, _, _), entity_id in zip(entities, entity_ids):
        role = "investor" if entity_type == "investor" else "affected"
        connection.execute(
            """
            INSERT INTO event_entities(event_id, entity_id, role)
            VALUES (?, ?, ?)
            ON CONFLICT(event_id, entity_id) DO UPDATE SET role=excluded.role
            """,
            (event["id"], entity_id, role),
        )


def compute_coverage(
    articles: Iterable[dict[str, Any]], failures: list[dict[str, Any]]
) -> tuple[float, int, int]:
    successful = {article["source"] for article in articles if article["source"]}
    failed = {
        clean_text(failure.get("source"))
        for failure in failures
        if clean_text(failure.get("source"))
    }
    denominator = len(successful | failed)
    coverage = len(successful) / denominator if denominator else 0.0
    return coverage, len(successful), len(failed)


def fetch_report_signals(
    connection: sqlite3.Connection, report_date: str
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            s.*, e.event_family, e.event_type, e.title, e.event_date,
            e.amount_text, e.financing_round, e.regulator, e.decision,
            e.clinical_phase, e.clinical_outcome, e.impact_direction,
            e.impact_horizon, e.track, e.product_name, e.indication, e.trial_id,
            e.details_json, a.source_name, a.canonical_url,
            a.source_rating, es.evidence_status,
            COALESCE(GROUP_CONCAT(DISTINCT en.canonical_name), '') AS entity_names,
            COALESCE(GROUP_CONCAT(DISTINCT CASE WHEN en.entity_type='company' THEN en.canonical_name END), '') AS company_names,
            COALESCE(GROUP_CONCAT(DISTINCT CASE WHEN en.entity_type='investor' THEN en.canonical_name END), '') AS investor_names,
            MAX(COALESCE(en.watchlist, 0)) AS watchlist_hit
        FROM signals s
        JOIN events e ON e.id=s.event_id
        JOIN event_sources es ON es.event_id=e.id
        JOIN articles a ON a.id=es.article_id
        LEFT JOIN event_entities ee ON ee.event_id=e.id
        LEFT JOIN entities en ON en.id=ee.entity_id
        WHERE s.report_date=?
        GROUP BY s.id
        ORDER BY s.total_score DESC, e.event_date DESC, e.title
        """,
        (report_date,),
    ).fetchall()
    return [dict(row) for row in rows]


def event_detail(signal: dict[str, Any]) -> str:
    parts = [
        signal.get("amount_text"),
        signal.get("financing_round"),
        signal.get("regulator"),
        signal.get("decision"),
        signal.get("clinical_phase"),
        signal.get("clinical_outcome"),
    ]
    return " / ".join(markdown_text(part) for part in parts if clean_text(part)) or "未披露"


def select_top_signals(
    signals: list[dict[str, Any]], top_limit: int
) -> list[dict[str, Any]]:
    """Keep Top Signals score-led while guaranteeing family representation."""
    eligible = [signal for signal in signals if signal["canonical_url"]]
    if not eligible:
        return []
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    family_target = max(1, min(2, top_limit // len(FAMILY_LABELS)))
    for family in FAMILY_LABELS:
        candidates = [
            signal for signal in eligible if signal["event_family"] == family
        ][:family_target]
        for signal in candidates:
            selected.append(signal)
            selected_ids.add(signal["id"])
    for signal in eligible:
        if len(selected) >= top_limit:
            break
        if signal["id"] not in selected_ids:
            selected.append(signal)
            selected_ids.add(signal["id"])
    return sorted(
        selected,
        key=lambda signal: (
            -signal["total_score"],
            signal["event_date"],
            signal["title"],
        ),
    )[:top_limit]


def render_report(
    report_date: str,
    status: str,
    coverage: float,
    successful_sources: int,
    failed_sources: int,
    articles: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    top_limit: int,
) -> str:
    top = select_top_signals(signals, top_limit)
    family_counts = Counter(signal["event_family"] for signal in signals)
    category_counts = Counter(article["level_1_category"] for article in articles)
    lines = [
        f"# 医疗健康行业每日情报｜{report_date}",
        "",
        f"> 运行状态：`{status}`｜来源覆盖率：{coverage:.1%}（成功 {successful_sources}，失败 {failed_sources}）"
        "｜当前为影子运行，本报告不构成投资、交易或医疗建议。",
        "",
        "## Top Signals",
        "",
    ]
    if top:
        for index, signal in enumerate(top, 1):
            lines.extend(
                [
                    f"{index}. [{markdown_text(signal['title'])}]({signal['canonical_url']})"
                    f" — **{signal['total_score']}/100**，{FAMILY_LABELS[signal['event_family']]}，"
                    f"方向：{signal['impact_direction']}，时间尺度：{signal['impact_horizon']}，"
                    f"置信度：{signal['confidence']:.0%}",
                    f"   - 依据：重要性 {signal['materiality_score']}/30；关注名单 "
                    f"{signal['watchlist_score']}/25；新颖性 {signal['novelty_score']}/20；"
                    f"证据 {signal['evidence_score']}/15；趋势 {signal['trend_score']}/10。",
                    f"   - 解读：{signal['why_important']} 历史变化：{signal['history_change']}。",
                    f"   - 证据：{signal['source_name']}（{signal['source_rating']}级，"
                    f"{signal['evidence_status']}）；结构化详情：{event_detail(signal)}。",
                    "",
                ]
            )
    else:
        lines.extend(["本窗口暂无同时满足事件边界和有效来源链接的高优先级信号。", ""])

    watch_hits = [signal for signal in signals if signal["watchlist_hit"]]
    lines.extend(["## 关注名单命中", ""])
    if watch_hits:
        for signal in watch_hits:
            lines.append(
                f"- {markdown_text(signal['entity_names'])}："
                f"[{markdown_text(signal['title'])}]({signal['canonical_url']})"
            )
    else:
        lines.append("- 本窗口无关注名单命中。")
    lines.append("")

    for family in ("financing", "regulatory", "clinical"):
        rows = [signal for signal in signals if signal["event_family"] == family]
        if family == "financing":
            lines.extend(
                [
                    f"## {FAMILY_LABELS[family]}事件",
                    "",
                    "| 日期 | 公司 | 类型 | 轮次/资产 | 金额 | 交易方/投资方 | 赛道 | 来源 |",
                    "|---|---|---|---|---|---|---|---|",
                ]
            )
            if not rows:
                lines.append("| — | 本窗口无记录 | — | — | — | — | — | — |")
            for signal in rows:
                source = (
                    f"[{markdown_text(signal['source_name'])}]({signal['canonical_url']})"
                    if signal["canonical_url"]
                    else markdown_text(signal["source_name"])
                )
                event_type = signal["event_type"]
                if not event_type or event_type == "融资交易":
                    event_type = "融资"
                company = markdown_text(signal["company_names"]) or "未识别"
                investors = markdown_text(signal["investor_names"]) or "—"
                track = markdown_text(signal["track"]) or "—"
                lines.append(
                    f"| {signal['event_date']} | {company} | {markdown_text(event_type)} | "
                    f"{markdown_text(signal['financing_round']) or '—'} | "
                    f"{markdown_text(signal['amount_text']) or '未披露'} | "
                    f"{investors} | {track} | {source} |"
                )
        elif family == "regulatory":
            lines.extend(
                [
                    f"## {FAMILY_LABELS[family]}事件",
                    "",
                    "| 日期 | 公司 | 产品 | 适应症 | 监管机构 | 决定 | 来源 |",
                    "|---|---|---|---|---|---|---|",
                ]
            )
            if not rows:
                lines.append("| — | 本窗口无记录 | — | — | — | — | — |")
            for signal in rows:
                source = (
                    f"[{markdown_text(signal['source_name'])}]({signal['canonical_url']})"
                    if signal["canonical_url"]
                    else markdown_text(signal["source_name"])
                )
                lines.append(
                    f"| {signal['event_date']} | "
                    f"{markdown_text(signal['company_names']) or '未识别'} | "
                    f"{markdown_text(signal['product_name']) or '—'} | "
                    f"{markdown_text(signal['indication']) or '—'} | "
                    f"{markdown_text(signal['regulator']) or '—'} | "
                    f"{markdown_text(signal['decision']) or '—'} | {source} |"
                )
        else:
            lines.extend(
                [
                    f"## {FAMILY_LABELS[family]}事件",
                    "",
                    "| 日期 | 公司/申办方 | 资产 | 试验编号 | 阶段 | 状态/数据 | 来源 |",
                    "|---|---|---|---|---|---|---|",
                ]
            )
            if not rows:
                lines.append("| — | 本窗口无记录 | — | — | — | — | — |")
            for signal in rows:
                source = (
                    f"[{markdown_text(signal['source_name'])}]({signal['canonical_url']})"
                    if signal["canonical_url"]
                    else markdown_text(signal["source_name"])
                )
                lines.append(
                    f"| {signal['event_date']} | "
                    f"{markdown_text(signal['company_names']) or '未识别'} | "
                    f"{markdown_text(signal['product_name']) or '—'} | "
                    f"{markdown_text(signal['trial_id']) or '—'} | "
                    f"{markdown_text(signal['clinical_phase']) or '—'} | "
                    f"{markdown_text(signal['clinical_outcome']) or '—'} | {source} |"
                )
        lines.append("")

    lines.extend(["## 趋势与结构", ""])
    lines.append(
        "- 三类事件分布："
        + "；".join(
            f"{FAMILY_LABELS[family]} {family_counts.get(family, 0)} 条"
            for family in FAMILY_LABELS
        )
        + "。"
    )
    lines.append(
        "- 赛道分布："
        + (
            "；".join(
                f"{category} {count} 篇"
                for category, count in category_counts.most_common()
            )
            if category_counts
            else "本窗口无文章"
        )
        + "。"
    )
    lines.append("- 趋势分数仅在至少 7 个历史日报日后启用，避免短历史造成伪趋势。")
    lines.append("")

    low_confidence = [signal for signal in signals if signal["confidence"] < 0.60]
    lines.extend(["## 待核实事项", ""])
    if status == "partial":
        lines.append(
            f"- 来源覆盖率 {coverage:.1%} 低于 95% 目标，本日报为 `partial`，不应视为完整市场扫描。"
        )
    for failure in failures:
        lines.append(
            f"- {markdown_text(failure.get('source') or '未知来源')}："
            f"{markdown_text(failure.get('error_category') or failure.get('error_detail') or '采集失败')}"
        )
    for signal in low_confidence:
        lines.append(
            f"- 低置信度：{markdown_text(signal['title'])}（{signal['confidence']:.0%}）。"
        )
    if status != "partial" and not failures and not low_confidence:
        lines.append("- 本窗口无新增待核实事项。")
    lines.append("")

    lines.extend(["## 完整附录", ""])
    if not articles:
        lines.append("- 本窗口无文章。")
    for article in sorted(
        articles, key=lambda item: (item["publish_time"], item["title"]), reverse=True
    ):
        title = markdown_text(article["title"]) or "无标题"
        linked = f"[{title}]({article['url']})" if article["url"] else title
        lines.append(
            f"- {article['publish_time'] or article['published_date']}｜"
            f"{markdown_text(article['source'])}｜{markdown_text(article['level_1_category'])}"
            f" / {markdown_text(article['level_2_category'])}｜{linked}"
        )
    lines.extend(
        [
            "",
            "---",
            "",
            "方法说明：评分由重要性（30）、关注名单（25）、新颖性（20）、"
            "证据质量（15）和趋势变化（10）组成。缺失字段保持为空，不由模型臆测补齐。",
            "",
        ]
    )
    return "\n".join(lines)


def process_payload(
    payload: dict[str, Any],
    *,
    database_path: Path = DEFAULT_DATABASE,
    report_dir: Path = DEFAULT_REPORT_DIR,
    report_date: dt.date | None = None,
    watchlist_path: Path | None = None,
    coverage_threshold: float = 0.95,
    top_limit: int = 10,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    current_time = now or dt.datetime.now(TIMEZONE)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=TIMEZONE)
    selected_date = report_date or current_time.astimezone(TIMEZONE).date()
    date_text = selected_date.isoformat()
    observed_at = current_time.astimezone(dt.timezone.utc).isoformat()
    watchlist = load_watchlist(watchlist_path)
    raw_articles = payload.get("articles", [])
    if not isinstance(raw_articles, list):
        raise ValueError("payload.articles must be a list")
    failures = payload.get("failures", [])
    if not isinstance(failures, list):
        failures = []
    normalized = [normalize_article(article, selected_date) for article in raw_articles]
    deduplicated = list({article["id"]: article for article in normalized}.values())
    coverage, successful_sources, failed_sources = compute_coverage(deduplicated, failures)
    status = "healthy" if coverage >= coverage_threshold else "partial"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"healthcare_daily_{date_text}.md"
    connection = connect_database(database_path)
    started_at = observed_at
    event_records: list[tuple[dict[str, Any], dict[str, Any], list[tuple[str, str, bool]]]] = []
    try:
        with connection:
            connection.execute("DELETE FROM signals WHERE report_date=?", (date_text,))
            for article in deduplicated:
                connection.execute(
                    """
                    DELETE FROM event_sources
                    WHERE article_id=?
                      AND event_id NOT IN (SELECT event_id FROM signals)
                    """,
                    (article["id"],),
                )
                connection.execute(
                    "DELETE FROM article_entities WHERE article_id=?", (article["id"],)
                )
            connection.execute(
                """
                DELETE FROM events
                WHERE NOT EXISTS (
                    SELECT 1 FROM event_sources es WHERE es.event_id=events.id
                )
                  AND NOT EXISTS (
                    SELECT 1 FROM signals s WHERE s.event_id=events.id
                )
                """
            )
            for article in deduplicated:
                entities = article_entities(article, watchlist)
                entity_ids = persist_article(connection, article, entities, observed_at)
                family = event_family(article)
                if not family or not is_signal_candidate(article, family):
                    continue
                event = extract_event(article, family)
                persist_event(connection, event, article, entities, entity_ids, observed_at)
                event_records.append((event, article, entities))

            family_counts = Counter(event["event_family"] for event, _, _ in event_records)
            history = historical_context(connection, date_text, family_counts)
            for event, article, entities in event_records:
                watched = any(is_watchlist for _, _, is_watchlist in entities)
                materiality = materiality_score(
                    event, f"{article['title']} {article['summary']}"
                )
                watch_score = 25 if watched else 0
                novelty = 20 if event["event_date"] == date_text else 10
                evidence = SOURCE_RATING_POINTS.get(article["source_rating"], 5)
                if evidence_status(article) == "unverified":
                    evidence = min(evidence, 3)
                trend, change = history[event["event_family"]]
                total = materiality + watch_score + novelty + evidence + trend
                signal_id = stable_id("signal", date_text, event["id"])
                connection.execute(
                    """
                    INSERT INTO signals(
                        id, report_date, event_id, total_score, materiality_score,
                        watchlist_score, novelty_score, evidence_score, trend_score,
                        why_important, history_change, confidence, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(report_date, event_id) DO UPDATE SET
                        total_score=excluded.total_score,
                        materiality_score=excluded.materiality_score,
                        watchlist_score=excluded.watchlist_score,
                        novelty_score=excluded.novelty_score,
                        evidence_score=excluded.evidence_score,
                        trend_score=excluded.trend_score,
                        why_important=excluded.why_important,
                        history_change=excluded.history_change,
                        confidence=excluded.confidence
                    """,
                    (
                        signal_id,
                        date_text,
                        event["id"],
                        total,
                        materiality,
                        watch_score,
                        novelty,
                        evidence,
                        trend,
                        why_important(event, entities, watched),
                        change,
                        event["confidence"],
                        observed_at,
                    ),
                )

            signals = fetch_report_signals(connection, date_text)
            report_content = render_report(
                date_text,
                status,
                coverage,
                successful_sources,
                failed_sources,
                deduplicated,
                failures,
                signals,
                top_limit,
            )
            report_path.write_text(report_content, encoding="utf-8")
            connection.execute(
                """
                INSERT INTO report_runs(
                    run_id, report_date, status, coverage, article_count,
                    event_count, signal_count, report_path, failures_json,
                    started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_date) DO UPDATE SET
                    status=excluded.status,
                    coverage=excluded.coverage,
                    article_count=excluded.article_count,
                    event_count=excluded.event_count,
                    signal_count=excluded.signal_count,
                    report_path=excluded.report_path,
                    failures_json=excluded.failures_json,
                    completed_at=excluded.completed_at
                """,
                (
                    stable_id("run", date_text),
                    date_text,
                    status,
                    coverage,
                    len(deduplicated),
                    len(event_records),
                    len(signals),
                    str(report_path),
                    json.dumps(failures, ensure_ascii=False, sort_keys=True),
                    started_at,
                    observed_at,
                ),
            )
    finally:
        connection.close()
    return {
        "status": status,
        "mode": "shadow",
        "report_date": date_text,
        "coverage": round(coverage, 4),
        "articles": len(deduplicated),
        "events": len(event_records),
        "signals": len(signals),
        "database_path": str(database_path),
        "report_path": str(report_path),
        "delivery": {"status": "disabled", "reason": "shadow mode; use --send explicitly"},
    }


def search_events(
    database_path: Path,
    *,
    query: str = "",
    family: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Read-only event search interface reserved for a future Agent/RAG layer."""
    connection = connect_readonly_database(database_path)
    try:
        clauses: list[str] = []
        values: list[Any] = []
        if query:
            clauses.append("(e.title LIKE ? OR en.canonical_name LIKE ?)")
            values.extend([f"%{query}%", f"%{query}%"])
        if family:
            clauses.append("e.event_family=?")
            values.append(family)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        values.append(max(1, min(limit, 500)))
        rows = connection.execute(
            f"""
            SELECT e.*, GROUP_CONCAT(DISTINCT en.canonical_name) AS entity_names
            FROM events e
            LEFT JOIN event_entities ee ON ee.event_id=e.id
            LEFT JOIN entities en ON en.id=ee.entity_id
            {where}
            GROUP BY e.id
            ORDER BY e.event_date DESC, e.last_seen_at DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_entity_history(
    database_path: Path, entity_name: str, limit: int = 100
) -> list[dict[str, Any]]:
    """Read-only entity timeline interface reserved for future structured Q&A."""
    connection = connect_readonly_database(database_path)
    try:
        rows = connection.execute(
            """
            SELECT e.*, en.canonical_name, en.entity_type
            FROM entities en
            JOIN event_entities ee ON ee.entity_id=en.id
            JOIN events e ON e.id=ee.event_id
            WHERE en.normalized_name=?
            ORDER BY e.event_date DESC
            LIMIT ?
            """,
            (entity_name.casefold(), max(1, min(limit, 500))),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_event_evidence(database_path: Path, event_id: str) -> list[dict[str, Any]]:
    """Read-only provenance interface reserved for future evidence-backed answers."""
    connection = connect_readonly_database(database_path)
    try:
        rows = connection.execute(
            """
            SELECT a.source_name, a.canonical_url, a.title, a.published_at,
                   es.source_rating, es.evidence_status
            FROM event_sources es
            JOIN articles a ON a.id=es.article_id
            WHERE es.event_id=?
            ORDER BY es.source_rating, a.published_at DESC
            """,
            (event_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def collect_payload(report_date: dt.date) -> dict[str, Any]:
    from dashboard_scraper import scrape_all

    window_end = dt.datetime.combine(report_date, dt.time(9, 0))
    window_start = window_end - dt.timedelta(hours=48)
    payload = scrape_all(window_start=window_start, window_end=window_end)
    payload["time_window"] = {
        "start": window_start.isoformat(),
        "end": window_end.isoformat(),
    }
    return payload


def deliver_report(
    config_path: Path, report_path: Path, confirm_first_send: bool
) -> dict[str, Any]:
    try:
        from healthcare_intelligence import deliver_digest
        return deliver_digest(config_path, report_path, confirm_first_send)
    except ImportError:
        return {"status": "delivery-unavailable", "message": "deliver_digest not available (healthcare_intelligence.py simplified to config-only)"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Existing scraper JSON; omit to collect")
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--watchlist", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--date", help="Report date in YYYY-MM-DD; defaults to today")
    parser.add_argument("--coverage-threshold", type=float, default=0.95)
    parser.add_argument("--top-signals", type=int, default=10)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--confirm-first-send", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report_date = (
            dt.date.fromisoformat(args.date)
            if args.date
            else dt.datetime.now(TIMEZONE).date()
        )
        runtime_root = args.runtime_root.expanduser().resolve()
        database = args.database or runtime_root / "intelligence" / "healthcare_intelligence.sqlite3"
        report_dir = args.report_dir or runtime_root / "reports"
        watchlist = args.watchlist
        if watchlist is None and (runtime_root / "watchlist.json").exists():
            watchlist = runtime_root / "watchlist.json"
        payload = load_json(args.input.resolve(), {}) if args.input else collect_payload(report_date)
        result = process_payload(
            payload,
            database_path=database,
            report_dir=report_dir,
            report_date=report_date,
            watchlist_path=watchlist,
            coverage_threshold=args.coverage_threshold,
            top_limit=max(5, min(args.top_signals, 10)),
        )
        if args.send:
            config = args.config or runtime_root / "config.yaml"
            result["delivery"] = deliver_report(
                config.resolve(),
                Path(result["report_path"]),
                args.confirm_first_send,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"healthy", "partial"} else 1
    except (OSError, ValueError, RuntimeError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(
            json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
