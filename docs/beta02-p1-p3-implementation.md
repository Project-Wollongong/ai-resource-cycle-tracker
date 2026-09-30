# Beta02 P01–P03 实施记录

本轮范围：阶段 0（实施记录与固定验收样本）。不开发产品页面、P04 衍生计算或 P05 投资判断。

用户最新推进条件：先提交 [阶段 0 单表审核清单](beta02-stage0-review-table.md)，等待用户审核并明确回复 **“阶段 0 确认”** 后，才开始 P01 开发。系统权限弹窗、技术检查通过、单独某条事实的修订意见都不等于该确认。P01、P02、P03 当前均保持 **未开始**。

## 需求基线

- [P01 v0.6](../卧龙岗项目_Beta02_P01_Product_Development_Requirement_中文版_Draft_v0.6.md)：实体身份、关系历史、候选结构与人工确认。
- [P02 v0.2 文件](../卧龙岗项目_Beta02_P02_Product_Development_Requirement_中文版_Draft_v0.2.md)：原始证据采集与保存。文件正文仍标 v0.1，按文件实际内容实施。
- [P03 v0.1](../卧龙岗项目_Beta02_P03_PRD_中文版_Draft_v0.1.md)：官方文档类型优先、Summary / Highlights-first、多事件、Reported Facts。

## 状态定义与阶段台账

状态只使用：**未开始、开发中、已完成、已验证**。

- 未开始：尚未实施。
- 开发中：正在实施，或仍存在必须完成的验收项。
- 已完成：实现与交付物齐备，但尚未通过全部验收。
- 已验证：阶段测试及业务验收全部通过；涉及人工确认的内容已由实际审核人确认。

| 阶段 | 状态 | 交付与验收门槛 |
|---|---|---|
| 0 实施记录与固定样本 | 开发中 | 固定 PDF、预期事实、定位、F01–F08 覆盖、链接验证、人工签核 |
| P01 实体骨架 | 未开始 | Stock / Project / Asset Unit / Commodity，身份连续、历史关系、候选与人工确认、可查询 |
| P02 数据采集 | 未开始 | 日常 pipeline 真实下载、原始 PDF 与文本留存、来源身份、版本保留、可重跑 |
| P03 解析与事实结构化 | 未开始 | 正式接入 pipeline、官方类型与事件分离、摘要事实、实体映射、事实历史、API / 前端可查看 |
| P01–P03 集成验收 | 未开始 | 真实数据贯通；后端测试、前端测试、前端 build 全部通过 |

P04、P05 不属于本轮实施阶段，不得因既有表或旧功能存在而提前扩展。

## 现状检查（2026-09-24）

只读检查 `data/tracker.db`：32 只股票（29 active）、518 条公告、16,834 条股价、3,343 条商品 / 基准序列记录。Project、StockProject、EvidenceDocument、P3Fact、P3Statement、P4Feature 均为 0 条。

`AI_ANALYZER=noop`，`AI_ANALYZER_ALLOW_PAID_CALLS=false`。旧公告流程按标题分类评分，文档获取依赖 analyzer 开关；已有公告直接跳过，尚无独立证据下载和 P03 持久化处理链。`DFS Revised Completion Timing` 的旧分类为 STUDY / 80，不能用来判断正文含义。

保留数据库、旧功能和用户未提交修改；本阶段不调用应用启动、迁移、日常 pipeline 或消息推送。候选样本存放在开发文档目录，不能作为真实业务数据导入或显示给普通用户。

## 固定样本与审核规则

样本见 [验收样本说明](beta02-acceptance-samples.md) 与 `beta02-acceptance/samples.json`。固定原文副本、来源 ID、PDF SHA-256 和页码共同确定答题标准，不能仅依靠在线链接或标题。

审核分两层：

1. Codex 对照原文核对事实、单位、时间、主体与页码，并保留可复核摘录；这是机器辅助核对。
2. 产品负责人逐份审核后填写 `human_review.status=confirmed`、真实审核人和审核时间；机器不得代填人工签核。审核前属于候选答案，不得声称“人工确认已通过”。

任何事实修订都应记录原因和审核人；源 PDF 内容改变时保留旧版本并另建样本版本，禁止静默替换固定答案。P01 实体候选不等于批准后的实体基线。

