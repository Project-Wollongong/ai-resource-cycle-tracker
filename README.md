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
| `AI_ANALYZER` | `noop` / `rules_fulltext` / `claude`。默认 `rules_fulltext`：纯正则抽取钻孔数据并与本公司历史比出分位，不发生任何 API 调用 |
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
| 5 | Resource 子分的同源上下文（`services/scoring_service.py`） | 一份公告按每条钻孔各产出一个 qualitative context，一份季报常有十条。排序取前 8 时，单份文件就能占满全部名额并独自决定该子分 | 已处理 |
| 4 | Cycle Score 子分（`analysis/scoring.py`） | `announcement_score`（权重 0.40）与 `resource_score`（权重 0.20）都读 `ai_metrics` 里的 `interval_quality_label` 与 `materiality_label`。一份钻探公告的同一组标签会同时抬高两个子分 | 已处理 |

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

**Resource 子分：一份公告一票。** 排序前先按 `ann_id` 折叠，每份公告只保留得分最高的那条上下文。启用 `rules_fulltext` 后立刻看到后果：BRE 的 resource 被一份季报的四条钻孔顶到 96.6，折叠后为 93.1，背后是四份不同公告。`components.resource` 现在同时给出 `context_count`（原始上下文数）与 `announcement_count`（去重后的公告数），两者的差距就是同源程度。

**Cycle Score 层：质量标签只归一侧。** 两个子分读的是同一组标签，但分工不同——`announcement_score` 回答「发生了什么、多新、是否价格敏感」，`resource_score` 回答「这个结果好不好」。质量与重要性描述的是内容本身，因此只留给 `resource_score`，它还会结合趋势、深度、分位数一起判断，读得更完整。

重叠部分原先是 `announcement_score` 里一个封顶 10 分的加成，叠加价格敏感系数与权重后，最多影响约 4.8 个 Cycle Score 点——不足以跨两级标签，但足以让一只股票从 `Monitor` 跨到 `Watch Closely`。移除时 `AI_ANALYZER=noop`，加成恒为 0，因此历史分数一分未变。标签本身仍写入 `components.announcement`，供阅读，不参与计分。

### 尚未处理

**事件族划分偏粗。** 同一天的两份互不相关的钻探公告会被归入同一事件族，因而被当作一份证据。这是刻意选择的保守方向——宁可低估共振，也不要制造虚假共振。待 P03 把事件类型抽取稳定后，可以改为按真实事件聚合。

## P05 分析 Agent

P05 要的是三个**互相独立**的分析 Agent。Technical 与 Catalyst 已经是真的——各自读自己的数据、各有七个专业视角；Fundamental 仍由 `p5_p6_adapter` 投影 Cycle Score，待后续替换。

| Agent | 读什么 | 禁止读什么 | 状态 |
|---|---|---|---|
| Technical | 日线价量 | 公告、评分、其他引擎 | ✅ 真 Agent |
| Catalyst | P03 项目事件 | **价格、成交量、技术指标**、其他引擎 | ✅ 真 Agent |
| Fundamental | —— | —— | ⚠️ 仍是投影 |

### Technical Agent

### 七个视角

| 视角 | 判断什么 | 报出条件 |
|---|---|---|
| `trend` | 均线排列与 50 日斜率 | 四项条件全部同向 |
| `momentum` | 10/20/60 日涨跌速度 | 长短周期反向，或 20 日 ≥25% |
| `participation` | 成交是否支撑价格 | 相对量 ≥3x，或价涨量缩 |
| `volatility` | ATR 收缩与扩张 | 14 日 ATR 为 50 日的 ≤65% 或 ≥180% |
| `structure` | 60 日区间位置 | 位于顶部 ≥90% 或底部 ≤10% |
| `breakout` | 突破、跌破、假突破 | 创 60/252 日新高新低，或突破未守住 |
| `exhaustion` | 偏离均线的程度 | 超过该股**自身**常态偏离的 2.5 倍 |

`exhaustion` 不用固定阈值：同样偏离 20%，对一只常年横盘的股票是极端，对一只日常跳动 15% 的股票是常态，所以比的是它自己的习惯。

### 三条约束

