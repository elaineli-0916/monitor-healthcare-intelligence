#!/usr/bin/env python3
"""
统一医疗健康数据抓取：动脉网 (vbdata.cn) + ByDrug聚合 + 政府来源
四级分类体系（继承 vbdata_scraper.py 的完整分类树）

输出统一 JSON → generate_dashboard.py 生成 HTML 看板。

用法:
  python3 dashboard_scraper.py --output result.json
  python3 dashboard_scraper.py --source vbdata        # 仅动脉网
  python3 dashboard_scraper.py --source bydrug        # 仅 ByDrug
"""

import json, sys, time, hashlib, re, datetime as dt, urllib.request, urllib.error, urllib.parse
from pathlib import Path
from typing import Any

from classification_engine import get_default_engine

# ═══════════════════════════════════════════════════════════
 
# ═══════════════════════════════════════════════════════════

CATEGORIES = {
    "1. 创新药": {
        "1.1 小分子创新药": [],
        "1.2 生物药（抗体/蛋白/核酸/ADC/XDC偶联药物）": [],
        "1.3 细胞与基因治疗（CGT）": [],
        "1.4 医药CXO（CRO/CDMO/CSO）": [],
        "1.5 AI制药": [],
        "1.6 合成生物学": [],
    },
    "2. 医疗器械": {
        "2.1 心血管介入": [],
        "2.2 骨科与植入物": [],
        "2.3 体外诊断（IVD）": [],
        "2.4 医学影像": [],
        "2.5 手术机器人": [],
        "2.6 神经调控与脑机接口": [],
    },
    "3. 医疗服务": {
        "3.1 专科医院/连锁诊所": [],
        "3.2 第三方医学检验（ICL）": [],
        "3.3 数字医疗/互联网医院": [],
        "3.4 院外康复与居家医疗": [],
    },
    "4. 消费医疗与医美": {
        "4.1 医美耗材与器械（注射/光电/埋线）": [],
        "4.2 功效性护肤品": [],
        "4.3 减重/代谢管理": [],
        "4.4 眼视光（近视防控/OK镜）": [],
        "4.5 口腔正畸与种植": [],
        "4.6 辅助生殖": [],
        "4.7 听力": [],
        "4.8 睡眠": [],
        "4.9 营养保健（功能食品/特医食品/抗衰）": [],
    },
    "其他/综合": {},
}

CLASSIFICATION_RULES = [
    ("1.1 小分子创新药", ["小分子", "化药", "化学药", "透皮贴", "透皮贴剂"]),
    ("1.2 生物药（抗体/蛋白/核酸/ADC/XDC偶联药物）", ["抗体", "单抗", "双抗", "蛋白", "核酸", "生物药", "疫苗",
                                                      "t细胞", "tce", "t细胞衔接器", "gpcr",
                                                      "降压疫苗", "claris bio", "adc", "xdc", "偶联药物", "抗体偶联"]),
    ("1.3 细胞与基因治疗（CGT）", ["细胞治疗", "基因治疗", "car-t", "car-nk", "cgt", "基因编辑",
                                     "cell therapy", "gene therapy", "core biomedicine"]),
    ("1.4 医药CXO（CRO/CDMO/CSO）", ["cro", "cdmo", "cso", "cxo", "合同.*研究",
                                      "生命科学设备", "租赁平台", "excedr"]),
    ("1.5 AI制药", ["ai制药", "人工智能.*药", "计算.*药物"]),
    ("1.6 合成生物学", ["合成生物", "synbio", "synthetic biology", "生物制造"]),
    ("2.1 心血管介入", ["心血管", "心脏", "冠脉", "介入", "支架", "瓣膜", "起搏器",
                         "aurenar", "女性心血管"]),
    ("2.2 骨科与植入物", ["骨科", "植入物", "关节", "脊柱", "骨"]),
    ("2.3 体外诊断（IVD）", ["ivd", "体外诊断", "诊断", "流式细胞", "质谱", "pcr",
                               "测序", "试剂盒", "检验", "standard biotools"]),
    ("2.4 医学影像", ["影像", "超声", "mri", "ct", "pet", "影像诊断", "机器人超声",
                       "商汤医疗", "ai医学影像"]),
    ("2.5 手术机器人", ["手术机器人", "手术机", "腔镜"]),
    ("2.6 神经调控与脑机接口", ["神经调控", "脑机", "神经刺激", "脑起搏器", "dbs"]),
    ("3.1 专科医院/连锁诊所", ["专科医院", "连锁诊所", "诊所", "医疗集团"]),
    ("3.2 第三方医学检验（ICL）", ["第三方.*检验", "icl", "独立.*实验室"]),
    ("3.3 数字医疗/互联网医院", ["数字医疗", "互联网医院", "数字健康", "远程医疗", "健康管理",
                                  "ai.*医疗", "人工智能.*医疗", "数字化", "数字疗法", "线上.*药",
                                  "美团买药", "mirae", "药品追溯", "waic", "爱康", "ikkei"]),
    ("3.4 院外康复与居家医疗", ["居家医疗", "院外康复", "全周期管理", "慢阻肺", "osa",
                                  "居家", "rpm", "远程.*监护", "telemetrix", "睡眠呼吸"]),
    ("4.1 医美耗材与器械（注射/光电/埋线）", ["医美", "玻尿酸", "肉毒素", "光电", "埋线", "射频", "超声刀"]),
    ("4.2 功效性护肤品", ["护肤品", "功效.*护肤", "药妆"]),
    ("4.3 减重/代谢管理", ["减重", "减肥", "代谢", "glp-1", "司美格鲁肽", "体重"]),
    ("4.4 眼视光（近视防控/OK镜）", ["眼视光", "近视", "ok镜", "角膜塑形", "视力", "眼科"]),
    ("4.5 口腔正畸与种植", ["口腔", "正畸", "种植", "牙"]),
    ("4.6 辅助生殖", ["辅助生殖", "试管婴儿", "ivf", "生殖"]),
    ("4.7 听力", ["听力", "助听", "助听器"]),
    ("4.8 睡眠", ["睡眠", "失眠", "抗失眠", "睡眠呼吸", "osa", "法赞雷生"]),
    ("4.9 营养保健（功能食品/特医食品/抗衰）", ["保健品", "功能食品", "特医", "营养", "益生菌", "维生素", "抗衰"]),
]

