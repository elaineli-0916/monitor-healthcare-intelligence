#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从爬虫 JSON 生成医疗健康投研看板 HTML"""

import json
import re
import hashlib
import datetime as dt
import os
import sys
from pathlib import Path



REPO_ROOT = Path(__file__).resolve().parents[2]  # skill is at repo root
sys.path.insert(0, str(REPO_ROOT))

try:
    from healthcare_assistant.frontend.injection import assistant_block_html
except ImportError:
    def assistant_block_html():
        print("警告: 未找到 healthcare_assistant 包（前端注入资源），跳过悬浮助手注入")
        return ""


EVENT_TYPE_KEYWORDS = [
    ("投融资", ['融资', '投资', '领投', '种子轮', 'a轮', 'b轮', 'c轮', 'd轮', 'ipo', '募资']),
    ("并购", ['收购', '并购', '买断']),
    ("临床试验", ['临床', '试验', '期临床', 'i期', 'ii期', 'iii期', '临床研究']),
    ("产品获批", ['获批', '批准', '获准', '批件']),
    ("注册申报", ['fda', 'nmpa', 'ema', 'pmda', 'mhra', '申报', '注册', '受理', 'nda', 'bla', '上市申请', '上市许可']),
    ("政策", ['政策', '法规', '医保', '集采', '意见', '行动方案']),
    ("合作授权", ['合作', '授权', 'license', '合资', '战略合作']),
    ("产品发布", ['发布', '推出', '新品', '新产品']),
    ("行业研究", ['研究', '报告', '分析', '观点', '趋势']),
]

DASHBOARD_CATEGORIES = [
    ("1. 创新药", [
        "1.1 小分子创新药",
        "1.2 生物药（抗体/蛋白/核酸/ADC/XDC偶联药物）",
        "1.3 细胞与基因治疗（CGT）",
        "1.4 医药CXO（CRO/CDMO/CSO）",
        "1.5 AI制药",
        "1.6 合成生物学",
    ]),
    ("2. 医疗器械", [
        "2.1 心血管介入",
        "2.2 骨科与植入物",
        "2.3 体外诊断（IVD）",
        "2.4 医学影像",
        "2.5 手术机器人",
        "2.6 神经调控与脑机接口",
    ]),
    ("3. 医疗服务", [
        "3.1 专科医院/连锁诊所",
        "3.2 第三方医学检验（ICL）",
        "3.3 数字医疗/互联网医院",
        "3.4 院外康复与居家医疗",
    ]),
    ("4. 消费医疗与医美", [
        "4.1 医美耗材与器械（注射/光电/埋线）",
        "4.2 功效性护肤品",
        "4.3 减重/代谢管理",
        "4.4 眼视光（近视防控/OK镜）",
        "4.5 口腔正畸与种植",
        "4.6 辅助生殖",
        "4.7 听力",
        "4.8 睡眠",
        "4.9 营养保健（功能食品/特医食品/抗衰）",
    ]),
    ("其他/综合", []),
]

IMPORTANCE_KEYWORDS = {
    "high": ['重磅', '突破', '首次', '首款', '首个', '里程碑', '重大'],
    "low": ['据悉', '消息', '可能', '或'],
}

COMPANY_SUFFIXES = ['公司', '集团', '医药', '生物', '科技', '医疗', '制药', '健康']
DRUG_SUFFIXES = ['药', '素', '肽', '单抗', '疫苗', '胶囊', '片', '注射液', '贴剂']


def infer_event_type(text):
    text_lower = text.lower()
    for etype, keywords in EVENT_TYPE_KEYWORDS:
        for kw in keywords:
            if kw in text_lower:
                return etype
    return "行业研究"


def infer_importance(text):
    text_lower = text.lower()
    for imp, keywords in IMPORTANCE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return imp
    return "medium"


def extract_entities(title, tags):
    companies = []
    products = []
    for tag in tags:
        if tag and len(tag) > 1:
            if any(tag.endswith(s) for s in COMPANY_SUFFIXES):
                companies.append(tag)
            elif any(s in tag for s in DRUG_SUFFIXES):
                products.append(tag)
            else:
                companies.append(tag)

    # Also extract company mentions from title
    known_companies = {
        '百济神州': ('百济神州', 'company'),
        '广药': ('广药集团', 'company'),
        '昌郁医药': ('昌郁医药', 'company'),
        '高特佳': ('高特佳投资', 'company'),
        '商汤医疗': ('商汤医疗', 'company'),
        '爱康': ('爱康集团', 'company'),
        'Excedr': ('Excedr', 'company'),
        'Mirae': ('Mirae', 'company'),
        'Nexus': ('Nexus', 'company'),
        'CORE Biomedicine': ('CORE Biomedicine', 'company'),
        'Claris Bio': ('Claris Bio', 'company'),
        'Novanta': ('Novanta', 'company'),
        'Dopl Technologies': ('Dopl Technologies', 'company'),
        'Aurenar': ('Aurenar', 'company'),
        'Standard BioTools': ('Standard BioTools', 'company'),
    }
    for name, (full_name, etype) in known_companies.items():
        if name in title:
            if etype == 'company':
                if full_name not in companies:
                    companies.append(full_name)

    known_products = {
        '法赞雷生': ('法赞雷生', 'product'),
        'TCE': ('T细胞衔接器(TCE)', 'product'),
        'GPCR': ('GPCR靶向药物', 'product'),
        '降压疫苗': ('降压疫苗', 'product'),
        '透皮贴剂': ('透皮贴剂', 'product'),
        'Telemetrix RPM': ('Telemetrix RPM', 'product'),
        '质谱流式': ('质谱流式细胞仪', 'product'),
        'iKKie': ('爱康iKKie', 'product'),
    }
    for name, (full_name, etype) in known_products.items():
        if name in title:
            if full_name not in products:
                products.append(full_name)

    return companies[:3], products[:3]