## 事实与后续计算的边界

| 内容 | P03 可以保存的来源事实 | 留给后续层 |
|---|---|---|
| 工期 | 公司报告的原计划、新计划、延期原因与限定条件 | P04 计算延迟时长；P05 判断影响 |
| 现金流 | 对应期间、币种、现金余额、报告的各项现金流 | P04 Cash Burn / Runway / 环比计算 |
| 融资 | 拟募集与已募集金额分别保存、发行价、证券数量、条件 | P04 折价率、稀释率、融资后 runway |
| 资源 / 储量 | 吨位、品位、金属量、分类、公司明确报告的变动百分比 | P04 自行计算增长与分类转换；P05 质量判断 |
| 钻探 | 原文的厚度、品位、深度、including 区间及商品 | P04 品位×厚度、历史比较；P05 重要性判断 |
| 冶金 | 试验条件、样品、回收率、产品品位 | P04 跨期比较；P05 是否优秀或降低风险 |
| 许可 / 交易 | 申请与授予、签约与完成、约束条件分别保存 | P05 利好 / 利空、买卖判断 |

公司明确报告的百分比是 Reported Fact；系统自行重算的相同比例才是 P04 计算。公司使用的 “positive / strong / successful” 不得转成系统结论。

## 解析验收约束

- 官方 metadata / Appendix 类型决定 Document Type；标题关键词只做路由，不能充当已发生事件或关键事实。
- 一份文件允许多个 F01–F08 事件；Administrative / Director Interest 为非核心路由，不算第九个事件家族。
- 只在明确 Summary / Highlights 等区域内要求第一版提取。无摘要样本保留为边界案例，记录待定的个案方案，不擅自设计全文 fallback。
- 关键事实必须保留主体、时间、状态、单位、限定条件及原文定位；不可把计划当完成、申请当授予、收入当现金、储量当资源。
- 正常更新保留旧事实；更正 / 撤回保留原披露并表达关系。标题 “Revised Completion Timing” 不能单凭 revised 认定为对旧公告的更正。
- 验收至少检查事件漏检、错误新增事件、数值/单位/期间错误、越界解析和虚构实体；“程序未报错”不等于通过。

## 后续实施顺序

每阶段先运行对应阶段测试，再进入下一阶段。P01 的 baseline 必须经过真实人工确认；P02、P03 必须从日常 pipeline 产生真实记录，并可通过 API 或前端查看，不能以建表、手工塞样例或仅有测试通过代替交付。

阶段 0 的离线样本检查与在线链接检查独立记录；网络检查成功不代表人工签核完成。全部 P01–P03 完成后才进行后端测试、前端测试及前端 build 的集成验收。

## 阶段 0 验收记录（2026-09-24）

已交付：10 份公告固定 PDF（约 12.6 MB）、68 项关键事实候选、可阅读审核文档、JSON 回归输入及独立检查脚本。每份均记录股票、标题、官方 source ID、URL、期望事件、关键事实、物理页码/区域、原文摘录、原始 ASX metadata、下载时间及 SHA-256。

| 检查 | 结果 | 证据 / 限制 |
|---|---|---|
| 固定文件签名、SHA-256、字节数和页数 | 10/10 通过 | 固定文件未被在线复查覆盖 |
| 事实原文定位 | 68/68 通过 | 检查引用摘录确实在指定页；不能代替对全部数值语义的人工审核 |
| 目视核对 | 已完成机器辅助核对 | 10 份首页；另含 S02 PDF 11、12、13 页，核对表格列/单位；不是人工签核 |
| F01–F08 覆盖 | 8/8 通过 | 默认摘要事件覆盖；另有 Appendix 5B 与 Appendix 3Y 场景 |
| 在线 ASX 链接 | 10/10 HTTP 200、可解析 PDF | [在线复查记录](beta02-acceptance/link-check-2026-09-24.json) |
| 在线与固定源文本比较 | 10/10 逐页标准化文本一致 | 本次重新下载的二进制 hash 均不同；未查明原因，不能宣称字节或视觉完全相同。保留固定副本，不能据此自动判定业务修订 |
| 人工签核门槛 | 正确阻止通过 | 10 份 `pending`；Python 进程 `--require-human` 返回 2，非机器解析错误 |
| 前端页面 / build | 本阶段不适用 | 未改产品前端；全量后端/前端测试及 build 留给 P01–P03 集成验收 |