**隔离靠 import 图保证，不靠注释。** PRD 明写不能仅凭提示词声明"禁止读取"。`technical_lenses.py` 只 import 标准库与 `DailyBar`；`p5_technical_agent.py` 在模型层只碰 `AnalyticalSignal`。两条测试用 AST 解析断言这件事，顺手加一个 import 立刻变红。

**七个视角共用一个 `dependency_group`。** 它们读的是同一条价格序列，所以一天七个同向读数是**一份**证据而非七份。`price_action:{日期}` 这个键让下游的证据独立性统计不会把它当成七次独立确认。

**沉默与缺席分开记。** 每个视角都有 `status`：`reported`（有实质读数，产出信号）、`no_material_change`（算过了，没事发生）、`insufficient_data`（日线不够，说清差多少根）。只有第一种产出 Signal——PRD 要求"没有实质变化时允许 No Material Signal，不得强行制造信号"——但三种都进 Narrative，所以"看了没事"和"根本没看"在记录上永远分得开。

### 被证伪的规则不会制造确认

252 日新高在本项目回测中测得 +5 日超额 −29.78%。它照样报出，但方向写 `neutral`、置信度 `low`：`_engines()` 只统计非 neutral 的引擎，所以它**无法**成为把单一读数变成"确认"的第二票。这条策略原先在适配器里，现在移到了产生读数的地方。

### 七视角一览

详情页每个引擎上方有一排七视角标记。只列出「产出了信号的那几条」说得出发生了什么，却说不出**看了多少**——四条催化发现，读起来和另外三个视角「算过了没事」还是「历史不够没法算」完全一样。引擎内部把这两者分得很清楚，叙事里也写了，但折叠着。

所以三种状态是三个不同的记号：

| 记号 | 含义 |
|---|---|
| `▲▲▲` / `▼▼▼` | 有实质读数，个数表示强度，方向用现有的涨跌色 |
| `◆◆` | 中性读数——被回测证伪的规则照常报告，但画成"同向"就等于给了它没资格给的确认 |
| `·` | 算过了，无实质变化 |
| `—` | 证据不足 |

名册由接口**重算**而不是存储：lenses 是纯函数，重算不需要加字段，也不会和它读的数据脱节。

### 输出

每条信号带 `narrative`（`analytical_signals.narrative`，本次新增的列），内容是七个视角的逐条读数加一句结论。当多空视角同时存在时，结论会明说"内部存在分歧，不宜当作单一方向的确认"，而不是只报多空计数。

### Catalyst Agent

读 P03 项目事件，判断项目走到哪、下一步等什么、卡在哪。七个视角：

| 视角 | 判断什么 |
|---|---|
| `lifecycle` | 当前生命周期阶段，以及阶段是否推进 |
| `milestone` | 里程碑完成，或已披露安排被撤回 |
| `derisking` | 审批、合作、资金到位 |
| `bottleneck` | 已到某阶段、但前置条件仍无证据 |
| `timeline` | 公司修订了此前披露的计划 |
| `forward` | 下一关键事件，以及已等待多久 |
| `dependency` | 披露超过 180 天仍未见结论的事项 |

阶段是**证据的排序，不是项目必须跑的跑道**。矿业公司常把钻探、冶金、审批并行推进，所以「阶段」取的是有证据支持的最远一点，而不是最新那条公告。

### 三条写进代码的 PRD 约束

**计划不等于完成。** 一笔 `proposed` 的配售不算去风险，只有 `funds_received` 或 `completed` 才算。前者报 `neutral` 并注明「到账前不构成去风险」。

**沉默不是失败。** PRD 原文：「未收到公告不能自动判定为 Milestone Failure」。`forward` 视角在长期无公告时报的是「已等待 N 天」，方向 `neutral`、置信度 `low`，并写明「不能据此判定里程碑失败」。

**不凭空生成概率。** Forward Catalyst Map 的 `probability` 恒为 `not_assessed`——PRD 明确不在 Pilot 建里程碑概率模型，也不许在证据不足时编一个数。

### Forward Catalyst Map

