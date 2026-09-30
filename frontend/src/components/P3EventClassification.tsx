import { Descriptions, Space, Tag, Typography } from "antd";

import type { P3Event } from "../api/types";

export const P3_FAMILY_NAMES: Record<string, string> = {
  F01: "Exploration & Drilling",
  F02: "Resource & Reserve",
  F03: "Metallurgy & Processing",
  F04: "Development & Study",
  F05: "Permitting & Project Access",
  F06: "Funding & Capital",
  F07: "Commercial & Corporate Transaction",
  F08: "Financial / Operating",
  OTHER: "Other / Needs Review",
};

export function P3EventTags({ events, revisionTags = [] }: { events: P3Event[]; revisionTags?: string[] }) {
  const families = [...new Set(events.flatMap((event) => [event.primary_family || event.event_family, ...(event.secondary_families ?? [])]))];
  const eventTypes = [...new Set(events.filter((event) => event.active_result !== false).map((event) => event.event_type))];
  const revisions = [...new Set([...revisionTags, ...events.flatMap((event) => event.revision_tags ?? [])])];
  const reviewNeeded = events.some((event) => event.review_needed || event.classification_status === "review_needed");
  return (
    <Space size={[4, 4]} wrap>
      {families.filter((family) => family !== "OTHER").map((family) => <Tag color="geekblue" key={family}>{P3_FAMILY_NAMES[family] ?? family}</Tag>)}
      {eventTypes.filter((type) => type !== "OTHER_NEEDS_REVIEW").map((type) => <Tag key={type}>{type}</Tag>)}
      {revisions.map((tag) => <Tag color="orange" key={tag}>{tag}</Tag>)}
      {reviewNeeded && <Tag color="warning">待人工复核</Tag>}
    </Space>
  );
}

export function P3EventDetails({ events, parserVersion }: { events: P3Event[]; parserVersion?: string | null }) {
  if (events.length === 0) return <Typography.Text type="secondary">未解析</Typography.Text>;
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      {events.map((event) => (
        <Descriptions key={event.event_id || event.id} size="small" column={2} bordered>
          <Descriptions.Item label="Event Family">{P3_FAMILY_NAMES[event.primary_family || event.event_family] ?? event.primary_family}</Descriptions.Item>
          <Descriptions.Item label="具体 Event">{event.event_title}</Descriptions.Item>
          <Descriptions.Item label="业务状态">{event.event_status}</Descriptions.Item>
          <Descriptions.Item label="有效状态">
            <Space size={4}><Tag color={(event.display_validity_status || event.validity_status) === "current" ? "green" : (event.display_validity_status || event.validity_status) === "correction_pending_review" ? "orange" : "default"}>
              {(event.display_validity_status || event.validity_status || "current") === "correction_pending_review" ? "可能修正，待人工复核" : (event.display_validity_status || event.validity_status || "current")}
            </Tag><a href={`/api/p3/events/${event.id}/history`} target="_blank" rel="noreferrer">查看版本</a></Space>
          </Descriptions.Item>
          <Descriptions.Item label="分类状态">{event.review_needed ? "待人工复核" : event.classification_status}</Descriptions.Item>
          <Descriptions.Item label="修订标签">{event.revision_tags?.join(" / ") || "-"}</Descriptions.Item>
          <Descriptions.Item label="来源" span={2}>{event.source_section} · p{event.source_page_start ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="分类依据" span={2}>{event.classification_reason || event.classification_source}</Descriptions.Item>
          <Descriptions.Item label="原文摘录" span={2}>{event.source_excerpt || "-"}</Descriptions.Item>
          <Descriptions.Item label="解析版本">{parserVersion || `run ${event.parse_run_id}`}</Descriptions.Item>
          <Descriptions.Item label="实体">{event.asset_unit?.name || event.project?.name || "未映射"}</Descriptions.Item>
        </Descriptions>
      ))}
    </Space>
  );
}