COMPANY_CATEGORIES = {
    "百济神州": "1. 创新药", "beigene": "1. 创新药",
    "昌郁医药": "1.1 小分子创新药", "广药": "1.1 小分子创新药",
}


def classify_article(title: str, summary: str, tags: list = None) -> tuple:
    """兼容旧调用：返回 (level2_subcat, level1_parent)。"""
    result = classify_article_details(title, summary, tags)
    return result["level_2_category"], result["level_1_category"]


def classify_article_details(
    title: str, summary: str, tags: list | None = None
) -> dict[str, Any]:
    """返回带分类方法、置信度和理由的完整三层分类结果。"""
    return get_default_engine().classify(title, summary, tags).to_dict()


def get_parent_category(subcat: str) -> str:
    for parent, subs in CATEGORIES.items():
        if parent == subcat:
            return parent
        for sub in subs:
            if sub == subcat:
                return parent
    return "其他/综合"


# ═══════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════

def fp(title: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", "", title).encode()).hexdigest()[:16]


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


# ═══════════════════════════════════════════════════════════
#  Source 1: 动脉网 vbdata.cn（主页 + 投融资频道）
# ═══════════════════════════════════════════════════════════

def scrape_vbdata_new() -> list[dict]:
    """爬取动脉网主页 event-card 列表"""
    html = fetch_html("https://www.vbdata.cn/new")
    articles: list[dict] = []
    cards = html.split('<div class="event-card"')
    for card in cards[1:]:
        card_raw = '<div class="event-card"' + card
        title_m = re.search(r'<h1 class="title-content"[^>]*>(.*?)</h1>', card_raw, re.DOTALL)
        if not title_m:
            continue
        title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
        if not title:
            continue

        summary_m = re.search(r'<div class="card-summary"[^>]*>(.*?)</div>', card_raw, re.DOTALL)
        summary = re.sub(r'<[^>]+>', '', summary_m.group(1)).strip() if summary_m else ""

        source_m = re.search(r'<a class="spa1[^"]*"[^>]*>(.*?)</a>', card_raw)
        source = re.sub(r'<[^>]+>', '', source_m.group(1)).strip() if source_m else "动脉网"
        if "等信源发布" in source or len(source) > 20:
            source = "动脉网"

        tag_matches = re.findall(r'<a[^>]*>#([^<]+)</a>', card_raw)
        tags = [t.strip() for t in tag_matches]

        date_m = re.search(r'<span class="spa2"[^>]*>(\d{4}-\d{2}-\d{2}[\d: ]*)</span>', card_raw)
        date = date_m.group(1).strip() if date_m else dt.datetime.now().strftime("%Y-%m-%d %H:%M")

        # 真实文章链接，优先 intelDetail
        links = re.findall(r'href="(https?://www\.vbdata\.cn/intelDetail/\d+)"', card_raw)
        if not links:
            links = re.findall(r'href="(https?://www\.vbdata\.cn/\d+)"', card_raw)
        link = links[0] if links else ""

        classification = classify_article_details(title, summary, tags)

        articles.append({
            "title": title,
            "summary": summary[:300],
            "source": source,
            "source_url": link,
            "source_rating": "B",
            "publish_time": date,
            **classification,
            "source_type": "vbdata",
        })
    return articles


def _parse_vbdata_relative_date(card: str, now: dt.datetime) -> str:
    """解析 vbdata 的相对时间"""
    time_m = re.search(r'<span[^>]*>(\d+)\s+小时([前后])</span>', card)
    if time_m:
        hours = int(time_m.group(1))
        direction = time_m.group(2)
        abs_time = now - dt.timedelta(hours=hours) if direction == "前" else now
        return abs_time.strftime("%Y-%m-%d %H:%M")
    time_m = re.search(r'<span[^>]*>(\d+)\s+天([前后])</span>', card)
    if time_m:
        days = int(time_m.group(1))
        direction = time_m.group(2)
        abs_time = now - dt.timedelta(days=days) if direction == "前" else now + dt.timedelta(days=days)
        return abs_time.strftime("%Y-%m-%d %H:%M")
    return None  # no fallback to now()


def scrape_vbdata_financing() -> list[dict]:
    """VBData 投融资频道"""
    now = dt.datetime.now()
    html = fetch_html("https://www.vbdata.cn/articleList?category=166")
    articles: list[dict] = []
    cards = html.split('<div class="article" data-v-701e6002')
    for card in cards[1:]:
        card_raw = '<div class="article" data-v-701e6002' + card

        title_m = re.search(r'class="h1 over-p2"[^>]*>(.*?)</a>', card_raw, re.DOTALL)
        if not title_m:
            title_m = re.search(r'<a[^>]*class="h1 over-p2"[^>]*>(.*?)</a>', card_raw, re.DOTALL)
        if not title_m:
            continue
        title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
        if not title:
            continue

        summary_m = re.search(r'<h2 class="over-p1"[^>]*>(.*?)</h2>', card_raw, re.DOTALL)
        summary = re.sub(r'<[^>]+>', '', summary_m.group(1)).strip() if summary_m else ""

        link_m = re.search(r'<a href="(https?://www\.vbdata\.cn/\d+)"', card_raw)
        link = link_m.group(1) if link_m else ""

        tag_section = re.search(r'<div class="tags1"[^>]*>(.*?)</div>', card_raw, re.DOTALL)
        tags = []
        if tag_section:
            tags = [t.strip() for t in re.findall(r'<a[^>]*>(.*?)</a>', tag_section.group(1))]
        tags = [t for t in tags if t and t != "相关赛道"]

        author_m = re.search(r'<span class="author"[^>]*>(.*?)</span>', card_raw)
        source = author_m.group(1).strip() if author_m else "动脉网"

        date = _parse_vbdata_relative_date(card_raw, now)
        classification = classify_article_details(title, summary, tags)

        articles.append({
            "title": title,
            "summary": summary[:300],
            "source": source,
            "source_url": link,
            "source_rating": "B",
            "publish_time": date,
            **classification,
            "source_type": "vbdata",
        })
    return articles


def scrape_vbdata() -> list[dict]:
    """双源抓取 + 去重（保留 time_source/time_confidence）"""
    home = scrape_vbdata_new()
    fin = scrape_vbdata_financing()
    seen = set()
    merged = []
    for a in home + fin:
        key = a.get("source_url") or a["title"]
        if key in seen:
            continue
        seen.add(key)
        a["id"] = fp(a["title"])
        # 确保 time 字段存在
        if "time_source" not in a:
            a["time_source"] = "vbdata_html" if a.get("publish_time") else "failed"
        if "time_confidence" not in a:
            a["time_confidence"] = 1.0 if a.get("publish_time") else 0
        merged.append(a)
    return merged


# ═══════════════════════════════════════════════════════════
#  Source 2: ByDrug 聚合来源（精选 A/B/C 级来源）
# ═══════════════════════════════════════════════════════════

# 从 sources.md 动态加载全部 ByDrug 来源
def load_bydrug_sources() -> list[dict]:
    """从 references/sources.md 读取所有 source_news_cn 条目"""
    src_path = Path(__file__).parent.parent / "references" / "sources.md"
    if not src_path.exists():
        src_path = Path("skills/monitor-healthcare-intelligence/references/sources.md")
    with open(src_path, 'r') as f:
        src_content = f.read()
    table_start = src_content.index('## source_news_cn')
    table_content = src_content[table_start:]
    rows = re.findall(
        r'\|\s*([^|]+?)\s*\|\s*[^|]+?\s*\|\s*([ABCD])\s*\|\s*(https://bydrug[^|\s]+)',
        table_content
    )
    sources = []
    for name, rating, url in rows:
        name = name.strip()
        slug = url.strip().rsplit('/', 1)[-1]
        sources.append({"name": name, "slug": slug, "rating": rating.strip()})
    return sources

_BYDRUG_SOURCES = None

def get_bydrug_sources() -> list[dict]:
    global _BYDRUG_SOURCES
    if _BYDRUG_SOURCES is None:
        _BYDRUG_SOURCES = load_bydrug_sources()
    return _BYDRUG_SOURCES

# 旧硬编码列表保留作 fallback
BYDRUG_SOURCES_FALLBACK = [
    {"name": "医药魔方", "slug": "医药魔方", "rating": "B"},
    {"name": "医药魔方Plus", "slug": "医药魔方Plus", "rating": "B"},
    {"name": "医药魔方Invest", "slug": "医药魔方Invest", "rating": "B"},
    {"name": "药时代", "slug": "药时代", "rating": "B"},
    {"name": "药明康德", "slug": "药明康德", "rating": "B"},
    {"name": "医药笔记", "slug": "医药笔记", "rating": "B"},
    {"name": "医药经济报", "slug": "医药经济报", "rating": "B"},
    {"name": "动脉网", "slug": "动脉网", "rating": "B"},
    {"name": "E药经理人", "slug": "E药经理人", "rating": "B"},
    {"name": "药渡", "slug": "药渡", "rating": "B"},
    {"name": "生物谷", "slug": "生物谷", "rating": "B"},
    {"name": "米内网", "slug": "米内网", "rating": "B"},
    {"name": "医药观澜", "slug": "医药观澜", "rating": "B"},
    {"name": "研发客", "slug": "研发客", "rating": "B"},
    {"name": "GBIHealth", "slug": "GBIHealth", "rating": "B"},
    {"name": "Insight数据库", "slug": "DXY-Insight", "rating": "B"},
    {"name": "CPHI制药在线", "slug": "CPHI制药在线", "rating": "B"},
    {"name": "新康界", "slug": "新康界", "rating": "B"},
    {"name": "赛柏蓝", "slug": "赛柏蓝", "rating": "B"},
    {"name": "医疗器械创新网", "slug": "医疗器械创新网", "rating": "B"},
    {"name": "MedTF", "slug": "MedTF", "rating": "B"},
    {"name": "生辉", "slug": "生辉", "rating": "B"},
    {"name": "同写意", "slug": "同写意", "rating": "B"},
    {"name": "深究科学", "slug": "深究科学", "rating": "B"},
    {"name": "医药投资部落", "slug": "医药投资部落", "rating": "B"},
    {"name": "瞪羚社", "slug": "瞪羚社", "rating": "B"},
    {"name": "药创新", "slug": "药创新", "rating": "B"},
    {"name": "Medaverse", "slug": "Medaverse", "rating": "B"},
    {"name": "氨基观察", "slug": "氨基观察", "rating": "B"},
    {"name": "新药猎人笔记", "slug": "新药猎人笔记", "rating": "B"},
    {"name": "一度医药", "slug": "一度医药", "rating": "B"},
    {"name": "蓝鲸新闻", "slug": "蓝鲸新闻", "rating": "B"},
    {"name": "药智网", "slug": "药智网", "rating": "B"},
    # C级精选
    {"name": "细胞与基因治疗领域", "slug": "细胞与基因治疗领域", "rating": "C"},
    {"name": "药融圈info", "slug": "药融圈info", "rating": "C"},
    {"name": "医药速览", "slug": "医药速览", "rating": "C"},
    {"name": "精准药物", "slug": "精准药物", "rating": "C"},
]


def _resolve_iife_params(html: str) -> dict:
    """从 __NUXT__ IIFE 提取参数映射表 (variable_name -> value)"""
    m = re.search(r'__NUXT__=\(function\(([^)]+)\)\{return\s*', html)
    if not m:
        return {}
    pnames = [p.strip() for p in m.group(1).split(',')]
    idx = html.index('__NUXT__')
    body_start = html.index('{', idx + 50)
    depth = 0
    for i in range(body_start, len(html)):
        if html[i] == '{': depth += 1
        elif html[i] == '}':
            depth -= 1
            if depth == 0:
                body_end = i + 1
                break
    args_start = html.find("(", body_end)
    if args_start < 0:
        return {}
    depth = 0
    in_str = False
    escaped = False
    args_end = -1
    for i in range(args_start, len(html)):
        char = html[i]
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_str:
            escaped = True
            continue
        if char == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                args_end = i
                break
    if args_end < 0:
        return {}
    args_str = html[args_start + 1:args_end]
    args = []
    buf, in_str, escaped = '', False, False
    for c in args_str:
        if escaped:
            buf += c
            escaped = False
            continue
        if c == "\\" and in_str:
            buf += c
            escaped = True
            continue
        if c == '"':
            in_str = not in_str
        elif c == ',' and not in_str:
            args.append(_decode_js_value(buf.strip()))
            buf = ''
            continue
        buf += c
    if buf.strip():
        args.append(_decode_js_value(buf.strip()))
    return {pnames[i]: args[i] for i in range(min(len(pnames), len(args)))}


def _decode_js_value(raw: str, params: dict | None = None) -> str:
    """Decode a simple Nuxt literal or resolve an IIFE parameter."""
    value = raw.strip()
    if not value:
        return ""
    if value.startswith('"') and value.endswith('"'):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = value[1:-1]
        return str(decoded)
    if params and value in params:
        return str(params.get(value) or "")
    return ""


def _find_js_object_start(text: str, pos: int) -> int:
    start = text.rfind("{", 0, pos)
    if start < 0:
        raise ValueError("cannot find article object start")
    return start


def _find_js_object_end(text: str, start: int) -> int:
    depth = 0
    in_str = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_str:
            escaped = True
            continue
        if char == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    raise ValueError("cannot find article object end")


def _extract_bydrug_article_objects(html: str) -> list[str]:
    objects: list[str] = []
    seen_spans: set[tuple[int, int]] = set()
    for match in re.finditer(r'\besid:"[0-9a-f]{32}"', html):
        start = _find_js_object_start(html, match.start())
        end = _find_js_object_end(html, start)
        span = (start, end)
        if span not in seen_spans:
            seen_spans.add(span)
            objects.append(html[start:end])
    return objects


def _object_field(obj: str, field: str, params: dict) -> str:
    match = re.search(
        rf'\b{re.escape(field)}:("[^"\\]*(?:\\.[^"\\]*)*"|[A-Za-z_$][\w$]*)',
        obj,
    )
    return _decode_js_value(match.group(1), params) if match else ""


def _object_tags(obj: str, params: dict) -> list[str]:
    match = re.search(r'\btags:\[([^\]]*)\]', obj)
    if not match:
        return []
    tags = []
    for raw in match.group(1).split(","):
        value = _decode_js_value(raw.strip(), params)
        if value:
            tags.append(value)
    return tags


def parse_bydrug_source_html(html: str) -> list[dict]:
    """Parse ByDrug Nuxt SSR source-page articles without crossing object bounds."""
    params = _resolve_iife_params(html)
    article_objects = _extract_bydrug_article_objects(html)
    articles: list[dict] = []
    for obj in article_objects:
        esid = _object_field(obj, "esid", params)
        title = _object_field(obj, "title", params)
        if not esid or not title or len(title) < 5:
            continue
        pub_time = ""
        time_source = "failed"
        time_confidence = 0.0
        for field, src, conf in [
            ("publishTime", "bydrug_nuxt", 0.95),
            ("createTime", "bydrug_nuxt", 0.9),
            ("updateTime", "bydrug_nuxt", 0.85),
        ]:
            value = _object_field(obj, field, params)
            if value:
                pub_time = value
                time_source = src
                time_confidence = conf
                break
        articles.append({
            "title": title,
            "summary": _object_field(obj, "abstracts", params)[:300],
            "tags": _object_tags(obj, params),
            "bydrug_url": f"https://bydrug.pharmcube.com/news/detail/{esid}",
            "publish_time": pub_time,
            "time_source": time_source,
            "time_confidence": time_confidence,
            "original_url": "",
        })
    return articles


def scrape_bydrug_source_page(slug: str) -> list[dict]:
    """抓取 ByDrug 来源页面文章列表（从 Nuxt.js SSR __NUXT__ 数据提取）"""
    encoded_slug = slug if '%' in slug else urllib.parse.quote(slug)
    url = f"https://bydrug.pharmcube.com/news/summary/source/{encoded_slug}"
    html = fetch_html(url)
    return parse_bydrug_source_html(html)


def _in_time_window(
    article: dict,
    window_start: dt.datetime | None,
    window_end: dt.datetime | None,
) -> bool:
    if not window_start or not window_end:
        return True
    parsed = parse_time(article.get("publish_time", ""))
    if parsed is None:
        return False
    return window_start <= parsed <= window_end


def scrape_bydrug(
    window_start: dt.datetime | None = None,
    window_end: dt.datetime | None = None,
) -> tuple[list[dict], list[dict], dict[str, int]]:
    """完整 ByDrug 抓取（从 sources.md 动态加载全部来源）。
    并发获取 /news/detail/{esid} 详情页中的原文链接。"""
    import concurrent.futures
    results: list[dict] = []
    failures: list[dict] = []
    now = dt.datetime.now()
    sources = get_bydrug_sources()
    total = len(sources)
    success = 0
    outside_window = 0
    unknown_time = 0
    print(f"  加载 {total} 个 ByDrug 来源（A:{sum(1 for s in sources if s['rating']=='A')} B:{sum(1 for s in sources if s['rating']=='B')} C:{sum(1 for s in sources if s['rating']=='C')}）")

    for i, src in enumerate(sources):
        slug = src["slug"]
        try:
            page_articles = scrape_bydrug_source_page(slug)
            success += 1
            kept_articles = []
            for pa in page_articles:
                if window_start and window_end:
                    parsed = parse_time(pa.get("publish_time", ""))
                    if parsed is None:
                        unknown_time += 1
                        continue
                    if parsed < window_start or parsed > window_end:
                        outside_window += 1
                        continue
                kept_articles.append(pa)

            for pa in kept_articles:
                pub_ts = pa.get("publish_time") or None
                ts = pa.get("time_source", "failed")
                tc = pa.get("time_confidence", 0)
                classification = classify_article_details(
                    pa["title"], pa.get("summary", ""), pa.get("tags", [])
                )
                results.append({
                    "title": pa["title"],
                    "summary": pa.get("summary", ""),
                    "source": src["name"],
                    "source_url": pa["bydrug_url"],
                    "source_rating": src["rating"],
                    "publish_time": pub_ts,
                    "time_source": ts,
                    "time_confidence": tc,
                    "tags": pa.get("tags", []),
                    **classification,
                    "source_type": "bydrug",
                    "_esid": pa.get("bydrug_url", "").split("/")[-1],
                })
            print(f"  [{i+1}/{total}] {src['name']}: {len(kept_articles)}/{len(page_articles)} 篇")
        except Exception as e:
            print(f"  [{i+1}/{total}] {src['name']}: 失败 - {str(e)[:40]}")
            failures.append({
                "source": src["name"],
                "url": f"https://bydrug.pharmcube.com/news/summary/source/{urllib.parse.quote(slug)}",
                "error_category": "ByDrug 来源抓取失败",
                "error_detail": str(e)[:200],
            })

    # 并发获取 /news/detail/{esid} 提取原文链接
    detail_articles = [a for a in results if a.get("_esid")]
    if detail_articles:
        print(f"  并发获取 {len(detail_articles)} 篇 /news/detail/ 详情页 ...")
        orig_count = 0

        def _fetch_orig(art):
            nonlocal orig_count
            try:
                dh = fetch_html(f"https://bydrug.pharmcube.com/news/detail/{art['_esid']}")
                orig_m = re.findall(r'href="(https?://mp\.weixin\.qq\.com[^"]+)"', dh)
                if orig_m:
                    art["source_url"] = orig_m[0]
                    orig_count += 1
                    return
                links = re.findall(r'href="(https?://[^"]+)"', dh)
                for link in links:
                    if "pharmcube.com" not in link and "bydrug" not in link:
                        if "beian" not in link:
                            art["source_url"] = link
                            orig_count += 1
                            return
            except Exception:
                pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            list(ex.map(_fetch_orig, detail_articles))
        print(f"    完成，找到 {orig_count} 个原文链接")

    # 去重
    seen, deduped = set(), []
    for a in results:
        a.pop("_esid", None)
        f = fp(a["title"])
        if f not in seen:
            seen.add(f)
            a["id"] = f
            deduped.append(a)
    print(f"  ByDrug 去重后: {len(deduped)} 篇 (成功 {success}/{total} 来源)")
    if window_start and window_end:
        print(f"  ByDrug 时间过滤: 排除窗口外 {outside_window} 篇，无有效时间 {unknown_time} 篇")
    metrics = {
        "sources_total": total,
        "sources_successful": success,
        "source_failures": len(failures),
        "outside_window_excluded": outside_window,
        "unknown_time_excluded": unknown_time,
    }
    return deduped, failures, metrics


# ═══════════════════════════════════════════════════════════
#  Source 3: 政府获批来源
# ═══════════════════════════════════════════════════════════

GOV_SOURCES = [
    {"name": "国家药监局药品监管动态", "url": "https://www.nmpa.gov.cn/yaopin/ypjgdt/index.html", "region": "中国", "rating": "A", "api": None},
    {"name": "国家药监局医疗器械监管动态", "url": "https://www.nmpa.gov.cn/ylqx/ylqxjgdt/index.html", "region": "中国", "rating": "A", "api": None},
    {"name": "国家药监局化妆品监管动态", "url": "https://www.nmpa.gov.cn/hzhp/hzhpjgdt/index.html", "region": "中国", "rating": "A", "api": None},
    {"name": "FDA 新药批准 (美国)", "url": "https://www.fda.gov/drugs/novel-drug-approvals-fda", "region": "美国", "rating": "A",
     "api": "https://api.fda.gov/drug/drugsfda.json?search=submissions.submission_status_date:[{from}+TO+{to}]&limit=20"},
    {"name": "EMA 药品数据 (欧盟)", "url": "https://www.ema.europa.eu/en/medicines/download-medicine-data", "region": "欧盟", "rating": "A", "api": None},
    {"name": "PMDA 批准药品 (日本)", "url": "https://www.pmda.go.jp/english/review-services/reviews/approved-information/drugs/0002.html", "region": "日本", "rating": "A", "api": None},
    {"name": "MHRA 上市许可 (英国)", "url": "https://www.gov.uk/government/collections/marketing-authorisations-lists-of-granted-licences", "region": "英国", "rating": "A", "api": None},
    {"name": "TGA 批准决定 (澳大利亚)", "url": "https://www.tga.gov.au/products/regulations-all-products/about-australian-register-therapeutic-goods-artg/about-australian-prescription-medicine-decision-summaries-auspmdss", "region": "澳大利亚", "rating": "A", "api": None},
]


def _scrape_fda_api(api_url_template: str, window_start: dt.datetime = None, window_end: dt.datetime = None) -> tuple[list[dict], list[dict]]:
    """Scrape FDA drug approvals via openFDA API. Returns only NDA/BLA original approvals."""
    from_date = (window_start or dt.datetime.now() - dt.timedelta(days=90)).strftime("%Y%m%d")
    to_date = (window_end or dt.datetime.now()).strftime("%Y%m%d")
    url = api_url_template.replace("{from}", from_date).replace("{to}", to_date)
    articles, failures = [], []
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "HealthcareIntelligenceMonitor/1.0")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for r in data.get("results", []):
            app_num = r.get("application_number", "")
            # Only NDA or BLA, skip ANDA (generics)
            if not (app_num.startswith("NDA") or app_num.startswith("BLA")):
                continue
            ofda = r.get("openfda", {}) or {}
            brand = (ofda.get("brand_name") or ["?"])[0]
            generic = (ofda.get("generic_name") or [""])[0]
            company = (ofda.get("manufacturer_name") or ["?"])[0]
            for sub in r.get("submissions", []):
                st = sub.get("submission_type", "")
                ss = sub.get("submission_status", "")
                sd = sub.get("submission_status_date", "")
                if st == "ORIG" and ss == "AP" and sd >= from_date:
                    app_type = app_num[:3] if app_num else "?"
                    if sd >= from_date:
                        articles.append({
                            "title": f"FDA \u6279\u51c6: {brand} ({generic[:80] if generic else '\u65b0\u5206\u5b50\u5b9e\u4f53'})",
                            "summary": f"\u7533\u8bf7\u53f7 {app_num}\uff08{app_type}\uff09\uff0c\u516c\u53f8: {company}\uff0c\u6279\u51c6\u65e5\u671f: {sd}",
                            "source": "FDA \u65b0\u836f\u6279\u51c6 (\u7f8e\u56fd)",
                            "source_url": f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={app_num}",
                            "source_rating": "A",
                            "publish_time": f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}T00:00:00",
                            "level_1_category": "1. \u521b\u65b0\u836f",
                            "level_2_category": "1.1 \u5c0f\u5206\u5b50\u521b\u65b0\u836f",
                            "classification_method": "rule",
                            "classification_confidence": 0.9,
                            "classification_reason": "FDA \u539f\u59cb\u65b0\u836f\u7533\u8bf7\u83b7\u6279",
                            "classification_schema_version": "1.0",
                            "classification_model_revision": "none",
                            "source_type": "government",
                        })
        n = len(articles)
        print(f"  FDA API: {n} NDA/BLA approvals ({from_date} ~ {to_date})")
    except Exception as exc:
        failures.append({
            "source": "FDA \u65b0\u836f\u6279\u51c6 (\u7f8e\u56fd)", "url": url,
            "error_category": f"FDA API \u9519\u8bef: {str(exc)[:80]}",
            "error_detail": str(exc)[:200],
        })
        print(f"  FDA API: \u5931\u8d25 \u2014 {exc}")
    return articles, failures


