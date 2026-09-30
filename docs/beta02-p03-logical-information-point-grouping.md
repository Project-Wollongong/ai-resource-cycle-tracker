# Beta02 P03 第三阶段：逻辑信息点分组

## 目标

`P3Fact` 继续保存公司披露的全部原子事实；`P3InformationPoint` 将属于同一逻辑声明的 Fact 组织为一个前端展示组。分组不会删除、合并数值或截断底层 Fact。

例如钻孔交集：

```text
Information Point: BCRC115 — 8m @ 1.5% Li2O from 89m
  1. Hole ID = BCRC115              (primary)
  2. Interval Length = 8m           (component)
  3. Grade = 1.5% Li2O              (component)
  4. From Depth = 89m               (component)
  5. True Width = 8m                (component, if reported)
```

这是一个逻辑信息点和五个原子 Fact，不是五个独立的前端摘要行。

## P3Fact 分组字段

- `information_point_group_id`：对应 `p3_information_points.id`；
- `information_point_type`：例如 `drill_intersection`、`resource_reserve_row`；
- `parent_fact_id`：组成 Fact 指向组内主 Fact，主 Fact 自身为空；
- `display_order`：组内稳定展示顺序，从 0 开始。

原有 `p3_information_point_facts` 关联表继续保留，记录 `primary/component` 角色和显示顺序。新增字段是查询和前端展示的便捷投影，不替代正式关联表。

## 分组边界

### 钻孔交集

按 Hole ID 和完整区间签名分组。母区间和 `including` 子区间是不同 group。顺序为 Hole、Interval、Grade、From、To、True Width。

### Resource / Reserve

- 表格中的一个分类行形成 `resource_reserve_row`；
- Type、Classification、Tonnage、Grade、Contained Metal、Commodity 为组成 Fact；
- 摘要中的 Reserve/Resource 声明使用 `resource_reserve_summary`，不与表格行混为一组；
- Resource 与 Reserve、不同分类、不同来源分别分组。

### 现金流

按字段、期间类型和期间范围分组。Current Quarter 与 Year-to-Date 永远是两个信息点，即使数值相同。

### 时间表

Previous Timing、Revised Timing 和 Timeline Change 组成一个 `timeline_change`；Study Type、FID、CAPEX Review 保持独立。

### 冶金、许可与交易

- Recovery、Product Grade、Sample Count 组成 `metallurgical_test_result`；
- Permit scope/term、Permit status 按同一原文声明分组；
- Earn-in 总体条款、Phase 1、Phase 2、Current Ownership、Manager 分别分组；
- Manager 不生成 Operator Fact。

### Summary bullet

同一 Summary bullet、同一 Family、同一语义声明可以组成一个信息点。钻孔、时间表、现金流、Resource/Reserve 和冶金结果等专属规则优先于通用 bullet 分组。

## API 与前端

- `GET /announcements/{announcement_id}/facts` 支持按 `information_point_group_id` 和 `information_point_type` 过滤；
- Fact API 返回四个分组字段；
- Information Point API 返回 group ID、type、primary Fact ID 和有序组成 Fact；
- 公告展开区域默认按逻辑信息点显示，可展开查看所有原子 Fact；
- `parse-status.information_point_grouping` 返回原子 Fact 数、信息点数、类型统计及 `all_facts_preserved`。

## 数量策略

20–50 仍然是覆盖目标，不是配额：

- 不为了达到 20 而复制或拆碎 Fact；
- 不为了低于 50 而删除 Fact；
- 前端以 Information Point 控制主表数量；
- 所有底层 Fact 可通过展开组或 Fact API 查询；
- 少于 20 时继续显示“来源不足”。

## 数据库兼容

SQLite 兼容初始化会增量添加四个字段和索引，并根据已有 `p3_information_point_facts` 回填历史分组引用。旧 Parse Run、Fact、Information Point 和审核结果均保留。

Parser 版本：`p3_reported_fact_v3_1_information_points`。
