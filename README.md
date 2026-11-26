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
| Announcement | 40% | 公告分类分数、时间衰减、price-sensitive 加成、多公告 bonus、钻探上下文小幅加成 |
| Resource | 20% | 优先使用公告抽取出的钻探上下文自动评分；没有上下文时默认 50；可手工覆盖 |
| Commodity | 20% | 对应商品或 ETF 代理的 20/60 日动量 |
| Risk | 10% | 第一版自动规则：成交额流动性、近期融资/配股、停牌/暂停、重要股东退出；可手工覆盖，越高代表越安全 |
| Sentiment | 10% | 第一版为中性默认 50 / `insufficient_data`；后续接入论坛和社媒讨论热度、情绪、hype risk |

Funding Score 仍会计算并展示，但它现在定位为独立的资金确认层，不再参与 `Cycle Score` 主权重。它继续用于放量、突破等信号触发和回测分组。

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
| `BREAKOUT_252D` | 收盘价创 252 日新高，且相对成交量和成交额达标；同日优先于 60 日突破。**已降级为 `watch_only`**，详见「信号分级」 |
| `KEY_ANNOUNCEMENT` | 新公告分数达到阈值，或 price-sensitive 公告达到较低阈值；融资和停牌被排除 |
| `SCORE_CROSS_UP` | Cycle Score 上穿 High Priority 线 |

信号会永久入库，并自动创建 +5、+20、+60、+120 交易日的前向收益记录。同一股票同一天同一因果机制的信号共享 `event_key`，并由 `role` 区分 primary / secondary，详见「信号与评分的去重」。

## 回测口径

- 信号在收盘后产生，因此入场价使用“信号后第一个交易日收盘价”，避免前视偏差。
- 超额收益 = 信号收益 - 同期 `OZR.AX`（ASX 资源 ETF）收益。
- 交易日按个股自身 K 线日历计算，停牌和假日自然跳过。
- 股票长期无 K 线时，对应信号标记为 `unavailable`，不进入收益统计，但展示数量，用于暴露幸存者偏差。
- `replay` 信号由历史行情重放价格类规则产生，不含公告信号、标签和 Cycle Score。
- 同一股票同一天的多个信号入场价相同、收益相同，统计时按股票-日去重；`total_signals` 为信号条数，`total_signal_days` 为背后的独立交易日数，详见「信号与评分的去重」。
- 样本量小于 10 时标记为低样本。

## 信号分级

信号规则不是生而平等的。前向收益回测显示，部分规则在统计上没有预测价值，甚至是负贡献。这类规则**不删除、照常产出并入库**（删掉就等于丢失证据，也无法继续观察它在新市场环境下的表现），但会被降级，不再参与下游的「确认」判断。

| 等级 | 含义 | 下游行为 |
|---|---|---|
| `confirming` | 默认等级，可作为正面证据 | 计入共振判定、市场确认、每日故事 |
| `watch_only` | 回测证伪，仅作关注提示 | P5 方向标 `neutral`、不计入 engine 共振、不计入市场确认、前端标「仅关注」 |

### 当前被降级的规则

| 规则 | 回测依据 | 处理 |
|---|---|---|
| `BREAKOUT_252D` | n=119（+120 天）：胜率 30.3%，相对 `OZR.AX` 平均超额 **−29.78%**。按周期看 +5d 为 +1.04%，+20d 起转负并持续恶化 | 降为 `watch_only`；technical magnitude 从 85 降至 30 |

读法：创 252 日新高并放量，在样本期内更像一波行情的尾声而非起点。短线（5 日内）仍微正，说明它确实反映了市场关注度，问题出在把它当作买入并持有的依据。因此保留为「值得看一眼」的提示。

### 实现

分级定义在 `analysis/signals.py` 的 `SIGNAL_GRADE`，回测依据记录在 `SIGNAL_EVIDENCE_NOTE`，统一通过 `is_confirming(signal_type)` 查询。新增降级规则只需改这一处，下游自动生效：

