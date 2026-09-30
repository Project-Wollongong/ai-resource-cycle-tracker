# Beta02 P03：Information Point 定义与分组规则

## 1. 正式定义

### 原子 Fact

`P3Fact` 是公告明确披露的一个最小、可查询字段，例如：

- Hole ID = BCRC115
- Interval Length = 8m
- Grade = 1.5% Li2O
- From Depth = 89m

每条 Fact 独立保存值、单位、状态、期间、实体归属、PDF 页码、原文、Parse Run 和提取器版本。Fact 是 P03 的事实底座，不能为了展示数量而合并、删除或覆盖。

### 逻辑 Information Point

`P3InformationPoint` 是公司在一个明确原文证据位置表达的一项独立声明，由一条或多条 P3Fact 组成。例如：

> BCRC115: 8m @ 1.5% Li2O from 89m

它是一个逻辑信息点，底层包含 Hole ID、Interval、Grade、From Depth、True Width 等多个 Fact。

Information Point 是计数和展示层，不是新的事实来源，不进行计算，也不代替 P3Fact。

## 2. 计数规则

- 同一原文声明、同一语义对象、同一期间下的多个字段计为一个 Information Point。
- 同一句包含两个独立声明时可生成两个点，但必须各自有清晰的事实边界。
- 不同 PDF 页、不同期间、不同钻孔区间、不同 Resource/Reserve 行分别计数。
- 标题与 Summary 数值冲突时分别保存为两个来源点并进入复核。
- Event Family、Event 标签、文档类别、Revised 标签不计为信息点。
- 缺失字段、“未找到”、模型推测、宣传形容词和 P04 计算结果不计数。
- 重复出现且来源、值、期间完全相同的事实不重复计数。

## 3. 专属分组规则

### F01 钻孔

- 一条母区间是一个 Information Point。
- `including` 子区间是独立 Information Point，不覆盖母区间。
- Hole ID、Interval、Grade、From、True Width 是该点的组件 Fact。
- Drill Programme、Drilling Completed、Assay Pending 分别是独立状态点。
- 不计算 Grade × Thickness。

### F02 Resource / Reserve

- Resource/Reserve 表的一行分类是一个 Information Point。
- 一行中的 Type、Classification、Tonnage、Grade、Contained Metal、Commodity 是组件 Fact。
- Measured/Indicated/Inferred 与 Proved/Probable 不得组成同一点。
- 历史 Resource 引用是独立 historical_reference 点。
- 标题 30%、Summary 32% 是两个来源点，均保留并复核。

### F08 现金流表

- 一个现金流字段在一个明确期间内是一个 Information Point。
- Current Quarter 与 Year-to-Date 必须是两个点，即使数值恰好相同。
- Cash Balance、Operating、Investing、Financing、Exploration Spend、Development Spend、Administration Spend 分开计数。
- Period-end Cash Balance 不等于 Cash Runway。

### 其他 Family

- F04：原时间、修订时间和 Schedule Change 可组合成一个 Timeline Change 点；Study、FID、CAPEX Review 等独立声明另计。
- F06：融资金额、发行价、证券数量、SPP 上限、用途按独立原文声明分组；committed 与 received 不合并。
- F03：同一批测试中的 Recovery、Product Grade、Composite 数量组成一个 Test Result 点；Processing Route 可独立。
- F05：同一许可证的 Type/ID/Status/Authority/Area/Expiry 按同一许可声明分组；Groundwater technical support 与正式 granted 分开。
- F07：总体 Earn-in、Phase 1、Phase 2、Current Ownership、Manager 分别按原文声明分组；Manager 不生成 Operator 点。

## 4. 20–50 目标区间

20–50 是覆盖目标，不是硬性配额：

- `<20`：`count_status=source_insufficient`，显示“来源不足”；不复制、不细碎拆分、不编造。
- `20–50`：`count_status=target_range`。
- `>50`：`count_status=high_density`；数据库保留全部点，前端分页或折叠，不截断。

同时返回：

- `information_point_count`
- `atomic_fact_count`
- `summary_point_count`
- `standard_form_point_count`
- `body_fallback_point_count`
- `review_needed_count`
- `summary_coverage_ratio`

## 5. Summary 优先

来源顺序保持：Summary → Highlights → Key Results → Executive Summary → 标准表格 → Body Fallback。

Information Point 保存 `source_section`、页码和原文。Summary 不包含 Appendix 5B 数值、Reserve 表行或详细交易阶段时，允许从标准表格/正文提取，但必须显式标记来源。

## 6. 当前固定样本基线

| 样本 | 逻辑信息点 | 原子 Fact | 状态 |
|---|---:|---:|---|
| S01 CVV | 5 | 8 | 来源不足 |
| S02 AGY | 17 | 17 | 来源不足 |
| S03 AGY | 7 | 7 | 来源不足 |
| S04 CYL | 8 | 17 | 来源不足 |
| S05 WC8 | 18 | 74 | 来源不足 |
| S06 GL1 | 6 | 9 | 来源不足 |
| S07 DYL | 5 | 11 | 来源不足 |
| S09 WC8 | 11 | 37 | 来源不足 |

这些数字用于说明当前来源和规则下的真实覆盖情况，不为达到 20 条而人为增加。

## 7. 数据库存储

逻辑信息点与 P01/P02/P03 数据共同保存在正式 `data/tracker.db`：

- `p3_information_points`
- `p3_information_point_facts`

关联表保留一个 Information Point 下所有 P3Fact ID、组件角色和显示顺序。新 Parse Run 创建新版本，旧点通过 `superseded_by_id` 保留。