def infer_regions(title, summary):
    regions = []
    region_patterns = [
        (r'美国', '美国'), (r'中国', '中国'), (r'FDA', '美国'),
        (r'欧洲', '欧洲'), (r'英国|牛津', '英国/欧洲'),
        (r'日本', '日本/亚太'), (r'出海', '全球/出海'),
    ]
    text = title + summary
    for pattern, region in region_patterns:
        if re.search(pattern, text):
            if region not in regions:
                regions.append(region)
    return regions


# Source rating lookup - A=政府官源, B=专业媒体/研究, C=自媒体/聚合
SOURCE_RATINGS = {
    "动脉网": "B", "CISION": "B", "PR Newswire": "B", "GlobeNewswire": "B",
    "AHHM": "B", "E药学苑": "B", "凯乘资本": "B",
    "李佳英": "B", "赵泓维": "B", "武瑛港": "B", "高康平": "B",
    "李汶芸": "B", "李秋萩": "B", "周秋寒": "B", "季嘉颖": "B", "钟庆宏": "B",
    "国家医保局": "A", "国家药监局": "A", "中国药审": "A",
    "FDA": "A", "EMA": "A", "PMDA": "A",
    "药明康德": "B", "医药魔方": "B", "丁香园": "B", "药渡": "B",
}


def get_source_rating(source):
    """Map source name to rating (A/B/C)"""
    if not source:
        return "B"
    for key, rating in SOURCE_RATINGS.items():
        if key in source:
            return rating
    return "B"


def enrich_articles(articles):
    """为文章补充事件类型、重要性、公司、产品等字段"""
    enriched = []
    for i, a in enumerate(articles):
        text = a.get('title', '') + ' ' + a.get('summary', '')
        companies, products = extract_entities(a.get('title', ''), a.get('tags', []))
        src = a.get('source', '')
        # 兼容新旧字段名
        source_url = a.get('source_url') or a.get('link') or a.get('url', '')
        publish_time = a.get('publish_time') or a.get('date', '')
        level1 = a.get('level_1_category') or a.get('parent_category', '其他/综合')
        level2 = a.get('level_2_category') or a.get('classification', '其他/综合')
        source_rating = a.get('source_rating') or get_source_rating(src)
        e = {
            'id': a.get('id', '') or source_url.split('/')[-1] or f'article_{i}',
            'title': a.get('title', ''),
            'summary': a.get('summary', ''),
            'source': src,
            'source_rating': source_rating,
            'publish_time': publish_time,
            'url': source_url,
            'level_1_category': level1,
            'level_2_category': level2,
            'classification_method': a.get('classification_method', 'legacy'),
            'classification_confidence': a.get('classification_confidence', 0),
            'classification_reason': a.get('classification_reason', ''),
            'classification_schema_version': a.get('classification_schema_version', ''),
            'classification_model_revision': a.get('classification_model_revision', ''),
            'event_type': infer_event_type(text),
            'importance': infer_importance(text),
            'companies': companies,
            'products': products,
            'tags': a.get('tags', []),
            'regions': infer_regions(a.get('title', ''), a.get('summary', '')),
            'source_type': a.get('source_type', ''),
        }
        enriched.append(e)
    return enriched