def scrape_government(window_start: dt.datetime = None, window_end: dt.datetime = None) -> tuple[list[dict], list[dict]]:
    """采集政府获批来源。FDA 走 openFDA API，其他来源检测可访问性。"""
    articles, failures = [], []
    for src in GOV_SOURCES:
        try:
            if src.get("api"):
                api_arts, api_fails = _scrape_fda_api(src["api"], window_start, window_end)
                articles.extend(api_arts)
                failures.extend(api_fails)
                continue

            # Non-API sources: accessibility check
            fetch_html(src["url"])
            articles.append({
                "title": f"[{src['region']}] {src['name']}",
                "summary": f"官方页面可访问。待实现结构化解析。链接: {src['url']}",
                "source": src["name"],
                "source_url": src["url"],
                "source_rating": src["rating"],
                "publish_time": dt.datetime.now().isoformat(timespec="seconds"),
                "level_1_category": "其他/综合",
                "level_2_category": "其他/综合",
                "classification_method": "other",
                "classification_confidence": 1.0,
                "classification_reason": "官方来源可访问标记",
                "classification_schema_version": "1.0",
                "classification_model_revision": "none",
                "source_type": "government",
            })
            print(f"  {src['name']}: 可访问")
        except Exception as exc:
            msg = str(exc).lower()
            if "412" in msg:
                cat = "HTTP 412（需浏览器环境，无法直接抓取）"
            elif "404" in msg:
                cat = "HTTP 404 页面不存在"
            elif "name or service" in msg:
                cat = "DNS 解析失败"
            elif "timeout" in msg:
                cat = "连接超时"
            else:
                cat = f"网络错误: {str(exc)[:80]}"
            failures.append({
                "source": src["name"], "url": src["url"],
                "error_category": cat, "error_detail": str(exc)[:200],
            })
            print(f"  {src['name']}: 失败 — {cat}")
    return articles, failures
