#!/usr/bin/env python3
"""Portable Healthcare source monitor, digest generator, and mail dispatcher."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import gzip
import hashlib
import html
import json
import os
import random
import re
import shutil
import smtplib
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "风险事件",
        (
            "失败",
            "未达",
            "终止",
            "召回",
            "处罚",
            "暂停",
            "退市",
            "造假",
            "严重不良",
            "警告信",
            "撤回",
        ),
    ),
    (
        "一级市场投融资与投资事件",
        ("融资", "A轮", "B轮", "C轮", "Pre-IPO", "Pre-A", "投资", "并购", "收购", "基金"),
    ),
    (
        "创新药研发事件",
        ("新药", "管线", "临床试验", "IND", "I期", "II期", "III期", "三期", "入组", "授权"),
    ),
    (
        "药品/器械审批事件",
        ("获批", "批准", "受理", "上市许可", "NMPA", "FDA", "CE认证", "注册证"),
    ),
    (
        "医疗器械动态",
        ("医疗器械", "设备", "IVD", "手术机器人", "检测试剂", "影像设备"),
    ),
    (
        "政策监管",
        ("政策", "监管", "医保", "集采", "目录", "指导意见", "合规", "条例"),
    ),
    (
        "市场数据",
        ("销售额", "市场规模", "份额", "同比", "终端", "价格", "渗透率"),
    ),
    (
        "企业动态",
        ("合作", "战略", "人事", "管理层", "业绩", "产能", "任命", "签约"),
    ),
    (
        "学术与技术突破",
        (
            "论文",
            "研究",
            "综述",
            "揭示",
            "机制",
            "技术突破",
            "Nature",
            "Science",
            "Cell",
            "Sci Adv",
            "新技术",
            "新机制",
        ),
    ),
    (
        "二级市场与研究观点",
        ("股价", "上市公司", "港股", "A股", "研报", "券商", "评级", "目标价"),
    ),
]
CATEGORY_ORDER = {name: index for index, (name, _) in enumerate(CATEGORY_RULES)}
SETUP_ALWAYS_REQUIRED = {
    "setup.sources_confirmed",
    "collection_window_hours",
    "schedule.enabled",
    "timezone",
    "delivery.enabled",
    "ai.mode",
    "output_dir",
    "retention.raw_days",
    "retention.log_days",
}
SETUP_SCHEDULE_REQUIRED = {
    "schedule.frequency",
    "schedule.time",
    "schedule.catch_up_once",
}
SETUP_DELIVERY_REQUIRED = {
    "delivery.adapters",
    "delivery.recipients",
}
GENERIC_ENTITY_TRIGRAMS = {
    "完成融",
    "轮融资",
    "数亿元",
    "创新药",
    "临床试",
    "床试验",
    "主要终",
    "要终点",
    "医疗器",
    "疗器械",
    "研究发",
    "究发现",
    "公司公",
    "司公告",
}
LINK_RE = re.compile(r"/news/detail/", re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")


def clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", html.unescape(value or "")).strip()


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(default)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_config(path: Path) -> dict[str, Any]:
    """Load JSON-formatted YAML without a dependency, or PyYAML when available."""
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError(
                "config.yaml is not JSON-formatted YAML; install PyYAML or use the provided template"
            ) from exc
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("configuration root must be an object")
    return data


def load_env_file(path: Path) -> dict[str, str]:
    values = dict(os.environ)
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in values:
            values[key] = value
    return values


def resolve_path(config_path: Path, value: str | Path) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else (config_path.parent / candidate).resolve()


def runtime_paths(config_path: Path, config: dict[str, Any]) -> dict[str, Path]:
    root = resolve_path(config_path, config.get("output_dir", "."))
    return {
        "root": root,
        "data": root / "data",
        "raw": root / "raw",
        "state": root / "state",
        "outbox": root / "outbox",
        "logs": root / "logs",
    }


def ensure_runtime(paths: dict[str, Path]) -> None:
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)


def parse_markdown_table(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    # Column name normalization for Chinese headers
    _cn_to_en = {"名称": "Name", "ByDrug 链接": "ByDrug URL", "类型": "Source Type", "等级": "Trust"}
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip().replace("\\|", "|") for cell in line.strip().strip("|").split("|")]
        if header is None and ("Name" in cells or "名称" in cells) and ("ByDrug URL" in cells or "ByDrug 链接" in cells):
            cells = [_cn_to_en.get(c, c) for c in cells]
            header = cells
            continue
        if header is None or all(set(cell) <= {"-", ":"} for cell in cells if cell):
            continue
        if len(cells) < len(header):
            cells.extend([""] * (len(header) - len(cells)))
        rows.append(dict(zip(header, cells)))
    return rows


def nested_get(config: dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    value: Any = config
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def nested_set(config: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    target: dict[str, Any] = config
    for part in parts[:-1]:
        child = target.get(part)
        if not isinstance(child, dict):
            child = {}
            target[part] = child
        target = child
    target[parts[-1]] = value


def required_setup_fields(config: dict[str, Any]) -> set[str]:
    required = set(SETUP_ALWAYS_REQUIRED)
    if truthy(nested_get(config, "schedule.enabled", False)):
        required.update(SETUP_SCHEDULE_REQUIRED)
    if truthy(nested_get(config, "delivery.enabled", False)):
        required.update(SETUP_DELIVERY_REQUIRED)
    return required


def confirmation_hash(config: dict[str, Any]) -> str:
    snapshot = copy.deepcopy(config)
    setup = snapshot.get("setup")
    if isinstance(setup, dict):
        for key in (
            "completed",
            "confirmed_at",
            "confirmed_fields",
            "config_hash",
            "sources_hash",
        ):
            setup.pop(key, None)
    canonical = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(canonical)


def setup_status(config_path: Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config(config_path)
    setup = config.get("setup") if isinstance(config.get("setup"), dict) else {}
    answered = {
        str(value) for value in setup.get("answered_fields", []) if str(value).strip()
    }
    required = required_setup_fields(config)
    missing = sorted(required - answered)
    errors: list[str] = []

    if setup.get("sources_confirmed") is not True:
        errors.append("数据源范围尚未确认（setup.sources_confirmed 必须为 true）")
    try:
        window = float(config.get("collection_window_hours", 0))
        if window <= 0:
            errors.append("collection_window_hours 必须大于 0")
    except (TypeError, ValueError):
        errors.append("collection_window_hours 必须是数字")
    try:
        ZoneInfo(str(config.get("timezone", "")))
    except (KeyError, ValueError, TypeError):
        errors.append("timezone 不是有效的 IANA 时区")
    if not str(config.get("output_dir", "")).strip():
        errors.append("output_dir 不能为空")
    for key in ("raw_days", "log_days"):
        try:
            if int(config.get("retention", {}).get(key, 0)) <= 0:
                errors.append(f"retention.{key} 必须大于 0")
        except (TypeError, ValueError):
            errors.append(f"retention.{key} 必须是整数")
    if not str(config.get("ai", {}).get("mode", "")).strip():
        errors.append("ai.mode 不能为空")

    schedule = config.get("schedule", {})
    if truthy(schedule.get("enabled", False)):
        if not str(schedule.get("frequency", "")).strip():
            errors.append("启用定时任务时 schedule.frequency 不能为空")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", str(schedule.get("time", ""))):
            errors.append("启用定时任务时 schedule.time 必须为 HH:MM")

    delivery = config.get("delivery", {})
    if truthy(delivery.get("enabled", False)):
        recipients = delivery.get("recipients", [])
        if not isinstance(recipients, list) or not recipients:
            errors.append("启用推送时 delivery.recipients 不能为空")
        else:
            invalid = [
                str(recipient)
                for recipient in recipients
                if "@" not in str(recipient)
                or str(recipient).lower().endswith("@example.com")
            ]
            if invalid:
                errors.append("收件人包含无效或示例邮箱：" + "、".join(invalid))
        adapters = delivery.get("adapters", [])
        if not isinstance(adapters, list) or not adapters:
            errors.append("启用推送时 delivery.adapters 不能为空")

    sources_path = resolve_path(config_path, config.get("sources_file", "sources.md"))
    if setup.get("sources_confirmed") is True:
        if not sources_path.exists():
            errors.append(f"数据源文件不存在：{sources_path}")
        else:
            enabled_sources = [
                row
                for row in parse_markdown_table(sources_path)
                if truthy(row.get("Enabled", "true"))
            ]
            if not enabled_sources:
                errors.append("数据源文件中没有启用的来源")

    completed = setup.get("completed") is True
    if completed:
        stored_hash = str(setup.get("config_hash", ""))
        current_hash = confirmation_hash(config)
        if not stored_hash:
            errors.append("已完成配置缺少确认指纹，必须重新确认")
        elif stored_hash != current_hash:
            errors.append("配置在用户确认后发生变化，必须重新确认")
        stored_sources_hash = str(setup.get("sources_hash", ""))
        if not stored_sources_hash:
            errors.append("已完成配置缺少数据源确认指纹，必须重新确认")
        elif sources_path.exists():
            current_sources_hash = sha256_text(
                sources_path.read_text(encoding="utf-8")
            )
            if stored_sources_hash != current_sources_hash:
                errors.append("数据源范围在用户确认后发生变化，必须重新确认")
    ready_to_finalize = not missing and not errors
    return {
        "completed": completed,
        "ready_to_finalize": ready_to_finalize,
        "valid": completed and ready_to_finalize,
        "missing_fields": missing,
        "errors": errors,
        "answered_fields": sorted(answered),
        "required_fields": sorted(required),
        "confirmed_at": setup.get("confirmed_at", ""),
        "config_path": str(config_path),
    }


def require_setup_complete(config_path: Path, config: dict[str, Any]) -> None:
    report = setup_status(config_path, config)
    if report["valid"]:
        return
    details = report["missing_fields"] + report["errors"]
    suffix = "；".join(details) if details else "尚未获得用户最终确认"
    raise RuntimeError(
        "初始化未完成，禁止联网采集或发送。"
        f"{suffix}。先运行 setup-status，逐项 configure，再由用户确认后运行 finalize-setup。"
    )


def parse_assignment_value(raw_value: str) -> Any:
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value


def configure_workspace(config_path: Path, assignments: list[str]) -> dict[str, Any]:
    if not assignments:
        raise RuntimeError("configure 至少需要一个 --set 路径=值")
    config = load_config(config_path)
    setup = config.setdefault("setup", {})
    if not isinstance(setup, dict):
        setup = {}
        config["setup"] = setup
    answered = {
        str(value) for value in setup.get("answered_fields", []) if str(value).strip()
    }
    protected = {"setup.completed", "setup.confirmed_at", "setup.confirmed_fields"}
    for assignment in assignments:
        if "=" not in assignment:
            raise RuntimeError(f"无效配置项（应为 路径=值）：{assignment}")
        dotted_path, raw_value = assignment.split("=", 1)
        dotted_path = dotted_path.strip()
        if not dotted_path or dotted_path in protected:
            raise RuntimeError(f"不允许通过 configure 修改：{dotted_path}")
        nested_set(config, dotted_path, parse_assignment_value(raw_value.strip()))
        answered.add(dotted_path)
    setup = config.setdefault("setup", {})
    setup["version"] = 1
    setup["completed"] = False
    setup["confirmed_at"] = ""
    setup["config_hash"] = ""
    setup["sources_hash"] = ""
    setup["confirmed_fields"] = []
    setup["answered_fields"] = sorted(answered)
    write_json(config_path, config)
    return setup_status(config_path, config)


def finalize_setup(config_path: Path, confirmed_by_user: bool) -> dict[str, Any]:
    if not confirmed_by_user:
        raise RuntimeError("必须在用户查看完整配置并明确确认后使用 --confirmed-by-user")
    config = load_config(config_path)
    report = setup_status(config_path, config)
    if not report["ready_to_finalize"]:
        details = report["missing_fields"] + report["errors"]
        raise RuntimeError("初始化配置不完整：" + "；".join(details))
    setup = config.setdefault("setup", {})
    setup["version"] = 1
    setup["completed"] = True
    setup["confirmed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    setup["confirmed_fields"] = report["answered_fields"]
    sources_path = resolve_path(config_path, config.get("sources_file", "sources.md"))
    setup["sources_hash"] = sha256_text(sources_path.read_text(encoding="utf-8"))
    setup["config_hash"] = confirmation_hash(config)
    write_json(config_path, config)
    return setup_status(config_path, config)


class ListPageParser(HTMLParser):
    """Collect article detail anchors and nearby text from a source page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, str]] = []
        self.current: dict[str, Any] | None = None
        self.in_title_anchor = False

    def _flush(self) -> None:
        if not self.current:
            return
        title = clean_text("".join(self.current["title"]))
        context = clean_text(" ".join(self.current["context"]))
        if title and self.current["url"]:
            self.items.append({"url": self.current["url"], "title": title, "context": context})
        self.current = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        if LINK_RE.search(href):
            self._flush()
            self.current = {"url": href, "title": [], "context": []}
            self.in_title_anchor = True

    def handle_data(self, data: str) -> None:
        if not self.current:
            return
        self.current["context"].append(data)
        if self.in_title_anchor:
            self.current["title"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self.in_title_anchor = False

    def close(self) -> None:
        super().close()
        self._flush()


class DetailPageParser(HTMLParser):
    """Extract stable fields from simple or framework-rendered detail HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depths = {"title": 0, "h1": 0, "time": 0, "main": 0}
        self.parts: dict[str, list[str]] = {key: [] for key in self.depths}
        self.capture_depths = {"target_title": 0, "abstracts": 0, "target_time": 0}
        self.capture_parts: dict[str, list[str]] = {
            key: [] for key in self.capture_depths
        }
        self.tag_stack: list[tuple[str, set[str]]] = []
        self.all_text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.current_link: str | None = None
        self.current_link_text: list[str] = []
        self.origin_link = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        classes = set((attrs_dict.get("class") or "").split())
        ancestor_classes = {
            class_name
            for _, ancestor_class_set in self.tag_stack
            for class_name in ancestor_class_set
        }
        if tag in self.depths:
            self.depths[tag] += 1
        for key, depth in self.capture_depths.items():
            if depth:
                self.capture_depths[key] += 1
        if (
            not self.capture_depths["target_title"]
            and "title" in classes
            and "top-container" in ancestor_classes
        ):
            self.capture_depths["target_title"] = 1
        if not self.capture_depths["abstracts"] and "abstracts" in classes:
            self.capture_depths["abstracts"] = 1
        if (
            not self.capture_depths["target_time"]
            and "text" in classes
            and "second-raw" in ancestor_classes
        ):
            self.capture_depths["target_time"] = 1
        if tag == "a":
            self.current_link = attrs_dict.get("href") or ""
            self.current_link_text = []
            if "origin_link" in classes:
                self.origin_link = self.current_link
        self.tag_stack.append((tag, classes))

    def handle_data(self, data: str) -> None:
        self.all_text.append(data)
        for tag, depth in self.depths.items():
            if depth:
                self.parts[tag].append(data)
        for key, depth in self.capture_depths.items():
            if depth:
                self.capture_parts[key].append(data)
        if self.current_link is not None:
            self.current_link_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.depths and self.depths[tag]:
            self.depths[tag] -= 1
        for key, depth in self.capture_depths.items():
            if depth:
                self.capture_depths[key] -= 1
        if tag == "a" and self.current_link is not None:
            self.links.append((self.current_link, clean_text("".join(self.current_link_text))))
            self.current_link = None
            self.current_link_text = []
        if self.tag_stack:
            self.tag_stack.pop()


def parse_list_page(content: str, base_url: str) -> list[dict[str, str]]:
    parser = ListPageParser()
    parser.feed(content)
    parser.close()
    result: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in parser.items:
        url = urllib.parse.urljoin(base_url, item["url"])
        if url in seen_urls:
            continue
        seen_urls.add(url)
        result.append({**item, "url": url})
    return result


def strip_markup(value: str) -> str:
    parser = DetailPageParser()
    parser.feed(value or "")
    parser.close()
    return clean_text(" ".join(parser.all_text))


def parse_werss_feed(content: str, feed_url: str) -> list[dict[str, str]]:
    """Parse either RSS or Atom into the same candidate shape as a source page."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise RuntimeError(f"invalid WeRSS XML: {exc}") from exc

    def local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()

    def child_text(element: ET.Element, names: set[str]) -> str:
        for child in element:
            if local_name(child.tag) in names:
                return clean_text("".join(child.itertext()))
        return ""

    items: list[dict[str, str]] = []
    for element in root.iter():
        if local_name(element.tag) not in {"item", "entry"}:
            continue
        title = child_text(element, {"title"})
        link = ""
        for child in element:
            if local_name(child.tag) != "link":
                continue
            link = clean_text(child.attrib.get("href", "")) or clean_text(child.text or "")
            if link:
                break
        published = child_text(element, {"pubdate", "published", "updated", "date"})
        summary = child_text(element, {"description", "summary", "content", "encoded"})
        summary = strip_markup(summary)
        if title and link:
            items.append(
                {
                    "url": urllib.parse.urljoin(feed_url, link),
                    "title": title,
                    "context": published,
                    "feed_summary": summary,
                    "feed_url": feed_url,
                    "via": "werss",
                }
            )
    return items


def parse_detail_page(content: str, fallback_title: str, detail_url: str) -> dict[str, str]:
    parser = DetailPageParser()
    parser.feed(content)
    parser.close()
    targeted_title = clean_text("".join(parser.capture_parts["target_title"]))
    generic_title = clean_text("".join(parser.parts["h1"])) or clean_text(
        "".join(parser.parts["title"])
    )
    title = targeted_title or generic_title or fallback_title
    title = re.sub(r"医药新闻-ByDrug-.*$", "", title).strip() or fallback_title
    time_text = clean_text("".join(parser.capture_parts["target_time"])) or clean_text(
        "".join(parser.parts["time"])
    )
    targeted_summary = clean_text("".join(parser.capture_parts["abstracts"]))
    main_text = clean_text("".join(parser.parts["main"]))
    all_text = clean_text(" ".join(parser.all_text))
    summary_source = targeted_summary or main_text or all_text
    if "版权声明" in summary_source:
        summary_source = summary_source.split("版权声明", 1)[0].strip()
    if summary_source.startswith(title):
        summary_source = summary_source[len(title) :].strip()
    summary = summary_source[:500]
    original_url = urllib.parse.urljoin(detail_url, parser.origin_link) if parser.origin_link else ""
    for href, link_text in parser.links:
        if original_url:
            break
        absolute = urllib.parse.urljoin(detail_url, href)
        host = urllib.parse.urlparse(absolute).netloc.lower()
        if host and "pharmcube.com" not in host and not absolute.startswith("javascript:"):
            if "原文" in link_text or "weixin.qq.com" in host:
                original_url = absolute
                break
            if not original_url:
                original_url = absolute
    return {
        "title": title,
        "time_text": time_text or all_text,
        "summary": summary,
        "original_url": original_url,
    }


def parse_publish_time(text: str, now: dt.datetime, timezone: ZoneInfo) -> dt.datetime | None:
    value = clean_text(text)
    clock = re.search(r"(\d{1,2}):(\d{2})", value)
    hour, minute = (int(clock.group(1)), int(clock.group(2))) if clock else (0, 0)

    def build_datetime(
        year: int,
        month: int,
        day: int,
        hour_value: int = 0,
        minute_value: int = 0,
    ) -> dt.datetime | None:
        try:
            return dt.datetime(
                year,
                month,
                day,
                hour_value,
                minute_value,
                tzinfo=timezone,
            )
        except ValueError:
            return None

    if "前天" in value:
        day = (now - dt.timedelta(days=2)).date()
        return dt.datetime.combine(day, dt.time(hour, minute), timezone)
    if "昨天" in value:
        day = (now - dt.timedelta(days=1)).date()
        return dt.datetime.combine(day, dt.time(hour, minute), timezone)
    if "今天" in value:
        return dt.datetime.combine(now.date(), dt.time(hour, minute), timezone)
    full = re.search(
        r"(?<!\d)(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?(?:[ T](\d{1,2}):(\d{2}))?",
        value,
    )
    if full:
        return build_datetime(
            int(full.group(1)),
            int(full.group(2)),
            int(full.group(3)),
            int(full.group(4) or 0),
            int(full.group(5) or 0),
        )
    month_day = re.search(
        r"(?<!\d)(\d{1,2})[-/.月](\d{1,2})日?(?:[ T](\d{1,2}):(\d{2}))?", value
    )
    if month_day:
        m = int(month_day.group(1))
        d = int(month_day.group(2))
        if m < 1 or m > 12 or d < 1 or d > 31:
            month_day = None
    if month_day:
        candidate = build_datetime(
            now.year,
            m,
            d,
            int(month_day.group(3) or 0),
            int(month_day.group(4) or 0),
        )
        if candidate is None:
            return None
        if candidate > now + dt.timedelta(days=2):
            try:
                candidate = candidate.replace(year=now.year - 1)
            except ValueError:
                return None
        return candidate
    relative = re.search(r"(\d+)\s*(分钟|小时|天)前", value)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        delta = {
            "分钟": dt.timedelta(minutes=amount),
            "小时": dt.timedelta(hours=amount),
            "天": dt.timedelta(days=amount),
        }[unit]
        return now - delta
    try:
        parsed = parsedate_to_datetime(value)
        if parsed:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone)
            return parsed.astimezone(timezone)
    except (TypeError, ValueError, OverflowError):
        pass
    return None