- `p5_p6_adapter.py` — 非 confirming 规则的 P5 分析信号方向写为 `neutral`；`_engines()` 只统计非 neutral 的 engine，因此被降级的规则无法让 `signal_structure` 变成 `confirmation`
- `report.py` — `_has_market_confirmation()` 与 `_market_confirmation_reasons()` 跳过被降级的规则
- `SignalTable.tsx` — 信号列附加「仅关注」标签，悬停显示回测依据

### 注意

分级依据是**单一 400 天窗口、29 支股票、一轮上涨周期**，且股票池为事后选取（幸存者可见）。这说明的是「在目前能观察到的历史里该规则为负贡献」，不等于它在其他市场环境中同样无效。样本扩充或跨周期验证后应重新评估分级。

## 信号与评分的去重

多个维度同时变好，不等于多份独立证据。同一个事件往往会在好几个地方留下痕迹，如果每处都单独计分，系统会把一次事件读成一场共振，从而高估把握。下面记录已识别的重复计分点、各自的处理方式，以及目前仍未处理的部分。

### 已识别的重复计分点

| # | 位置 | 怎么重复的 | 状态 |
|---|---|---|---|
| 1 | 信号生成（`analysis/signals.py`） | 突破本身就要求放量（`breakout_rel_vol` 默认 1.5），所以创新高当天若放量达标，`BREAKOUT_*` 和 `REL_VOL_SPIKE` 会同时触发。两者机械耦合，不是两次独立观察 | 已处理 |
| 2 | 回测统计（`services/backtest.py`） | 同一股票同一天的多个信号，入场价相同、前向收益完全相同。按信号条数统计会虚增样本量；按标签或分数段分组时，它们还会落进同一组被当成多个独立样本 | 已处理 |
| 3 | P5/P6 证据独立性（`services/p5_p6_adapter.py`） | `dependency_group` 原先以单份公告 ID 为键。公司常为同一件事一次发好几份文件（年报 + Appendix 4G + MD&A；收购公告 + 投资者演示），会被判成多个独立来源 | 已处理 |
| 4 | Cycle Score 子分（`services/scoring_service.py`） | `announcement_score`（权重 0.40）与 `resource_score`（权重 0.20）读取同一批 `Announcement` 行。一份钻探公告可同时抬高两者，相当于让单一事件推动 Cycle Score 的 60% | **未处理** |

### 处理方式

**信号层：事件归组 + 主次标记。** `signals` 表的 `event_key` 把同一股票、同一天、同一因果机制的信号归为一个事件，`role` 标记哪一条代表它：

```
event_key = "{stock_id}|{date}|{mechanism}"     mechanism: price_action / announcement
role      = primary | secondary
```

同一 mechanism 内按 `BREAKOUT_252D` > `BREAKOUT_60D` > `REL_VOL_SPIKE` 取 primary。两条信号都保留入库，不删除任何一条——消费方可以自行决定只数 primary 还是全数。价格行为与公告属于不同因果机制，各自独立成事件。

**回测层：按股票-日去重。** 聚合时以「分组 + 周期 + 股票 + 日期」为键去重。由于同日信号的前向收益本就完全相同，这是在删除重复行，不是在做取舍。接口同时返回两个口径：

- `total_signals`：信号条数
- `total_signal_days`：背后的独立股票-日数量

两者差距即重叠程度。以当前数据集为例，608 条信号实际只来自 495 个独立交易日。

**P5/P6 层：按事件族归组。** `dependency_group` 改为 `announcement_event:{日期}:{事件族}`，公告类型映射到 administrative / commercial / development / exploration / financial / funding / other / ownership / resource（见 `ANN_TYPE_TO_EVENT_FAMILY`）。`source_event_id` 仍保留文档 ID，证据链可追溯。`_evidence_independence()` 统计的是不同 `dependency_group` 的数量，而非信号条数，因此同一事件衍生的多条信号只算一份证据。

### 尚未处理