离线技术结果见 [离线验收记录](beta02-acceptance/offline-final-2026-09-24.json)。阶段 0 保持 **开发中（技术交付完成、等待真实人工确认）**；P01–P03 均未开始。不得标记为已验证。

可从仓库根目录复跑（Windows PowerShell）：

```powershell
# 离线：只检查固定样本，不读取业务数据库，不访问网络
backend/.venv-win/Scripts/python.exe scripts/verify_beta02_acceptance.py

# 在线：验证链接；不覆盖固定 PDF。可通过 --report 指定一个尚不存在的报告文件
backend/.venv-win/Scripts/python.exe scripts/verify_beta02_acceptance.py --online

# 业务验收：人工未签核时返回 2；技术失败返回 1；全部通过返回 0
backend/.venv-win/Scripts/python.exe scripts/verify_beta02_acceptance.py --require-human
```

脚本依赖现有后端环境的 `pypdf`；在线检查另外使用 `httpx`。本阶段 PDF 渲染仅用于建立答题标准，未引入应用依赖或生产解析逻辑。

## P01 当前进度（额度重置后复核）
本次复核确认 P01 第一部分处于 **开发中**，尚未标记为已完成或已验证。

| 项目 | 状态 | 证据 / 待办 |
|---|---|---|
| Stock 长期身份字段与 `stock_identities` 历史表 | 开发中 | 已实现并迁移现有 SQLite；待继续完成集成验收 |
| 旧代码/旧名称解析与冲突保护 | 开发中 | 后端单元测试与 API 测试 6/6 通过 |
| Stock 详情页身份展示 | 开发中 | 已接入类型与展示；待前端运行时验收 |
| P01 | 开发中 | 不得标记为已完成；P02/P03 仍未开始 |

数据库迁移为加法迁移：现有 32 个 Stock 保留，新增 64 条当前身份基线；未删除旧数据。前端 `tsc -b` 通过，Vitest/Vite 当前被 Windows `esbuild spawn EPERM` 阻断，需在可启动 esbuild 的环境复验。

## P01 第二部分进度（Project / Asset Unit / Commodity）
当前仍为 **开发中**，未标记完成：

- 新增 Project identity、Project relationship history、Asset Unit（含父子层级与身份历史）和 CommodityRelationship 实体。
- 新增 `/api/projects` 列表、创建和详情查询，详情包含 Asset Unit。
- 旧 Project、StockProject、Evidence 关系保持兼容；未删除旧数据。
- P01 仍需继续补齐人工初始化样本以及前端 Project/Asset 展示验收。
- 开发验证不启动额外服务；前端沿用既有 `5173`，后端沿用既有 `8000` 约定，避免端口不一致。

## P01 收尾复核（前端与人工样本）
已完成候选基线文件：`beta02-acceptance/p01-entity-baseline-candidate.json` 与对应 Markdown 表。当前 10 条公告样本仍为 `pending_human_review`，未伪造审核人或审核时间。

StockDetail 已增加 Project / Asset Unit 区域，并通过 `/api/stocks/{code}/projects` 读取真实关系。前端 TypeScript 检查通过；Vitest/Vite 运行时仍受 Windows `esbuild spawn EPERM` 阻断，因此前端展示尚未标记为“已验证”。

## P01 权威数据约束
P01 实体初始化只接受官方 ASX PDF 中可定位的名称、关系和页码。候选登记见 `beta02-acceptance/p01-authority-register.json`；数据库审计见 `beta02-acceptance/p01-authority-audit.json`。在人工确认前，候选不会写入 Project / Asset Unit / CommodityRelationship 权威表。当前数据库仍为 0 个 Project、Asset Unit、CommodityRelationship 和 ProjectRelationship，避免把推断数据当成真实业务数据。

## Project / Asset Unit 身份历史 API 复核
已补齐并测试：Project 与 Asset Unit 身份历史的列表、新增、修改和受限删除 API。当前身份和非 `manual` 来源记录不可删除；历史别名删除不会影响已确认来源记录。后端完整测试已达到 235 passed，前端 TypeScript 检查通过。