class NetworkFetcher:
    def __init__(self, config: dict[str, Any]) -> None:
        collection = config.get("collection", {})
        self.minimum = float(collection.get("min_delay_seconds", 0.8))
        self.maximum = float(collection.get("max_delay_seconds", 1.5))
        self.retries = int(collection.get("max_retries", 3))
        self.timeout = int(collection.get("timeout_seconds", 25))
        self.user_agent = collection.get(
            "user_agent", "HealthcareIntelligenceMonitor/1.0 (+personal research)"
        )
        self.request_count = 0

    def fetch(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            if self.request_count:
                time.sleep(random.uniform(self.minimum, self.maximum))
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
                },
            )
            try:
                self.request_count += 1
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read()
                    charset = response.headers.get_content_charset() or "utf-8"
                    return body.decode(charset, errors="replace")
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(min(2**attempt, 4))
        raise RuntimeError(f"failed to fetch {url}: {last_error}")


class FixtureFetcher:
    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir
        self.responses = read_json(fixture_dir / "responses.json", {})

    def fetch(self, url: str) -> str:
        filename = self.responses.get(url)
        if not filename:
            raise RuntimeError(f"fixture response not found: {url}")
        return (self.fixture_dir / filename).read_text(encoding="utf-8")


def save_raw(raw_dir: Path, kind: str, key: str, content: str) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{kind}-{sha256_text(key)[:16]}.html.gz"
    path = raw_dir / filename
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(content)
    return path


