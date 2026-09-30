# Beta02 P01–P03 最终实施报告

日期：2026-09-30  
数据库：`data/tracker.db`  
交付范围：P01 实体、P02 原始证据、P03 Event/Fact/实体映射/版本关系，以及 Preview-first 历史回填。

## 1. 结论与状态口径

代码、兼容数据库初始化、固定 PDF 离线端到端、正式数据库单样本回填、完整后端/前端测试和生产构建已完成。真实 ASX 网络不是单元测试依赖，本次最终回归没有重新下载实时公告；采用已保存且 Hash 可验证的官方 PDF fixture 和正式 EvidenceDocument。P01 Baseline、P3 review_needed Mapping/Fact/Version Relation 的业务确认仍属于人工审核，不能宣称已由自动测试批准。

状态定义：

- 完成：已实现并有自动或离线集成证据。
- 部分完成：结构和流程可用，但当前正式库没有足够数据或需要业务审核。
- 待人工确认：程序不能替代 P01/P3 审核人的决定。
- 未验证：需要外部实时网络或人工浏览器业务签字，本次未伪造成功。

## 2. 修改文件清单

本最终步骤新增或修改：

- `backend/app/models.py`：BackfillRun、BackfillRunItem。
- `backend/app/database.py`：新表兼容初始化。
- `backend/app/schemas.py`：回填 Preview/Run 请求模型和范围校验。
- `backend/app/services/backfill_service.py`：只读 Preview、token 确认、逐公告执行、幂等和 Retry Failed。
- `backend/app/services/announcements.py`：新公告 Evidence 成功后自动触发 P3。
- `backend/app/services/pipeline.py`：P3 成功、待复核、失败、跳过统计。
- `backend/app/services/config_service.py`：`parse_p3` 和 parser version 默认配置。
- `backend/app/api/routes/admin.py`：回填管理 API。
- `backend/tests/test_p03_final_backfill.py`：最终步骤 6 个后端专项测试。
- `frontend/src/pages/Backfill.tsx`、`Backfill.test.tsx`：管理端回填页及测试。
- `frontend/src/api/types.ts`、`frontend/src/App.tsx`：回填类型、菜单和路由。
- `README.md`、`docs/beta02-p1-p3-implementation.md`、本报告。

以上均为增量修改；未删除或回退已有 P01/P02/P03 文件和历史数据。

## 3. 数据模型和兼容初始化

BackfillRun 保存 status、requested_by、parser/pipeline version、筛选和配置快照、Preview token、总数/成功/跳过/部分/失败计数、下载/文本/解析/Event/Fact/Mapping/待复核计数、错误摘要、retry_of_run_id 和时间。BackfillRunItem 保存 Announcement/Stock/Evidence 外键、状态、当前或失败阶段、input hash、创建计数、错误和时间；同一 Run/Announcement 有唯一约束。

`init_db()` 使用 `create_all(checkfirst)` 创建新表。没有对既有 P3 表做破坏性迁移，也没有重建或删除历史证据。正式库已成功初始化。

## 4. P01 验收状态

| 项目 | 状态 | 说明 |
|---|---|---|
| Stock 和历史身份 | 完成 | 正式库 32 Stock；StockIdentity/当前身份结构已实现。 |
| Project | 完成 | 正式库 9 Project。 |
| Asset Unit | 完成 | 正式库 5 Asset Unit：Yin、Bolt Cutter Central、Hutt、Chewy、Leia。 |
| Commodity Relationship | 完成 | 独立关系模型和来源字段已实现。 |
| 历史 ownership/operator | 部分完成 | 模型/审核流程已实现；正式关系仍取决于来源和人工确认。 |
| 实体审核 / Entity Proposal | 完成 | P3 候选只能进入 P01 审核；批准前不进入普通 Project Tree。 |
| Baseline Version | 待人工确认 | 固定文件和冻结流程存在，但业务 sign-off 不由自动测试代替。 |