## P01 第一部分收口：Stock 长期身份
Stock 长期身份第一部分已完成开发并验证：现有 32 个 Stock 均有当前 ticker 与 company name 身份基线，共 64 条 `stock_identities` 记录；旧代码/旧名称解析、冲突保护、API 和 StockDetail 展示已接入。相关后端测试 8/8 通过，前端 TypeScript 检查通过。

由于当前环境的 Vite/Vitest 仍被 `esbuild spawn EPERM` 阻断，前端运行时验收保持待验证；这不影响 Stock 身份数据已写入和 API 验证结果。

## Commodity Relationship API 复核
已完成 Project 与 Asset Unit 商品关系的新增、查询、修改、删除和 `as_of` 历史区间查询 API。相同目标、相同商品的时间区间禁止重叠；来源不是 `manual` 的记录禁止删除。现有来源候选记录保留，新增日期字段为空表示未声明生效区间。

## Ownership / Operator 管理复核
已完成 Project ownership/operator 历史关系 API：列表、`as_of` 查询、新增、修改、受限删除和区间重叠校验；StockDetail 项目区域增加当前 Operator 展示。来源不是 `manual` 的关系记录不可删除。后端完整测试 237 passed，前端 TypeScript 检查通过。

## Asset Unit Materiality Gate 复核
已建立 Asset Unit Proposal 闸门：临时 Prospect / Target / Zone 名称只能进入 `pending` 提案；正式 Asset Unit 创建接口现在要求已批准提案。批准时保存 rationale、来源页码、原文摘录并生成身份记录；拒绝或重复审核会被阻止。现有来源候选资产保留为 `source_candidate`，不自动视为已批准实体。后端完整测试 238 passed。

## Project / Asset Unit 前端验收开发
已新增独立 Project 详情页 `/projects/:projectKey`，展示项目身份、地区、Commodity、Ownership / Operator 历史和 Asset Unit；StockDetail 的项目名称可进入该页面。前端 TypeScript 检查通过，后端完整测试 238 passed。Vite/Vitest 运行时仍需在可启动 esbuild 的 Windows 环境复验。

## P01 后端收口复核
Project 详情 API 现在统一返回身份历史、Commodity 关系、Ownership / Operator 历史、Asset Unit 和 Materiality Proposal 状态；Asset Unit 详情也返回身份与 Commodity 关系。P01 后端模型、迁移、API 与回归测试已完成，前端运行时验收仍单独待处理。

## P01 最终验收复核
固定 ASX PDF 候选已完成逐名文本核验，记录见 `beta02-acceptance/p01-source-verification.json`。数据库当前已导入 9 个 Project、5 个 Asset Unit、13 条 CommodityRelationship 和 9 条 StockProject 来源候选；均保留 `source_candidate`，未伪造人工确认。Commodity / Ownership / Operator API 已通过后端回归。前端 `npm run build` 仍被当前 Windows 环境 `esbuild spawn EPERM` 阻断。

## P01 Baseline V1 冻结记录
已建立 `beta02-acceptance/p01-baseline-v1.json`。固定来源中明确的持股/运营方事实已写入 `project_relationships`，当前包括：Rincon 77.5% JV interest（“earning up to 90%”保留为条件事实）以及 Nova Joint Venture 公告中 RMR 为 current manager 的来源记录。每条关系保留 ASX 公告编号、页码和原文摘录。Baseline 状态为 `source_backed_frozen_pending_human_signoff`，不能把它描述为已完成人工签核。

## P01 第三部分：Proposed Entity Dataset 与 Baseline 审核
已建立 `p01_entity_proposals` proposed dataset。资料可通过管理 API 人工录入或按项目名、Asset Unit 名称、source_ref 搜索；任何 proposed 记录不会自动写入 Project / Asset Unit 正式事实。管理端新增“实体审核”页面，支持 Approve、Reject、Correct、Merge、Split、Rename、Project/Asset Unit 层级调整、Commodity、Ownership、Operator 调整，并记录审核人、审核时间、修改历史。只有 Approve 才创建正式实体和关系。后端完整测试 239 passed，前端 TypeScript 检查通过；Vite 运行时仍受 esbuild EPERM 阻断。

