# Beta02 P03 数据库一致性审计

审计日期：2026-09-29  
审计版本：`p3_database_consistency_v1`  
正式业务数据库：`data/tracker.db`

## 结论

当前有效数据通过全部关键一致性检查：14 项通过、0 项失败。另有 1 项历史警告，涉及旧解析版本中保留的 15 条错误实体归属；最新 Parse Run 已修正，旧记录按 P03 的版本保留要求不覆盖、不删除。

仓库中的正式业务数据库只有 `data/tracker.db`。`data/yfinance_cache/tkr-tz.db` 是 yfinance 自动生成的行情时区缓存，不包含 P01/P02/P03 业务表，审计会将它列为非业务缓存，但不把它视为第二个业务数据库。

## 数据清单

| 对象 | 数量 | 说明 |
|---|---:|---|
| Stock | 32 | 正式 Stock 记录 |
| Pilot Stock | 29 | MAU、PEX、XAM 当前为非激活/非 pilot 成员 |
| Project | 9 | 与 P01 已批准清单一致 |
| Asset Unit | 5 | 与 P01 已批准清单一致 |
| Announcement | 518 | 同库保存 |
| EvidenceDocument | 10 | 同库保存 |
| P3Event | 72 | 包括保留的历史 Parse Run 结果 |
| P3Fact | 66 | 包括保留的历史 Parse Run 结果 |
| Information Point | 35 | 逻辑信息点分组 |

五个 Asset Unit 的现有父级关系为：

- Gifford Creek Critical Metals Project：Yin
- Tabba Tabba：Bolt Cutter Central、Hutt、Chewy、Leia

## 强制规则

1. P3 只读取 P01 已批准的 `projects`、`project_identities`、`asset_units` 和 `asset_unit_identities`。
2. 名称匹配使用完整 token 边界；例如 `Yin` 可以匹配 “Yin deposit”，但不能匹配 “assaying”。
3. Asset Unit 命中后，其 Project 必须等于该 Asset Unit 在 P01 中的父 Project；冲突时不建立归属。
4. 只有 Fact 自身的证据文本明确命中唯一已批准实体时才建立归属。不会继承相邻 bullet、兄弟 Fact 或 Event 的推测上下文。
5. 无法确认时保存为 Company 层：`project_id=NULL`、`asset_unit_id=NULL`、`project_attribution_status='unknown'`。
6. P3 分类、解析和事实提取服务不创建 Project、Asset Unit 或其 Identity。
7. 每条 P3Fact 仍须连接已存在的 Stock、Announcement、EvidenceDocument、P3Event 和 P3ParseRun。

## 审计项目

- 运行时数据库路径与唯一业务数据库文件
- P01/P02/P03 必要表是否在同一数据库
- SQLite `integrity_check` 与 `foreign_key_check`
- 32/9/5 基准数量及实体名称唯一性
- P3Fact 所有父级外键是否存在
- P3Fact 的 Project/Asset Unit 是否具有当前已批准 Identity
- Asset Unit 与其父 Project 是否一致
- 最新结果是否仍含 `inferred_from_context`
- 无法归属的最新 Fact 是否正确留在 Company 层
- Fact → Event → Evidence → Announcement → Stock 链路是否一致
- Information Point 的成员、父 Fact 与显示顺序是否一致
- 是否存在由 P3/Parser 创建的 Project/Asset Unit Identity

## 当前历史警告

旧 Parse Run 4–10 中有 15 条 Fact 曾把 Caravel Project 与 Gifford Creek 的 Asset Unit `Yin` 错误组合。根因是旧逻辑用子字符串匹配，`Yin` 错误命中了 “assaying”。

新规则采用完整 token 匹配，最新 Parse Run 11 的 8 条 Fact 中：

- 5 条明确归属 Caravel Copper Project；
- 0 条归属 Asset Unit；
- 3 条因自身摘录没有明确实体名称而保留在 Company 层；
- 0 条使用 `inferred_from_context`；
- 解析前后均为 9 个 Project、5 个 Asset Unit，没有自动新增实体。

旧记录继续保留，用于解析版本和错误修复审计。普通用户接口的 latest-run 视图不会把这些历史错误作为当前有效结果返回。

## 复现方式

```powershell
.\backend\.venv-win\Scripts\python.exe scripts\audit_p3_database_consistency.py
.\backend\.venv-win\Scripts\python.exe scripts\audit_p3_database_consistency.py --json
```

管理端只读接口：

```text
GET /api/admin/p3/database-consistency
```

该接口和命令均为只读，不会修正、创建或删除任何实体和 Fact。
