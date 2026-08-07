# Healthcare Intelligence Skill

医疗健康行业情报监控 skill：采集 → 三层分类 → HTML 看板 → SQLite 情报库 → AI 日报。

代码与运行数据分离：
- 本目录 = skill 源码，进 Git
- 外部 runtime 目录 = 配置 / 模型 / SQLite / 采集输出，不进 Git

## 功能

- 采集：动脉网 + ByDrug 179 个来源 + FDA/EMA/PMDA/MHRA/TGA 政府官网
- 分类：三层引擎（规则 → SentenceTransformer 语义 → LLM 兜底），4+1 大类 28 子赛道
- 看板：交互式 HTML，含搜索/筛选/分类树
- SQLite：文章/实体/事件/信号 结构化存储
- 日报：信号评分 Top 10 + AI 助手生成精简简报

## 快速开始

```bash
# 1. 初始化
python3 scripts/healthcare_intelligence.py init --workspace <runtime-dir>

# 2. 按提示逐项配置（来源/时间窗口/运行方式/推送/模型/保留周期）
python3 scripts/healthcare_intelligence.py configure \
  --config <runtime-dir>/config.yaml --set collection_window_hours=48

# 3. 确认配置
python3 scripts/healthcare_intelligence.py setup-status \
  --config <runtime-dir>/config.yaml

python3 scripts/healthcare_intelligence.py finalize-setup \
  --config <runtime-dir>/config.yaml --confirmed-by-user

# 4. （可选）下载分类模型（~118 MB，1–5 分钟）
python3 scripts/healthcare_intelligence.py download-model --runtime <runtime-dir>

# 5. 采集 + 分类
python3 scripts/dashboard_scraper.py \
  --data-dir <runtime-dir>/data/$(date +%Y-%m-%d) \
  --start "2026-08-05 09:00" --end "2026-08-07 09:00"

# 6. 生成看板
python3 scripts/generate_dashboard.py \
  <runtime-dir>/data/YYYY-MM-DD \
  <runtime-dir>/dashboard.html

# 7. SQLite 入库 + 信号评分
python3 scripts/daily_intelligence.py \
  --input <runtime-dir>/data/YYYY-MM-DD/dashboard-data.json \
  --runtime-root <runtime-dir>
```

## 产出文件

```
<runtime-dir>/data/YYYY-MM-DD/
├── collected.txt          # 结构化 Markdown
├── dashboard-data.json    # 看板 JSON
├── errors.txt             # 错误日志
└── digest.txt             # AI 日报（助手生成后写入）

<runtime-dir>/intelligence/
└── healthcare_intelligence.sqlite3

<runtime-dir>/reports/
└── healthcare_daily_YYYY-MM-DD.md
```

## 脚本

| 脚本 | 作用 |
|---|---|
| `healthcare_intelligence.py` | 配置管理：init / configure / setup-status / finalize-setup / download-model |
| `dashboard_scraper.py` | 采集 + 三层分类 → `data/YYYY-MM-DD/` |
| `generate_dashboard.py` | JSON → HTML 交互看板 |
| `classification_engine.py` | 规则→语义→LLM 三层分类引擎 |
| `daily_intelligence.py` | SQLite 入库 + 信号评分(0-100) + 影子日报 |

## 依赖

```bash
pip install sentence-transformers  # 语义分类层（可选，不装则只用规则+LLM）
```

模型首次使用需下载（`download-model` 命令），约 118 MB，存于 `<runtime>/models/`。跳过则分类降级为关键词规则 + LLM 兜底。

## 测试

```bash
python3 scripts/test_classification_engine.py -v
python3 scripts/test_dashboard_scraper.py -v
python3 scripts/test_daily_intelligence.py -v
```

Agent 执行入口见 [SKILL.md](SKILL.md)。