界面在股票详情页：阶段梯子标出走到哪一级（阶段是**证据的排序，不是项目必须跑的跑道**，所以是标记而非路径）、下一关键事件、未解除的瓶颈、披露后长期未见结论的事项，以及与上次相比的变化。完成概率一栏固定显示「未评估」——Pilot 不建里程碑概率模型，PRD 也禁止在证据不足时编一个。

`forward_catalyst_maps` 表，按日追加而非覆盖——PRD 把它定义为**持续的内部分析状态，不是第三种正式输出**，两天之间的差异本身才是发现。记录当前阶段、下一关键事件、重要性、未解依赖、瓶颈、证据基础，以及与上次相比的变化。

### 跨引擎的同源折扣

Catalyst 的依赖组按**触发来源**决定，而不是一律按引擎：

- 由单一公告族触发的视角（里程碑完成、审批到位、计划修订）→ `announcement_event:{日期}:{族}`，与 Fundamental 用的是同一个键
- 读整段事件史得出的视角（阶段、瓶颈、等待、依赖）→ `project_progress:{日期}`

这样一份钻探公告同时推动 Fundamental 与 Catalyst 时，P06 只记一份证据；而「项目卡在 FID 前」这种跨越整段历史的判断，才算独立的第三方意见。

## 项目经济性抽取

Fundamental 的第 5 视角（项目经济性）所需的数字——NPV、IRR、CAPEX、OPEX、AISC、回收期——由 [`p3_economics.py`](backend/app/services/p3_economics.py) 从研究类公告正文抽取。这是三个需要读散文的视角之外、唯一能用规则做干净的一个。

### 为什么不是「匹配术语 + 匹配数字」

三件事让它比看上去难，每一条都是在本项目 301 份真实原文上实测出来的：

**术语往往不是缩写。** 资本开支写成 `initial capital expenditure of A$277 million` 的次数远多于 `CAPEX`；全维持成本基本都是全称。只认缩写时，72 份讨论资本估算的文档里只抽出 2 份。

**缩写往往不是术语。** `irr` 作为子串出现 215 次，真正是内部收益率的只有 84 次，其余藏在 `irregular` 和 `Irrigation Act` 里。词边界能解决这个，但解决不了下一层：术语表里的 `NPV Net present value NSW New South Wales` 是定义，风控段落里的 `project value (NPV)` 既不是定义也不是数字。两者都靠**要求数值紧挨术语**排除，而不是「术语之后的某处」。

**NPV 没有折现率就不是一个数。** A$1.5bn @ 6.5% 和 A$1.5bn @ 10% 描述的是不同的项目。读不到折现率时，该数字标为 `complete: false`，而不是悄悄当成可比数据发出去。

### 四道守卫，各自对应一类实测误报

| 守卫 | 挡住的 |
|---|---|
| 词边界 | `irregular`、`Irrigation Act` |
| 数值必须紧跟术语（70 字符内） | 术语表、风控套话捐赠的无关数字 |
| 金额必须带货币符号**或**量级词 | `commencing in 2029`（年份）、`+/- 10`（敏感性步长）、`ISO 31000`、`NPV7`（折现率被当成金额） |
| 项目级金额下限 100 万 | `NPV (Scaled @ $4.30`（每股换算系数） |
| 不跨句子边界 | `IRR . Wyloo has commenced a formal sale process…60%` —— 那个 60% 属于出售，不属于项目 |

句号后加空格才算句子结束——数字里的小数点不算；冒号也不算，它通常正是引出数值的那个符号（`Capital cost: A$120 million`）。

### 归属：同一个数字，不同的主张

公司报告「已经做到」的成本，和研究报告「预计能做到」的成本，是两种不同的主张；独立专家对公司的估值又是第三种。每条记录带 `basis`：

| 取值 | 线索 |
|---|---|
| `actual_result` | produced、actual、guidance、FY27 |
| `study_estimate` | study、DFS、PFS、scoping、base case |
| `third_party` | independent expert、the Scheme、valuation range |
| `unknown` | 没有线索时的默认——**不假定是研究估算** |

### 摘要优先的代价

P03 默认只读 Summary / Highlights，字段齐了就不往正文走。而 DFS 事件原先只要求 `study_type`，摘要里必然有，于是正文里的经济性数字永远读不到：改抽取器后 NPV 只从 1 条变成 7 条。