# ═══════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════
#  时间窗口
# ═══════════════════════════════════════════════════════════

def get_default_time_window() -> tuple[dt.datetime, dt.datetime]:
    """默认窗口：前一天 9:00 AM → 当天 9:00 AM (CST)"""
    now = dt.datetime.now()
    today_9am = dt.datetime(now.year, now.month, now.day, 9, 0)
    yesterday_9am = today_9am - dt.timedelta(days=1)
    return yesterday_9am, today_9am


def parse_time(t: str) -> dt.datetime | None:
    """解析时间字符串到 datetime"""
    if not t:
        return None
    value = t.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(value)
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        pass
    try:
        parts = value.replace("T", " ").split(" ")
        d = parts[0]
        m = parts[1] if len(parts) > 1 else "00:00"
        if len(m) > 5:
            m = m[:5]
        return dt.datetime.strptime(f"{d} {m}", "%Y-%m-%d %H:%M")
    except Exception:
        return None


def filter_by_time_window(articles: list[dict], window_start: dt.datetime, window_end: dt.datetime) -> list[dict]:
    """按时间窗口过滤文章。没有 publish_time 的文章不进入窗口结果。"""
    filtered = []
    for a in articles:
        t = parse_time(a.get("publish_time", ""))
        if t is None:
            continue
        if t < window_start or t > window_end:
            continue
        filtered.append(a)
    return filtered


