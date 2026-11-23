import { Alert, Button, Card, Input, Select, Space, Table, Tag, Typography, message } from "antd";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { P3VersionObject, P3VersionRelation } from "../api/types";

const STATUS_LABELS = { proposed: "待审核", confirmed: "已确认", rejected: "已拒绝" } as const;
const RELATION_TYPES = ["corrects", "restates", "revises", "replaces", "supersedes", "withdraws", "retracts", "related_to"];

function objectLabel(value: P3VersionObject | null) {
  if (!value) return "无替代对象";
  const label = value.field_name || value.title || value.fact_type || value.event_type || value.type;
  return `${label}${value.value_raw ? `：${value.value_raw}` : ""}`;
}

export function P3VersionReviewTable({
  rows, notes, corrections, onNote, onCorrection, onAction,
}: {
  rows: P3VersionRelation[];
  notes: Record<number, string>;
  corrections: Record<number, string>;
  onNote: (id: number, value: string) => void;
  onCorrection: (id: number, value: string) => void;
  onAction: (row: P3VersionRelation, action: "confirm" | "reject" | "correct") => void;
}) {
  return <Table<P3VersionRelation>
    size="small" rowKey="id" dataSource={rows} scroll={{ x: 1650 }} pagination={{ pageSize: 15 }}
    expandable={{ expandedRowRender: (row) => <Space direction="vertical" style={{ width: "100%" }}>
      <Typography.Text strong>关系证据</Typography.Text>
      <Typography.Text>{row.source_excerpt || "未提供摘录"}</Typography.Text>
      <Space wrap>
        {row.source_announcement && <a href={row.source_announcement.url} target="_blank" rel="noreferrer">{row.source_announcement.headline}</a>}
        {row.evidence_document && <a href={row.evidence_document.pdf_url} target="_blank" rel="noreferrer">打开原始 PDF · 第 {row.source_page_start ?? "?"} 页</a>}
      </Space>
      <Space wrap>
        <Input aria-label={`review-note-${row.id}`} placeholder="审核说明（必填）" value={notes[row.id] || ""} onChange={(event) => onNote(row.id, event.target.value)} style={{ width: 320 }} />
        <Input aria-label={`correction-${row.id}`} placeholder='修正 JSON，例如 {"relation_type":"revises"}' value={corrections[row.id] || ""} onChange={(event) => onCorrection(row.id, event.target.value)} style={{ width: 380 }} />
      </Space>
    </Space> }}
    columns={[
      { title: "Stock", render: (_, row) => row.stock ? `${row.stock.code} · ${row.stock.name}` : "-", width: 170 },
      { title: "前序对象", render: (_, row) => <Space direction="vertical" size={0}><span>{objectLabel(row.predecessor)}</span><Tag>{row.predecessor?.validity_status || "unknown"}</Tag></Space>, width: 230 },
      { title: "后续对象", render: (_, row) => <Space direction="vertical" size={0}><span>{objectLabel(row.successor)}</span>{row.successor && <Tag>{row.successor.validity_status}</Tag>}</Space>, width: 230 },
      { title: "关系", dataIndex: "relation_type", width: 110 },
      { title: "状态", render: (_, row) => <Tag color={row.status === "confirmed" ? "green" : row.status === "rejected" ? "red" : "orange"}>{STATUS_LABELS[row.status]}</Tag>, width: 90 },
      { title: "Family / Fact", render: (_, row) => row.successor?.family || row.predecessor?.family || row.successor?.fact_type || row.predecessor?.fact_type || "-", width: 130 },
      { title: "来源页", render: (_, row) => `第 ${row.source_page_start ?? "?"} 页`, width: 80 },
      { title: "检测", render: (_, row) => `${row.detected_by}${row.confidence == null ? "" : ` · ${Math.round(row.confidence * 100)}%`}`, width: 100 },
      { title: "审核", render: (_, row) => row.reviewed_by ? `${row.reviewed_by} · ${row.reviewed_at || ""}` : "-", width: 190 },
      { title: "操作", render: (_, row) => <Space>
        <Button size="small" onClick={() => onAction(row, "correct")}>修正</Button>
        {row.status === "proposed" && <Button size="small" danger onClick={() => onAction(row, "reject")}>拒绝</Button>}
        {row.status === "proposed" && <Button size="small" type="primary" onClick={() => onAction(row, "confirm")}>确认</Button>}
      </Space>, width: 180 },
    ]}
  />;
}

export default function VersionReview() {
  const [rows, setRows] = useState<P3VersionRelation[]>([]);
  const [status, setStatus] = useState("proposed");
  const [relationType, setRelationType] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [corrections, setCorrections] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    const query = new URLSearchParams();
    if (status) query.set("status", status);
    if (relationType) query.set("relation_type", relationType);
    try { setRows(await api.get<P3VersionRelation[]>(`/admin/p3/version-relations/review-needed?${query.toString()}`)); }
    catch (error) { message.error((error as Error).message); }
    finally { setLoading(false); }
  }, [status, relationType]);
  useEffect(() => { void load(); }, [load]);

  const act = async (row: P3VersionRelation, action: "confirm" | "reject" | "correct") => {
    if (!reviewer.trim() || !notes[row.id]?.trim()) { message.warning("请填写审核人和审核说明"); return; }
    let changes: Record<string, unknown> = {};
    if (action === "correct") {
      try { changes = JSON.parse(corrections[row.id] || "{}") as Record<string, unknown>; }
      catch { message.error("修正内容必须是 JSON"); return; }
    }
    const payload = { reviewer: reviewer.trim(), review_note: notes[row.id].trim(), ...changes };
    try {
      if (action === "correct") await api.put(`/admin/p3/version-relations/${row.id}`, payload);
      else await api.post(`/admin/p3/version-relations/${row.id}/${action}`, payload);
      message.success("版本关系审核已保存"); await load();
    } catch (error) { message.error((error as Error).message); }
  };

  return <Card title="P03 修正、替代和撤回审核" extra={<Space>
    <Input placeholder="审核人" value={reviewer} onChange={(event) => setReviewer(event.target.value)} style={{ width: 150 }} />
    <Select value={status} onChange={setStatus} style={{ width: 110 }} options={["proposed", "confirmed", "rejected"].map((value) => ({ value, label: STATUS_LABELS[value as keyof typeof STATUS_LABELS] }))} />
    <Select allowClear placeholder="关系类型" value={relationType || undefined} onChange={(value) => setRelationType(value || "")} style={{ width: 140 }} options={RELATION_TYPES.map((value) => ({ value, label: value }))} />
  </Space>}>
    <Alert type="info" showIcon message="候选关系不会自动撤回或替代事实；只有人工确认后才改变 Current 状态。" style={{ marginBottom: 12 }} />
    <div aria-busy={loading}><P3VersionReviewTable rows={rows} notes={notes} corrections={corrections}
      onNote={(id, value) => setNotes((old) => ({ ...old, [id]: value }))}
      onCorrection={(id, value) => setCorrections((old) => ({ ...old, [id]: value }))}
      onAction={(row, action) => void act(row, action)} /></div>
  </Card>;
}