## P01 资料搜索与人工录入复核
已补充只读 ASX 在线来源搜索 `GET /api/admin/entity-source-search/online?code=...`，并保留 ASX 被阻断时的 503 可解释错误；在线结果不会自动写入 Proposed 或正式实体。管理端页面支持本地来源搜索、Proposed 审核和完整人工动作。后端测试 240 passed，前端 TypeScript 通过；Vite 浏览器运行时仍待解除 esbuild EPERM 后验收。

## P01 资料搜索与前端运行时复核（2026-09-26）

- 在线 ASX 检索接口已完成并通过模拟源回归测试：`GET /api/admin/entity-source-search/online` 只返回候选来源，不创建 Proposed Entity，也不写入 Project / Asset Unit。
- 真实网络验证结果：ASX API 返回 `SourceBlockedError`，Windows 错误为 `WinError 10061`（连接被目标主机拒绝）。接口按设计返回 HTTP 503，原因会透传给管理端；当前环境未获得可用 ASX 网络连接，因此不能声称已验证在线结果内容。
- 前端运行时复核结果：`npm run dev -- --host 127.0.0.1 --port 5173` 与 `npm run build` 均在 Vite 加载配置时被 `esbuild` 的 `spawn EPERM` 阻断。原生 `@esbuild/win32-x64/esbuild.exe --version` 可执行，但 Node 子进程启动仍被 Windows 环境拒绝；端口约定仍保持前端 5173、后端 8000。
- 验证结果：后端 P01 相关测试 3/3 通过；全后端测试此前 240/240 通过；前端 `tsc -b` 通过。浏览器页面和 Vite build 仍待解除该环境阻断后验收。
- 状态：P01 第三部分继续保持“开发中/待运行时验收”；`p01-baseline-v1.json` 继续保持 `source_backed_frozen_pending_human_signoff`。联网检索结果必须由人工录入 Proposed Entity 后才能进入审核流程。

## 阻断解除复核（2026-09-27）

- ASX 官方 API 已恢复实测连接。使用项目 `AsxJsonAnnouncementSource` 请求 `AGY`，成功返回 3 条公告（含公告编号、标题和 PDF URL）；结果仍只进入只读搜索响应，不会自动写入实体事实。
- Windows `esbuild spawn EPERM` 的原因是受限执行环境拒绝启动 esbuild service 子进程；原生二进制本身可执行。使用提升权限运行 Node/Vite 后，`npm run build` 成功，Vite 5173 开发服务器成功启动并返回 HTTP 200。
- 当前浏览器运行时阻断已解除（需在同等允许启动子进程的环境运行）；前端端口仍为 5173，后端端口仍为 8000。

## P02 第一部分：可追溯原始证据（2026-09-27）

状态：开发完成，已验证。

- `EvidenceDocument` 增加独立的下载、文本提取、证据状态、Hash、文件大小、内容类型、抓取时间、重试和重复文件字段；旧的 `raw_storage_path`、`raw_text_path`、`content_hash` 保留兼容。
- `Announcement.evidence_document_id` 关联主证据。旧公告不丢失，未抓取的旧记录保持 `metadata_only/pending`。
- 本地目录固定为 `data/evidence/asx/{TICKER}/{ANNOUNCEMENT_ID}/`，包含 `original.pdf`、`raw_text.txt`、`metadata.json`。
- 新公告进入 pipeline 后先保留 Announcement，再尝试证据下载；失败只更新 EvidenceDocument 失败状态，不回滚公告。PDF 用临时文件、PDF 文件头、非空检查和 SHA-256 验证后原子写入；同一公告重跑不会重复下载，Hash 相同的其他证据会记录 `duplicate_of_id`。
- Raw Text 使用 pypdf 逐页提取，不做总结、情绪解释或 P3 Fact 生成；扫描件/无文本 PDF 保留原始 PDF，并标记 `text_status=failed`。
- API：`GET /api/announcements/{announcement_id}/evidence`、`GET /api/announcements/evidence/{id}/original`、`GET /api/announcements/evidence/{id}/raw-text`、`POST /api/announcements/{announcement_id}/evidence/fetch`、`POST /api/announcements/evidence/{id}/retry`。
- StockDetail 公告列表增加 Evidence 状态、本地 PDF、重试按钮和展开详情；原外部 ASX 标题链接保留。

