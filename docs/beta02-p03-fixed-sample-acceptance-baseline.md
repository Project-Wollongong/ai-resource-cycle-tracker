# Beta02 P03 固定样本验收基线 v2

基线文件：`docs/beta02-acceptance/p03-fixed-sample-baseline-v2.json`  
样本来源：`docs/beta02-acceptance/samples.json` 与本地 PDF fixture  
状态：自动化基线已冻结，待人工签署

## 计数口径

- 原子 Fact：一条持久化的 `P3Fact`。
- 逻辑信息点：一个由一个或多个原子 Fact 组成、可回到同一来源主张的 `P3InformationPoint`。
- Summary 信息点：来源为 Summary、Highlights、Key Results 或 Executive Summary。
- 表格信息点：来源为标准 ASX 表格，目前为 `standard_form`。
- Body fallback：Summary 和标准表格完成缺口检查后，才从 `body` 或 `body_fallback` 补取。
- 待复核数：`review_status=review_needed` 的逻辑信息点数。基线同时保留待复核原子 Fact 数用于诊断。
- 未找到字段：同时报告 Family 规则要求槽位和固定样本必须提取的 Fact Type。
- 20–50 是覆盖目标，不是通过配额；不补数、不截断。少于 20 显示 `source_insufficient`。

## 当前固定基线

| 样本 | 原子 Fact | 信息点 | Summary | 表格 | Body | 待复核 | 未找到 | Project / Asset Unit |
|---|---:|---:|---:|---:|---:|---:|---|---|
| S01 CVV | 8 | 5 | 5 | 0 | 0 | 1 | F05.approval_status | Caravel Copper Project；3 个 Company Fact |
| S02 AGY | 17 | 17 | 3 | 14 | 0 | 12 | F03.processing_route、F03.test_programme、F04.construction_progress | Rincon Lithium Project；16 个 Company Fact |
| S03 AGY | 7 | 7 | 2 | 0 | 5 | 7 | 无 | Company |
| S04 CYL | 17 | 8 | 6 | 0 | 2 | 5 | 无 | Trident、Plutonic Gold Belt；1 个 Company Fact |
| S05 WC8 | 74 | 18 | 18 | 0 | 0 | 16 | 无 | Tabba Tabba；Bolt Cutter Central、Hutt、Chewy、Leia；3 个 Company Fact |
| S06 GL1 | 9 | 6 | 0 | 0 | 6 | 6 | 无 | Manna Lithium Project；7 个 Company Fact |
| S07 DYL | 11 | 5 | 2 | 0 | 3 | 4 | 无 | Nova Joint Venture；7 个 Company Fact |
| S08 EL8 | 0 | 0 | 0 | 0 | 0 | 0 | 无 | Company；Appendix 3Y 路由负例，不生成 P03 业务 Fact |
| S09 WC8 | 37 | 11 | 11 | 0 | 0 | 7 | 无 | Tabba Tabba / Bolt Cutter Central；5 个 Company Fact |
| S10 DRE | 0 | 0 | 0 | 0 | 0 | 0 | F03.test_programme、F05.permit_status、F05.permit_type；必需 Fact `permit_status`、`permit_type` | 未确认，留在 Company 层 |

## 验收解释

1. S05 的 74 个原子 Fact 被组合成 18 个逻辑信息点，主要因为一条钻孔交集包含 Hole、Interval、Grade、From、True Width 等多个原子字段。
2. S02 的 14 个表格信息点来自 Appendix 5B；没有把这些数据伪装成 Summary 来源。
3. S03、S04、S06、S07 只有在 Summary 缺字段后才使用正文 fallback。
4. S08 是 Appendix 3Y 负例。0 个业务 Fact 是正确结果，不应为了达到 20 个而制造信息点。
5. S10 当前没有提取到 F05 Permit Type/Status，是明确的高优先级覆盖缺口；基线记录问题但不编造结果。
6. Project/Asset Unit 仅来自固定 P01 已批准目录；无法由 Fact 自身证据确认的内容继续留在 Company 层。

## 自动复验

```powershell
.\backend\.venv-win\Scripts\python.exe scripts\verify_p03_facts.py
.\backend\.venv-win\Scripts\python.exe scripts\verify_p03_facts.py --check
.\backend\.venv-win\Scripts\python.exe scripts\verify_p03_facts.py --json
```

`--check` 会重新解析全部十个本地 PDF fixture，先验证 SHA-256，再逐字段比较计数、来源、缺失字段、复核数量和实体归属。任何基线漂移都会返回非零退出码。