把 `project_economics` 加进 DFS 事件的字段要求后（一个槽位，六种数字任一满足即可），缺这些数字的研究公告会自动下探正文。结果：

| 指标 | 改前 | 改后 |
|---|---|---|
| NPV | 1 | **22** |
| IRR | 6 | **21** |
| 回收期 | 2 | **10** |
| AISC | 2 | **6** |
| CAPEX | 2 | **5** |

冻结基线相应新增三条 `F04.project_economics` 未找到标记——核对过，那三份样本正文里只有「capital cost estimate has been received」这类**没有数字的定性表述**，报未找到是正确答案。事实数与信息点数一条未变。

## P06 的结论从哪里来

机会强度 `opportunity_strength` 原先是 Cycle Score 的查表结果。这意味着 P05 的两个真引擎**影响不了唯一重要的那个字段**——它们改变融合记录的质地（置信度、信号结构、证据独立性），结论却照旧由老链路给出。两个自己读数据的引擎只是装饰。

现在由信号推导，四条规则各自对应一件查表做不到的事：

**只有正向读数能抬升强度。** 强度喂给注意力状态，注意力状态喂给买入决策，所以一个证据充分的看空判断绝不能以「机会」的身份走到那里——它属于 `conflicts`。

**中性读数一分不计。** 这是被回测证伪的规则无法制造「确认」的地方：252 日新高方向写 `neutral`，于是它永远当不成把单一读数变成共识的第二票。

**数来源，不数信号。** 七个技术视角在同一天同向，是**一份**证据；`dependency_group` 就是说这件事的字段。置信度同样改成数来源——原先数行数，让一个引擎的七条读数冒充三份独立印证。

置信度另外还脱离了老链路：它曾经以 `risk_score >= 45` 为门槛，那是新链路唯一仍然说不清的一块。现在只看两个它自己有的输入——有几个独立来源给出了方向，以及那些读数**自报**的置信度。风险有自己的入口（`blocking_conditions`，直接让融合记录不可行动），不需要在这里再来一次。

**过热、主驱动、阻断条件也一并换了来源。** 过热原先问的是「价格类信号触发了，而公告分和资源分都低吗」——那是在没有更好东西之前拼出来的代理指标。Technical Agent 现在直接报这件事：`exhaustion` 量的是价格偏离**它自己**的常态多少（不是固定百分比），`participation` 抓的是量能跟不上的上涨。这一项比其他几项要紧：P08 在 Decision Ready 时读到 medium 或 high 就给 `wait` 而不是 `act`。

主驱动因素原先列的是分项数值（`announcement: 100`）——那是在报数字，不是在报发现。现在取引擎自己写的那句话。

阻断条件**只换了一半，另一半照实标注**。P05 定义了三个 Agent，风险不在其中——系统对风险唯一的读数仍是老链路的 `risk_score`。与其删掉它、或者假装它是新的，条件名里直接写上 `legacy_` 前缀，读的人能看出这份清单哪半是引擎产出的。

要分清置信度说的是什么：`high` 的意思是「这个判断可信」，不是「机会好」。HAS 现在是三个独立来源、平均自报置信 0.72，判为 `high`——而它的结论恰恰是明确看空。

**分歧不是强度。** 被同等来源的看空证据顶住的看多判断会被封顶，因为两个引擎指向相反时，诚实的读法是不确定，不是信心。

### 分歧必须看得见

封顶曾经是静默的：强度因为引擎分歧被压到 `weak`，而记录里 `conflict_flag` 是 0、`conflicts` 是空。**一个项目在推进、股价在跌**——架构里单列为一种状态的背离——被压成了一句没有解释的「弱」。

现在 `conflicts` 区分两种：

| 条目 | 含义 |
|---|---|
| `engine_internal_divergence:technical` | 同一引擎内部不一致（趋势看多、衰竭看空） |
| `cross_engine_divergence:fundamental_vs_catalyst+technical` | 跨引擎不一致 |

实跑第一天就在 BRE 上抓到后者：resource 分 93.1（两个月内三条高品位发现），而技术面与催化面同时看空。这是 PRD 点名的 Technical ↔ Fundamental 背离。