def deduplicate_articles(article_lists: list[list[dict]]) -> list[dict]:
    """去重：link 优先，title 次优先"""
    seen_links: set = set()
    seen_titles: set = set()
    result: list[dict] = []
    for articles in article_lists:
        for a in articles:
            link = a.get("source_url", "").strip()
            title = a.get("title", "").strip()
            if link and link in seen_links:
                continue
            if title and title in seen_titles:
                continue
            if link:
                seen_links.add(link)
            if title:
                seen_titles.add(title)
            result.append(a)
    return result


def scrape_all(source_filter: str = "", window_start: dt.datetime = None, window_end: dt.datetime = None) -> dict[str, Any]:
    print("=" * 60)
    print("统一医疗健康数据抓取（四级分类体系）")
    if window_start and window_end:
        print(f"时间窗口: {window_start.strftime('%Y-%m-%d %H:%M')} ~ {window_end.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    all_articles: list[dict] = []
    failures: list[dict] = []
    collection_quality: dict[str, Any] = {}

    if not source_filter or source_filter == "vbdata":
        print("\n[1/3] 动脉网 vbdata.cn（主页 + 投融资频道）")
        vb_articles = scrape_vbdata()
        if window_start and window_end:
            vb_articles = filter_by_time_window(vb_articles, window_start, window_end)
            print(f"  动脉网: {len(vb_articles)} 篇（去重+时间过滤后）")
        else:
            print(f"  动脉网: {len(vb_articles)} 篇（去重后）")
        all_articles.extend(vb_articles)

    if not source_filter or source_filter == "bydrug":
        print("\n[2/3] ByDrug 聚合来源")
        bd_articles, bd_failures, bd_metrics = scrape_bydrug(window_start, window_end)
        failures.extend(bd_failures)
        collection_quality["bydrug"] = bd_metrics
        if window_start and window_end:
            print(f"  ByDrug: {len(bd_articles)} 篇（时间过滤后）")
        all_articles.extend(bd_articles)

    if not source_filter:
        print("\n[3/3] 政府获批来源")
        gov_arts, gov_fails = scrape_government()
        if window_start and window_end:
            gov_arts = filter_by_time_window(gov_arts, window_start, window_end)
        all_articles.extend(gov_arts)
        failures.extend(gov_fails)

    # 全局去重：link 优先 → title 次优先
    deduped = deduplicate_articles([all_articles])
    for a in deduped:
        a["id"] = a.get("id") or fp(a["title"])
        a["collected_at"] = dt.datetime.now().isoformat(timespec="seconds")

    deduped.sort(key=lambda x: x.get("publish_time") or "", reverse=True)

    stats: dict = {
        "total": len(deduped),
        "by_source": {},
        "by_level1_category": {},
        "by_level2_category": {},
        "by_rating": {},
        "by_source_type": {},
        "collection_quality": collection_quality,
    }
    for a in deduped:
        s = a.get("source", "未知")
        stats["by_source"][s] = stats["by_source"].get(s, 0) + 1
        c1 = a.get("level_1_category", "其他/综合")
        stats["by_level1_category"][c1] = stats["by_level1_category"].get(c1, 0) + 1
        c2 = a.get("level_2_category", "其他/综合")
        stats["by_level2_category"][c2] = stats["by_level2_category"].get(c2, 0) + 1
        r = a.get("source_rating", "B")
        stats["by_rating"][f"{r}级"] = stats["by_rating"].get(f"{r}级", 0) + 1
        t = a.get("source_type", "other")
        stats["by_source_type"][t] = stats["by_source_type"].get(t, 0) + 1

    print(f"\n{'=' * 60}")
    print(f"完成: {len(deduped)} 篇, 失败 {len(failures)} 来源")
    for cat, cnt in sorted(stats["by_level1_category"].items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt} 篇")
    for rating, cnt in sorted(stats["by_rating"].items()):
        print(f"  {rating}: {cnt} 篇")
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "articles": deduped,
        "failures": failures,
        "stats": stats,
    }