**Cycle Score 子分之间的同源计分（上表 #4）。** `_resource_score_from_contexts()` 与公告子分读取同一批公告行，二者没有共享去重键。当前 `AI_ANALYZER=noop`，`resource_score` 恒为默认 50，该问题不会显现；一旦启用 `rules_fulltext` 或 `claude` 分析器，同源放大会立即生效。修复前请留意：此时的 Cycle Score 高分可能来自一个事件，而非多维共振。

**事件族划分偏粗。** 同一天的两份互不相关的钻探公告会被归入同一事件族，因而被当作一份证据。这是刻意选择的保守方向——宁可低估共振，也不要制造虚假共振。待 P03 把事件类型抽取稳定后，可以改为按真实事件聚合。

## P04 衍生指标

P03 记录公司说了什么，P04 把这些陈述变成可比较的数字。P04 不重读文档：每个指标都标注它由哪些 P03 事实算出、用的什么公式、来自原文第几页，因此屏幕上的任何一个数都能走回它所出自的那句话。指标为追加写入并带 `formula_version`，改定义不会重写历史——换个版本重算，然后比较两者。

接口：`GET /api/stocks/{code}/features`（可选 `?feature_group=funding`）。流水线在 P03 事实落库之后、评分之前自动计算。

### 已实现的三组

| 组 | 指标 | 公式 | 数据来源 | 当前 `formula_version` |
|---|---|---|---|---|
| `funding` | `cash_runway_quarters`<br>`quarterly_burn` | 8.6 项 ÷ \|8.3 项\| | Appendix 5B 第 8 节 | `funding_runway_v1` |
| `dilution` | `placement_discount_pct` | 配售价 ÷ 公告前收盘 − 1 | 融资公告 + 日线 | `placement_discount_v1` |
| `resource` | `contained_metal_reconciliation_pct_*` | 吨位 × 品位 vs 公告披露金属量 | JORC 资源 / 储量表 | `contained_metal_check_v1` |

**现金跑道**：ASX 强制勘探公司在 Appendix 5B 第 8.7 项自行披露可用季度数。P04 不采信该数字，而是用第 8.6 与 8.3 项重算，并把差额记入 `variance_vs_entity_reported`——解析出错或公司算错都会显现，而不是被悄悄吞掉。跑道低于 2 个季度时打 `below_asx_disclosure_threshold`，那既是 ASX 要求回答第 8.8 项的门槛，也是稀释性融资几乎必然发生的水平。

**配售折价**：参考价取公告**前一交易日**收盘，因为配售是按谈判时的市价定的，公告当天股价已包含该消息。门控按文档类别（`ISSUED CAPITAL` 等融资类）判断，不看事件类型——年报会复述历史期权与发行价，P03 同样归类为 `Placement` 事件，拿它们对比今天的股价会得出无意义的折价。折价 ≤ −20% 标 `deep_discount`。

**资源量交叉校验**：见下节。偏差超过 10% 即判定不一致，超过 100% 额外标 `likely_column_misread`。仅处理 JORC 表明确无歧义的单位配对（g/t → koz / Moz，% → t / kt）；ppm、lb、oz/t 等不作换算而非猜测，因为错误换算会表现为源数据有误，与本校验要传达的信号相冲突。

## 资源量表格的列对齐解析

JORC 表格为矿体中的每种元素单独设列，一行读作 `36.8 Mt ｜ 1.00 % Li2O ｜ 62.4 ppm Ta2O5`。早期实现按位置取「分类后的前三个数字」，并把单位与元素硬编码为黄金：

```python
table = re.search(r"Probable\s+(\d+)\s+(\d+)\s+(\d+)", text)   # 旧实现
```

这对单一金矿碰巧成立，对其他矿种则给出可信外观的错误数字。实测中它把一家锂矿的钽 ppm 读成了黄金盎司，把一家铜钼矿读成了金矿，而数字本身毫无破绽。

`services/p3_resource_table.py` 改为从表头读取列定义，支持三种真实排版：