def classify_item(title: str, summary: str) -> tuple[str, list[str]]:
    text = f"{title} {summary}".lower()
    matches: list[str] = []
    for category, signals in CATEGORY_RULES:
        matched = any(signal.lower() in text for signal in signals)
        if category == "企业动态" and matched:
            enterprise_without_cooperation = any(
                signal.lower() in text for signal in signals if signal != "合作"
            )
            cooperation_has_company_context = (
                "合作" in text
                and any(
                    marker in text
                    for marker in ("公司", "企业", "集团", "药业", "医药", "科技", "双方", "签署", "达成")
                )
                and "合作揭示" not in text
            )
            matched = enterprise_without_cooperation or cooperation_has_company_context
        if matched:
            matches.append(category)
    if "风险事件" in matches:
        primary = "风险事件"
    elif matches:
        primary = min(matches, key=lambda name: CATEGORY_ORDER[name])
    else:
        primary = "企业动态"
    tags = [name for name in matches if name != primary]
    return primary, tags


def normal_title(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value).lower()


def title_similarity(left: str, right: str) -> float:
    a, b = normal_title(left), normal_title(right)
    if not a or not b:
        return 0.0
    a_pairs = {a[index : index + 2] for index in range(max(1, len(a) - 1))}
    b_pairs = {b[index : index + 2] for index in range(max(1, len(b) - 1))}
    union = a_pairs | b_pairs
    return len(a_pairs & b_pairs) / len(union) if union else 0.0