def generate_html(enriched_articles, output_path, failures=None):
    """生成完整的双栏投研看板 HTML"""
    # Organize by category
    from collections import OrderedDict
    tree = OrderedDict()
    cat_order = ["1. 创新药", "2. 医疗器械", "3. 医疗服务", "4. 消费医疗与医美", "其他/综合"]

    # Pre-populate with ALL categories (including empty ones)
    FULL_CATEGORIES = DASHBOARD_CATEGORIES

    for pcat, subcats in FULL_CATEGORIES:
        if pcat not in tree:
            tree[pcat] = OrderedDict()
        for scat in subcats:
            tree[pcat][scat] = []

    # Fill with actual article data
    for a in enriched_articles:
        pcat = a['level_1_category']
        if pcat not in tree:
            tree[pcat] = OrderedDict()
        scat = a['level_2_category']
        if scat not in tree[pcat]:
            tree[pcat][scat] = []
        tree[pcat][scat].append(a)

    # Data JSON for embedding
    data_json = json.dumps(enriched_articles, ensure_ascii=False)
    tree_json = json.dumps(tree, ensure_ascii=False)
    failures_json = json.dumps(failures or [], ensure_ascii=False)

    # Count stats
    total_articles = len(enriched_articles)
    all_subs = set()
    for pcat, subs in tree.items():
        for scat in subs:
            all_subs.add(scat)
    total_subs = len(all_subs)
    sources = sorted(set(a['source'] for a in enriched_articles if a['source']))
    event_counts = {}
    for article in enriched_articles:
        event_type = article["event_type"]
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
    event_order = [event_type for event_type, _ in EVENT_TYPE_KEYWORDS]
    event_types = [event_type for event_type in event_order if event_type in event_counts]
    event_types.extend(sorted(set(event_counts) - set(event_types)))
    stat_items = [
        "<div class=\"stat-item\" onclick='quickFilter(\"all\")'>"
        f'<span class="stat-num">{total_articles}</span> <span class="stat-label">全部</span>'
        '</div>'
    ]
    stat_items.extend(
        "<div class=\"stat-item\" onclick='quickFilter("
        + json.dumps(event_type, ensure_ascii=False)
        + ")'>"
        f'<span class="stat-num">{event_counts[event_type]}</span> '
        f'<span class="stat-label">{event_type}</span>'
        '</div>'
        for event_type in event_types
    )
    stat_bar_html = "\n      ".join(stat_items)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>医健赛道观测台</title>
<style>
:root {{
  --primary: #173B57;
  --accent: #2563EB;
  --bg: #F6F8FB;
  --card-bg: #FFFFFF;
  --text: #1F2937;
  --muted: #64748B;
  --border: #E5E7EB;
  --sidebar-w: 280px;
  --cat-1: #2563EB;
  --cat-2: #059669;
  --cat-3: #7C3AED;
  --cat-4: #DB2777;
  --cat-other: #64748B;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.5;
  overflow: hidden; height: 100vh;
}}

/* Layout */
.app {{ display:flex; height:100vh; }}

/* Sidebar */
.sidebar {{
  width: var(--sidebar-w); min-width: var(--sidebar-w);
  background: #F0F8FD; border-right: 1px solid var(--border);
  display:flex; flex-direction:column; height:100vh; overflow:hidden;
}}
.sidebar-header {{
  padding: 20px 16px 12px; border-bottom: 1px solid var(--border);
  background: #EDF6FC;
}}
.sidebar-header h1 {{
  font-size: 22px; font-weight: 900; color: var(--primary); font-family: "Songti SC", serif; letter-spacing: 2px; text-shadow: 0 2px 4px rgba(23,59,87,.15);
}}
.sidebar-header .subtitle {{
  font-size: 12px; color: var(--muted); margin-top: 2px;
}}
.sidebar-header .datasource {{
  font-size: 10px; color: #94A3B8; margin-top: 8px; padding-top: 6px; border-top: 1px dashed #CBD5E1;
}}
.sidebar-stats {{
  padding: 12px 16px; background: #D0E8F9; font-size: 12px; color: var(--muted);
  border-bottom: 1px solid var(--border);
}}
.sidebar-stats .stat-row {{ display:flex; justify-content:space-between; padding:2px 0; }}
.sidebar-stats .stat-row .num {{ font-weight:600; color: var(--primary); }}
.sidebar-search {{
  padding: 10px 16px; border-bottom: 1px solid var(--border);
  background: #E3F2FD;
}}
.sidebar-search input {{
  width:100%; padding:6px 10px; border:1px solid var(--border); border-radius:6px;
  font-size:12px; outline:none; background: #EDF6FC;
}}
.sidebar-search input:focus {{ border-color:var(--accent); }}