def _write_collected_txt(path: Path, result: dict) -> None:
    """Write structured markdown of all articles to collected.txt."""
    articles = result.get("articles", [])
    failures = result.get("failures", [])
    stats = result.get("stats", {})
    tw = result.get("time_window", {})

    lines = []
    lines.append(f"# Healthcare Intelligence Collected — {dt.datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append(f"- 生成时间：{result.get('generated_at', '')}")
    lines.append(f"- 时间窗口：{tw.get('start', '')} ~ {tw.get('end', '')}")
    total_sources = len(set(a.get("source", "") for a in articles))
    lines.append(f"- 来源数：{total_sources}")
    lines.append(f"- 文章总数：{len(articles)}")
    lines.append(f"- 失败来源：{len(failures)}")
    lines.append("")
    lines.append("## 分类统计")
    for cat, cnt in sorted(stats.get("by_level1_category", {}).items(), key=lambda x: -x[1]):
        lines.append(f"- {cat}: {cnt} 篇")
    lines.append("")

    for i, a in enumerate(articles, 1):
        lines.append(f"## {i}. {a.get('title', '')}")
        lines.append("")
        lines.append(f"- 发布时间：{a.get('publish_time', '')}")
        lines.append(f"- 一级分类：{a.get('level_1_category', '')}")
        lines.append(f"- 二级分类：{a.get('level_2_category', '')}")
        cat_method = a.get('classification_method', '')
        cat_confidence = a.get('classification_confidence', 0)
        lines.append(f"- 分类方法：{cat_method}（置信度 {cat_confidence:.0%}）")
        lines.append(f"- 来源可信度：{a.get('source_rating', '')}")
        lines.append(f"- 事件类型：{a.get('event_type', '')}")
        lines.append(f"- 重要性：{a.get('importance', '')}")
        summary = a.get('summary', '') or ''
        if summary:
            lines.append(f"- 概要：{summary}")
        if a.get('tags'):
            lines.append(f"- 标签：{'、'.join(a['tags'])}")
        lines.append(f"- 来源链接：")
        lines.append(f"  - [{a.get('source', '')}]({a.get('source_url', '')})")
        lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))


