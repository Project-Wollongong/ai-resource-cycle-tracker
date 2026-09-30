# Beta02 固定公告验收样本（候选答案 v1）

便于集中审核的入口：[阶段 0 单表审核清单](beta02-stage0-review-table.md)。按用户最新指示，只有收到明确的 **“阶段 0 确认”** 后才开始 P01 开发；P01、P02、P03 均未开始。

**人工签核尚未完成。** 以下事实由 Codex 对照原始 PDF 文本与页面图像核对，不能标作人工已确认。请产品负责人逐份确认或修正；签核后才能冻结为人工验收基线。

固定数据：[samples.json](beta02-acceptance/samples.json)。原始 PDF 保存在 `beta02-acceptance/pdfs/`，仅供开发回归，未写入业务数据库或前端。所有页码均为从 1 开始的 PDF 物理页；例如 S02 的 PDF 第 11 页是 Appendix 5B 印刷第 1 页。

`summary` 是默认 Pilot 必验；`reference_only` 是已核对的原文参考答案，但不要求摘要解析器越界提取；`routing_only` 只用于文件类型。S04 首页面向读者的项目符号摘要没有 Highlights 标题，边界已明确标注，需随人工审核确认。S06 没有明确摘要，必须保留待个案处理状态。

这些是关键事实的最低回归标准，不能用通过本样本清单宣称“全部摘要事实已无损提取”。金标准由预先核对的原文产生，不得从未来解析器输出反向生成。

## 覆盖矩阵

| 家族 / 场景 | 默认摘要正向样本 | 补充 / 反例 |
|---|---|---|
| F01 Exploration & Drilling | S05、S09 | 未来 MRE 不等于 F02 已发布 |
| F02 Resource & Reserve | S04 | S10 是既有资源引用，不是新 MRE 事件 |
| F03 Metallurgy & Processing | S01、S02、S09 | S05 metallurgical drilling 不等于回收率结果 |
| F04 Development & Study | S01、S02、S04、S05、S10 | DFS 不等于完成，更不等于利好 |
| F05 Permitting & Project Access | S10 | S06 无摘要；技术支持不等于正式 grant |
| F06 Funding & Capital | S03 | 认购承诺不等于到账 |
| F07 Commercial & Corporate Transaction | S05、S07 | earn-in 目标权益不等于当前权益 |
| F08 Financial / Operating Periodic | S05、S09 | S02 Appendix 5B 表格参考答案 |
| Quarterly / Appendix 5B | S02 | Document Type 不等于只有 F08 |
| Administrative / Director Interest | 无核心事件 | S08 Appendix 3Y，Ownership / Governance |

## 逐份审核清单

### S01 · CVV · DFS Revised Completion Timing