def entity_tokens(value: str) -> set[str]:
    normalized = normal_title(value)
    latin = set(re.findall(r"[a-z][a-z0-9-]{2,}", normalized))
    chinese = {
        normalized[index : index + 3]
        for index in range(max(0, len(normalized) - 2))
        if re.fullmatch(r"[\u4e00-\u9fff]{3}", normalized[index : index + 3])
    }
    return latin | (chinese - GENERIC_ENTITY_TRIGRAMS)


def merge_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    sorted_items = sorted(
        items,
        key=lambda item: (
            CATEGORY_ORDER.get(item["category"], 99),
            item["published_at"],
            item["title"],
        ),
    )
    for item in sorted_items:
        item_date = dt.datetime.fromisoformat(item["published_at"]).date()
        target: dict[str, Any] | None = None
        for group in groups:
            lead = group["items"][0]
            lead_date = dt.datetime.fromisoformat(lead["published_at"]).date()
            shared = entity_tokens(item["title"]) & entity_tokens(lead["title"])
            if (
                item["category"] == group["category"]
                and item_date == lead_date
                and shared
                and title_similarity(item["title"], lead["title"]) >= 0.30
            ):
                target = group
                break
        if target is None:
            groups.append({"category": item["category"], "items": [item]})
        else:
            target["items"].append(item)

    events: list[dict[str, Any]] = []
    for group in groups:
        members = group["items"]
        links: list[dict[str, str]] = []
        seen_links: set[str] = set()
        sources: list[str] = []
        for member in members:
            for source in member.get("source_names", []):
                if source not in sources:
                    sources.append(source)
            for label, url in (
                ("ByDrug", member.get("bydrug_url", "")),
                ("WeRSS Feed", member.get("feed_url", "")),
                ("原文", member.get("original_url", "")),
            ):
                if url and url not in seen_links:
                    seen_links.add(url)
                    links.append({"label": label, "url": url})
        grades = [member.get("trust", "C") for member in members]
        evidences = [member.get("evidence", "unverified") for member in members]
        events.append(
            {
                "id": sha256_text("|".join(sorted(member["id"] for member in members)))[:16],
                "category": group["category"],
                "title": members[0]["title"],
                "summary": members[0].get("summary", ""),
                "published_at": min(member["published_at"] for member in members),
                "tags": sorted({tag for member in members for tag in member.get("tags", [])}),
                "sources": sources,
                "links": links,
                "trust": min(grades) if grades else "C",
                "evidence": "primary" if "primary" in evidences else (
                    "secondary" if "secondary" in evidences else "unverified"
                ),
                "items": members,
            }
        )
    return sorted(
        events,
        key=lambda event: (
            0 if event["category"] == "风险事件" else 1,
            CATEGORY_ORDER.get(event["category"], 99),
            event["published_at"],
        ),
    )


