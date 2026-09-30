import { Alert, Space, Table, Tag, Tooltip, Typography } from "antd";

import type { P3InformationPoint, P3ParseStatus } from "../api/types";

const SUMMARY_SECTIONS = new Set(["summary", "highlights", "key_results", "executive_summary"]);

export function informationPointCountLabel(status: Pick<P3ParseStatus, "information_point_count" | "count_status">) {
  if (status.count_status === "source_insufficient") return `${status.information_point_count} 个信息点 · 来源不足`;
  if (status.count_status === "high_density") return `${status.information_point_count} 个信息点 · 高密度`;
  return `${status.information_point_count} 个信息点 · 目标范围`;
}

export default function P3InformationPoints({ points, status }: { points: P3InformationPoint[]; status?: P3ParseStatus }) {
  const extraction = status?.fact_extraction;
  const grouping = status?.information_point_grouping;
  const extractionPath = extraction
    ? `Summary/Highlights bullets ${extraction.summary_bullet_count} 条，提取 ${extraction.summary_fact_count} 个 Fact；标准表格${extraction.standard_form_used ? `补缺 ${extraction.standard_form_fact_count} 个` : "未读取"}；正文${extraction.body_fallback_used ? `补缺 ${extraction.body_fallback_fact_count} 个` : "未读取"}。${extraction.remaining_missing_fields.length ? `仍缺：${extraction.remaining_missing_fields.join("、")}` : "Family 字段检查已通过。"}`
    : null;
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      {status && (
        <Alert
          type={status.count_status === "target_range" ? "success" : "info"}
          showIcon
          message={informationPointCountLabel(status)}
          description={`20–50 是覆盖目标，不补数、不截断。Summary ${status.summary_point_count}，标准表格 ${status.standard_form_point_count}，正文 fallback ${status.body_fallback_point_count}，原子 Fact ${status.atomic_fact_count}。`}
        />
      )}
      {extractionPath && <Typography.Text type="secondary">提取路径：{extractionPath}</Typography.Text>}
      {grouping && <Typography.Text type="secondary">逻辑分组：{grouping.atomic_fact_count} 个原子 Fact → {grouping.information_point_count} 个信息点；底层 Fact {grouping.all_facts_preserved ? "全部保留" : "需复核"}。</Typography.Text>}
      <Table
        aria-label="逻辑信息点"
        size="small"
        rowKey="id"
        dataSource={points}
        pagination={{ pageSize: 10, hideOnSinglePage: true }}
        expandable={{
          rowExpandable: (point) => point.facts.length > 0,
          expandedRowRender: (point) => (
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              {[...point.facts].sort((a, b) => a.display_order - b.display_order).map((fact) => (
                <Space key={fact.id} size={6}>
                  <Typography.Text type="secondary">{fact.display_order + 1}.</Typography.Text>
                  <Typography.Text strong={fact.role === "primary"}>{fact.field_name}</Typography.Text>
                  <Typography.Text>{fact.value_raw}{fact.unit_raw && !fact.value_raw.toLowerCase().includes(fact.unit_raw.toLowerCase()) ? ` ${fact.unit_raw}` : ""}</Typography.Text>
                  <Tag>{fact.status}</Tag>
                  <Tag color={fact.role === "primary" ? "blue" : "default"}>{fact.role === "primary" ? "主 Fact" : "组成 Fact"}</Tag>
                </Space>
              ))}
            </Space>
          ),
        }}
        columns={[
          { title: "Family", dataIndex: "family", width: 75, render: (value) => <Tag>{value}</Tag> },
          { title: "逻辑信息点", dataIndex: "point_title" },
          { title: "原子 Fact", dataIndex: "fact_count", width: 90 },
          { title: "来源", key: "source", width: 150, render: (_, point) => <Space size={4}><Tag color={SUMMARY_SECTIONS.has(point.source_section) ? "green" : point.source_section === "standard_form" ? "blue" : "orange"}>{point.source_section}</Tag><Tooltip title={point.source_excerpt}><Typography.Text>第 {point.source_page_start ?? "?"} 页</Typography.Text></Tooltip></Space> },
          { title: "状态", key: "status", width: 150, render: (_, point) => <Space size={4}><Tag>{point.status}</Tag>{point.review_status === "review_needed" && <Tag color="orange">待复核</Tag>}</Space> },
        ]}
      />
    </Space>
  );
}
