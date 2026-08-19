# AI Resource Cycle Tracker

面向 **ASX 中小盘资源勘探股 / 开发股** 的投研雷达。系统通过行情、成交量、公告、商品代理价格和历史信号表现，发现正在形成市场共识的资源股故事，并给出可解释的 `Cycle Score`。

> 仅供研究参考，不构成投资建议。系统输出固定为 `High Priority` / `Watch Closely` / `Monitor` / `Ignore`，不是买卖建议。`Cycle Score` 衡量的是“资源故事的市场共识强度”，不是上涨概率。

## 架构

```text
yfinance 日线 / 商品代理 / 基准
        +
ASX 公告 API
        |
        v
SQLite 数据层
        |
        v
规则层：指标 / 公告分类 / 资源上下文
        |
        v
评分层：Cycle Score
        |
        +--> 信号引擎 --> 信号留痕 --> 前向收益回填 --> 回测
        |
        +--> 日报 --> Telegram / Email / Web Dashboard
```

- 后端：FastAPI + SQLAlchemy + SQLite（`data/tracker.db`）
- 调度：APScheduler，可配置每个交易日 ASX 收盘后自动跑 pipeline
- 前端：React + Vite + TypeScript + Ant Design + ECharts
- 数据源：yfinance 行情、ASX 公告、商品/ETF 代理、OZR.AX 基准
- AI 分析层：
  - `noop`：默认，不抓全文，不产生额外网络/付费调用
  - `rules_fulltext`：抓公告文档/PDF，用规则抽取品位、宽度、深度、项目、商品等
  - `claude`：显式允许付费调用后，用 Anthropic 做公告全文结构化摘要

## 快速开始

### Windows PowerShell

```powershell
# 1. 后端环境
cd backend
py -3.10 -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env

# 2. 初始化股票池
cd ..
backend\.venv-win\Scripts\python.exe scripts\seed_watchlist.py
backend\.venv-win\Scripts\python.exe scripts\validate_seed.py

# 3. 首次跑全量 pipeline + 历史回放
backend\.venv-win\Scripts\python.exe scripts\run_pipeline.py
backend\.venv-win\Scripts\python.exe scripts\replay_signals.py --days 400

# 4. 启动后端
cd backend
.\.venv-win\Scripts\python.exe -m uvicorn app.main:app --port 8000

# 5. 启动前端（另开 PowerShell）
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。

### macOS / Linux

```bash
cd backend
python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env

cd ..
backend/.venv/bin/python scripts/seed_watchlist.py
backend/.venv/bin/python scripts/validate_seed.py
backend/.venv/bin/python scripts/run_pipeline.py
backend/.venv/bin/python scripts/replay_signals.py --days 400

cd backend
.venv/bin/uvicorn app.main:app --port 8000