/* Category tree */
.category-tree {{
  flex:1; overflow-y:auto; padding: 8px 0;
}}
.category-tree::-webkit-scrollbar {{ width:4px; }}
.category-tree::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:2px; }}
.tree-parent {{
  font-size: 13px; font-weight: 600; color: var(--primary);
  padding: 8px 16px 4px; cursor: pointer; user-select: none;
  display:flex; justify-content:space-between; align-items:center;
}}
.tree-parent:hover {{ color: var(--accent); }}
.tree-parent .count {{ font-weight:400; color:var(--muted); font-size:11px; }}
.tree-parent .arrow {{ font-size:10px; color:var(--muted); transition:transform .15s; }}
.tree-parent .arrow.collapsed {{ transform:rotate(-90deg); }}
.tree-child {{
  font-size: 12px; padding: 3px 16px 3px 28px; cursor: pointer;
  display:flex; justify-content:space-between; align-items:center;
  border-left: 2px solid transparent; transition: all .1s;
}}
.tree-child:hover {{ background:#90CAF9; }}
.tree-child.active {{ border-left-color:var(--accent); background:#EFF6FF; color:var(--accent); font-weight:500; }}
.tree-child .count {{ font-size:11px; color:var(--muted); }}
.tree-child .count.zero {{ color:#D1D5DB; }}
.tree-child.empty {{ color:#CBD5E1; cursor:default; font-style:italic; }}
.tree-children {{ overflow:hidden; transition:max-height .2s; }}
.tree-children.collapsed {{ max-height:0 !important; }}

/* Content area */
.content {{
  flex:1; display:flex; flex-direction:column; overflow:hidden;
}}

/* Toolbar */
.toolbar {{
  padding: 12px 20px; background:#E3F2FD; border-bottom:1px solid var(--border);
  display:flex; align-items:center; gap:10px; flex-wrap:wrap; flex-shrink:0;
}}
.toolbar-title {{
  font-size:15px; font-weight:600; color:var(--primary); margin-right:auto;
  white-space:nowrap;
}}
.toolbar .filter-group {{
  display:flex; align-items:center; gap:4px;
}}
.toolbar select, .toolbar input[type="date"] {{
  padding:4px 8px; border:1px solid var(--border); border-radius:4px;
  font-size:12px; background:#EDF6FC; outline:none; cursor:pointer;
}}
.toolbar select:focus {{ border-color:var(--accent); }}
.toolbar .filter-btn {{
  padding:4px 10px; border:1px solid var(--border); border-radius:4px;
  font-size:12px; background:var(--card-bg); cursor:pointer; transition:all .1s;
  white-space:nowrap;
}}
.toolbar .filter-btn:hover {{ border-color:var(--accent); color:var(--accent); }}
.toolbar .filter-btn.active {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
.toolbar .toolbar-search {{
  padding:4px 8px; border:1px solid var(--border); border-radius:4px;
  font-size:12px; outline:none; width:140px; background:#EDF6FC;
}}
.toolbar .toolbar-search:focus {{ border-color:var(--accent); }}

/* Stat bar */
.stat-bar {{
  padding: 8px 20px; background: #EDF6FC; border-bottom: 1px solid var(--border);
  display: flex; gap: 12px 16px; font-size: 12px; flex-shrink: 0; flex-wrap: wrap;
}}
.stat-bar .stat-item {{
  cursor: pointer; padding: 2px 6px; border-radius: 4px;
  transition: background .1s;
}}
.stat-bar .stat-item:hover {{ background: #e2e8f0; }}
.stat-bar .stat-item .stat-num {{ font-weight: 700; color: var(--primary); }}
.stat-bar .stat-item .stat-label {{ color: var(--muted); }}

/* News list */
.news-list {{
  flex:1; overflow-y:auto; padding:12px 20px;
}}
.news-list::-webkit-scrollbar {{ width:6px; }}
.news-list::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:3px; }}

/* Category section */
.cat-section {{
  margin-bottom: 20px;
}}
.cat-section-header {{
  display:flex; align-items:center; gap:8px;
  padding:6px 0; margin-bottom:8px;
  border-bottom:1px solid var(--border);
  position:sticky; top:0; background:var(--bg); z-index:1;
}}
.cat-section-header .cat-badge {{
  display:inline-block; padding:1px 8px; border-radius:3px;
  font-size:11px; font-weight:600; color:#fff;
}}
.cat-section-header .cat-name {{
  font-size:13px; font-weight:600; color:var(--primary);
}}
.cat-section-header .cat-count {{
  font-size:11px; color:var(--muted); margin-left:auto;
}}

/* News item */
.news-item {{
  display:flex; flex-direction:column;
  padding: 10px 12px; margin-bottom:6px;
  background: var(--card-bg); border:1px solid var(--border);
  border-radius:6px; transition:border-color .15s;
}}
.news-item:hover {{ border-color:#CBD5E1; }}
.news-item-top {{
  display:flex; align-items:center; gap:6px; margin-bottom:4px;
}}
.news-item-top .cat-tag {{
  display:inline-block; padding:0 6px; border-radius:3px;
  font-size:10px; font-weight:600; color:#fff; line-height:18px; flex-shrink:0;
}}
.news-item-top .event-type {{
  display:inline-block; padding:0 6px; border-radius:3px;
  font-size:10px; font-weight:500; line-height:18px;
  background:var(--bg); color:var(--muted); flex-shrink:0;
}}
.news-item-top .importance-dot {{
  width:6px; height:6px; border-radius:50%; flex-shrink:0;
}}
.news-item-top .title {{
  font-size:14px; font-weight:600; color:var(--text);
  text-decoration:none; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}}
.news-item-top .title:hover {{ color:var(--accent); }}
.news-item-summary {{
  font-size:12px; color:#475569; line-height:1.5;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
  margin-bottom:4px; cursor:pointer;
}}
.news-item-summary.expanded {{ -webkit-line-clamp:unset; }}
.news-item-meta {{
  display:flex; align-items:center; gap:8px; flex-wrap:wrap;
  font-size:11px; color:var(--muted);
}}
.news-item-meta .source {{
  background:#EFF6FF; color:var(--accent); padding:1px 5px; border-radius:3px;
}}

.rating-badge {{
  display:inline-block; padding:1px 6px; border-radius:3px; font-size:0.68rem; font-weight:600; margin-right:4px;
}}
.rating-badge.rating-A {{ background:#DCFCE7; color:#166534; }}
.rating-badge.rating-B {{ background:#DBEAFE; color:#1E40AF; }}
.rating-badge.rating-C {{ background:#F3F4F6; color:#6B7280; }}
.news-item-meta .tag {{
  background:#F1F5F9; color:#64748B; padding:1px 4px; border-radius:2px;
}}
.news-item-meta .classification-audit {{
  color:var(--muted); border:1px solid var(--border); border-radius:10px;
  padding:1px 6px; cursor:help;
}}
.news-item-meta a {{ color:var(--accent); text-decoration:none; }}
.news-item-meta a:hover {{ text-decoration:underline; }}
.news-item-meta .company {{
  background:#F0FDF4; color:#059669; padding:1px 5px; border-radius:3px;
}}
.news-item-meta .product {{
  background:#FEF3C7; color:#D97706; padding:1px 5px; border-radius:3px;
}}

/* Colors */
.cat-color-1 {{ background:var(--cat-1); }}
.cat-color-2 {{ background:var(--cat-2); }}
.cat-color-3 {{ background:var(--cat-3); }}
.cat-color-4 {{ background:var(--cat-4); }}
.cat-color-other {{ background:var(--cat-other); }}

/* Empty state */
.no-articles {{ padding:40px; text-align:center; color:var(--muted); font-size:13px; }}

/* Clear filter */
.filter-clear {{
  margin-left:auto; font-size:11px; cursor:pointer; color:var(--accent);
}}

/* Responsive */
@media (max-width:900px) {{
  .sidebar {{ display:none; position:fixed; z-index:100; }}
  .sidebar.open {{ display:flex; }}
}}

/* Scrollbar */
.news-list, .category-tree {{
  scroll-behavior: smooth;
}}
</style>
  <link rel="stylesheet" href="https://cdn.staticfile.org/font-awesome/7.0.0/css/all.min.css">
</head>
<body>
<div class="app" id="app">
  <div class="sidebar" id="sidebar">
    <div class="sidebar-header">
      <div style="display:flex;align-items:center;gap:12px;">
        <i class="fas fa-chart-line" style="font-size:28px;color:#0a2448;"></i>
        <div style="flex:1;min-width:0;">
          <h1>医健赛道观测台</h1>
          <div class="subtitle">医疗基金自建产业情报观测平台</div>
        </div>
      </div>
      <div class="datasource">数据源：政府官方、产业媒体、投融资公开资讯（ByDrug、动脉网等）</div>
    </div>
    <div class="sidebar-stats" id="sidebarStats">
      <div class="stat-row"><span>今日收录</span><span class="num" id="statTotal">{total_articles} 条</span></div>
      <div class="stat-row"><span>覆盖子赛道</span><span class="num" id="statSubs">{total_subs} 个</span></div>
      <div class="stat-row"><span>更新时间</span><span class="num" id="statTime">--</span></div>
    </div>
    <div class="sidebar-search">
      <input type="text" id="sidebarSearch" placeholder="搜索标题、公司、标签、摘要…" oninput="onSearch(this.value)">
    </div>
    <div class="category-tree" id="categoryTree"></div>
  </div>

  <div class="content">
    <div class="toolbar">
      <span class="toolbar-title">全部资讯</span>
      <span style="font-size:12px;color:var(--muted)" id="toolbarCount">{total_articles} 条</span>
      <div class="filter-group">
        <select id="filterDate" onchange="applyFilters()">
          <option value="">全部日期</option>
        </select>
        <select id="filterRating" onchange="applyFilters()">
          <option value="">评级: 全部</option>
          <option value="A">评级: A (官源)</option>
          <option value="B">评级: B (专业)</option>
          <option value="C">评级: C (自媒体)</option>
        </select>
        <select id="filterSource" onchange="applyFilters()">
          <option value="">全部来源</option>
{"".join(f'<option value="{s}">{s}</option>' for s in sources)}
        </select>
        <select id="filterEventType" onchange="applyFilters()">
          <option value="">全部事件</option>
{"".join(f'<option value="{e}">{e}</option>' for e in event_types)}
        </select>
        <select id="filterCategory" onchange="applyFilters()">
          <option value="">全部一级分类</option>
{"".join(f'<option value="{c}">{c}</option>' for c in cat_order if c in tree)}
        </select>
        <select id="sortOrder" onchange="applyFilters()">
          <option value="time">按发布时间</option>
          <option value="category">按分类</option>
        </select>
      </div>
    </div>

    <div class="stat-bar" id="statBar">
      {stat_bar_html}
    </div>

    <div class="failures" id="failuresBox" style="display:none;margin:12px 0;">
      <details style="background:#FFF7ED;border:1px solid #FDBA74;border-radius:6px;padding:10px 16px;">
        <summary style="cursor:pointer;font-weight:bold;color:#C2410C;font-size:0.9rem;user-select:none;">
          ⚠ 采集问题 (<span id="failureParseCount">0</span> 个解析 / <span id="failureFetchCount">0</span> 个连接) — 点击展开
        </summary>
        <div id="failuresDetail" style="margin-top:8px;font-size:0.82rem;color:#92400E;"></div>
      </details>
    </div>
    <div class="news-list" id="newsList"></div>
  </div>
</div>

<script>
const ARTICLES = {data_json};
const FAILURES_DATA = {failures_json};
const TREE = {tree_json};

const CAT_COLORS = {{
  "1. 创新药": "#2563EB",
  "2. 医疗器械": "#059669",
  "3. 医疗服务": "#7C3AED",
  "4. 消费医疗与医美": "#DB2777",
  "其他/综合": "#64748B"
}};
const CAT_CLASSES = {{
  "1. 创新药": "cat-color-1",
  "2. 医疗器械": "cat-color-2",
  "3. 医疗服务": "cat-color-3",
  "4. 消费医疗与医美": "cat-color-4",
  "其他/综合": "cat-color-other"
}};
const IMPORTANCE_COLORS = {{ high: "#DC2626", medium: "#F59E0B", low: "#9CA3AF" }};
const CAT_ORDER = {json.dumps(cat_order)};

// Set update time
document.getElementById('statTime').innerText = new Date().toLocaleString('zh-CN', {{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}});

// Build category tree
function buildTree() {{
  const tree = document.getElementById('categoryTree');
  const parentStates = JSON.parse(localStorage.getItem('tree_states') || '{{}}');

  for (const parent of CAT_ORDER) {{
    const subs = TREE[parent];
    if (!subs) continue;
    const subEntries = Object.entries(subs);
    const parentCount = subEntries.reduce((s, [,items]) => s + items.length, 0);

    const isCollapsed = parentStates[parent] === false;
    const parentDiv = document.createElement('div');
    parentDiv.className = 'tree-parent';
    parentDiv.dataset.parent = parent;
    parentDiv.innerHTML = `<span>${{parent}} <span class="count">${{parentCount}}</span></span><span class="arrow ${{isCollapsed ? 'collapsed' : ''}}">▼</span>`;
    parentDiv.onclick = () => {{
      const children = parentDiv.nextElementSibling;
      const arrow = parentDiv.querySelector('.arrow');
      children.classList.toggle('collapsed');
      arrow.classList.toggle('collapsed');
      const states = JSON.parse(localStorage.getItem('tree_states') || '{{}}');
      states[parent] = !children.classList.contains('collapsed');
      localStorage.setItem('tree_states', JSON.stringify(states));
    }};
    tree.appendChild(parentDiv);

    const childrenDiv = document.createElement('div');
    childrenDiv.className = 'tree-children' + (isCollapsed ? ' collapsed' : '');
    childrenDiv.style.maxHeight = subEntries.length * 30 + 'px';

    for (const [sub, items] of subEntries) {{
      const child = document.createElement('div');
      child.className = 'tree-child';
      child.dataset.sub = sub;
      child.dataset.parent = parent;
      const isEmpty = items.length === 0;
      if (isEmpty) child.classList.add('empty');
      child.innerHTML = `<span>${{sub}}</span><span class="count ${{isEmpty ? 'zero' : ''}}">${{items.length}}</span>`;
      child.onclick = () => {{
        if (!isEmpty) {{
          document.querySelectorAll('.tree-child').forEach(c => c.classList.remove('active'));
          child.classList.add('active');
          scrollToCategory(parent, sub);
        }}
      }};
      childrenDiv.appendChild(child);
    }}
    tree.appendChild(childrenDiv);
  }}
}}

// Scroll to category
function scrollToCategory(parent, sub) {{
  const el = document.getElementById('section-' + sub.replace(/[\\s()/.]+/g, '-'));
  if (el) {{
    el.scrollIntoView({{ behavior:'smooth', block:'start' }});
  }}
}}

// Render news
function renderNews(articles) {{
  const list = document.getElementById('newsList');
  list.innerHTML = '';
  if (articles.length === 0) {{
    list.innerHTML = '<div class="no-articles">暂无匹配的资讯</div>';
    return;
  }}

  const grouped = {{}};
  for (const a of articles) {{
    const key = a.level_1_category + '||' + a.level_2_category;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(a);
  }}

  for (const [key, items] of Object.entries(grouped)) {{
    const [parent, sub] = key.split('||');
    const secId = 'section-' + sub.replace(/[\\s()/.]+/g, '-');

    const section = document.createElement('div');
    section.className = 'cat-section';
    section.id = secId;

    const header = document.createElement('div');
    header.className = 'cat-section-header';
    const badge = document.createElement('span');
    badge.className = 'cat-badge ' + (CAT_CLASSES[parent] || 'cat-color-other');
    badge.textContent = parent.replace(/^\\d+\\.\\s*/, '');
    header.appendChild(badge);
    const name = document.createElement('span');
    name.className = 'cat-name';
    name.textContent = sub;
    header.appendChild(name);
    const cnt = document.createElement('span');
    cnt.className = 'cat-count';
    cnt.textContent = `${{items.length}} 条`;
    header.appendChild(cnt);
    section.appendChild(header);

    for (const a of items) {{
      const item = document.createElement('div');
      item.className = 'news-item';

      // Top row
      const top = document.createElement('div');
      top.className = 'news-item-top';

      const catTag = document.createElement('span');
      catTag.className = 'cat-tag ' + (CAT_CLASSES[a.level_1_category] || 'cat-color-other');
      catTag.textContent = a.level_2_category.replace(/^\\d+\\.\\d+\\s*/, '');
      top.appendChild(catTag);

      const etype = document.createElement('span');
      etype.className = 'event-type';
      etype.textContent = a.event_type;
      top.appendChild(etype);

      const imp = document.createElement('span');
      imp.className = 'importance-dot';
      imp.style.background = IMPORTANCE_COLORS[a.importance] || '#9CA3AF';
      top.appendChild(imp);

      const title = document.createElement('a');
      title.className = 'title';
      title.href = a.url || '#';
      title.target = '_blank';
      title.textContent = a.title;
      top.appendChild(title);

      item.appendChild(top);

      // Summary
      const summary = document.createElement('div');
      summary.className = 'news-item-summary';
      summary.textContent = a.summary || '';
      summary.onclick = () => summary.classList.toggle('expanded');
      item.appendChild(summary);

      // Meta
      const meta = document.createElement('div');
      meta.className = 'news-item-meta';

      if (a.source_rating) {{
        const r = document.createElement('span');
        r.className = 'rating-badge rating-' + a.source_rating;
        r.textContent = a.source_rating + '级';
        meta.appendChild(r);
      }}
      if (a.source) {{
        const s = document.createElement('span');
        s.className = 'source';
        s.textContent = a.source;
        meta.appendChild(s);
      }}

      if (a.publish_time) {{
        const t = document.createElement('span');
        t.textContent = a.publish_time;
        meta.appendChild(t);
      }}

      if (a.classification_method) {{
        const audit = document.createElement('span');
        audit.className = 'classification-audit';
        const confidence = Math.round((a.classification_confidence || 0) * 100);
        audit.textContent = `分类:${{a.classification_method}} ${{confidence}}%`;
        audit.title = a.classification_reason || '';
        meta.appendChild(audit);
      }}

      for (const c of (a.companies || [])) {{
        const tag = document.createElement('span');
        tag.className = 'company';
        tag.textContent = c;
        meta.appendChild(tag);
      }}

      for (const p of (a.products || [])) {{
        const tag = document.createElement('span');
        tag.className = 'product';
        tag.textContent = p;
        meta.appendChild(tag);
      }}

      for (const t of (a.tags || [])) {{
        const tag = document.createElement('span');
        tag.className = 'tag';
        tag.textContent = '#' + t;
        meta.appendChild(tag);
      }}

      if (a.regions && a.regions.length > 0) {{
        const r = document.createElement('span');
        r.textContent = a.regions.join(' / ');
        meta.appendChild(r);
      }}

      if (a.url) {{
        const lnk = document.createElement('a');
        lnk.href = a.url;
        lnk.target = '_blank';
        lnk.textContent = '查看原文 →';
        meta.appendChild(lnk);
      }}

      item.appendChild(meta);
      section.appendChild(item);
    }}

    list.appendChild(section);
  }}

  // Intersection observer for active highlight
  const observer = new IntersectionObserver((entries) => {{
    entries.forEach(entry => {{
      if (entry.isIntersecting) {{
        const id = entry.target.id;
        document.querySelectorAll('.tree-child').forEach(c => c.classList.remove('active'));
        const sub = id.replace(/^section-/, '').replace(/-/g, ' ');
        document.querySelectorAll('.tree-child').forEach(c => {{
          if (c.dataset.sub && c.dataset.sub.replace(/[\\s()/.]+/g, '-') === id.replace('section-', '')) {{
            c.classList.add('active');
          }}
        }});
      }}
    }});
  }}, {{ threshold: 0.2 }});

  document.querySelectorAll('.cat-section').forEach(s => observer.observe(s));
}}

// Search and filter
let currentFilter = {{ search: '', source: '', eventType: '', category: '', date: '', sort: 'time' }};

function onSearch(value) {{
  currentFilter.search = value;
  applyFilters();
}}

function applyFilters() {{
  currentFilter.rating = document.getElementById('filterRating').value;
  currentFilter.source = document.getElementById('filterSource').value;
  currentFilter.eventType = document.getElementById('filterEventType').value;
  currentFilter.category = document.getElementById('filterCategory').value;
  currentFilter.date = document.getElementById('filterDate').value;
  currentFilter.sort = document.getElementById('sortOrder').value;

  let filtered = ARTICLES.filter(a => {{
    if (currentFilter.search) {{
      const q = currentFilter.search.toLowerCase();
      const haystack = (a.title + ' ' + a.summary + ' ' + (a.companies||[]).join(' ') + ' ' + (a.products||[]).join(' ') + ' ' + (a.tags||[]).join(' ')).toLowerCase();
      if (!haystack.includes(q)) return false;
    }}
    if (currentFilter.rating && (a.source_rating || 'B') !== currentFilter.rating) return false;
    if (currentFilter.source && a.source !== currentFilter.source) return false;
    if (currentFilter.eventType && a.event_type !== currentFilter.eventType) return false;
    if (currentFilter.category && a.level_1_category !== currentFilter.category) return false;
    if (currentFilter.date && a.publish_time && !a.publish_time.startsWith(currentFilter.date)) return false;
    return true;
  }});

  // Sort
  if (currentFilter.sort === 'time') {{
    filtered.sort((a, b) => (b.publish_time || '').localeCompare(a.publish_time || ''));
  }}

  document.getElementById('toolbarCount').textContent = filtered.length + ' 条';
  renderNews(filtered);
}}

function quickFilter(type) {{
  if (type === 'all') {{
    document.getElementById('filterEventType').value = '';
  }} else {{
    document.getElementById('filterEventType').value = type;
  }}
  applyFilters();
}}

// Populate date options
function initDates() {{
  const dates = [...new Set(ARTICLES.map(a => a.publish_time ? a.publish_time.split(' ')[0] : '').filter(Boolean))].sort().reverse();
  const sel = document.getElementById('filterDate');
  dates.forEach(d => {{
    const opt = document.createElement('option');
    opt.value = d; opt.textContent = d;
    sel.appendChild(opt);
  }});
}}

// Init
buildTree();
initDates();
renderNews(ARTICLES);
document.getElementById('toolbarCount').textContent = ARTICLES.length + ' 条';

const FAILURES = FAILURES_DATA;
if (FAILURES.length > 0) {{
  document.getElementById('failuresBox').style.display = 'block';
  const FETCH = FAILURES.filter(function(f) {{ return f.error_category === 'fetch'; }});
  const PARSE = FAILURES.filter(function(f) {{ return f.error_category === 'parse'; }});
  document.getElementById('failureParseCount').innerText = PARSE.length;
  document.getElementById('failureFetchCount').innerText = FETCH.length;
  const detail = document.getElementById('failuresDetail');
  const items = [];
  if (FETCH.length > 0) {{
    items.push('<div style="margin-bottom:8px;font-weight:bold;color:#B91C1C;">⚠ 连接失败（' + FETCH.length + ' 个来源）— 需关注</div>');
    FETCH.forEach(function(f) {{
      items.push('<div style="margin-bottom:2px;color:#B91C1C;">• <b>' + f.source + '</b>: ' + (f.error_detail || '').replace(/^fetch \\u2014 /, '') + '</div>');
    }});
  }}
  if (PARSE.length > 0) {{
    items.push('<div style="margin-top:10px;margin-bottom:8px;font-weight:bold;color:#92400E;">ℹ 解析失败（' + PARSE.length + ' 个来源）— 内容已收录但日期/格式需修复</div>');
    PARSE.forEach(function(f) {{
      items.push('<div style="margin-bottom:2px;color:#92400E;">• <b>' + f.source + '</b>: ' + (f.error_detail || '').replace(/^fetch \\u2014 /, '') + '</div>');
    }});
  }}
  detail.innerHTML = items.join('');
}}

</script>
</body>
</html>'''

    # 低侵入注入：仅在 </body> 前追加悬浮助手块，不动现有任何标记/脚本
    html = html.replace("</body>", assistant_block_html() + "</body>", 1)

    with open(output_path, 'w') as f:
        f.write(html)
    print(f'HTML 看板已生成: {output_path} ({os.path.getsize(output_path)} bytes)')
    print(f'包含 {len(enriched_articles)} 条资讯，{total_subs} 个子赛道')


if __name__ == '__main__':
    import sys
    input_path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/dashboard_data.json'
    input_path_obj = Path(input_path)

    # If input is a directory (e.g. data/YYYY-MM-DD/), look for dashboard-data.json inside
    if input_path_obj.is_dir():
        json_candidate = input_path_obj / "dashboard-data.json"
        if json_candidate.exists():
            input_path = str(json_candidate)

    output_dir = Path(os.environ.get('HEALTHCARE_RUNTIME_ROOT', str(Path(input_path).parent)))
    default_output = output_dir / f'dashboard_{dt.datetime.now().strftime("%Y_%m_%d_%H_%M")}.html'
    output_path = sys.argv[2] if len(sys.argv) > 2 else str(default_output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(input_path, 'r') as f:
        data = json.load(f)

    if isinstance(data, dict) and 'articles' in data:
        articles = data['articles']
        failures = data.get('failures', [])
    elif isinstance(data, list):
        articles = data
        failures = []
    else:
        articles = []
        failures = []

    enriched = enrich_articles(articles)
    generate_html(enriched, output_path, failures=failures)