def _write_errors_txt(path: Path, result: dict) -> None:
    """Write failure log to errors.txt."""
    failures = result.get("failures", [])
    tw = result.get("time_window", {})

    lines = []
    lines.append(f"# 采集错误日志 — {dt.datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append(f"- 时间窗口：{tw.get('start', '')} ~ {tw.get('end', '')}")
    lines.append(f"- 失败来源数：{len(failures)}")
    lines.append("")

    if failures:
        for f in failures:
            source = f.get("source", f.get("name", "未知"))
            error = f.get("error", f.get("error_category", "未知错误"))
            lines.append(f"- **{source}**：{error}")
    else:
        lines.append("无失败来源。")

    with open(path, "w") as f:
        f.write("\n".join(lines))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/tmp/dashboard_data.json")
    parser.add_argument("--data-dir", default="", help="按日期归档目录，写入 collected.txt + errors.txt + dashboard-data.json")
    parser.add_argument("--source", default="")
    parser.add_argument("--start", default="", help="时间窗口开始 (YYYY-MM-DD HH:MM)，默认前一天9:00")
    parser.add_argument("--end", default="", help="时间窗口结束 (YYYY-MM-DD HH:MM)，默认当天9:00")
    args = parser.parse_args()

    if args.start and args.end:
        ws = dt.datetime.strptime(args.start, "%Y-%m-%d %H:%M")
        we = dt.datetime.strptime(args.end, "%Y-%m-%d %H:%M")
    else:
        ws, we = get_default_time_window()

    result = scrape_all(source_filter=args.source, window_start=ws, window_end=we)
    result["time_window"] = {"start": ws.isoformat(), "end": we.isoformat()}

    # Determine output directory
    if args.data_dir:
        out_dir = Path(args.data_dir)
    else:
        out_dir = Path(args.output).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write dashboard-data.json
    json_path = out_dir / "dashboard-data.json"
    with open(json_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n输出: {json_path}")

    # Write collected.txt and errors.txt when --data-dir is used
    if args.data_dir:
        _write_collected_txt(out_dir / "collected.txt", result)
        print(f"输出: {out_dir / 'collected.txt'}")
        _write_errors_txt(out_dir / "errors.txt", result)
        print(f"输出: {out_dir / 'errors.txt'}")
