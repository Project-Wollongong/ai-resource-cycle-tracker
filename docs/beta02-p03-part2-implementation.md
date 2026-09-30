# Beta02 P03 第二部分：公告分类规则和八类事件

## 实现范围

本增量在 P03 第一部分的 `P3ParseRun` / `P3Event` 上实现 F01–F08。旧 `Announcement.ann_type`、`type_score` 和 `ai_metrics` 保留兼容，但不作为 P03 正式分类结果。

规则和测试按产品顺序组织：F04 → F08 → F06 → F02 → F01 → F03 → F05 → F07。

## 分类链

1. ASX Header Type / Sub-type / Standard Form 路由文档类别；
2. 标题具体短语只形成候选；
3. Summary / Highlights / Key Results / Executive Summary 确认业务 Event；
4. Appendix 5B / 4C 额外读取标准表单锚点页；
5. 没有摘要时仅以 `body_fallback` 建立待复核结果；
6. 保存 Family、Event Type、业务状态、页码、原文、分类原因、parser version；
7. 修订词作为 modifier，并以 pending-review 关系候选连接 `AnnouncementVersionRelation`；
8. 人工确认、修正、拒绝写入不可变审核记录；新 parse run 不覆盖已人工处理的有效结果。

泛词 `update/results/project/positive/significant/strong/successful/progress/activity/announcement/report/review/change` 不单独触发 Family。Appendix 3Y 路由到 Ownership / Governance，不自动产生 F06、F07、项目 ownership 或 P01 更新。

## 数据模型

`Announcement` 新增官方 Header/Sub-type/standard form 字段。`P3Event` 新增 `primary_family`、`secondary_families_json`、分类状态/来源/置信度/理由、修订标签、审核字段、原始自动分类和 `active_result`。旧 `event_family` 同步保留。

新增 `P3EventClassificationReview`：保存 confirm/correct/reject 的 before/after JSON、reviewer、note 和时间。`P3Fact` / `P3Statement` 预留 nullable `p3_event_id`、`parse_run_id`、`asset_unit_id`（Statement 同时补 source excerpt）。轻量 SQLite 初始化只做加列/建表/回填，不删除旧 Announcement、EvidenceDocument、ParseRun 或 Event。

## API

- `GET /api/announcements/{announcement_id}/events`
- `GET /api/announcements/{announcement_id}/classification-summary`
- `GET /api/admin/p3/classification-review`
- `GET /api/admin/p3/events/{event_id}/reviews`
- `POST /api/admin/p3/events/{event_id}/confirm`
- `POST /api/admin/p3/events/{event_id}/reject`
- `PUT /api/admin/p3/events/{event_id}`

## 固定样本结果

- S01：F04 Project Schedule / Timeline Update + Project Delay；Revised；DFS 保持 planned，并识别计划冶金测试。
- S02：F08 Quarterly / Cash Position / Cash Flow（含 operating/investing/financing）及 F04/F03 更新；标准表单页保留。
- S03：F06 Placement=firm commitments、SPP=planned；不标 funds received。
- S04：F02 Ore Reserve Update + F04 Construction/Timeline；不把 June Resource 引用变成新 MRE。
- S05：F01 Drill Results，并允许 F04、F07、F08 独立事件；未来 maiden MRE 不生成 F02。
- S06：F05 clearing permit=granted、groundwater licence=technical support、works/environmental approval=pending；因正文 fallback 待复核。
- S07：F07 Farm-in / Earn-in / Joint Venture；Earn-in=conditional；Manager 不转成 Operator。
- S08：Appendix 3Y 非核心路由，不生成 F01–F08。
- S09：F03 Metallurgical Test Results + Recovery / Product Grade、F01 drilling、F08 cash；试验回收率不转成经营回收率。

## 待人工复核

- 没有明确 Summary/Highlights、使用正文 fallback 的样本（当前固定样本 S06）；
- 标题候选与摘要 Family 冲突的结果；
- S03 从正文补充得到的 firm-commitment / issue-price 状态；
- 自动创建但尚未确认的 revised/correction/replacement/withdrawal predecessor 关系；
- 未能唯一映射到 P01 Project / Asset Unit 的事件。

## 测试

- 后端：`cd backend; .\\.venv-win\\Scripts\\python.exe -m pytest -q` → 283 passed；
- 前端：`cd frontend; npm test -- --run` → 6 files / 16 tests passed；
- 类型：`cd frontend; npx tsc -b` → passed；
- 构建：`cd frontend; npm run build` → passed。

测试完全使用本地 fixture，不依赖实时 ASX 网络。

## P03 第三部分接口

第三部分应通过已预留的 `p3_event_id` 在每个有效 `P3Event` 下写入 `P3Fact` / `P3Statement`，按 Family 使用不同 schema：F04 计划/里程碑/CAPEX，F08 期间与现金流列口径，F06 commitment/settlement/receipt，F02 Resource/Reserve 分类，F01 program/status/intersection，F03 test scope/recovery/product grade，F05 permit type/status/authority，F07 binding state/consideration/current-vs-earn-in ownership。每条记录继续保留 `evidence_document_id`、页码、excerpt、parse run/extractor version；不计算 P04 衍生指标，不输出 P05 投资判断。

## 已知限制

- 当前是 deterministic Pilot；复杂版式、扫描件/OCR 和跨页表格可能进入复核。
- Appendix 5B 目前完成事件分类与页级定位，尚未结构化 Current Quarter 与 YTD 数值列。
- 标题与正文增长百分比等多来源数值留待 P3Fact 双来源保存。
- 实体匹配仍以 P01 current name/alias 的确定性匹配为主，不自动创建新永久实体。