- 股票：`CVV`；公告时间（数据库悉尼本地时间）：`2026-09-18 09:10:53.000000`。
- ASX 公告编号（source documentKey）：`2924-03136859-6A1344354`。
- [ASX PDF](https://asx.api.markitdigital.com/asx-research/1.0/file/2924-03136859-6A1344354) · [固定原文](beta02-acceptance/pdfs/S01.pdf)。
- Document Type：Project / DFS timing update；ASX 原始 category：`PROGRESS REPORT`。
- 期望核心事件：F04 / Project Delay [reported]；F04 / Project Schedule / Timeline Update [reported]；F03 / Metallurgical Testwork Planned / Commenced [planned]。
- 摘要边界：PDF 第 1 页 Highlights 六个项目符号；止于 Managing Director 引述之前。
- P01 研究候选：Caravel Copper Project；不表示实体或关系已批准。
- 下载校验：HTTP 200；4 页；211,278 bytes；UTC `2026-09-24T10:26:56.883329+00:00`。
- SHA-256：`48de74c15471745929da95741947f67eab15f5f744ba9ea08a45f84d708fc33c`。
- 人工确认：**待确认**；审核人：____；日期：____；修订意见：____。

| 事实 ID / 字段 | 候选关键事实 | 原文位置 / 解析范围 | 限定条件 |
|---|---|---|---|
| S01-F01 / `dfs_release_timing` | {"previous": "September 2026", "revised": "Q4 2026"} | PDF p.1，Highlights 第 1 条；`summary` | 计划披露时间改变；不是 DFS 已完成 |
| S01-F02 / `metallurgical_testwork_objectives` | 进一步改善铜精矿品位及回收率；制备铜和钼精矿供营销；重测样品以确认金银回收率 | PDF p.1，Highlights 第 2 条；`summary` | 计划工作；未报告新的回收率数值 |
| S01-F03 / `groundwater_modelling` | Yarragadee / Leederville 数值模拟拟支持 Gillingarra H3 报告及 DWER 受理 | PDF p.1，Highlights 第 3 条；`summary` | 待完成；不是地下水许可已授予 |
| S01-F04 / `environmental_review_document` | ERD 拟更新调查结果和供水模型后提交 EPA | PDF p.1，Highlights 第 4 条；`summary` | 未来工作；不是环保审批已通过 |
| S01-F05 / `plant_capital_estimate_review` | 公司拟在纳入 study 前全面审核并接受流程厂资本成本估算 | PDF p.1，Highlights 第 5 条；`summary` | 未给出 CAPEX 数值 |
| S01-F06 / `fid_target` | end of 2027 | PDF p.1，Highlights 第 6 条；`summary` | 目标时间，非已作出投资决定 |

**不得出现的输出：** 因 DFS 字样输出利好、80 分或研究已完成；将未来 funding / JV partnering 当作已签融资或 JV；将 revised timing 自动标为历史披露更正/撤回；自行计算延期天数。

### S02 · AGY · Quarterly Activities/Appendix 5B Cash Flow Report

- 股票：`AGY`；公告时间（数据库悉尼本地时间）：`2026-07-31 09:44:04.000000`。
- ASX 公告编号（source documentKey）：`2924-03116443-6A1336571`。
- [ASX PDF](https://asx.api.markitdigital.com/asx-research/1.0/file/2924-03116443-6A1336571) · [固定原文](beta02-acceptance/pdfs/S02.pdf)。
- Document Type：Quarterly Activities Report + Appendix 5B；ASX 原始 category：`QUARTERLY ACTIVITIES REPORT`。
- 期望核心事件：F04 / Engineering / FEED Update [ongoing]；F03 / Metallurgical Testwork Update [reported]。
- 摘要边界：PDF 第 1 页 HIGHLIGHTS 五条；现金表在 PDF 第 11–13 页，不属于默认摘要范围。
- P01 研究候选：Rincon Lithium Project、Tonopah Lithium Project；不表示实体或关系已批准。
- 下载校验：HTTP 200；15 页；829,915 bytes；UTC `2026-09-24T10:27:02.208633+00:00`。
- SHA-256：`3f166da63eb384d1c722cefd4f661c78bf30579762b34e3bf075658cce3017dd`。
- 人工确认：**待确认**；审核人：____；日期：____；修订意见：____。

| 事实 ID / 字段 | 候选关键事实 | 原文位置 / 解析范围 | 限定条件 |
|---|---|---|---|
| S02-F01 / `project_development` | Rincon 12ktpa 项目的可研与工程工作推进中；单位：ktpa | PDF p.1，HIGHLIGHTS 第 1 条；`summary` | 设计/开发规模；非实际年产量 |
| S02-F02 / `process_testwork` | 与国际技术服务商开展工艺测试，为 DFS 设计、设备尺寸与经济评估提供数据 | PDF p.1，HIGHLIGHTS 第 2 条；`summary` | 按原文报告，不作投资评价 |
| S02-F03 / `quarter_end` | 2026-06-30 | PDF p.11，Appendix 5B 封面 Quarter ended；`reference_only` | 按原文报告，不作投资评价 |
| S02-F04 / `net_operating_cash_flow` | -220；单位：AUD thousand | PDF p.11，Appendix 5B item 1.9，Current quarter 列；`reference_only` | 本季 -220；YTD 六个月 -415，不混列 |
| S02-F05 / `net_investing_cash_flow` | -1282；单位：AUD thousand | PDF p.12，Appendix 5B item 2.6，Current quarter 列；`reference_only` | 按原文报告，不作投资评价 |
| S02-F06 / `net_financing_cash_flow` | -5；单位：AUD thousand | PDF p.12，Appendix 5B item 3.10，Current quarter 列；`reference_only` | 按原文报告，不作投资评价 |
| S02-F07 / `cash_and_cash_equivalents` | 2060；单位：AUD thousand | PDF p.13，Appendix 5B item 4.6；item 5.5 亦可复核；`reference_only` | 截至 2026-06-30；不是 2,060 AUD |
| S02-F08 / `rincon_interest` | 77.5% JV interest, earning up to 90% | PDF p.1，第 1 页摘要之后 Rincon 小标题；`reference_only` | P01 研究候选；90% 是 earning up to，不是当前持股 |

**不得出现的输出：** 仅凭 Quarterly 标签认定摘要含现金数字；将 Appendix 表格数据假装来自 Highlights；把 cash flow 当现金余额；计算现金跑道或 burn；把意向评估当签署战略交易。

参考范围事件（不等于摘要必验事件）：F08 / Period-end Cash Position；F08 / Periodic Cash Flow Update。

### S03 · AGY · Successful $3M Placement and SPP launched

- 股票：`AGY`；公告时间（数据库悉尼本地时间）：`2026-09-02 09:35:54.000000`。
- ASX 公告编号（source documentKey）：`2924-03130574-6A1341758`。
- [ASX PDF](https://asx.api.markitdigital.com/asx-research/1.0/file/2924-03130574-6A1341758) · [固定原文](beta02-acceptance/pdfs/S03.pdf)。
- Document Type：Placement and SPP announcement；ASX 原始 category：`ISSUED CAPITAL`。
- 期望核心事件：F06 / Placement [firm_commitments]；F06 / Share Purchase Plan / SPP [planned]。
- 摘要边界：PDF 第 1 页 HIGHLIGHTS 三条，横线以内；发行价及数量在横线下正文。
- P01 研究候选：Rincon Lithium Project；不表示实体或关系已批准。
- 下载校验：HTTP 200；4 页；433,367 bytes；UTC `2026-09-24T10:27:05.184191+00:00`。
- SHA-256：`e45852e34688882f9c00815eeed9029ae7efc69865626996ac1ea9eec1f0f0c1`。
- 人工确认：**待确认**；审核人：____；日期：____；修订意见：____。

| 事实 ID / 字段 | 候选关键事实 | 原文位置 / 解析范围 | 限定条件 |
|---|---|---|---|
| S03-F01 / `placement_amount` | 3；单位：million dollars (source $) | PDF p.1，HIGHLIGHTS 第 1 条；`summary` | 正文限定为 firm commitments / before costs；不可标到账 |
| S03-F02 / `use_of_funds` | 推进 12ktpa Rincon 开发、工程及可研 | PDF p.1，HIGHLIGHTS 第 2 条；`summary` | 按原文报告，不作投资评价 |
| S03-F03 / `spp_status` | 拟推出，合资格股东可按 placement 相同条件参与 | PDF p.1，HIGHLIGHTS 第 3 条；`summary` | 按原文报告，不作投资评价 |
| S03-F04 / `placement_issue_price` | 0.036；单位：dollars/share (source $) | PDF p.1，第 1 页 HIGHLIGHTS 下正文；`reference_only` | 按原文报告，不作投资评价 |
| S03-F05 / `placement_new_shares` | 83333334；单位：shares | PDF p.1，第 1 页正文；`reference_only` | 按原文报告，不作投资评价 |
| S03-F06 / `spp_target` | 500000；单位：dollars (source $) | PDF p.1，第 1 页正文；`reference_only` | 上限、非包销；不是已募集 |

**不得出现的输出：** 融资用途提及项目开发便新增实际施工/钻探事件；把募集承诺当结算完成；系统计算折价或稀释；输出 successful 投资结论。

### S04 · CYL · Trident Reserve grows by 30%

- 股票：`CYL`；公告时间（数据库悉尼本地时间）：`2026-09-14 08:24:19.000000`。
- ASX 公告编号（source documentKey）：`2924-03134886-6A1343577`。
- [ASX PDF](https://asx.api.markitdigital.com/asx-research/1.0/file/2924-03134886-6A1343577) · [固定原文](beta02-acceptance/pdfs/S04.pdf)。
- Document Type：Ore Reserve update；ASX 原始 category：`PROGRESS REPORT`。
- 期望核心事件：F02 / Ore Reserve Update [reported]；F04 / Construction Progress Update [reported]；F04 / Project Schedule / Timeline Update [planned]。
- 摘要边界：PDF 第 1 页主栏标题下、金色横线上方的十条摘要项目符号；不含左侧公司简介/页脚或下方储量表。
- P01 研究候选：Trident、Plutonic Gold Belt；不表示实体或关系已批准。
- 下载校验：HTTP 200；16 页；905,631 bytes；UTC `2026-09-24T10:27:09.917697+00:00`。
- SHA-256：`d47bb8d74c88a5122771323a57f3328a81dcfdbea13e2c757242ec75cb9c779a`。
- 人工确认：**待确认**；审核人：____；日期：____；修订意见：____。

| 事实 ID / 字段 | 候选关键事实 | 原文位置 / 解析范围 | 限定条件 |
|---|---|---|---|
| S04-F01 / `trident_underground_reserve` | {"contained_gold": 524, "grade": 4.2}；单位：koz Au; g/t Au | PDF p.1，首页摘要第 1 条；`summary` | Reserve，不是 Resource |
| S04-F02 / `company_reported_reserve_increase` | 32；单位：% | PDF p.1，首页摘要第 1 条；`summary` | 公司明确报告；标题 30% 与摘要 32% 分开保留，不自行改为 30 |
| S04-F03 / `mine_life_and_production_plan` | {"mine_life": "approximately 10 years", "annual_production": "60–80 koz"} | PDF p.1，首页摘要第 1 条；`summary` | 预计稳态年产，非当前实际产量 |
| S04-F04 / `previously_reported_resource` | {"date": "June 2026", "contained_gold": "1.1 Moz", "grade": "5.4 g/t Au"} | PDF p.1，首页摘要第 3 条；`summary` | 引用过去 Resource，不是本次新资源事件 |
| S04-F05 / `inferred_resource_gold` | 448；单位：koz Au | PDF p.1，首页摘要第 4 条；`summary` | 按原文报告，不作投资评价 |
| S04-F06 / `development_completed` | 250；单位：m | PDF p.1，首页摘要第 6 条；`summary` | 按原文报告，不作投资评价 |
| S04-F07 / `first_ore_expected` | CY2027 | PDF p.1，首页摘要第 6 条；`summary` | 预计而非已投产 |
| S04-F08 / `probable_reserve_tonnage` | 3.9；单位：Mt | PDF p.1，第 1 页主栏储量表 Probable 行；`reference_only` | 按原文报告，不作投资评价 |

**不得出现的输出：** 将历史 75% 转换率当本次计算结果；因摘要中引用 June 资源而生成新的 MRE 公告；混入左侧公司全体资产数据作为 Trident 数据。

### S05 · WC8 · CONTINUED STRONG DRILL RESULTS

- 股票：`WC8`；公告时间（数据库悉尼本地时间）：`2026-08-31 08:02:59.000000`。
- ASX 公告编号（source documentKey）：`2924-03128755-6A1341087`。
- [ASX PDF](https://asx.api.markitdigital.com/asx-research/1.0/file/2924-03128755-6A1341087) · [固定原文](beta02-acceptance/pdfs/S05.pdf)。
- Document Type：Drilling results；ASX 原始 category：`PROGRESS REPORT`。
- 期望核心事件：F01 / Drilling Results / Assay Results [reported]；F07 / Project / Asset Acquisition [reported]；F04 / Study Update / Revision [ongoing]；F08 / Period-end Cash Position [reported]。
- 摘要边界：PDF 第 1 页 Highlights 全部，含 Bolt Cutter Central / Tabba Tabba 子标题，止于页底横线。
- P01 研究候选：Bolt Cutter Central、Tabba Tabba、Hutt、Chewy、Leia；不表示实体或关系已批准。
- 下载校验：HTTP 200；24 页；2,458,591 bytes；UTC `2026-09-24T10:27:20.077984+00:00`。
- SHA-256：`18cb777f4d463d33e174b4d039e882fcccc004f56d068126e7fcc286bd8e1f73`。
- 人工确认：**待确认**；审核人：____；日期：____；修订意见：____。

| 事实 ID / 字段 | 候选关键事实 | 原文位置 / 解析范围 | 限定条件 |
|---|---|---|---|
| S05-F01 / `bcrc115_intersections` | [{"width_m": 8, "grade_pct": 1.5, "from_m": 89}, {"width_m": 16, "grade_pct": 1.5, "from_m": 116}] | PDF p.1，Highlights / Bolt Cutter Central / BCRC115；`summary` | 两条均为 est. true width；Li2O |
| S05-F02 / `bcrc113_intersection` | {"width_m": 18, "grade_pct": 1.1, "from_m": 16} | PDF p.1，Highlights / BCRC113；`summary` | est. true width |
| S05-F03 / `bcrc112_intersections` | [{"width_m": 11, "grade_pct": 1.5, "from_m": 67}, {"width_m": 6, "grade_pct": 1.5, "from_m": 174}] | PDF p.1，Highlights / BCRC112；`summary` | 两条均为 est. true width |
| S05-F04 / `bcrc123_intersection` | {"width_m": 4, "grade_pct": 1.6, "from_m": 104} | PDF p.1，Highlights / BCRC123；`summary` | est. true width |
| S05-F05 / `bcrc116_intersection` | {"width_m": 6, "grade_pct": 1.0, "from_m": 85} | PDF p.1，Highlights / BCRC116；`summary` | est. true width |
| S05-F06 / `tamt038_intersection` | {"width_m": 25.1, "grade_pct": 1.2, "from_m": 56.5} | PDF p.1，Highlights / Tabba Tabba / Hutt / TAMT038；`summary` | est. true width |
| S05-F07 / `tamt040_intersections` | [{"width_m": 21.4, "grade_pct": 0.9, "from_m": 22.6}, {"included_width_m": 8.6, "grade_pct": 1.4, "from_m": 28.6}] | PDF p.1，Highlights / Hutt / TAMT040；`summary` | 包括区间不可丢失；母区间标 est. true width |
| S05-F08 / `tamt036_intersections` | [{"reported_width_m": 13.9, "grade_pct": 2.0, "from_m": 45.2, "estimated_true_width_m": 10.0}, {"included_reported_width_m": 7.8, "grade_pct": 2.3, "from_m": 45.2, "estimated_true_width_m": 5.6}] | PDF p.1，Highlights / Chewy / TAMT036；`summary` | 报告区间长度与估计真厚度分别保存；不要求正式 Hole 层级 |
| S05-F09 / `tarc435_intersections` | [{"reported_width_m": 18, "grade_pct": 1.3, "from_m": 69, "estimated_true_width_m": 16.4}, {"included_reported_width_m": 9, "grade_pct": 2.0, "from_m": 74, "estimated_true_width_m": 8.2}] | PDF p.1，Highlights / Leia / TARC435；`summary` | 按原文报告，不作投资评价 |
| S05-F10 / `maiden_mre_target` | Q4 2026 | PDF p.1，Highlights / Bolt Cutter Central 进度；`summary` | 未来计划；不生成已发布 MRE 的 F02 事件 |
| S05-F11 / `lct_rights_acquired` | E45/2364 | PDF p.1，Highlights 尾部第 1 条；`summary` | LCT rights，不扩张成整个项目所有权 |
| S05-F12 / `dfs_delivery_target` | H2 2026 | PDF p.1，Highlights 尾部第 2 条；`summary` | 按原文报告，不作投资评价 |
| S05-F13 / `cash_balance` | {"value": 37.2, "as_of": "2026-06-30"}；单位：million dollars (source $) | PDF p.1，Highlights 最后 1 条；`summary` | 按原文报告，不作投资评价 |

**不得出现的输出：** 只抽第一条或前十条区间；将 metallurgy drilling 当冶金回收率结果；将未来 MRE 误判已发布 F02；计算品位×厚度、强弱或历史百分位。

### S06 · GL1 · Manna Clearing Permit and Groundwater Licence secured

- 股票：`GL1`；公告时间（数据库悉尼本地时间）：`2026-08-20 08:59:12.000000`。
- ASX 公告编号（source documentKey）：`2924-03123369-6A1339377`。
- [ASX PDF](https://asx.api.markitdigital.com/asx-research/1.0/file/2924-03123369-6A1339377) · [固定原文](beta02-acceptance/pdfs/S06.pdf)。
- Document Type：Project permitting update；ASX 原始 category：`PROGRESS REPORT`。
- 期望核心事件：无默认核心事件输出。
- 摘要边界：无明确 Summary / Highlights；不自动全文 fallback。
- P01 研究候选：Manna Lithium Project；不表示实体或关系已批准。
- 下载校验：HTTP 200；4 页；429,417 bytes；UTC `2026-09-24T10:27:22.862761+00:00`。
- SHA-256：`5150d0fa1ebdc68305778b2820eab0c33443250d0e991281a0058f1524b0646d`。
- 人工确认：**待确认**；审核人：____；日期：____；修订意见：____。

| 事实 ID / 字段 | 候选关键事实 | 原文位置 / 解析范围 | 限定条件 |
|---|---|---|---|
| S06-F01 / `clearing_permit_status` | approved and effective; no appeals | PDF p.1，第 1 页首段；`reference_only` | 按原文报告，不作投资评价 |
| S06-F02 / `groundwater_licence_status` | DWER technical support for grant | PDF p.1，第 1 页首段；`reference_only` | 原文字样；不从标题推定正式 grant |
| S06-F03 / `clearing_permit_id` | CPS 11464/1 | PDF p.1，第 1 页第 3 段；`reference_only` | 按原文报告，不作投资评价 |
| S06-F04 / `clearing_authorisation` | {"max_area_ha": 875, "expiry": "2031-08-19", "term_years": 5} | PDF p.1，第 1 页第 4 段；`reference_only` | 按原文报告，不作投资评价 |
| S06-F05 / `works_approval` | expected before end of September 2026 quarter | PDF p.1，第 1 页第 5 段；`reference_only` | 尚待取得 |

**不得出现的输出：** 没有 Summary/Highlights 就偷偷全文解析并声称属于默认摘要；标题 secured 等同全部许可正式签发；把 remaining Works Approval 标已完成。

参考范围事件（不等于摘要必验事件）：F05 / Environmental Approval Granted；F05 / Water / Infrastructure / Other Statutory Permit。

### S07 · DYL · Nova Joint Venture, Namibia - A$5m Earn-In By Core Energy

- 股票：`DYL`；公告时间（数据库悉尼本地时间）：`2026-09-02 08:55:54.000000`。
- ASX 公告编号（source documentKey）：`2924-03130488-6A1341768`。
- [ASX PDF](https://asx.api.markitdigital.com/asx-research/1.0/file/2924-03130488-6A1341768) · [固定原文](beta02-acceptance/pdfs/S07.pdf)。
- Document Type：JV earn-in agreement；ASX 原始 category：`PROGRESS REPORT`。
- 期望核心事件：F07 / Farm-in / Farm-out [reported]。
- 摘要边界：PDF 第 1 页蓝色 Highlights 框两条；不含框下正文。
- P01 研究候选：Nova Joint Venture、Nova Energy (Namibia) (Proprietary) Limited；不表示实体或关系已批准。
- 下载校验：HTTP 200；3 页；3,268,239 bytes；UTC `2026-09-24T10:27:32.621254+00:00`。
- SHA-256：`855aa6178dce91190f038bbec5d074d3221baeecfa1e7a1564af3a518c4f77b9`。
- 人工确认：**待确认**；审核人：____；日期：____；修订意见：____。

| 事实 ID / 字段 | 候选关键事实 | 原文位置 / 解析范围 | 限定条件 |
|---|---|---|---|
| S07-F01 / `earn_in_terms` | {"expenditure_aud_million": 5, "maximum_interest_pct": 51, "phases": 2} | PDF p.1，Highlights 第 1 条；`summary` | up to / 条件性取得，不是当前已持有 51% |
| S07-F02 / `jv_manager_and_funding` | Core Energy Minerals Limited；earn-in 期间担任 Manager，并承担全部勘探支出及运营 | PDF p.1，Highlights 第 2 条；`summary` | 原文角色是 Manager；未确认与 Operator 等价，不自动生成 Operator Change 或修改 P01 operator |
| S07-F03 / `phase_1_terms` | {"interest_pct": 25, "spend_aud_million": 2, "months": 18} | PDF p.1，第 1 页正文 Phase 1；`reference_only` | 按原文报告，不作投资评价 |
| S07-F04 / `phase_2_terms` | {"additional_interest_pct": 26, "spend_aud_million": 3, "months_after_phase_1": 24} | PDF p.1，第 1 页正文 Phase 2；`reference_only` | 按原文报告，不作投资评价 |
| S07-F05 / `current_jv_interests` | {"RMR": 65, "Nova Africa": 25, "Sixzone": 10}；单位：% | PDF p.1，第 1 页正文 Current shareholders；`reference_only` | P01 关系候选；RMR 是 DYL 子公司，不能直接把 DYL 当项目全资所有人 |

**不得出现的输出：** 写成收款 A$5M 已到账；自动把 P01 ownership 改成 51%；把未来分阶段权益替代当前权益。

### S08 · EL8 · Change of Director's Interest Notice

- 股票：`EL8`；公告时间（数据库悉尼本地时间）：`2026-09-11 16:41:39.000000`。
- ASX 公告编号（source documentKey）：`2924-03134678-6A1343454`。
- [ASX PDF](https://asx.api.markitdigital.com/asx-research/1.0/file/2924-03134678-6A1343454) · [固定原文](beta02-acceptance/pdfs/S08.pdf)。
- Document Type：Appendix 3Y - Change of Director’s Interest Notice；ASX 原始 category：`SECURITY HOLDER DETAILS`。
- 期望核心事件：无默认核心事件输出。
- 摘要边界：无明确 Summary / Highlights；不自动全文 fallback。
- P01 研究候选：无；不表示实体或关系已批准。
- 下载校验：HTTP 200；4 页；587,364 bytes；UTC `2026-09-24T10:27:35.788682+00:00`。
- SHA-256：`308acf1ce125ef2fccef323b79c7ba7ac388bc780c50ee86e81baf2fe14d5aee`。
- 人工确认：**待确认**；审核人：____；日期：____；修订意见：____。

| 事实 ID / 字段 | 候选关键事实 | 原文位置 / 解析范围 | 限定条件 |
|---|---|---|---|
| S08-F01 / `form_type` | Appendix 3Y | PDF p.1，第 1 页表单标题；`routing_only` | 按原文报告，不作投资评价 |
| S08-F02 / `director` | Murray Hill | PDF p.1，第 1 页 Name of Director；`reference_only` | 按原文报告，不作投资评价 |
| S08-F03 / `date_of_change` | 2026-09-11 | PDF p.1，第 1 页 Part 1 最后一行；`reference_only` | 按原文报告，不作投资评价 |

**不得出现的输出：** 因为 Interest / securities 字样认作项目所有权变更或融资 F06；为非核心表单创建矿业 Project/Asset Unit；把董事权益变动当买入或利好信号。

### S09 · WC8 · POSITIVE METALLURGY TESTWORK FROM BOLT CUTTER CENTRAL

- 股票：`WC8`；公告时间（数据库悉尼本地时间）：`2026-07-07 08:34:39.000000`。
- ASX 公告编号（source documentKey）：`2924-03108404-6A1332742`。
- [ASX PDF](https://asx.api.markitdigital.com/asx-research/1.0/file/2924-03108404-6A1332742) · [固定原文](beta02-acceptance/pdfs/S09.pdf)。
- Document Type：Metallurgy testwork and drilling update；ASX 原始 category：`PROGRESS REPORT`。
- 期望核心事件：F03 / Metallurgical Test Results [reported]；F01 / Drilling Results / Assay Results [reported]；F01 / Drilling Completed [reported]；F08 / Period-end Cash Position [reported]。
- 摘要边界：PDF 第 1 页 Highlights 全部，止于 Figure 1 图片上方横线。
- P01 研究候选：Bolt Cutter Central、Tabba Tabba；不表示实体或关系已批准。
- 下载校验：HTTP 200；25 页；2,198,963 bytes；UTC `2026-09-24T10:27:56.570512+00:00`。
- SHA-256：`6aa640eba76d557ceefc7d8bfa98ed4f570dfe9165affde4dca0bb79a1df4716`。
- 人工确认：**待确认**；审核人：____；日期：____；修订意见：____。

| 事实 ID / 字段 | 候选关键事实 | 原文位置 / 解析范围 | 限定条件 |
|---|---|---|---|
| S09-F01 / `metallurgy_results` | {"average_recovery_pct": 82.5, "average_product_grade_pct_li2o": 5.66, "composites": 3} | PDF p.1，Highlights 第 1 条子项；`summary` | sighter testwork / 三个复合样；不是全矿实际生产回收率 |
| S09-F02 / `process_route` | Whole of Ore Flotation | PDF p.1，Highlights 第 1 条子项；`summary` | 同拟用于 Tabba Tabba 的方法 |
| S09-F03 / `bcdd007_intersections` | [{"width_m": 7.1, "grade_pct": 1.3, "from_m": 20.8}, {"width_m": 4.3, "grade_pct": 1.4, "from_m": 29.9}] | PDF p.1，Highlights / BCDD007；`summary` | est. true width |
| S09-F04 / `bcdd009_intersection` | {"width_m": 5.6, "grade_pct": 1.6, "from_m": 149.9} | PDF p.1，Highlights / BCDD009；`summary` | est. true width |
| S09-F05 / `bcdd018_intersection` | {"width_m": 7.7, "grade_pct": 1.1, "from_m": 7.4} | PDF p.1，Highlights / BCDD018；`summary` | est. true width |
| S09-F06 / `bcrc071_intersection` | {"width_m": 7.0, "grade_pct": 1.1, "from_m": 7.0} | PDF p.1，Highlights / BCRC071；`summary` | est. true width |
| S09-F07 / `bcrc079_intersection` | {"width_m": 5.0, "grade_pct": 1.4, "from_m": 65.0} | PDF p.1，Highlights / BCRC079；`summary` | est. true width |
| S09-F08 / `resource_drilling_status` | RC drilling complete; resource modelling underway; estimation/reporting Q3 | PDF p.1，Highlights 倒数第 2 条；`summary` | 不是已发布资源量 |
| S09-F09 / `cash_balance` | {"value": 43.3, "as_of": "2026-03-31"}；单位：million dollars (source $) | PDF p.1，Highlights 最后 1 条；`summary` | 按原文报告，不作投资评价 |

**不得出现的输出：** 只识别标题 F03 而漏掉 F01 / F08；将 recovery 82.5% 与 grade 5.66% 互换；将原文 excellent / positive 当模型评级；计算与 S05 的现金消耗率。

### S10 · DRE · Yin Rare Earths Mining Lease Application, Gifford Creek

- 股票：`DRE`；公告时间（数据库悉尼本地时间）：`2026-08-31 08:04:54.000000`。
- ASX 公告编号（source documentKey）：`2924-03128764-6A1341100`。
- [ASX PDF](https://asx.api.markitdigital.com/asx-research/1.0/file/2924-03128764-6A1341100) · [固定原文](beta02-acceptance/pdfs/S10.pdf)。
- Document Type：Mining lease application；ASX 原始 category：`PROGRESS REPORT`。
- 期望核心事件：F05 / Mining Lease Application [submitted]；F04 / Study Update / Revision [ongoing]。
- 摘要边界：PDF 第 1 页 HIGHLIGHTS 三条；止于橙色横线。
- P01 研究候选：Yin、Gifford Creek Critical Metals Project；不表示实体或关系已批准。
- 下载校验：HTTP 200；7 页；1,234,231 bytes；UTC `2026-09-24T10:29:47.216438+00:00`。
- SHA-256：`552b9ec7b7af10d9e9df8945a120f2c53e6b2f03cd47c0eb7a68c3995a44124d`。
- 人工确认：**待确认**；审核人：____；日期：____；修订意见：____。

| 事实 ID / 字段 | 候选关键事实 | 原文位置 / 解析范围 | 限定条件 |
|---|---|---|---|
| S10-F01 / `mining_lease_application` | submitted for Yin Rare Earth deposits | PDF p.1，HIGHLIGHTS 第 1 条；`summary` | application；不是 granted |
| S10-F02 / `existing_resource` | {"tonnage_mt": 29.98, "grade_pct_treo": 1.04, "measured_indicated_pct": "approximately 88"} | PDF p.1，HIGHLIGHTS 第 2 条；`summary` | 申请依据的既有资源，不产生本次新 MRE 事件 |
| S10-F03 / `existing_high_grade_resource` | {"tonnage_mt": 11.63, "grade_pct_treo": 1.93, "reported_classification": "approximately 94% Measured & Inferred"} | PDF p.1，HIGHLIGHTS 第 2 条；`summary` | 原文写 Measured & Inferred；不得自动更正成 Indicated |
| S10-F04 / `supporting_infrastructure` | application allows for open pit mine and haul operation infrastructure | PDF p.1，HIGHLIGHTS 第 2 条；`summary` | 申请范围，不是矿山已建成 |
| S10-F05 / `study_and_approval_work` | ongoing at Gifford Creek | PDF p.1，HIGHLIGHTS 第 3 条；`summary` | 按原文报告，不作投资评价 |

**不得出现的输出：** Mining Lease Application 识别成 Mining Lease Grant；既有资源引用误作新资源发布；把正文、背景页的所有元素自动设为 P01 经济暴露。

## 人工审核提交方式

请逐份查看固定 PDF 和上表，按 `Sxx-Fxx` 列出修订。审核无误后，请明确回复 **“阶段 0 确认”**；收到这句话之后才开始 P01 开发。仅当实际审核人确认后，才更新 JSON 中对应 `human_review` 的状态、审核人、时间与意见，并同步本页。不能用系统权限弹窗、Codex 自检、链接成功或 JSON 检查通过替代人工确认。

## 后续回归使用

1. P01：从 entity_candidates 与明确主体/权益事实提出候选；保持临时 target、条件性权益和已批准实体的区别。
2. P02：用固定文件 hash、页数与官方 metadata 校验下载/保存；生产 evidence 数据不得直接由样本夹伪造。
3. P03：对 summary 的预期事件、关键事实及 must_not 做正反断言；reference_only 只有在具体范围被明确批准后才纳入提取要求。
4. API / 前端：以后展示真实解析记录时，检查来源可打开、单位和时间完整、无利好/利空或推导指标混入。内部样本清单不提供普通用户页面。

事实与 P04 / P05 的边界及实施状态见 [实施记录](beta02-p1-p3-implementation.md)。
