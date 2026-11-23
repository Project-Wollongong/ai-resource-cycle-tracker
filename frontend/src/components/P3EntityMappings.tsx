import { Space, Table, Tag, Typography } from "antd";

import type { P3EntityMapping } from "../api/types";

const METHOD_LABELS: Record<P3EntityMapping["match_method"], string> = {
  exact_match: "准确匹配",
  alias_match: "别名匹配",
  former_name_match: "历史名称匹配",
  unresolved_candidate: "待确认候选",
  fuzzy_match: "模糊匹配建议",
  model_suggestion: "模型建议",
  manual_confirmation: "人工确认",
  p01_proposal_approved: "P01 审核批准",
};

const TYPE_LABELS: Record<P3EntityMapping["mention_type"], string> = {
  stock: "Stock",
  project: "Project",
  asset_unit: "Asset Unit",
  commodity: "Commodity",
};

export default function P3EntityMappings({ mappings }: { mappings: P3EntityMapping[] }) {
  if (mappings.length === 0) {
    return <Typography.Text type="secondary">未识别到已知实体名称</Typography.Text>;
  }
  return (
    <Table
      size="small"
      rowKey="id"
      pagination={false}
      dataSource={mappings}
      columns={[
        {
          title: "实体",
          key: "entity",
          render: (_, row) => <Tag>{TYPE_LABELS[row.mention_type]}</Tag>,
        },
        {
          title: "公告原文名称",
          dataIndex: "mention_text_raw",
        },
        {
          title: "映射结果",
          key: "mapping",
          render: (_, row) => row.status === "confirmed" && row.matched_entity ? (
            <Space direction="vertical" size={0}>
              <Typography.Text strong>{row.matched_entity.name}</Typography.Text>
              {row.matched_alias && row.matched_alias.value !== row.matched_entity.name && (
                <Typography.Text type="secondary">原名：{row.matched_alias.value}</Typography.Text>
              )}
            </Space>
          ) : <Typography.Text type="warning">待确认</Typography.Text>,
        },
        {
          title: "方式 / 状态",
          key: "method",
          render: (_, row) => (
            <Space size={4} wrap>
              <Tag color={row.match_method === "exact_match" ? "blue" : row.match_method === "fuzzy_match" || row.match_method === "model_suggestion" ? "orange" : "purple"}>{METHOD_LABELS[row.match_method]}</Tag>
              {row.human_locked && <Tag>人工锁定</Tag>}
              <Tag color={row.status === "confirmed" ? "green" : row.status === "review_needed" || row.status === "ambiguous" ? "orange" : "default"}>
                {row.status === "confirmed" ? "已确认" : row.status === "review_needed" || row.status === "ambiguous" ? "待确认" : row.status === "superseded" ? "已替代" : "已拒绝"}
              </Tag>
            </Space>
          ),
        },
        {
          title: "证据",
          key: "evidence",
          render: (_, row) => (
            <Space direction="vertical" size={0}>
              {row.source_page ? (
                <a href={`/api/announcements/evidence/${row.evidence_document_id}/original`} target="_blank" rel="noreferrer">
                  第 {row.source_page} 页原文
                </a>
              ) : <Typography.Text type="secondary">页码未知</Typography.Text>}
              <Typography.Text type="secondary" ellipsis={{ tooltip: row.source_excerpt }} style={{ maxWidth: 360 }}>
                {row.source_excerpt}
              </Typography.Text>
            </Space>
          ),
        },
      ]}
    />
  );
}
