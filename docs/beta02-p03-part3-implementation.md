# Beta02 P03 第三部分：Reported Facts 实施说明

## 1. 修改文件

- 数据模型与兼容迁移：`backend/app/models.py`、`backend/app/database.py`、`backend/app/schemas.py`
- 提取链：`p3_parse_service.py`、`p3_fact_extractor.py`、`p3_fact_rules.py`、`p3_value_normalizer.py`、`p3_fact_validation.py`、`p3_fact_review.py`
- API：`backend/app/api/routes/p3.py`、`backend/app/api/routes/admin.py`
- 前端：`frontend/src/api/types.ts`、`StockDetail.tsx`、`P3FactsTable.tsx`
- 测试与离线验收：`backend/tests/test_p03_facts.py`、`P3FactsTable.test.tsx`、`scripts/verify_p03_facts.py`

## 2. P3Fact 模型与迁移

`p3_facts` 现在正式保存 Event、Announcement、EvidenceDocument、Parse Run、Stock、Project/Asset Unit 回链，以及原始值、数值/文本值、原始/标准单位、原始/标准币种、数量类型、期间、as-of/effective 日期、事实状态、项目归属状态、来源区域、PDF 页码、原文摘录、提取器版本、置信度、审核状态和 supersession。

保留旧字段 `value_json`、`unit`、`confidence`、`source_page`、`schema_name`，新写入会同步这些兼容字段。轻量迁移只执行 `ADD COLUMN`、兼容字段回填和新表初始化，不删除或覆盖旧事实。新增 `p3_fact_reviews`，每次 confirm/correct/reject 保存 `before_json`、`after_json`、审核人、备注和时间。实际数据库已验证为 47 个 `p3_facts` 列，审核表存在。

## 3. 字段字典（首批四类，按开发顺序）

1. F04：Study Type、NPV、IRR、Payback、CAPEX、OPEX、AISC、Processing Capacity、Annual Production、Mine Life、Development Completed、DFS Completion、Previous Timing、Timeline Change、FID Target、First Ore Timing、CAPEX Review。
2. F08：Reporting Period、Cash Balance、Operating/Investing/Financing Cash Flow、Exploration/Development/Administration Spend；Current Quarter 数值与 YTD 原值分别保存。
3. F06：Funding Amount、Funding Method、Issue Price、New Securities Issued、SPP Limit、Use of Funds；并提供 Debt Facility、Interest Rate、Government Grant Amount 基础规则。
4. F02：Resource/Reserve Type、Classification、Tonnage、Grade、Commodity、Contained Metal、Reported Increase、Historical Resource Reference。

## 4. 后四类基础字段

5. F01：Hole ID、Interval Length、Grade、Commodity、From Depth、True Width、Drilling Status、Maiden MRE Target；`including` 区间以独立 group 保存。
6. F03：Testwork Type、Recovery、Product Grade、Sample/Composite、Processing Route、Test Programme；metadata 明确标记 testwork scope。
7. F05：Permit Type/ID/Status、Authority、Area、Expiry Date、Works Approval Status；technical support、pending、granted/effective 分开。
8. F07：Transaction Type、Earn-in Amount/Percentage、Maximum/Current Ownership、Manager、Asset Rights；不从 Manager 推导 Operator。

## 5. 标准化规则

- `value_raw`、`unit_raw`、`currency_raw`、`source_excerpt` 永久保留。
- A$/AUD/$A → AUD，US$/USD → USD；仅 `$` 保留原文并设 `currency_normalized=unknown`、进入复核。
- 支持 AUD thousand/million、Mt、ktpa、koz、Moz、g/t、%、Li2O%、m、ha 等；未知单位设为 `unknown`，不猜测。
- Q4/H2/CY 只转换为日期范围并记录转换方法，不伪造成单日。
- Appendix 5B 保留负号；Current Quarter 写入事实值，YTD 保存在独立来源元数据中，绝不混用。

## 6. 状态规则

- reported：公告明确报告；planned/targeted/forecast/estimated：计划、目标、预计或估算。
- applied/pending/technical_support/granted/effective：申请、待批、技术支持、正式授予、生效严格分开。
- committed：firm commitments；received 仅在原文明确到账时使用。
- completed：明确完成；historical_reference：历史资源引用；conditional：earn-in 等条件性安排。

## 7. 重跑和审核

新提取器版本创建新 Parse Run、Event 和 Fact；旧记录不删。普通查询取最新有效 Run，同时以人工确认/修正结果优先覆盖同一事实键。人工修正保留 `original_extraction_json` 和完整审核记录。拒绝只将该结果设为 inactive/rejected，不删除证据。

## 8. API