### 换掉之后的实际差别

| 股票 | 新判断 | 旧判断（Cycle Score 查表） |
|---|---|---|
| WC8 | weak | moderate |
| ARU / AUC | none | weak |
| AGY / BMN / CVV / HAS / HCH / MEK | weak | none |

两个方向都有变化，说明新旧不是简单的平移。每条融合记录的 `metadata` 同时保留 `cycle_score_strength`，老结论随时可比对。

注意力状态与交易决策没有变化——十只股票的证据仍不支持任何强势判断，整个名单处在下跌趋势中。这是结论，不是故障。

## P07 的人工确认

P07 按设计**从不自动晋升到 L4（Decision Ready）或 L5**——那一步留给人。引擎只给推荐。

问题是这个保留位没有门：`manual_override` 字段在、引擎也确实会让路（[attention_state.py](backend/app/services/attention_state.py) 在动任何状态前先检查它），但没有任何接口能设置它。于是这一步谁也迈不出去，而它下面的 P08 决策、P09 持仓、P10 复盘**一次都没运行过**。

### 接口

| 方法 | 路径 | 鉴权 |
|---|---|---|
| `GET` | `/api/attention/levels` | 公开 |
| `GET` | `/api/attention/{code}` | 公开（附带最新交易决策） |
| `PUT` | `/api/attention/{code}` | 管理员 |
| `DELETE` | `/api/attention/{code}?actor=…` | 管理员 |

```json
PUT /api/attention/WC8
{"level": "L4", "actor": "Rachel", "note": "补充尽调后确认", "lock": false}
```

设定会**当场重算交易决策**——P08 读的是注意力状态，状态一动决策就过期了，等下一次流水线会让晋升看起来毫无效果。

### 三条约束

**必须记录是谁。** `actor` 为空直接拒绝。设定不是编辑而是事件：引擎的区间被关闭、新区间打开，历史里留着谁动的、什么时候、以及**引擎当时的结论是什么**。

**人控制注意力状态，不控制决策规则。** 把一只手工提到 L4，如果 P06 读到过热风险，P08 照样给 `wait`。晋升打开的是流程，不是结论。

**解除不伪造转换。** `DELETE` 只清标记、不关区间——下一条融合记录会正常推动它。而且有迟滞：解除后的 L4 先降到 L3 再到 L2，一个弱势日不足以抹掉一次晋升。

### 顺带修掉的静默覆写

手工状态被引擎「保持」时，[attention_state.py](backend/app/services/attention_state.py) 会把引擎文本写回 `reason`——层级留住了，**人写的理由没了**，留下一个谁也说不清来由的状态。

现在保留人的理由，并把引擎此刻的判断记在旁边：`engine_would_be`。这才是有用的对照——「你钉在 L4，引擎现在读 L1」。

### 尾部链路首次跑通

用 WC8 的真实数据演练了一次，五层全部执行：

```
P7   L1 → L4（人工，manual_override）
P8   pass → act / starter_buy（把握 medium）
P9   建仓 10000 股 @ 0.195 → 平仓 @ 0.21
P10  复盘：收益 +7.69%，结果质量 profit，决策质量 supported
     → 并自动产生一条策略学习候选
```

五个复盘维度（论据、信号、决策、仓位管理、归因）全部产出。演练数据已清除，WC8 的覆盖已解除。

### 复盘回链到当初的证据

P10 的 `state_transition_review` 原先是空的，因为它从持仓事件里读这些 ID，而**建仓和离场这两类事件从来不写**——只有持仓期间的定期复查会写。一笔开仓就平、中间没有复查的交易，事后完全追溯不到任何证据。

现在两端都记录当时的注意力状态与融合记录，复盘因此能回答它存在的那个问题：

```
进场: {"attention_state_level": "L4", "opportunity_strength": "weak", ...}
离场: {"attention_state_level": "L4", "opportunity_strength": "weak", ...}
持仓期间状态变化: false
结论: Attention stayed at L4 throughout; the exit was not driven by a change of state.
```