cd ../frontend
npm install
npm run dev
```

## 环境变量

后端配置位于 `backend/.env`。

| 变量 | 说明 |
|---|---|
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 配置后推送日报；不配置仍会生成日报并入库 |
| `EMAIL_SMTP_HOST` / `EMAIL_FROM` / `EMAIL_TO` | 配置后通过 SMTP 邮件推送日报 |
| `EMAIL_SMTP_PORT` / `EMAIL_SMTP_USERNAME` / `EMAIL_SMTP_PASSWORD` / `EMAIL_USE_TLS` | SMTP 端口、登录凭据和 TLS |
| `ENABLE_SCHEDULER` | `true` 开启每日自动 pipeline；开发时建议关闭，避免 reload 双跑 |
| `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` | 默认 18:30 Australia/Sydney |
| `ASX_ACCESS_TOKEN` | ASX 前端接口 token，失效时需要更新 |
| `AI_ANALYZER` | `noop` / `rules_fulltext` / `claude` |
| `AI_ANALYZER_ALLOW_PAID_CALLS` / `ANTHROPIC_API_KEY` | 只有选择 `claude` 且显式允许付费调用时才会调用 Anthropic |
| `ADMIN_API_TOKEN` | 前端设置页执行 pipeline、replay、配置编辑等管理操作所需 token |

权重、标签阈值、信号阈值、商品映射、回测基准存储在数据库 `app_config` 表，可在前端设置页修改，无需重启。

## Cycle Score

默认权重如下，可在设置页调整：

| 子分 | 权重 | 当前实现 |
|---|---:|---|
| Funding | 35% | 放量、成交额流动性门槛、20/60/252 日突破、连涨、量能趋势 |
| Announcement | 30% | 公告分类分数、时间衰减、price-sensitive 加成、多公告 bonus、钻探上下文小幅加成 |
| Resource | 20% | 优先使用公告抽取出的钻探上下文自动评分；没有上下文时默认 50；可手工覆盖 |
| Commodity | 10% | 对应商品或 ETF 代理的 20/60 日动量 |
| Risk | 5% | 默认 50；可手工覆盖，越高代表越安全 |

评分标签：

- `High Priority`：默认 `Cycle Score >= 75`
- `Watch Closely`：默认 `>= 60`
- `Monitor`：默认 `>= 45`
- `Ignore`：低于监控线

每次评分都会保存 `components` JSON，用于前端展示评分拆解。

## 信号类型

| 类型 | 触发条件 |
|---|---|
| `REL_VOL_SPIKE` | 相对成交量达到阈值，且上涨日，且成交额达到最低流动性门槛 |
| `BREAKOUT_60D` | 收盘价创 60 日新高，且相对成交量和成交额达标 |
| `BREAKOUT_252D` | 收盘价创 252 日新高，且相对成交量和成交额达标；同日优先于 60 日突破 |
| `KEY_ANNOUNCEMENT` | 新公告分数达到阈值，或 price-sensitive 公告达到较低阈值；融资和停牌被排除 |
| `SCORE_CROSS_UP` | Cycle Score 上穿 High Priority 线 |

信号会永久入库，并自动创建 +5、+20、+60、+120 交易日的前向收益记录。

## 回测口径

- 信号在收盘后产生，因此入场价使用“信号后第一个交易日收盘价”，避免前视偏差。
- 超额收益 = 信号收益 - 同期 `OZR.AX`（ASX 资源 ETF）收益。
- 交易日按个股自身 K 线日历计算，停牌和假日自然跳过。
- 股票长期无 K 线时，对应信号标记为 `unavailable`，不进入收益统计，但展示数量，用于暴露幸存者偏差。
- `replay` 信号由历史行情重放价格类规则产生，不含公告信号、标签和 Cycle Score。
- 样本量小于 10 时标记为低样本。

## 定性矿业上下文

钻探公告可以在 `Announcement.ai_metrics` 中包含 `qualitative_context` 和 `qualitative_contexts`：

- `qualitative_context`：主截距上下文，保留向后兼容
- `qualitative_contexts`：每个有效截距一条上下文

上下文字段包括：

| 字段 | 含义 |
|---|---|
| `width_m` / `grade` / `unit` | 抽取到的截距宽度、品位和单位 |
| `normalized_unit` | 标准化单位，例如 `%` 或 `g/t` |
| `commodity` / `project` / `region` | 用于比较的商品、项目和区域 |
| `extraction_quality` | `complete` 或 `partial`，表示字段完整性 |
| `missing_fields` | 缺失字段，如 `project`、`region`、`depth_m` |
| `comparison_warnings` | 比较降级、历史不足、单位标准化等警告 |
| `grade_thickness` | `width_m * grade` |
| `depth_category` | `shallow` / `medium` / `deep` / `unknown` |
| `interval_quality_label` | `exceptional` / `strong` / `moderate` / `weak` / `insufficient_history` |
| `company_percentile` | 同公司、同商品、同单位历史分位 |
| `project_percentile` | 同项目历史分位 |
| `regional_percentile` | 同区域历史分位 |
| `trend_vs_previous` | `improving` / `flat` / `deteriorating` / `insufficient_history` |
| `materiality_label` | `high` / `medium` / `low` / `insufficient_history` |
| `qualitative_assessment` | 面向 UI 的中性描述，不含买卖或股价语言 |

比较规则：

- 优先使用同项目历史。
- 项目历史不足时，回退到同公司历史，并在 UI 中明确提示。
- 公司和项目历史都不足、但区域历史足够时，可回退到区域历史。
- 不会凭空编造地区或同业基准。
- 历史不足时分位为空，标签为 `insufficient_history`。

## 前端页面

- 雷达排名：按 Cycle Score 排序，展示子分、标签和当日信号数量。
- 个股详情：价格/成交量图、信号点、评分拆解、分数历史、公告、定性上下文、信号历史。
- 信号记录：按信号类型、标签、来源、代码筛选。
- 回测：按信号类型、标签、分数段、截距质量、materiality 查看历史表现。
- 日报：Top Cycle Scores、当日信号、关键公告、异动股、推送状态。
- 设置：股票池、运行 pipeline/replay、Telegram 测试、参数、权重校准、配置历史。

## 项目结构

```text
backend/app/
├─ datasources/    # ASX 公告、yfinance 日线、商品/基准
├─ analysis/       # indicators / classifier / scoring / signals / ai_stub
├─ services/       # pipeline、回测、回放、日报、市场数据、配置
├─ notify/         # Telegram 和 SMTP Email
└─ api/routes/     # stocks / signals / announcements / backtest / reports / config / admin

frontend/src/
├─ pages/          # Ranking / StockDetail / Signals / Backtest / Reports / Settings
├─ components/     # 图表、评分拆解、信号表、上下文面板
└─ api/            # API client 和类型

scripts/
├─ seed_watchlist.py
├─ validate_seed.py
├─ run_pipeline.py
└─ replay_signals.py
```

## 测试

```powershell
cd backend
.\.venv-win\Scripts\python.exe -m pytest tests -q

cd ..\frontend
npm test -- --run
npm run build
```

测试覆盖公告分类、指标、评分边界、信号触发、回测入场价、超额收益、配置历史、公告 API、AI/规则抽取和定性上下文。

## 已知限制

1. 系统度量的是正面资源故事强度，不是完整风险判断。负面消息可能表现为“无公告 + 下跌”，存在滞后。
2. ASX 公告接口通常只提供最近公告，历史公告类信号无法完整回放。
3. yfinance 对微盘股可能缺数据，股票池需要定期校验。
4. 锂、铀、稀土使用 ETF 代理，不是完全精确的商品价格。
5. `Resource` 和 `Risk` 在没有上下文或人工覆盖时默认 50，仍需要人工研究补充。
6. 规则全文分析只做窄范围抽取，不能替代地质、矿权、财务和估值尽调。
7. `claude` 分析器只有在显式允许付费调用且配置 API key 时才会运行。
