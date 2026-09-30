import { Button, Card, Space, Table, Tag, Typography, message } from "antd";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { P3EntityMapping } from "../api/types";

const methodLabel: Record<string, string> = {
  fuzzy_match: "模糊匹配建议",
  model_suggestion: "模型建议",
  unresolved_candidate: "未解析候选",
};

export default function P3EntityMappingReview({ reviewer }: { reviewer: string }) {
  const [rows, setRows] = useState<P3EntityMapping[]>([]);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await api.get<P3EntityMapping[]>("/admin/p3/entity-mappings/review-needed"));
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const act = async (row: P3EntityMapping, action: "confirm" | "reject") => {
    if (!reviewer.trim()) {
      message.warning("请先填写审核人");
      return;
    }
    try {
      await api.post(`/admin/p3/entity-mappings/${row.id}/${action}`, {
        reviewer: reviewer.trim(),
        review_note: action === "confirm" ? "人工核对名称、Stock 和 Parent Project 后确认" : "人工审核拒绝该建议",
      });
      message.success("映射审核已保存");
      await load();
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  return <Card title="P03 模糊匹配 / 模型建议审核">
    <Typography.Paragraph type="secondary">
      模糊匹配和模型输出仅是待确认建议；确认后生成独立的人工锁定映射，后续自动解析不会覆盖。
    </Typography.Paragraph>
    <Table size="small" rowKey="id" loading={loading} dataSource={rows} scroll={{ x: 1250 }} columns={[
      { title: "原文名称", dataIndex: "mention_text_raw", width: 150 },
      { title: "类型", dataIndex: "mention_type", width: 100 },
      { title: "建议实体", render: (_, row) => row.candidate_entity?.name || row.matched_entity?.name || String(row.candidate_payload?.display_name || "无已知实体建议"), width: 180 },
      { title: "方法", render: (_, row) => <Tag color={row.match_method === "model_suggestion" ? "geekblue" : "orange"}>{methodLabel[row.match_method] || row.match_method}</Tag>, width: 140 },
      { title: "置信度", render: (_, row) => `${Math.round(row.match_confidence * 100)}%`, width: 85 },
      { title: "Stock 验证", dataIndex: "stock_validation_result", width: 210 },
      { title: "Parent 验证", dataIndex: "parent_validation_result", width: 210 },
      { title: "证据", render: (_, row) => <Space direction="vertical" size={0}>
        {row.source_page ? <a href={`/api/announcements/evidence/${row.evidence_document_id}/original`} target="_blank" rel="noreferrer">第 {row.source_page} 页原文</a> : "页码未知"}
        <Typography.Text ellipsis={{ tooltip: row.source_excerpt }} style={{ maxWidth: 280 }}>{row.source_excerpt}</Typography.Text>
      </Space>, width: 300 },
      { title: "操作", render: (_, row) => row.candidate_entity || row.matched_entity ? <Space>
        <Button size="small" danger onClick={() => void act(row, "reject")}>拒绝</Button>
        <Button size="small" type="primary" onClick={() => void act(row, "confirm")}>确认</Button>
      </Space> : <Tag>等待 P01 候选审核</Tag>, width: 170 },
    ]} />
  </Card>;
}
