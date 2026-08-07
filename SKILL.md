---
name: monitor-healthcare-intelligence
description: 监控公开的医疗健康、医药、保健、生物技术和医疗器械数据源，对新增信息进行标准化与分类，生成可追溯的每日行业情报简报，保存可读的本地历史记录，并发送或重试邮件通知。当用户要求初始化、运行、定时、检查或排查医疗健康新闻、微信公众号监控流水线或每日投资研究简报时使用。
---

# 监控医疗健康行业情报

## 路由任务

- 首次配置：执行"初始化"。
- 手动更新：执行"单次运行"。
- 每日分析：执行"生成影子日报"。
- 定时监控：执行"配置定时任务"。
- 需要了解分类、可信度、数据源或发送规则：读取 `references/` 中对应文档。

## 固定入口

| 任务 | 脚本 |
|---|---|
| 初始化 / 配置 | `healthcare_intelligence.py init/configure/setup-status/finalize-setup` |
| 采集 + 分类 | `dashboard_scraper.py --data-dir data/YYYY-MM-DD` |
| HTML 看板 | `generate_dashboard.py data/YYYY-MM-DD output.html` |
| SQLite 入库 + 信号评分 | `daily_intelligence.py --input dashboard-data.json --runtime-root <runtime>` |
| AI 助手 / 日报 | `healthcare_assistant/backend/cli.py --runtime <runtime>` |

独立发布前，Agent 必须能说明当前走的是哪条入口、会写哪些外部 runtime 文件、不会触发哪些外部动作。

---

## 初始化

首次使用时必须完成初始化问答。`setup.completed` 不为 `true` 时不得开始任何联网采集。

1. 读取：
   - `references/sources.md`
   - `references/trust-model.md`
   - `references/delivery-and-scheduling.md`

2. 创建草稿工作区：

   ```bash
   python3 scripts/healthcare_intelligence.py init --workspace <runtime-directory>
   ```

   init 成功建立工作区后，Agent 必须立即设置 `HEALTHCARE_RUNTIME_ROOT` 环境变量。

3. 每次只询问一个问题，严格按顺序：
   1. 数据源范围和 `critical` 关键来源
   2. 采集时间窗口
   3. 手动或定时运行
   4. 是否推送
   5. Agent 模型使用方式
   6. 输出目录和数据保留周期

4. 每收到一个答案，立即写入 `config.yaml`：

   ```bash
   python3 scripts/healthcare_intelligence.py configure \
     --config <runtime>/config.yaml --set collection_window_hours=48
   ```

5. 运行 `setup-status` 展示配置摘要，取得用户确认后 `finalize-setup`。

6. 只有 `valid: true` 后才能执行首次采集。

7. 安装定时任务前必须另行确认。

---

## 单次运行

1. `setup-status` 确认 `valid: true`
2. 采集 + 三层分类：

   ```bash
   python3 scripts/dashboard_scraper.py \
     --data-dir <runtime>/data/$(date +%Y-%m-%d) \
     --start "<48h前>" --end "<现在>"
   ```

   产出：`collected.txt` + `dashboard-data.json` + `errors.txt`

3. 生成 HTML 看板：

   ```bash
   python3 scripts/generate_dashboard.py \
     <runtime>/data/YYYY-MM-DD \
     <runtime>/dashboard_YYYY_MM_DD.html
   ```

4. SQLite 入库 + 信号评分 + 影子日报：

   ```bash
   python3 scripts/daily_intelligence.py \
     --input <runtime>/data/YYYY-MM-DD/dashboard-data.json \
     --runtime-root <runtime>
   ```

5. 启动 AI 助手生成精简日报（写入 `data/YYYY-MM-DD/digest.txt`）：

   ```bash
   export HEALTHCARE_RUNTIME_ROOT=<runtime>
   python3 -m healthcare_assistant.backend.cli
   ```

---

## 采集规则

- 主要数据源：动脉网 vbdata.cn + ByDrug 179 个来源 + 政府官网
- 分类引擎：`classification_engine.py`，三层：规则 → SentenceTransformer 语义 → LLM 兜底
- 分类体系：4+1 大类 → 28 个子赛道（`references/dashboard-categories.json`）
-  1. 创新药 / 2. 医疗器械 / 3. 医疗服务 / 4. 消费医疗与医美 / 其他综合
- 0.8–1.5 秒随机间隔，单线程逐页请求
- 单个来源失败继续处理其他来源，写入 `errors.txt`
- NMPA 药品/器械/化妆品页面返回 HTTP 412，不要重试
- FDA 走 openFDA API，不抓网页

---

## 分类与聚合

- 每条信息分配一个赛道一级分类，可选辅助标签
- 风险事件覆盖优先
- 合并事件时保留所有贡献来源链接
- V1 不自动交叉验证；不得标记为 `corroborated`
- 明确说明不确定性
- 每份简报包含"仅供信息研究，不构成投资建议"

---

## 生成影子日报

```bash
python3 scripts/daily_intelligence.py \
  --input <dashboard-data.json> --runtime-root <runtime>
```

- 信号评分上限 100：重要性 30 + 关注名单 25 + 新颖性 20 + 证据 15 + 趋势 10
- 趋势分数至少积累 7 个历史日报日后启用
- 默认 `shadow` 模式，不发送邮件

---

## 存储约定

```
data/YYYY-MM-DD/
  collected.txt          # 结构化 Markdown（4+1 大类）
  dashboard-data.json    # 看板 JSON
  errors.txt             # 错误日志
  digest.txt             # AI 助手生成的统一日报
intelligence/
  healthcare_intelligence.sqlite3
reports/
  healthcare_daily_YYYY-MM-DD.md
state/
  seen-items.json
  source-failures.json
```

---

## 资源

| 脚本 | 作用 |
|---|---|
| `healthcare_intelligence.py` | 配置管理：init / configure / setup-status / finalize-setup |
| `dashboard_scraper.py` | 采集 + 三层分类 → `data/YYYY-MM-DD/` |
| `generate_dashboard.py` | JSON → HTML 交互看板 |
| `classification_engine.py` | 三层分类引擎（规则→语义→LLM） |
| `daily_intelligence.py` | SQLite 入库 + 信号评分 + 影子日报 |
| `evaluate_classification.py` | 评估分类质量 |

| 参考文档 | 内容 |
|---|---|
| `references/sources.md` | 179 个来源注册表 |
| `references/dashboard-categories.json` | 4+1 大类 → 28 子赛道（当前分类体系） |
| `references/trust-model.md` | 来源可信度和证据状态 |
| `references/delivery-and-scheduling.md` | 发送适配器和定时任务 |