def source_links_markdown(item: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    source_label = "、".join(item.get("source_names", [])) or "未知来源"
    if item.get("bydrug_url"):
        lines.append(f"  - [{source_label}（ByDrug）]({item['bydrug_url']})")
    if item.get("feed_url"):
        lines.append(f"  - [{source_label}（WeRSS Feed）]({item['feed_url']})")
    if item.get("original_url"):
        lines.append(f"  - [{source_label}（原文）]({item['original_url']})")
    return lines


def render_collected(
    items: list[dict[str, Any]],
    now: dt.datetime,
    coverage: float,
    status: str,
) -> str:
    lines = [
        f"# Healthcare Intelligence Collected — {now.date().isoformat()}",
        "",
        f"- 运行时间：{now.isoformat(timespec='minutes')}",
        f"- 状态：{status}",
        f"- 来源覆盖率：{coverage:.1%}",
        f"- 标准化条目：{len(items)}",
        "",
    ]
    if not items:
        lines.extend(["本次时间窗口内没有发现可用条目。", ""])
    for index, item in enumerate(
        sorted(items, key=lambda value: value["published_at"], reverse=True), start=1
    ):
        lines.extend(
            [
                f"## {index}. {item['title']}",
                "",
                f"- 发布时间：{item['published_at']}",
                f"- 一级分类：{item['category']}",
                f"- 辅助标签：{'、'.join(item.get('tags', [])) or '无'}",
                f"- 来源可信度：{item.get('trust', 'C')}",
                f"- 证据状态：{item.get('evidence', 'unverified')}",
                f"- 是否本次新增：{'是' if item.get('is_new') else '否（窗口内历史条目）'}",
                f"- 概要：{item.get('summary') or '未提取到正文概要'}",
                "- 来源链接：",
            ]
        )
        lines.extend(source_links_markdown(item) or ["  - 未提取到可用链接"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_digest(
    items: list[dict[str, Any]],
    events: list[dict[str, Any]],
    now: dt.datetime,
    coverage: float,
    status: str,
    failed_sources: list[str],
) -> str:
    risk_count = sum(event["category"] == "风险事件" for event in events)
    lines = [
        f"# 医疗健康行业每日简报 — {now.date().isoformat()}",
        "",
        "## 执行摘要",
        "",
        f"- 本次覆盖来源 {coverage:.1%}，状态为“{status}”。",
        f"- 时间窗口内共收录 {len(items)} 条，保守合并为 {len(events)} 个事件。",
        f"- 风险事件 {risk_count} 个；风险事件已置顶。",
    ]
    if failed_sources:
        lines.append(f"- 未成功访问 {len(failed_sources)} 个来源，详见采集情况。")
    if not events:
        lines.append("- 本次未发现可归类的新信息。")
    lines.extend(["", "## 聚合事件", ""])
    if not events:
        lines.extend(["无。", ""])
    for index, event in enumerate(events, start=1):
        lines.extend(
            [
                f"### {index}. [{event['category']}] {event['title']}",
                "",
                f"- 时间：{event['published_at']}",
                f"- 摘要：{event['summary'] or '未提取到正文概要'}",
                f"- 来源可信度：{event['trust']}",
                f"- 证据状态：{event['evidence']}",
                f"- 来源：{'、'.join(event['sources']) or '未知来源'}",
                f"- 合并条目数：{len(event['items'])}",
                f"- 辅助标签：{'、'.join(event['tags']) or '无'}",
                "- 全部贡献链接：",
            ]
        )
        for link in event["links"]:
            lines.append(f"  - [{link['label']}]({link['url']})")
        if not event["links"]:
            lines.append("  - 未提取到可用链接")
        lines.append("")
    lines.extend(["## 完整条目附录", ""])
    for index, item in enumerate(
        sorted(items, key=lambda value: value["published_at"], reverse=True), start=1
    ):
        lines.extend(
            [
                f"### {index}. {item['title']}",
                "",
                f"- 分类：{item['category']}",
                f"- 可信度/证据：{item.get('trust', 'C')} / {item.get('evidence', 'unverified')}",
                f"- 来源：{'、'.join(item.get('source_names', [])) or '未知来源'}",
                "- 链接：",
            ]
        )
        lines.extend(source_links_markdown(item) or ["  - 未提取到可用链接"])
        lines.append("")
    lines.extend(
        [
            "## 采集情况",
            "",
            f"- 覆盖率：{coverage:.1%}",
            f"- 状态：{status}",
            f"- 失败来源：{'、'.join(failed_sources) if failed_sources else '无'}",
            "",
            "> 仅供信息研究，不构成投资建议。",
            "",
        ]
    )
    return "\n".join(lines)


def call_optional_llm(
    digest: str,
    collected: str,
    config: dict[str, Any],
    env: dict[str, str],
) -> tuple[str, str | None]:
    ai = config.get("ai", {})
    mode = str(ai.get("mode", "auto")).lower()
    base_url = env.get("LLM_BASE_URL", "").rstrip("/")
    api_key = env.get("LLM_API_KEY", "")
    model = env.get("LLM_MODEL", "")
    if mode in {"off", "disabled", "agent"} or not (base_url and api_key and model):
        return digest, None
    path = str(ai.get("compatible_api_path", "/chat/completions"))
    endpoint = f"{base_url}{path if path.startswith('/') else '/' + path}"
    prompt = (
        "你是医疗健康投资研究助理。仅根据下列 collected.txt 生成不超过 500 字的中文执行摘要。"
        "合并同类事实，明确不确定性，不新增事实、链接、分类或投资建议。只返回摘要正文。\n\n"
        + collected[:50000]
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
        enhanced = clean_text(result["choices"][0]["message"]["content"])
        if not enhanced:
            raise ValueError("empty LLM response")
        replacement = f"## 执行摘要\n\n{enhanced}\n\n"
        updated = re.sub(
            r"## 执行摘要\n.*?(?=\n## )",
            replacement.rstrip(),
            digest,
            count=1,
            flags=re.DOTALL,
        )
        return updated, None
    except (KeyError, ValueError, OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return digest, f"LLM enhancement skipped after error: {exc}"


def update_source_record(record: dict[str, Any], source: dict[str, str]) -> None:
    name = source.get("Name", "未知来源")
    if name not in record["source_names"]:
        record["source_names"].append(name)
    incoming_grade = source.get("Trust", "C")
    record["trust"] = min(record.get("trust", "C"), incoming_grade)
    incoming_evidence = source.get("Evidence", "unverified")
    if incoming_evidence == "primary":
        record["evidence"] = "primary"
    elif record.get("evidence") != "primary" and incoming_evidence == "secondary":
        record["evidence"] = "secondary"
    record["critical"] = record.get("critical", False) or truthy(source.get("Critical"))


def expand_env_template(value: str, env: dict[str, str]) -> str:
    def replacement(match: re.Match[str]) -> str:
        key = match.group(1)
        if not env.get(key):
            raise RuntimeError(f"environment variable {key} is required by WeRSS URL")
        return env[key]

    return re.sub(r"\$\{([A-Z][A-Z0-9_]*)\}", replacement, value)




def classify_source_error(exc: Exception) -> str:
    """Categorize a fetch/parse exception for BC-005 error tracking."""
    msg = str(exc).lower()
    checks: list[tuple[str, tuple[str, ...]]] = [
        ("network_permission", (
            "name or service not known",
            "nodename nor servname",
            "temporary failure in name resolution",
            "connection refused",
            "connection reset",
            "permission denied",
        )),
        ("network_timeout", (
            "timeout",
            "timed out",
        )),
        ("source_http_error", (
            "http error",
        )),
        ("source_parse_error", (
            "page contains no",
            "parse error",
            "parse",
        )),
    ]
    for category, keywords in checks:
        if any(kw in msg for kw in keywords):
            return category
    return "unknown"

def collect_run(
    config_path: Path,
    sources_override: Path | None = None,
    output_override: Path | None = None,
    fixture_dir: Path | None = None,
    now_value: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    require_setup_complete(config_path, config)
    if output_override:
        configured_output = resolve_path(config_path, config.get("output_dir", "."))
        if output_override.resolve() != configured_output:
            raise RuntimeError(
                "禁止使用未经确认的 --output-dir；请先通过 configure 修改并重新确认"
            )
        config["output_dir"] = str(output_override)
    timezone = ZoneInfo(config.get("timezone", "Asia/Shanghai"))
    now = dt.datetime.fromisoformat(now_value) if now_value else dt.datetime.now(timezone)
    now = now.replace(tzinfo=timezone) if now.tzinfo is None else now.astimezone(timezone)
    cutoff = now - dt.timedelta(hours=float(config.get("collection_window_hours", 48)))
    paths = runtime_paths(config_path, config)
    ensure_runtime(paths)
    run_id = dt.datetime.now(timezone).strftime("%Y%m%d_%H%M%S") + "_" + os.urandom(4).hex()
    run_status_path = paths["state"] / "run-status.json"
    write_json(run_status_path, {
        "run_id": run_id,
        "status": "started",
        "started_at": now.isoformat(timespec="seconds"),
    })
    env = load_env_file(config_path.parent / ".env")
    configured_sources_path = resolve_path(
        config_path, config.get("sources_file", "sources.md")
    )
    if sources_override and sources_override.resolve() != configured_sources_path:
        raise RuntimeError(
            "禁止使用未经确认的 --sources-file；请先通过 configure 修改并重新确认"
        )
    sources_path = sources_override or configured_sources_path
    sources = [row for row in parse_markdown_table(sources_path) if truthy(row.get("Enabled", "true"))]
    if limit is not None:
        sources = sources[:limit]
    if not sources:
        raise RuntimeError(f"no enabled sources in {sources_path}")

    fetcher: NetworkFetcher | FixtureFetcher
    fetcher = FixtureFetcher(fixture_dir) if fixture_dir else NetworkFetcher(config)
    state_path = paths["state"] / "seen-items.json"
    state = read_json(state_path, {"ids": [], "items": {}})
    state.setdefault("ids", [])
    state.setdefault("items", {})
    seen_ids = set(state["ids"])
    cache: dict[str, dict[str, Any]] = state["items"]
    failure_path = paths["state"] / "source-failures.json"
    failure_state: dict[str, int] = read_json(failure_path, {})
    errors: list[str] = []
    failed_sources: list[str] = []
    fallback_sources: list[str] = []
    successful_sources = 0
    window_items: dict[str, dict[str, Any]] = {}
    raw_dir = paths["raw"] / now.date().isoformat()
    failure_alert_after = int(config.get("collection", {}).get("failure_alert_after", 3))

    for source in sources:
        name = source.get("Name", "未知来源")
        source_url = source.get("ByDrug URL", "")
        candidates: list[dict[str, str]] = []
        try:
            if not source_url:
                raise RuntimeError("ByDrug URL is empty")
            source_html = fetcher.fetch(source_url)
            save_raw(raw_dir, "source", source_url, source_html)
            candidates = parse_list_page(source_html, source_url)
            if not candidates:
                raise RuntimeError("page contains no article detail links")
            successful_sources += 1
            failure_state[name] = 0
        except Exception as exc:  # source isolation is intentional
            bydrug_error = str(exc)
            error_cat = classify_source_error(exc)
            # Environment errors (network/permission) don't count toward source failure count
            if error_cat in ("network_permission", "network_timeout"):
                errors.append(f"{name}: {bydrug_error} (环境错误：{error_cat})")
                failed_sources.append(name)
                continue
            failure_state[name] = int(failure_state.get(name, 0)) + 1
            werss_template = source.get("WeRSS URL", "").strip()
            fallback_ready = (
                truthy(source.get("Critical"))
                and bool(werss_template)
                and (not source_url or failure_state[name] >= failure_alert_after)
            )
            if fallback_ready:
                try:
                    feed_url = expand_env_template(werss_template, env)
                    feed_xml = fetcher.fetch(feed_url)
                    save_raw(raw_dir, "werss", feed_url, feed_xml)
                    candidates = parse_werss_feed(feed_xml, feed_url)
                    if not candidates:
                        raise RuntimeError("feed contains no items")
                    successful_sources += 1
                    fallback_sources.append(name)
                    errors.append(
                        f"{name}: ByDrug failed ({bydrug_error}); WeRSS fallback used"
                    )
                except Exception as fallback_exc:
                    failed_sources.append(name)
                    errors.append(
                        f"{name}: ByDrug failed ({bydrug_error}); WeRSS failed ({fallback_exc})"
                    )
                    continue
            else:
                failed_sources.append(name)
                errors.append(f"{name}: {bydrug_error}")
                continue

        for candidate in candidates:
            published = parse_publish_time(candidate["context"], now, timezone)
            if published is None:
                errors.append(f"{name}: could not parse date for {candidate['title']}")
                continue
            if published < cutoff or published > now + dt.timedelta(days=1):
                continue
            item_id = sha256_text(candidate["url"])
            cached = cache.get(item_id)
            if cached:
                record = copy.deepcopy(cached)
                record["is_new"] = False
                update_source_record(record, source)
                cache[item_id] = copy.deepcopy(record)
                cache[item_id].pop("is_new", None)
                window_items[item_id] = record
                continue
            try:
                if candidate.get("via") == "werss":
                    detail = {
                        "title": candidate["title"],
                        "summary": candidate.get("feed_summary", ""),
                        "original_url": candidate["url"],
                        "time_text": candidate["context"],
                    }
                else:
                    detail_html = fetcher.fetch(candidate["url"])
                    save_raw(raw_dir, "detail", candidate["url"], detail_html)
                    detail = parse_detail_page(
                        detail_html, candidate["title"], candidate["url"]
                    )
                detail_published = (
                    parse_publish_time(detail["time_text"], now, timezone) or published
                )
                category, tags = classify_item(detail["title"], detail["summary"])
                record = {
                    "id": item_id,
                    "title": detail["title"],
                    "summary": detail["summary"] or candidate["context"][:500],
                    "published_at": detail_published.isoformat(timespec="minutes"),
                    "bydrug_url": (
                        "" if candidate.get("via") == "werss" else candidate["url"]
                    ),
                    "feed_url": candidate.get("feed_url", ""),
                    "original_url": detail["original_url"],
                    "source_names": [name],
                    "category": category,
                    "tags": tags,
                    "trust": source.get("Trust", "C"),
                    "evidence": source.get("Evidence", "unverified"),
                    "critical": truthy(source.get("Critical")),
                    "is_new": item_id not in seen_ids,
                }
                cache[item_id] = {key: value for key, value in record.items() if key != "is_new"}
                seen_ids.add(item_id)
                window_items[item_id] = record
            except Exception as exc:  # article isolation is intentional
                errors.append(f"{name} / {candidate['title']}: {exc}")

    # ── Government approval sources ──
    print("\n采集政府获批来源...")
    gov_arts, gov_fails = scrape_government(window_start=cutoff, window_end=now)
    for ga in gov_arts:
        item_id = sha256_text(ga.get("source_url", "") + ga.get("title", ""))
        ga["id"] = item_id
        ga["published_at"] = ga.get("publish_time", ga.get("published_at", ""))
        ga["source_names"] = [ga.get("source", "未知")]
        ga["category"] = ga.get("level_1_category", "其他/综合")
        ga["tags"] = [ga.get("source_type", "government")]
        ga["trust"] = ga.get("source_rating", "A")
        ga["evidence"] = "primary"
        ga["critical"] = True
        ga["is_new"] = item_id not in seen_ids
        if item_id not in seen_ids:
            seen_ids.add(item_id)
            cache[item_id] = {k: v for k, v in ga.items() if k != "is_new"}
        window_items[item_id] = ga
    for gf in gov_fails:
        errors.append(f"{gf['source']}: {gf['error_category']} — {gf.get('error_detail', '')}")
    print(f"  政府来源: {len(gov_arts)} 条审批, {len(gov_fails)} 个失败")

    coverage = successful_sources / len(sources)
    threshold = float(config.get("collection", {}).get("coverage_threshold", 0.95))
    status = "healthy" if coverage >= threshold else "partial"
    items = list(window_items.values())
    events = merge_items(items)
    collected = render_collected(items, now, coverage, status)
    digest = render_digest(items, events, now, coverage, status, failed_sources)
    digest, llm_error = call_optional_llm(digest, collected, config, env)
    if llm_error:
        errors.append(llm_error)

    daily_dir = paths["data"] / now.date().isoformat()
    daily_dir.mkdir(parents=True, exist_ok=True)
    collected_path = daily_dir / "collected.txt"
    digest_path = daily_dir / "digest.txt"
    errors_path = daily_dir / "errors.txt"
    error_content = "\n".join(
        [f"# Errors — {now.date().isoformat()}", ""]
        + [f"- {message}" for message in errors]
        + (["无。"] if not errors else [])
    ) + "\n"
    for target, content_value in [
        (collected_path, collected),
        (digest_path, digest),
        (errors_path, error_content),
    ]:
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(content_value, encoding="utf-8")
        tmp.rename(target)

    state["ids"] = sorted(seen_ids)
    state["items"] = cache
    state["last_run"] = now.isoformat(timespec="seconds")
    state["last_status"] = status
    write_json(state_path, state)
    write_json(failure_path, failure_state)
    write_json(run_status_path, {
        "run_id": run_id,
        "status": "completed",
        "started_at": now.isoformat(timespec="seconds"),
        "completed_at": dt.datetime.now(timezone).isoformat(timespec="seconds"),
        "items": len(items),
        "events": len(events),
        "sources_successful": successful_sources,
        "sources_total": len(sources),
        "error_count": len(errors),
    })

    repeated = sorted(
        name for name, count in failure_state.items() if int(count) >= failure_alert_after
    )
    result = {
        "run_id": run_id,
        "status": status,
        "coverage": round(coverage, 4),
        "sources_total": len(sources),
        "sources_successful": successful_sources,
        "items": len(items),
        "new_items": sum(bool(item.get("is_new")) for item in items),
        "events": len(events),
        "werss_fallback_sources": fallback_sources,
        "repeated_failures": repeated,
        "collected_path": str(collected_path),
        "digest_path": str(digest_path),
        "errors_path": str(errors_path),
    }
    return result


def delivery_db(paths: dict[str, Path]) -> sqlite3.Connection:
    database = sqlite3.connect(paths["state"] / "delivery.sqlite3")
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS deliveries (
            digest_id TEXT PRIMARY KEY,
            delivered_at TEXT NOT NULL,
            adapter TEXT NOT NULL,
            recipients TEXT NOT NULL
        )
        """
    )
    database.commit()
    return database


def webhook_send(
    url: str,
    token: str,
    subject: str,
    content: str,
    recipients: list[str],
) -> None:
    payload = json.dumps(
        {"title": subject, "content": content, "recipients": recipients},
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"webhook returned HTTP {response.status}")


def smtp_send(
    config: dict[str, Any],
    env: dict[str, str],
    subject: str,
    content: str,
    recipients: list[str],
) -> None:
    delivery = config.get("delivery", {})
    host = env.get("SMTP_HOST") or delivery.get("smtp_host", "")
    username = env.get("SMTP_USERNAME", "")
    password = env.get("SMTP_APP_PASSWORD", "")
    sender = env.get("MAIL_FROM") or username
    if not (host and username and password and sender):
        raise RuntimeError("SMTP is not fully configured")
    port = int(delivery.get("smtp_port", 465))
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(content, subtype="plain", charset="utf-8")
    context = ssl.create_default_context()
    if truthy(delivery.get("smtp_starttls", False)):
        with smtplib.SMTP(host, port, timeout=30) as client:
            client.starttls(context=context)
            client.login(username, password)
            client.send_message(message)
    else:
        with smtplib.SMTP_SSL(host, port, timeout=30, context=context) as client:
            client.login(username, password)
            client.send_message(message)


def attempt_delivery(
    config: dict[str, Any],
    env: dict[str, str],
    paths: dict[str, Path],
    content: str,
    digest_id: str,
    subject: str,
    recipients: list[str],
) -> dict[str, Any]:
    database = delivery_db(paths)
    existing = database.execute(
        "SELECT adapter, delivered_at FROM deliveries WHERE digest_id = ?", (digest_id,)
    ).fetchone()
    if existing:
        database.close()
        return {"status": "already-delivered", "adapter": existing[0], "digest_id": digest_id}
    adapters = config.get("delivery", {}).get("adapters", ["webhook", "smtp"])
    errors: list[str] = []
    selected = ""
    for adapter in adapters:
        try:
            if adapter == "webhook":
                url = env.get("EMAIL_WEBHOOK_URL", "")
                if not url:
                    raise RuntimeError("EMAIL_WEBHOOK_URL is empty")
                webhook_send(url, env.get("EMAIL_WEBHOOK_TOKEN", ""), subject, content, recipients)
            elif adapter == "smtp":
                smtp_send(config, env, subject, content, recipients)
            else:
                raise RuntimeError(f"unsupported standalone adapter: {adapter}")
            selected = adapter
            break
        except Exception as exc:  # each adapter is an explicit fallback
            errors.append(f"{adapter}: {exc}")
    if selected:
        delivered_at = dt.datetime.now(dt.timezone.utc).isoformat()
        database.execute(
            "INSERT INTO deliveries(digest_id, delivered_at, adapter, recipients) VALUES (?, ?, ?, ?)",
            (digest_id, delivered_at, selected, json.dumps(recipients, ensure_ascii=False)),
        )
        database.commit()
        database.close()
        pending_path = paths["outbox"] / f"{digest_id}.json"
        if pending_path.exists():
            pending_path.unlink()
        return {"status": "delivered", "adapter": selected, "digest_id": digest_id}
    database.close()
    pending = {
        "digest_id": digest_id,
        "subject": subject,
        "content": content,
        "recipients": recipients,
        "errors": errors,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_json(paths["outbox"] / f"{digest_id}.json", pending)
    return {"status": "queued-outbox", "digest_id": digest_id, "errors": errors}


def deliver_digest(
    config_path: Path,
    digest_path: Path,
    confirm_first_send: bool = False,
) -> dict[str, Any]:
    config = load_config(config_path)
    require_setup_complete(config_path, config)
    paths = runtime_paths(config_path, config)
    ensure_runtime(paths)
    recipients = [str(value) for value in config.get("delivery", {}).get("recipients", [])]
    if not recipients:
        return {"status": "configuration-error", "message": "delivery.recipients is empty"}
    approval_path = paths["state"] / "first-send-approved.json"
    approval = read_json(approval_path, {"approved": False})
    if confirm_first_send:
        approval = {
            "approved": True,
            "approved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "recipients": recipients,
        }
        write_json(approval_path, approval)
    if not approval.get("approved") or approval.get("recipients") != recipients:
        return {
            "status": "approval-required",
            "message": (
                "Preview the digest and exact recipients, then rerun with "
                "--confirm-first-send. Recipient changes require new approval."
            ),
        }
    content = digest_path.read_text(encoding="utf-8")
    recipient_key = json.dumps(sorted(recipients), ensure_ascii=False)
    digest_id = sha256_text(content + "\nRECIPIENTS:" + recipient_key)
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", digest_path.name + " " + content[:200])
    date_label = date_match.group(0) if date_match else dt.date.today().isoformat()
    subject = f"医疗健康行业每日简报｜{date_label}"
    env = load_env_file(config_path.parent / ".env")
    return attempt_delivery(config, env, paths, content, digest_id, subject, recipients)


def retry_outbox(config_path: Path) -> list[dict[str, Any]]:
    config = load_config(config_path)
    require_setup_complete(config_path, config)
    paths = runtime_paths(config_path, config)
    ensure_runtime(paths)
    approval = read_json(paths["state"] / "first-send-approved.json", {"approved": False})
    if not approval.get("approved"):
        return [{"status": "approval-required"}]
    env = load_env_file(config_path.parent / ".env")
    results: list[dict[str, Any]] = []
    for pending_path in sorted(paths["outbox"].glob("*.json")):
        pending = read_json(pending_path, {})
        if not pending:
            continue
        if pending.get("recipients") != approval.get("recipients"):
            results.append(
                {
                    "status": "approval-required",
                    "digest_id": pending.get("digest_id", ""),
                    "message": "Outbox recipients do not match the approved recipient list.",
                }
            )
            continue
        results.append(
            attempt_delivery(
                config,
                env,
                paths,
                pending["content"],
                pending["digest_id"],
                pending["subject"],
                pending["recipients"],
            )
        )
    return results


def cleanup_runtime(config_path: Path) -> dict[str, int]:
    config = load_config(config_path)
    paths = runtime_paths(config_path, config)
    retention = config.get("retention", {})
    policies = {
        "raw": int(retention.get("raw_days", 30)),
        "logs": int(retention.get("log_days", 90)),
    }
    now = time.time()
    removed: dict[str, int] = {"raw": 0, "logs": 0, "errors": 0}
    for key, days in policies.items():
        root = paths[key].resolve()
        if not root.exists():
            continue
        cutoff = now - days * 86400
        for path in root.rglob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed[key] += 1
    error_cutoff = now - int(retention.get("log_days", 90)) * 86400
    data_root = paths["data"].resolve()
    if data_root.exists():
        for path in data_root.glob("*/errors.txt"):
            if path.is_file() and path.stat().st_mtime < error_cutoff:
                path.unlink()
                removed["errors"] += 1
    return removed


def initialize_workspace(workspace: Path) -> dict[str, str]:
    skill_root = Path(__file__).resolve().parent.parent
    workspace = workspace.expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    config_path = workspace / "config.yaml"
    env_path = workspace / ".env"
    sources_path = workspace / "sources.md"
    if not config_path.exists():
        config = load_config(skill_root / "assets" / "config.example.yaml")
        config["sources_file"] = "sources.md"
        config["output_dir"] = "."
        write_json(config_path, config)
    if not env_path.exists():
        shutil.copyfile(skill_root / "assets" / "env.example", env_path)
    if not sources_path.exists():
        shutil.copyfile(skill_root / "references" / "sources.md", sources_path)
    paths = runtime_paths(config_path, load_config(config_path))
    ensure_runtime(paths)
    return {
        "workspace": str(workspace),
        "config": str(config_path),
        "env": str(env_path),
        "sources": str(sources_path),
        "next_step": (
            "逐项询问用户并用 configure 写入回答；"
            "在用户查看汇总并确认前不得运行 finalize-setup 或 run"
        ),
    }


def print_result(result: Any) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))


def download_model(runtime_root: str) -> dict[str, Any]:
    """Download SentenceTransformer model for semantic classification.

    Model: paraphrase-multilingual-MiniLM-L12-v2 (~118 MB)
    Source: HuggingFace (sentence-transformers)
    Path:  <runtime>/models/paraphrase-multilingual-MiniLM-L12-v2
    """
    root = Path(runtime_root)
    model_dir = root / "models" / "paraphrase-multilingual-MiniLM-L12-v2"

    if model_dir.exists() and (model_dir / "model.safetensors").exists():
        return {
            "status": "already-exists",
            "model_dir": str(model_dir),
            "message": "模型已存在，无需下载",
        }

    model_dir.mkdir(parents=True, exist_ok=True)

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return {
            "status": "error",
            "message": "sentence-transformers 未安装。请先运行: pip install sentence-transformers",
        }

    print(f"正在从 HuggingFace 下载模型 sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (~118 MB) ...", file=sys.stderr)
    print(f"保存路径: {model_dir}", file=sys.stderr)
    print("预计耗时 1-5 分钟（取决于网络速度）", file=sys.stderr)

    try:
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        model.save(str(model_dir))
        return {
            "status": "downloaded",
            "model_dir": str(model_dir),
            "message": "模型下载完成",
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"下载失败: {exc}",
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a runtime workspace")
    init_parser.add_argument("--workspace", type=Path, required=True)

    configure_parser = subparsers.add_parser(
        "configure", help="Write one or more confirmed answers into config.yaml"
    )
    configure_parser.add_argument("--config", type=Path, required=True)
    configure_parser.add_argument(
        "--set",
        dest="assignments",
        action="append",
        default=[],
        metavar="PATH=VALUE",
    )

    status_parser = subparsers.add_parser(
        "setup-status", help="Show missing setup answers without changing state"
    )
    status_parser.add_argument("--config", type=Path, required=True)

    finalize_parser = subparsers.add_parser(
        "finalize-setup", help="Validate and lock setup after explicit user confirmation"
    )
    finalize_parser.add_argument("--config", type=Path, required=True)
    finalize_parser.add_argument("--confirmed-by-user", action="store_true")

    download_parser = subparsers.add_parser(
        "download-model", help="Download SentenceTransformer model for semantic classification (~118 MB)"
    )
    download_parser.add_argument("--runtime", type=Path, required=True, help="Runtime directory")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            print_result(initialize_workspace(args.workspace))
            return 0
        if args.command == "configure":
            print_result(configure_workspace(args.config.resolve(), args.assignments))
            return 0
        if args.command == "setup-status":
            print_result(setup_status(args.config.resolve()))
            return 0
        if args.command == "finalize-setup":
            print_result(
                finalize_setup(args.config.resolve(), args.confirmed_by_user)
            )
            return 0
        if args.command == "download-model":
            print_result(download_model(str(args.runtime.resolve())))
            return 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