CVV 真实公告验收：

- 公告：`2924-03136859-6A1344354` / `PS DFS Revised Completion Timing`
- 真实 ASX API 获取成功；数据库 Announcement id=473，EvidenceDocument id=1。
- `download_status=downloaded`，`text_status=extracted`，`evidence_status=text_ready`。
- 页数：4；SHA-256：`609806c85215a94a0af55426c584852798ea26f759b609c67a70a7e3b42b50c5`。
- 本地 PDF API 返回 HTTP 200 / `application/pdf`；Raw Text API 返回 HTTP 200，提取文本 9944 字符。
- 当前数据库 EvidenceDocument：10 条；`metadata_only` 9 条，`text_ready` 1 条；`pending` 下载 9 条，`extracted` 文本 1 条。

验证：后端 244 passed；前端 Vitest 14 passed；前端生产 build 成功。

P03 应通过 EvidenceDocument 的 `local_original_path` 读取主 PDF，通过 `local_raw_text_path` 读取 Raw Text；解析失败时必须保留并展示原始 PDF 和失败状态，不能回退到外部 URL作为唯一证据。

## P02 第二部分：采集可靠性、版本与历史 Baseline（2026-09-27）

状态：开发完成，已验证。

- 新增 `PipelineRunItem`，并扩展 `PipelineRun`：pipeline_type、provider、started_at、完成/跳过/失败计数、retry_of_run_id、配置快照和错误摘要。公告同步为每只股票写入独立运行项；单项失败保留并将整批标为 partial。
- 新增 `AnnouncementVersionRelation`。标题包含 Revised/Revision/Correction/Replacement/Withdrawal/Amended 等词时，只创建低置信度 `pending_review` 候选；单独的 Update 不会自动建立关系。新公告和新 EvidenceDocument 始终独立保存。
- 新增 Historical Baseline 导入：`POST /api/admin/evidence/historical-baseline`。导入 PDF 与新公告使用相同 EvidenceDocument、本地 PDF、Raw Text、Hash、页数和 metadata.json 结构，并标记 `historical_baseline=true`、`review_status`。
- 新增可配置采集入口：`GET/PUT /api/admin/ingestion-config`。默认值包含价格 daily/365 天/30 天回补、公告 daily/每次 20 条/下载 PDF/提取文本/3 次重试/30 秒超时、商品 daily/365 天/30 天回补。公告最大条数、Provider、PDF 下载和文本提取开关已在下一次 pipeline 中生效；密钥不返回。
- 新增统一 Provider contracts：`backend/app/datasources/adapters.py`，P03 继续只依赖内部 Announcement、EvidenceDocument、PriceBar、CommodityBar 和本地证据路径。
- 新增管理 API：`/api/admin/pipeline-runs`、`/items`、`retry`、`retry-failed`、版本关系创建/审核；新增 `/api/announcements/{announcement_id}/version-relations` 与 `/api/announcements/evidence?historical_baseline=true`。
- 新增前端 `/data-runs` 管理页，展示运行状态、Provider、成功/跳过/失败计数、配置快照、失败摘要和重跑入口；普通公告页保留原有证据状态和外部链接。

验证：后端 247 passed；前端 Vitest 14 passed；前端生产构建成功。当前版本关系自动候选仍需管理员人工确认，历史 Baseline 的来源日期和 Project/Asset Unit 关联在来源不完整时保持待确认。

P03 应读取统一 EvidenceDocument 的 `local_original_path` 和 `local_raw_text_path`，并通过 `historical_baseline` 区分历史补录；不应读取 Provider 原始 payload 或直接依赖外部 URL。

## P03 第一部分：市场数据统一与公告解析骨架（2026-09-27）

状态：开发完成，已验证。