## 5. P02 验收状态

| 项目 | 状态 | 说明 |
|---|---|---|
| Announcement 元数据 | 完成 | 正式库 518 条，Stock + ann_id 唯一。 |
| EvidenceDocument / PDF / Raw Text | 完成 | 正式库 10 Evidence；本地原件、文本、Hash、页数、状态结构可查询。 |
| 去重、重试、PipelineRun | 完成 | 同公告不重复、Hash 标记重复、逐 Stock 失败隔离和重试已测试。 |
| 修订公告关系 | 部分完成 | 只生成 pending_review 候选；确认必须人工完成。 |
| Historical Baseline | 完成 | 与新公告共用 EvidenceDocument 和安全 PDF API。 |
| Provider 可替换性 | 完成 | 内部 adapter contract 已实现；外部实时可用性取决于网络。 |
| 实时 ASX 新下载 | 未验证（本轮） | 本轮未访问实时网络；不伪造成功，使用已保存官方 PDF。 |

## 6. P03 验收状态

| 项目 | 状态 | 说明 |
|---|---|---|
| P3ParseRun / Summary-first | 完成 | parser+version+input hash 幂等；Summary/Highlights 优先，缺口才读表格/正文。 |
| F01–F08 / 多 Event | 完成 | 固定样本覆盖八类，泛词和 Appendix 3Y 负例通过。 |
| P3Fact | 完成 | 原始/标准化值、单位、币种、期间、状态、页码、摘录、版本和审核记录。 |
| P3Statement | 部分完成 | 正式模型和 API 基础存在；当前正式库记录为 0，未宣称有 Statement 数据覆盖。 |
| Information Point | 完成 | 原子 Fact 不丢失，逻辑点分组；20–50 是目标而非配额，来源不足明确标记。 |
| 实体映射 / P01 候选 | 完成 | exact/alias/fuzzy/model suggestion 均遵守人工确认边界；fuzzy/model 不自动确认。 |
| Correction/Replacement/Withdrawal | 完成（机制） | proposed 不改变 Current；确认后才 supersede/withdraw；当前正式库无已确认关系。 |
| Current 查询 | 完成 | 默认排除 withdrawn/superseded/rejected，历史查询保留来源。 |
| 管理员历史回填 | 完成 | 显式范围、只读 Preview、执行、逐项状态、重试、取消、版本快照。 |
| 人工业务审核 | 待人工确认 | review_needed 事实、映射、版本候选必须由管理员处理。 |

## 7. 正式数据库记录数量摘要

兼容初始化和 S01 单样本验收后的记录数：

| 表 | 数量 |
|---|---:|
| stocks | 32 |
| projects | 9 |
| asset_units | 5 |
| announcements | 518 |
| evidence_documents | 10 |
| p3_parse_runs | 12 |
| p3_events | 79 |
| p3_facts | 74 |
| p3_statements | 0 |
| entity_mentions | 56 |
| entity_mappings | 63 |
| p3_version_relations | 0 |
| backfill_runs / items | 2 / 2 |

这些数量是当前数据库快照，不代表 518 条历史公告均已解析；系统明确没有自动全量回填。

## 8. 新公告自动流程与失败恢复

新公告进入 `sync_announcements` 后依次保存 Announcement、EvidenceDocument、PDF/Hash、Raw Text，再在 `text_status=extracted` 时创建或复用 P3 Parse Run。解析内部创建 Event、Fact、Information Point、Entity Mention/Mapping、P01 候选和 proposed Version Relation。下载失败保留 Announcement；文本失败保留 PDF；任一 P3 失败不会伪造 Fact。日常 Pipeline 每只 Stock 独立隔离失败。

专项测试使用模拟新 ASX Announcement 验证 P02 完成后 P3 自动被调用；第二次同步同 Announcement 不再下载或解析。实时 ASX 网络本轮未执行，状态为“未验证（外部网络）”。

