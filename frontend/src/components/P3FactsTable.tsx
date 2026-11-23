import { Space, Table, Tag, Tooltip, Typography } from "antd";

import NoData from "./NoData";

import type { P3Event, P3Fact } from "../api/types";

const VALIDITY_LABELS: Record<string, string> = {
  current: "Current",
  historical: "Historical",
  superseded: "Superseded · 已由后续披露替代",
  withdrawn: "Withdrawn · 公司已撤回",
  correction_pending_review: "可能修正，待人工复核",
  rejected: "Rejected",
};

function validityColor(status: string) {
  if (status === "current") return "green";
  if (status === "withdrawn" || status === "rejected") return "red";
  if (status === "superseded" || status === "historical") return "default";
  return "orange";
}

export function hasDrillContext(events: Pick<P3Event, "primary_family">[]) {
  return events.some((event) => event.primary_family === "F01");
}

function displayValue(fact: P3Fact) {
  const value = fact.value_text || fact.value_raw || (fact.value_numeric != null ? String(fact.value_numeric) : "未找到");
  const unit = fact.unit_raw || fact.unit_normalized;
  return unit && !value.toLocaleLowerCase().includes(unit.toLocaleLowerCase()) ? `${value} ${unit}` : value;
}

function period(fact: P3Fact) {
  if (fact.as_of_date) return `截至 ${fact.as_of_date}`;
  if (fact.period_start || fact.period_end) return [fact.period_start, fact.period_end].filter(Boolean).join(" – ");
  if (fact.effective_date) return `生效 ${fact.effective_date}`;
  return "-";
}

export function neutralFactSummary(facts: P3Fact[]) {
  if (facts.length === 0) return "尚未提取事实";
  const preferred = ["timeline_change", "dfs_completion", "cash_balance", "funding_amount", "reported_increase", "recovery"];
  const rank = (fact: P3Fact) => {
    const index = preferred.indexOf(fact.fact_type);
    return index < 0 ? preferred.length : index;
  };
  const selected = [...facts].sort((a, b) => rank(a) - rank(b)).slice(0, 2);
  return selected.map((fact) => `${fact.field_name}：${displayValue(fact)}（${fact.status}）`).join("；");
}

export default function P3FactsTable({ facts }: { facts: P3Fact[] }) {
  if (facts.length === 0)
    return (
      <NoData
        title="尚未提取事实"
        reason="该公告已归档但未产出结构化事实：可能是文档类型尚无抽取规则（F01 钻探、F05 许可、F07 商业交易目前均无规则），也可能是摘要优先策略判定无需下探正文。"
      />
    );
  const familyFilters = [...new Set(facts.map((fact) => fact.family))].map((value) => ({ text: value, value }));
  const fieldFilters = [...new Set(facts.map((fact) => fact.field_name))].map((value) => ({ text: value, value }));
  return (
    <Table
      aria-label="已提取事实"
      size="small"
      rowKey="id"
      pagination={{ pageSize: 10, hideOnSinglePage: true }}
      dataSource={facts}
      columns={[
        { title: "Event", key: "event", render: (_, fact) => <Space size={4}><Tag>{fact.family}</Tag><span>{fact.event?.event_title || fact.event?.event_type || "-"}</span></Space>, filters: familyFilters, onFilter: (value, fact) => fact.family === value },
        { title: "字段", dataIndex: "field_name", filters: fieldFilters, onFilter: (value, fact) => fact.field_name === value },
        { title: "数值", key: "value", render: (_, fact) => displayValue(fact) },
        { title: "状态 / 期间", key: "status", render: (_, fact) => {
          const validity = fact.display_validity_status || fact.validity_status || "current";
          return <Space direction="vertical" size={0}>
            <Space size={4} wrap>
              <Tag color={fact.review_status === "review_needed" ? "orange" : "default"}>{fact.status}</Tag>
              <Tooltip title={fact.validity_reason || undefined}><Tag color={validityColor(validity)}>{VALIDITY_LABELS[validity] || validity}</Tag></Tooltip>
            </Space>
            <Typography.Text type="secondary">{period(fact)}</Typography.Text>
            <a href={`/api/p3/facts/${fact.id}/history`} target="_blank" rel="noreferrer">查看版本</a>
          </Space>;
        } },
        { title: "所属项目", key: "project", render: (_, fact) => fact.asset_unit?.name || fact.project?.name || (fact.project_attribution_status === "unknown" ? "Company / 未确认" : "Company") },
        { title: "证据", key: "evidence", render: (_, fact) => <Tooltip title={fact.source_excerpt}><a href={`/api/announcements/evidence/${fact.evidence_document_id}/original`} target="_blank" rel="noreferrer">第 {fact.source_page ?? "?"} 页原文</a></Tooltip> },
      ]}
    />
  );
}