- 新增 `InstrumentMapping` 与 `MarketDataPoint`，并保留现有 PriceBar/CommodityBar 兼容；`market_data_standard.py` 统一 instrument_code、instrument_type、trading_date、OHLCV、currency、source、source_symbol、timezone、is_adjusted、quality_status 和 quality_flags。缺失值、负值和异常值只标记 `review_needed`，不静默修正；本阶段不生成 MA、RSI、收益率、Runway、Signal 或投资判断。
- 新增 `P3ParseRun` 与 `P3Event`。现有 P3Fact/P3Statement 保留为 Event 后续 0..N 事实/陈述的承载表，本阶段不伪造事实内容。
- 新增本地解析服务：`p3_section_detector.py`、`p3_event_extractor.py`、`p3_parse_service.py`。解析只读取 EvidenceDocument 的本地 PDF 或 Raw Text，不读取外部 ASX URL。优先 Summary/Executive Summary/Highlights/Key Results；找不到时使用 `body_fallback` 并标记 `review_needed`；无本地文本则 failed/no_text。
- 解析版本按 parser_name、parser_version 和 input_hash 幂等；同版本同输入跳过重复 Run；Parser 版本或输入变化创建新 Run，旧成功 Run 标记 `superseded`，旧 Event 永久保留。
- 事件分类为中性事件族，不使用利好/利空/买卖标签。实体匹配只读取 P01 已批准的 ProjectIdentity/AssetUnitIdentity，不确定时留空并标记复核。
- 新增 API：`GET /api/announcements/{id}/parse-status`、`GET /api/announcements/{id}/events`、`POST /api/evidence/{id}/parse`、`GET /api/evidence/{id}/parse-runs`。
- StockDetail 公告列表增加未解析/已解析/失败/待复核状态和中性 Event 标签，展开区域显示事件页码；原外部标题链接和 P02 本地 PDF 状态保留。

CVV 验收：

- 公告 `2924-03136859-6A1344354` / `PS DFS Revised Completion Timing` 使用本地 EvidenceDocument 解析。
- ParseRun id=1，parser=`deterministic_p3_parser`，version=`p3_v1`，input hash 使用 PDF SHA-256，status=`parsed`，source_scope=`highlights`。
- 生成 6 个中性 Event：Project Delay、Project Schedule Update、Development & Study、Metallurgy Update、Permit / Approval Update、Financing；均保留第 1 页原文摘录，未生成投资方向判断。

验证：后端 252 passed；前端 Vitest 14 passed；前端生产构建成功。

P03 第二部分可在 P3Event 下继续实现八类事实/陈述提取：每条 P3Fact/P3Statement 继续通过 evidence_document_id、source_page 和 source_excerpt 回链，不改写本阶段原始 PDF、Raw Text 或事件历史。

## P03 第二部分：F01-F08 公告事件 Family 分类（2026-09-27）

状态：开发完成，已验证。

分类按指定优先顺序实现：F04 Development & Study、F08 Financial / Operating Periodic、F06 Funding & Capital、F02 Resource & Reserve、F01 Exploration & Drilling、F03 Metallurgy & Processing、F05 Permitting & Project Access、F07 Commercial & Corporate Transaction。

- 新增 `p3_family_classifier.py`，将官方 ASX `announcementType`、`subType`、表单/文档类型作为优先路由；标题关键词仅作初步 routing；P3 Summary/Highlights 解析后再次更新分类。
- `update`、`results`、`project`、`positive`、`significant` 等泛词不会单独触发 Family。
- Revised、Correction、Withdrawal、Retraction、Replacement、Amended 保存在 `revision_tags_json`，不会覆盖原始事件 Family。
- Announcement 现在保存 `document_category`、`event_families_json`、`event_labels_json`、`revision_tags_json`、分类来源和版本；P3Event 额外保存 `event_family`。
- 一份公告可保存多个 Family 和多个中性 Event；事件标签不参与 P04 计算，也不生成利好/利空判断。

CVV 验收：

- `2924-03136859-6A1344354` / `PS DFS Revised Completion Timing`
- 最新 ParseRun id=3，status=`parsed`，source_scope=`highlights`。
- 生成 8 个中性 Event：F04 Project Delay、F04 Project Schedule Update、F04 Development & Study、F03 Metallurgy Update、F05 Permit / Approval Update、F06 Financing、F01 Exploration Update、F07 Corporate / Commercial；每条均有第 1 页原文摘录。
- Revised 单独作为修订标签保留，不替代 F04/F03/F05 等原始事件。

新增/保留 API：公告列表返回文档类别、Family、Event 和修订标签；`/api/announcements/{id}/events` 返回 `event_family`；解析状态和 ParseRun 历史接口保持兼容。

