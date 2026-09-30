import { Alert, Button, Card, Input, Select, Space, Table, Tag, Typography, message } from "antd";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { P3UpdateProposal } from "../api/types";

const STATUS_LABELS: Record<P3UpdateProposal["status"], string> = {
  pending: "待审核", approved: "已批准", rejected: "已拒绝", superseded: "已替代",
};

export function P3UpdateProposalTable({
  rows, notes, corrections, onNote, onCorrection, onAction,
}: {
  rows: P3UpdateProposal[];
  notes: Record<number, string>;
  corrections: Record<number, string>;
  onNote: (id: number, value: string) => void;
  onCorrection: (id: number, value: string) => void;
  onAction: (row: P3UpdateProposal, action: "approve" | "reject" | "correct") => void;
}) {
  return <Table
    size="small" rowKey="id" dataSource={rows} scroll={{ x: 1600 }} pagination={{ pageSize: 10 }}
    expandable={{ expandedRowRender: (row) => <Space direction="vertical" style={{ width: "100%" }}>
      <Typography.Text strong>支持证据</Typography.Text>
      <Table size="small" rowKey="mention_id" pagination={false} dataSource={row.evidence} columns={[
        { title: "公告", render: (_, item) => item.announcement ? <a href={item.announcement.url} target="_blank" rel="noreferrer">{item.announcement.headline}</a> : "-" },
        { title: "日期", render: (_, item) => item.announcement?.ann_date?.slice(0, 10) || "-" },
        { title: "页码", render: (_, item) => item.source_page_start ? `第 ${item.source_page_start} 页` : "未知" },
        { title: "原文摘录", dataIndex: "source_excerpt", render: (value: string) => <Typography.Paragraph ellipsis={{ rows: 2, expandable: true }}>{value}</Typography.Paragraph> },
        { title: "PDF", render: (_, item) => item.evidence_document ? <a href={item.evidence_document.pdf_url} target="_blank" rel="noreferrer">打开原始 PDF</a> : "-" },
      ]} />
      {row.status === "pending" && <Space wrap>
        <Input placeholder="审核原因（必填）" value={notes[row.id] || ""} onChange={(e) => onNote(row.id, e.target.value)} style={{ width: 280 }} />
        <Input placeholder='修正 JSON，例如 {"proposed_asset_type":"pipe"}' value={corrections[row.id] || ""} onChange={(e) => onCorrection(row.id, e.target.value)} style={{ width: 360 }} />
      </Space>}
    </Space> }}
    columns={[
      { title: "候选类型", dataIndex: "proposal_type", width: 190 },
      { title: "Stock", render: (_, row) => row.stock ? `${row.stock.code} · ${row.stock.name}` : row.stock_id, width: 180 },
      { title: "原文名称", dataIndex: "proposed_name", width: 150 },
      { title: "Entity Type", dataIndex: "proposed_entity_type", width: 110 },
      { title: "候选 Parent Project", render: (_, row) => row.candidate_parent_project?.name || "待确认", width: 170 },
      { title: "Commodity", render: (_, row) => row.proposed_commodity || "待确认", width: 110 },
      { title: "支持数量", render: (_, row) => `${row.supporting_announcement_count} 公告 / ${row.supporting_evidence_count} PDF / ${row.supporting_event_count} Event / ${row.supporting_fact_count} Fact`, width: 260 },
      { title: "置信度", render: (_, row) => row.confidence == null ? "-" : `${Math.round(row.confidence * 100)}%`, width: 90 },
      { title: "来源", dataIndex: "created_by", width: 80 },
      { title: "状态", render: (_, row) => <Tag color={row.status === "approved" ? "green" : row.status === "rejected" ? "red" : "gold"}>{STATUS_LABELS[row.status]}</Tag>, width: 90 },
      { title: "审核", render: (_, row) => row.reviewed_by ? `${row.reviewed_by} · ${row.reviewed_at || ""}` : "-", width: 180 },
      { title: "最终实体", render: (_, row) => row.resulting_entity ? (row.resulting_entity.type === "project" && row.resulting_entity.project_key ? <Link to={`/projects/${encodeURIComponent(row.resulting_entity.project_key)}`}>{row.resulting_entity.name}</Link> : row.resulting_entity.name) : "-", width: 140 },
      { title: "操作", render: (_, row) => row.status === "pending" ? <Space>
        <Button size="small" onClick={() => onAction(row, "correct")}>修正</Button>
        <Button size="small" danger onClick={() => onAction(row, "reject")}>拒绝</Button>
        <Button size="small" type="primary" onClick={() => onAction(row, "approve")}>批准</Button>
      </Space> : "-", width: 180 },
    ]}
  />;
}

export default function P3UpdateProposalReview({ reviewer }: { reviewer: string }) {
  const [rows, setRows] = useState<P3UpdateProposal[]>([]);
  const [status, setStatus] = useState("pending");
  const [loading, setLoading] = useState(false);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [corrections, setCorrections] = useState<Record<number, string>>({});
  const load = useCallback(async () => {
    setLoading(true);
    try { setRows(await api.get<P3UpdateProposal[]>(`/admin/entity-review/p3-update-proposals?status=${status}`)); }
    catch (error) { message.error((error as Error).message); }
    finally { setLoading(false); }
  }, [status]);
  useEffect(() => { void load(); }, [load]);

  const act = async (row: P3UpdateProposal, action: "approve" | "reject" | "correct") => {
    if (!reviewer.trim()) { message.warning("请填写审核人"); return; }
    if (!notes[row.id]?.trim()) { message.warning("请填写审核原因"); return; }
    let correction: Record<string, unknown> = {};
    if (action === "correct") {
      try { correction = JSON.parse(corrections[row.id] || "{}") as Record<string, unknown>; }
      catch { message.error("修正内容必须是 JSON"); return; }
    }
    const payload = { reviewer: reviewer.trim(), review_note: notes[row.id].trim(), ...(action === "correct" ? { correction } : {}) };
    try {
      if (action === "correct") await api.put(`/admin/entity-review/p3-update-proposals/${row.id}`, payload);
      else await api.post(`/admin/entity-review/p3-update-proposals/${row.id}/${action}`, payload);
      message.success("P01 实体审核已保存"); await load();
    } catch (error) { message.error((error as Error).message); }
  };

  return <Card title="P03 候选实体更新" extra={<Select value={status} onChange={setStatus} options={["pending", "approved", "rejected", "superseded"].map((value) => ({ value, label: STATUS_LABELS[value as P3UpdateProposal["status"]] }))} />}>
    {!reviewer.trim() && <Alert type="info" showIcon message="批准、拒绝和修正均需填写页面上方的审核人。" style={{ marginBottom: 12 }} />}
    <div aria-busy={loading}>
      <P3UpdateProposalTable rows={rows} notes={notes} corrections={corrections}
        onNote={(id, value) => setNotes((old) => ({ ...old, [id]: value }))}
        onCorrection={(id, value) => setCorrections((old) => ({ ...old, [id]: value }))}
        onAction={(row, action) => void act(row, action)} />
    </div>
  </Card>;
}
