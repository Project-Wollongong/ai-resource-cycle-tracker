# Beta02 P03 第二阶段：Summary-first 事实提取

## 目标

事实提取不再把 Summary、标准表格和正文一次性混在一起扫描，而是按可审计的顺序执行：

1. Summary；
2. Highlights；
3. Key Results；
4. Executive Summary；
5. Family 字段缺口检查；
6. 有缺口且文档为 Appendix 5B/4C 时读取标准表格；
7. 仍有缺口时读取正文；
8. 保存仍未找到的字段，不猜测或补默认值。

## Bullet 处理

- `•`、`●`、`▪`、`◦`、`‣`、`o` 等项目符号按逻辑 bullet 拆分。
- PDF 换行造成的同一 bullet 多行文本会重新连接。
- 同一物理行包含多个 bullet 时分别处理。
- 一个复合 bullet 可以生成多个原子 `P3Fact`，例如 Recovery、Product Grade 和 Sample Count。
- 钻孔列表会把 Hole ID 父 bullet 作为子区间的上下文，但每个区间仍有自己的 bullet 编号和证据。

每个由摘要提取的 Fact 在 `metadata_json` 中记录：

- `source_region`；
- `source_unit`；
- `summary_bullet_index`；
- `summary_bullet_text`；
- `source_priority`。

正式字段 `source_section`、页码和 `source_excerpt` 继续作为查询和展示依据。

## Family 字段缺口

缺口由已经建立的 `P3Event` 决定，而不是由正文中的孤立关键词决定。例如：

- F04 Project Delay：检查 Timeline Change 与 Previous Timing；
- F08 Periodic Cash Flow：检查 Operating、Investing、Financing Cash Flow 和 Cash Balance；
- F06 Placement：检查 Funding Method、Funding Amount、Issue Price 和 New Securities；
- F02 Reserve Update：检查 Reserve Type、Classification、Tonnage、Grade、Contained Metal 和 Reported Change；
- F01 Drilling Results：检查 Hole ID、Interval、Grade 和 From Depth。

其他 Family 也使用对应 Event 激活的最小字段组。正文扫描后仍缺失的字段进入 `remaining_missing_fields`，不会生成空 Fact 或推测值。

## 来源升级与去重

- 摘要已满足 Event 字段时，不读取标准表格或正文。
- 标准表格只在存在字段缺口且识别为 Appendix 5B/4C 时读取。
- 正文只在标准表格处理后仍存在字段缺口时读取。
- 完全相同的事实优先保留高优先级来源；不同数值不会互相覆盖。
- 标题、摘要、表格或正文对同一字段披露不同数值时全部保留，并标记 `review_needed` 和 `source_value_conflict`。
- Reserve 表行等带有不同分类语义的记录不会因为数值相同而错误合并。

## Parse Run 审计

`P3ParseRun.output_summary_json.fact_extraction` 保存：

- 摘要区域优先级；
- bullet 数量；
- 摘要提取 Fact 数；
- 摘要后的字段缺口；
- 是否读取标准表格、页码和 Fact 数；
- 标准表格后的字段缺口；
- 是否读取正文、页码和 Fact 数；
- 最终未找到字段；
- 各来源区域 Fact 数。

`GET /announcements/{announcement_id}/parse-status` 同步返回该审计对象，前端在信息点区域显示本次提取路径。

## 版本

- Parser：`p3_reported_fact_v2_summary_first`
- Extractor：`p3_fact_v2_summary_first`

新版本创建新的 Parse Run、Event、Fact 和 Information Point；旧版本记录不删除。人工已确认的结果仍受原有保护规则约束。