这段演练输出里有个值得注意的对照：注意力状态是 L4（人工设定），而机会强度是 `weak`（引擎的判断）。**复盘如实记下了「人把一只引擎评为弱的股票提到了 Decision Ready」**——这正是事后该被看见的东西。

没有任何状态可回链时，复盘明说「cannot be traced to the evidence behind it」，而不是留一个空列表让人以为证据没问题。

## 外观：浅色 / 深色

两套调色板在 [`theme.ts`](frontend/src/theme.ts)，启动时写进 `:root`。深色不是把浅色反过来——纯黑让这些色相无处落脚，所以底色是同一色族里一块很深的板岩灰，每个强调色都是重新挑的而不是调亮的：浅色那组放到深底上全部跌破 4.5:1。

对比度是算出来的，不是看出来的。十一个承载文字的色，对 `#161D24` 和 `#0E1419` 两个底色，最低 4.87:1（`inkFaint`），其余都在 5:1 以上，全部通过 WCAG AA。测试里带了对比度函数，改色时会当场拦下。

图表跟着一起走。ECharts 原先是主题唯一没覆盖到的地方——AntD 和 CSS 变量都切了，坐标轴、蜡烛和提示框还停在白底上，而深色页面里一张白图是屏幕上最亮的东西。现在 [`chartTheme.ts`](frontend/src/chartTheme.ts) 从同一套调色板派生，靠 `data-theme` 属性上的 MutationObserver 跟随切换。

顺带收拾了配色纪律：信号标记原先是五种随意的色相，既超出四色预算，又让一条被回测证伪的规则（`BREAKOUT_252D`，+5 日超额 −29.78%）和有证据支持的规则获得同样的视觉分量。标记上本来就有字母区分类别，所以颜色腾出来承载真正要紧的事——该规则现在画成灰的。

全站现在零硬编码颜色，有一条测试扫描所有源文件守着这件事。

三态：跟随系统 / 浅色 / 深色。「跟随系统」是默认——同一个工具早上和晚上打开不该让人说两遍。

两件容易做错的事：

**切换的不只是变量，还有 AntD 的 algorithm。** 悬停态、边框、禁用态都是组件库自己推导的；只改 CSS 变量会让它们全部按白底计算。

**`tokens.css` 只重复三个颜色。** 它负责 React 挂载前的那一帧，没有它深色机器会闪一下白。但每多抄一个字面量就多一处可能和 `theme.ts` 漂移的地方，所以只留空白页面真正能看见的三个：底色、面色、文字色，其余十五个由 `applyPaletteVars` 随后写入。

## P06 的叙事

P06 把 Narrative 列为主交付成果。规则引擎写不出 PRD 要的那种交易员密度的散文，所以这里写的是诚实的版本，并且**在文末自报出身**：

> 以上为规则引擎对各分析引擎读数的结构化综述，不是交易员判断：它不推断行情阶段、不给顶底结论、不提出交易建议。

顺序照 PRD 自己的列法，因为顺序就是论证：结论 → 支持的读数 → 反对的读数 → 分歧 → 要改变结论需要什么。只读第一行的人也拿到最要紧的部分。

BRE 的真实输出：

```
结论：机会强度弱；证据来自三个以上互相独立的来源，置信度 high。
支持的读数：
  · 基本面·fundamental：exceptional / September 2026 Quarterly Report
反对的读数：
  · 项目催化·bottleneck：处于 study 阶段，但仍有 2 项前置条件未见证据…
  · 技术面·structure：价格位于 60 日区间底部 8% 处，支撑位 1.675。
另有 1 条中性读数（derisking）不计入方向——被回测证伪的规则照常记录，但不能充当确认。
分歧：
  · 基本面看多，而项目催化、技术面看空
要改变这个结论，需要：
  · 第二个独立来源的正向读数；单一来源无论多强都只能算弱
  · 当前 2 个负向来源中至少一个转向或失效
```

最后那节是刻意的：「留意后续进展」等于没说，读的人需要知道**具体哪个观察**能把结论推动。

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
9. 质量与重要性标签只计入 `resource` 子分（权重 0.20），`announcement` 子分不再读取它们——两者原先同时计分，详见「信号与评分的去重」。
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