| 排版 | 样例 | 对应方式 |
|---|---|---|
| 标签行 + 单位行 | `Tonnes CuEq Cu Au`<br>`(Mt) (%) (%) (g/t)` | 按列序号配对，非相邻关系 |
| 每单位独占一行 | `Li2O`<br>`(%)`<br>`Ta2O5`<br>`(ppm)` | 取紧邻的上一标签 |
| 单位内嵌元素 | `Grade (g/t Au)` | 从单位文本内解析元素 |

规则：

- **主商品**取既有品位列又有含量列的元素；等价品位（CuEq、AuEq）被识别并排除，因其由其他金属折算而来。
- **单一品位的表格**可继承未标注元素的含量列（如 `Ounces (Koz)`），因为表中只有一种商品。
- **列数与数值数不符则整行丢弃**。缺一条事实可以补回，错一条则不能。
- 每条事实记录 `table_row_ref`（页码 + 行偏移）。一份文档常含多张表、各表的行又共用同一分类名；没有行标识就无法确定哪个吨位对应哪个品位，而错误配对恰好会制造出本校验要捕捉的那类错误。
- 可识别 13 种商品（gold、copper、lithium、uranium、rare_earth、tantalum、nickel、zinc、lead、cobalt、silver、molybdenum、iron）。

### P04 只读取当前解析结果

P03 为追加写入：以新解析器重解析文档时，旧事实保留在库中、其解析运行被标记 `superseded`。P04 因此只读取未被取代的运行——否则修正后的抽取会悄悄输给它所替代的那个数字。

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
- 个股详情：价格/成交量图、信号点、**资金跑道卡片（P04：现金跑道、配售折价、资源量校验）**、评分拆解、分数历史、公告、定性上下文、信号历史。
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
│                  # p3_resource_table（JORC 表格列对齐）
│                  # p4_feature_service（现金跑道 / 配售折价 / 资源量校验）
├─ notify/         # Telegram 和 SMTP Email
└─ api/routes/     # stocks / signals / announcements / backtest / reports / config / admin

frontend/src/
├─ pages/          # Ranking / StockDetail / Signals / Backtest / Reports / Settings
├─ components/     # 图表、评分拆解、信号表、上下文面板、资金跑道面板
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
5. `Resource` 在没有上下文或人工覆盖时默认 50；`Risk` 已有第一版可观察风险规则，但仍需要人工研究补充。
6. Risk Score 第一版不会推断现金 runway、融资折价、债务或完整稀释条款；这些需要后续从 Appendix 5B、融资公告和股本结构中结构化抽取。
7. 规则全文分析只做窄范围抽取，不能替代地质、矿权、财务和估值尽调。
8. `claude` 分析器只有在显式允许付费调用且配置 API key 时才会运行。
9. Cycle Score 的 `announcement` 与 `resource` 两个子分读取同一批公告，存在同源重复计分（合计权重 0.60）。当前 `AI_ANALYZER=noop` 时 `resource` 恒为 50 不会显现，启用正文分析器后会生效，详见「信号与评分的去重 / 尚未处理」。
10. P04 指标依赖对应的公告类型：没有 Appendix 5B 就没有现金跑道，没有融资公告就没有折价。ASX 接口每支股票仅返回最近 5 份文件，因此多数股票当前无 P04 数据；历史文档需经管理员接口或批量导入工具补全。
11. 资源量交叉校验只覆盖 JORC 表中单位配对明确的行；ppm、lb、oz/t 等不作换算，相应行不产生校验结果，不代表数据已通过检查。

## Beta02 P01–P03 证据流水线

P01、P02、P03 采用严格分层：P01 管理经人工批准的 Stock、Project、Asset Unit、Commodity、Identity 和历史关系；P02 保存 Announcement 元数据、原始 PDF、Raw Text、SHA-256、页数和采集状态；P03 只把公司明确披露的内容整理成可追溯的 Event、Fact 和 Statement，不计算 P04 指标，也不产生投资判断。

新公告默认流程为：