## 9. 历史回填验收

### 9.1 正式库 S01 Preview 与执行

显式范围仅含 `2924-03136859-6A1344354`：

- Preview：1 条；已有 PDF=1、Raw Text=1；缺失=0；预计下载=0；只读=true。
- Run 1：success；成功 1、失败 0；新建 7 Event、8 Fact、63 Mapping 记录（包含 mention 候选/验证记录）；待复核计数 10。
- 同版本同 Hash 重跑 Run 2：success，Item=skipped；Event/Fact/Mapping 新增均为 0。
- 未选择的 517 条 Announcement 没有被扩大处理。

### 9.2 失败与 Retry Failed

隔离数据库测试以一条有 Raw Text 和一条缺失 Raw Text 的公告执行：批次为 partial，失败 Item 保留 `text_extract` 阶段和原因；补回固定文本后 `retry-failed` 新建带 `retry_of_run_id` 的 Run，仅包含原失败 Announcement，并成功处理。正式库没有为制造失败而写入伪公告。

## 10. 修订、替代和撤回验收

自动规则只能建立 `proposed` 关系，不改变旧对象。后端完整回归覆盖：CVV DFS September 2026 → Q4 2026 经人工 Confirm 后旧 Fact=Superseded、新 Fact=Current；Withdrawal fixture Confirm 后旧 Fact=Withdrawn 且其他 Fact 不受影响；不同季度 Cash Balance 不自动互相替代。历史对象、PDF、Raw Text、页码和摘录不删除。正式库当前 `p3_version_relations=0`，因此不能声称正式数据已有人工作出版本确认。

## 11. 固定样本结果

`scripts/verify_p03_facts.py --check` 使用 10 个本地官方 PDF、逐文件 SHA-256 校验和隔离数据库运行同一 P3 parser，基线无漂移：

| 样本 | Fact | 信息点 | Summary | 表格 | Body | 待复核 | 状态 |
|---|---:|---:|---:|---:|---:|---:|---|
| S01 CVV | 8 | 5 | 5 | 0 | 0 | 1 | 来源不足 |
| S02 AGY | 17 | 17 | 3 | 14 | 0 | 12 | 来源不足 |
| S03 AGY | 7 | 7 | 2 | 0 | 5 | 7 | 来源不足 |
| S04 CYL | 17 | 8 | 6 | 0 | 2 | 5 | 来源不足 |
| S05 WC8 | 74 | 18 | 18 | 0 | 0 | 16 | 来源不足 |
| S06 GL1 | 9 | 6 | 0 | 0 | 6 | 6 | 来源不足 |
| S07 DYL | 11 | 5 | 2 | 0 | 3 | 4 | 来源不足 |
| S08 EL8 | 0 | 0 | 0 | 0 | 0 | 0 | Appendix 3Y 负例 |
| S09 WC8 | 37 | 11 | 11 | 0 | 0 | 7 | 来源不足 |
| S10 DRE | 0 | 0 | 0 | 0 | 0 | 0 | 许可字段未找到 |

所有样本少于 20 个逻辑信息点时都标记 `source_insufficient`，没有填充或编造数量。详细未找到字段、Project/Asset Unit 归属和 reconciliation 位于 `docs/beta02-acceptance/p03-fixed-sample-baseline-v2.json`。

## 12. 前端交付

- `/admin/backfill`：筛选、范围警告、Preview、执行、运行统计、Item 失败阶段、取消和仅重试失败项。
- 普通 StockDetail：保留公告外链、本地 PDF、Evidence/Parse 状态、客观摘要、多个 Event、Fact、Information Point、实体映射和版本状态。
- Drill Context 只用于 F01 钻孔上下文；非钻探公告不再以 `No context` 暗示无价值。
- pending/review_needed 实体不进入正式 Project Tree；普通页只显示已批准实体。

## 13. 测试命令与结果