验证：后端 256 passed；前端 Vitest 14 passed；前端生产构建成功。

P03 下一阶段可按 F01-F08 分别增加 P3Fact/P3Statement 字段规则，例如 F06 金额/发行价、F04 工期/CAPEX、F08 现金和经营数据；本阶段未实现这些事实抽取，也未实现任何 P04 指标或投资判断。

## P03 最终步骤：完整回归、自动编排和管理员回填（2026-09-30）

状态：功能实现并通过离线固定样本、正式数据库单样本回填和完整自动测试；外部 ASX 实时网络未作为单元测试依赖，P01/P3 待审核记录仍需人工处理。

### 新公告自动流程

`sync_announcements` 在新 Announcement 写入后调用 P02 `ensure_evidence`。只有 Raw Text 成功时才调用版本化 `parse_evidence`；PDF 或文本失败时保留 Announcement/EvidenceDocument 和失败状态，不生成伪 Fact。日常 PipelineRun 记录 `p3_parsed`、`p3_review_needed`、`p3_failed`、`p3_skipped`。同一 Announcement 已存在时不重复进入新公告流程；同 Evidence、parser version、input hash 的 Parse Run 直接复用。

### Preview-first 历史回填

- 新增 `BackfillRun` 与 `BackfillRunItem`；兼容初始化仅创建新表，不改写旧 Announcement、PDF、Parse Run、Event、Fact、Mapping 或 Version Relation。
- Preview 要求至少一个 Stock、Announcement 或日期范围，未给范围直接拒绝，防止误处理全部 518 条历史公告。
- Preview 只查询统计并生成与筛选条件和候选 ID 绑定的 SHA-256 token，不写数据库、不下载、不解析。执行时 token 或候选集变化会要求重新 Preview。
- 每条公告独立处理并逐项提交。单条失败保留阶段和错误，批次为 `partial`；全部失败才为 `failed`。Retry Failed 创建带 `retry_of_run_id` 的新 Run，且只包含 failed/partial Item。
- 当前 P3 parser 是一个带幂等边界的原子阶段；分类、Fact、实体映射和版本候选开关用于决定是否进入 P3。请求后续 P3 动作却关闭 `parse_document` 会被拒绝。

### 正式数据库验收

对固定 S01/CVV `2924-03136859-6A1344354` 做了显式单公告 Preview 和执行，没有下载，也没有扩大范围：Preview=1 条、已有 PDF=1、已有 Raw Text=1、预计下载=0。Run 1 成功，新建 1 个 Parse Run、7 Event、8 Fact；第二次以同版本/同 Hash 重跑为 skipped，新增 Event/Fact/Mapping 均为 0。正式数据库未执行其他历史公告回填。

固定 10 个官方 PDF 通过 `scripts/verify_p03_facts.py --check` 的隔离数据库端到端解析，fixture SHA-256、Fact→Information Point 分组、来源区间和批准实体归属均无基线漂移。

### 管理页面与 API

新增 `/admin/backfill`：选择股票、公告、日期、Family、下载/文本/解析/Fact/映射/版本步骤、仅未解析和 Parser Version；显示只读 Preview、范围警告、统计、执行、运行列表、Item 详情、取消和仅重试失败项。

API 为 `/api/admin/backfill/preview`、`/run`、`/runs`、`/runs/{id}`、`/items`、`/retry-failed`、`/cancel`。响应只返回证据 ID 和安全业务字段，不返回本地文件路径或密钥。

### P04 边界

P04 可读取 P3Fact 的 `fact_type`、`value_raw`、`value_numeric`、`value_text`、单位/币种、期间/日期、状态、项目归属、Evidence/Page/Excerpt 和版本有效状态，计算 Cash Runway、Placement Discount、Resource Growth、Grade Change 和 Schedule Change。P04 不得修改或 supersede P3 原始事实；派生值必须存入 P4 独立结构。

最终逐项状态、记录数、测试和限制见 `docs/beta02-p1-p3-final-implementation-report.md`。

最终数据库只读一致性审计结果为 14 pass、1 warning、0 fail。唯一 warning 来自旧 Parse Run 4–10 的 15 条历史 Fact 实体归属不一致；最新验收 Run 12 未命中。旧事实依保留历史原则不自动覆盖，列入管理端人工复核。