- `GET /announcements/{announcement_id}/facts`：支持 family、event_id、project_id、asset_unit_id、fact_type、review_status、latest_parse_run_only。
- `GET /p3/facts/{fact_id}`：完整事实、Event、实体和 Evidence 来源。
- `GET /p3/facts/{fact_id}/history`：解析版本、审核动作和 supersession。
- `GET /admin/p3/facts/review-needed`：按股票、公告、Family、字段、状态筛选。
- `POST /admin/p3/facts/{fact_id}/confirm|reject`、`PUT /admin/p3/facts/{fact_id}`。

API 不返回本地文件系统路径。

## 9. 前端

公告主表新增中性“摘要”列，仅由有效 Event/P3Fact 生成；无事实显示“尚未提取事实”。展开区域新增“已提取事实”表，显示 Event、字段、值/单位、状态/期间、项目、PDF 页码原文链接，并支持 Family/字段筛选。`Context` 改为 `Drill Context`，仅 F01 展示；非钻探公告显示“不适用”。旧标题外链、PDF、Evidence 和解析标签保留。

## 10. 固定样例结果

离线脚本按可查询的原子事实计数；一个钻孔区间会拆成 Hole ID、Interval、Grade、From、True Width，因而多于 Stage 0 的复合“关键事实”条数。

| 样本 | 提取数 | 主要结果 |
|---|---:|---|
| S01 CVV | 9 | DFS、Q4 2026、September 2026、Schedule Change、FID、CAPEX Review、计划冶金测试 |
| S02 AGY | 12 | 期间、三类现金流、期末现金、开发/行政支出、12ktpa/DFS |
| S03 AGY | 7 | $3m committed、Placement、$0.036/share、83,333,334 shares、SPP limit、用途 |
| S04 CYL | 19 | Reserve 30%/32% 两来源、Probable 表、tonnage/grade/contained metal、mine life、first ore |
| S05 WC8 | 74 | 各钻孔原子字段、MRE target、DFS target、LCT rights、$37.2m cash |
| S06 GL1 | 9 | NVCP effective、Groundwater technical support、CPS ID、authority、area/expiry、Works pending |
| S07 DYL | 11 | A$5m/51% maximum、phase terms、current interests、Manager（非 Operator） |
| S09 WC8 | 37 | sighter testwork、82.5% recovery、5.66% product grade、route/composites、钻孔和现金 |

合计 180 条原子事实。执行：`python scripts/verify_p03_facts.py`；加 `--details` 可列出复核项。

## 11. 待人工复核

- S03：4 条，主要是正文 fallback 和仅 `$` 的未知币种。
- S04：12 条，包含标题 30% 与摘要 32% 冲突、正文/储量表 fallback。
- S05：1 条 `$37.2M`，币种未明示。
- S06：9 条均来自正文 fallback；尤其 Groundwater 只到 technical support，不能确认 granted。
- S07：8 条详细阶段/当前权益来自正文 fallback。
- S09：1 条 `$43.3M`，币种未明示。
- S01、S02 固定核心事实无待复核项。

## 12. 测试

- 后端全量：`cd backend; .venv-win/Scripts/python.exe -m pytest -q` → 301 passed（一次 Starlette/httpx 弃用警告）。
- 前端：`cd frontend; npm test` → 19 passed。
- 类型检查：`npx tsc -b` → passed。
- 生产构建：`npm run build` → passed，5474 modules transformed。
- 所有固定 PDF 测试离线运行，不访问 ASX 网络。

## 13. P03 明确未计算的 P04 指标

没有计算 Cash Runway、Placement Discount、Resource Growth、Grade Change、Grade × Thickness、NPV/IRR 重算、估值或历史差异；没有利好/利空或投资建议。公告直接披露的 NPV、IRR、增长百分比只能作为 reported fact 原样保存。

## 14. P04 接入方式

P04 以 `active_result=true` 且非 rejected 的 P3Fact 为唯一主要输入，按 Stock/Project/Asset、字段、期间和 as-of 日期选择可比事实，再将输入 fact IDs 写入 P4Feature 的 `input_refs_json`：现金与期间支出计算 Cash Runway；融资金额/发行价与市场价计算 Placement Discount；同口径 Resource/Reserve 历史事实计算 Resource Growth 和 Grade Change；历史比较保持 Resource/Reserve、分类、单位、币种和项目范围一致。所有公式及结果只写 P4Feature，不回写 P3Fact。

## 已知限制

- 当前是确定性英文规则，扫描件/OCR 质量差、复杂跨页表格或全新措辞会进入 review_needed。
- Appendix 5B 已覆盖固定表格结构；其他财务标准表需要按表单版本扩展规则。
- 实体归属只使用已批准 P01 identity 和少量固定钻孔前缀上下文；无法确认时保留 Company/unknown。
- P3Statement 仍保留兼容结构；本阶段目标是正式 P3Fact，不把叙事性判断写入 Statement。