```powershell
# backend
.\backend\.venv-win\Scripts\python.exe -m pytest backend/tests -q
# 346 passed, 1 third-party deprecation warning

# fixed official PDF acceptance
.\backend\.venv-win\Scripts\python.exe scripts\verify_p03_facts.py --check
# Baseline check passed: no measured drift

# frontend
cd frontend
npm test -- --run
# 13 files, 31 tests passed

npm run build
# tsc + Vite success; 5479 modules transformed
```

前端 esbuild 在默认受限沙箱中会触发 `spawn EPERM`；按已有授权在允许启动子进程的同一工作区执行后测试和构建均成功。这是执行环境限制，不是应用测试失败。

## 14. 幂等和数据保护

- Announcement：Stock+ann_id 唯一。
- Evidence：source_type+source_id 唯一；PDF Hash 重复有 `duplicate_of_id`，相同原件不重复下载。
- Parse Run：Evidence+parser name+version+input hash 复用；新版本/Hash 才新增并保留旧 Run。
- Event/Fact/Mapping：同 Parse Run 只创建一次；人工已确认 Mapping 不被自动建议覆盖。
- Backfill：Preview token 绑定标准化筛选和 candidate IDs；重复成功项 skipped；失败按 Item 重试。
- Version Relation：proposed 不改变 Current；确认后才改变旧对象有效状态，且不删除历史。

## 15. 未完成、限制和人工事项

1. P01 Baseline 与所有 P01/P3 pending/review_needed 项仍待授权业务审核人签字。
2. 正式库 P3Statement 当前为 0；模型存在，但本批固定样本没有形成正式 Statement 数据覆盖。
3. 518 条历史公告没有、也不应自动全量解析；当前只有管理员明确选取的 S01 做了正式回填验收。
4. 另外 4 个 Preview 样本缺正式 Evidence PDF/Raw Text；因本次 `download_missing_pdf=false` 没有下载或解析。
5. 本轮未访问实时 ASX 网络；新公告网络采集只由 mock 自动测试和此前已保存真实 Evidence 验证，不能宣称本轮实时网络成功。
6. 自动识别的版本关系、fuzzy/model entity suggestion 均只到待审核，不会自动改变正式实体或 Current 状态。
7. 当前同步 Run API 逐项提交，数据库可观察进度；非常大的管理员范围会让该 HTTP 请求持续较久，应继续保持小批次，后续可接任务队列但不能放宽 Preview/范围保护。
8. 最终只读一致性审计为 `14 pass / 1 warning / 0 fail`。warning 是旧 Parse Run（4–10）中 15 条历史 Fact 的 Project/Asset Unit 归属不一致；最新 Run 12 不在违规清单。依据“历史不可删除、人工结果不可覆盖”的规则，本次没有改写旧 Fact，管理端应在历史视图复核，普通 current/latest 查询不应把这些旧版本当当前归属。

## 16. P04 前置条件和只读输入契约

P04 可从普通 current-only Fact API 或管理端历史查询读取：`fact_type`、`fact_family`、`value_raw`、`value_numeric`、`value_text`、`unit_raw/unit_normalized`、`currency_raw/currency_normalized`、`period_start/end`、`as_of_date/effective_date`、`status`、Stock/Project/Asset Unit、EvidenceDocument、source page/excerpt、extractor version、review status 和 validity status。

允许的后续派生：Cash Balance + Burn → Cash Runway；Issue Price + Previous Close → Placement Discount；Current/Previous Resource → Resource Growth；Current/Previous Grade → Grade Change；当前/前序 DFS Timing → Schedule Change。

P04 不得反向修改 P3 的原始值、单位、币种、期间、状态、实体原文、Evidence、页码、摘录、提取器版本、人工审核记录或 Version Relation。只有经过来源和有效状态筛选的 P3Fact 才能作为 P04 主要输入，P4 结果必须独立保存。