```text
ASX metadata → Announcement → original.pdf / SHA-256 → raw_text.txt
→ EvidenceDocument → P3ParseRun → Summary-first Event / Fact
→ approved-entity mapping → proposed version relations → UI evidence
```

文件证据位于 `data/evidence/asx/{TICKER}/{ANNOUNCEMENT_ID}/`。数据库只保存受控路径和证据状态；普通 API 通过 EvidenceDocument 下载端点提供 PDF/Raw Text，不接受任意本地路径参数。P3 每条事实保留 EvidenceDocument、页码、摘录、解析器版本、原始值、标准化值、单位、币种、期间和状态。

Event 是一项中性业务事件（F01–F08）；Fact 是公告明确报告的原子字段；Statement 是带来源的文本陈述。P3 新发现的实体名称先形成 EntityMention/Mapping 或 P01 Update Proposal，只有 P01 审核批准后才进入正式 Project Tree。`current` 为当前有效事实，`historical` 为历史披露，`superseded` 为经确认已被替代，`withdrawn` 为经确认已撤回；普通页面默认排除 superseded/withdrawn/rejected。

### 管理员历史回填

入口：`/admin/backfill`。历史公告不会自动全量处理。管理员必须用 Stock、Announcement 或日期范围限定范围，先点击 Preview，核对缺失 PDF/Raw Text、解析状态、Stock/Family 分组、跳过原因和动作，再执行。Preview 严格只读，不下载、不调用模型、不写 P3 Fact。执行后可查看 BackfillRun/BackfillRunItem、失败阶段和原因，并仅重试失败项。

管理员 API：

```text
POST /api/admin/backfill/preview
POST /api/admin/backfill/run
GET  /api/admin/backfill/runs
GET  /api/admin/backfill/runs/{run_id}
GET  /api/admin/backfill/runs/{run_id}/items
POST /api/admin/backfill/runs/{run_id}/retry-failed
POST /api/admin/backfill/runs/{run_id}/cancel
```

### 公告缺口与历史 PDF 批量导入

当前 ASX 元数据源是最近公告流。每次同步若恰好收到 5 条公告，系统会将最早一条的日期与数据库中该股票已有的最新公告日期比较；两者之间存在空档时，会在每日运行结果的 `announcement_gaps` 中记录股票代码、起止日期和缺口天数。它是数据完整性提示，不会阻断价格、评分或证据处理。

ASX 历史公告应从合规的数据来源下载为原始 PDF，再放入 `data/inbox/`。文件名必须是 `CODE_YYYY-MM-DD_TYPE.pdf`，例如 `HAS_2026-06-30_5B.pdf`。先只检查：

```bash
backend/.venv/bin/python scripts/import_announcements.py --inbox data/inbox --dry-run
```

确认结果后执行导入：

```bash
backend/.venv/bin/python scripts/import_announcements.py --inbox data/inbox
```

工具会按 PDF 的 SHA-256 去重，保留原始文件和文本抽取结果，执行 P3 事实解析，并在全部文件处理完成后重算受影响股票的 P4 指标。文件名不合规、股票不在观察池或 PDF 损坏时，会单独报告并继续处理其余文件。

普通股票详情页继续显示经批准的项目树、公告外链、本地 PDF、Evidence 状态、客观摘要、多个 Event、Facts、实体映射、页码/摘录和版本状态。Drill Context 仅在 F01 钻孔信息存在时显示；非钻探公告显示不适用或留空。

P04 只能读取已保存且可追溯的 P3Fact，例如 Cash Balance、季度现金流、Issue Price、Resource/Reserve 数值和 DFS Timing。P04 计算结果必须另表保存，绝不能反向覆盖 P3 的 `value_raw`、单位、币种、期间、状态、页码、摘录、Evidence 或解析版本。

完整实施和验收结果见 [P01–P03 实施说明](docs/beta02-p1-p3-implementation.md) 与 [最终实施报告](docs/beta02-p1-p3-final-implementation-report.md)。
