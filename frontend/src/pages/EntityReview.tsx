import { Alert, Button, Card, Input, Select, Space, Table, Tag, Typography, message } from "antd";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { P01EntityProposal, P01SourceSearchResult } from "../api/types";
import P3UpdateProposalReview from "../components/P3UpdateProposalReview";
import P3EntityMappingReview from "../components/P3EntityMappingReview";

export default function EntityReview() {
  const [rows, setRows] = useState<P01EntityProposal[]>([]);
  const [status, setStatus] = useState("pending");
  const [reviewer, setReviewer] = useState("");
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [sources, setSources] = useState<P01SourceSearchResult[]>([]);
  const [actions, setActions] = useState<Record<number, string>>({});
  const [corrections, setCorrections] = useState<Record<number, string>>({});
  const load = useCallback(async () => {
    setLoading(true);
    try { setRows(await api.get<P01EntityProposal[]>(`/admin/entity-proposals?status=${status}`)); }
    catch (e) { message.error((e as Error).message); }
    finally { setLoading(false); }
  }, [status]);
  useEffect(() => { void load(); }, [load]);
  const search = async () => {
    if (query.trim().length < 2) { message.warning("请输入至少 2 个字符"); return; }
    try { setSources(await api.get<P01SourceSearchResult[]>(`/admin/entity-source-search?q=${encodeURIComponent(query.trim())}`)); }
    catch (e) { message.error((e as Error).message); }
  };
  const review = async (id: number, action: string) => {
    if (!reviewer.trim()) { message.warning("请输入审核人"); return; }
    let correction: Record<string, unknown> = {};
    try { correction = corrections[id] ? JSON.parse(corrections[id]) as Record<string, unknown> : {}; }
    catch { message.error("修改内容必须是 JSON"); return; }
    try { await api.post(`/admin/entity-proposals/${id}/review`, { action, reviewer: reviewer.trim(), review_note: "", correction }); message.success("审核已保存"); await load(); }
    catch (e) { message.error((e as Error).message); }
  };
  return <Space direction="vertical" style={{ width: "100%" }}><Card title="资料搜索（只读来源检索）"><Space><Input placeholder="公告标题、ASX 编号或来源标题" value={query} onChange={(e) => setQuery(e.target.value)} onPressEnter={() => void search()} style={{ width: 360 }} /><Button onClick={() => void search()}>搜索</Button></Space><Table size="small" rowKey={(r) => `${r.source_type}-${r.source_id}`} dataSource={sources} pagination={{ pageSize: 5 }} columns={[{ title: "来源", dataIndex: "source_type" }, { title: "编号", dataIndex: "source_id" }, { title: "标题", dataIndex: "title" }, { title: "链接", dataIndex: "url", render: (v: string) => v ? <a href={v} target="_blank" rel="noreferrer">打开</a> : "-" }, { title: "下一步", render: () => <Typography.Text type="secondary">核对 PDF 页码/原文后人工录入 Proposed</Typography.Text> }]} /></Card><Card title="实体审核 / P01 Baseline" extra={<Space><Input placeholder="审核人" value={reviewer} onChange={(e) => setReviewer(e.target.value)} style={{ width: 140 }} /><Select value={status} onChange={setStatus} options={["pending", "approved", "rejected"].map((v) => ({ value: v, label: v }))} /></Space>}>
    {!reviewer && <Alert type="info" showIcon message="审核动作需要填写审核人；搜索和人工录入只进入 proposed dataset。" style={{ marginBottom: 12 }} />}
    <Table rowKey="id" loading={loading} dataSource={rows} scroll={{ x: 1100 }} columns={[
      { title: "股票", dataIndex: "stock_id", width: 70 },
      { title: "Proposed Project", dataIndex: "proposed_project_name" },
      { title: "Proposed Asset Unit", dataIndex: "proposed_asset_name", render: (v: string | null) => v || "-" },
      { title: "来源", render: (_: unknown, r: P01EntityProposal) => <Typography.Text ellipsis={{ tooltip: r.source_excerpt }}>{r.source_type}: {r.source_ref}{r.source_page ? ` p.${r.source_page}` : ""}</Typography.Text> },
      { title: "状态", dataIndex: "status", render: (v: string) => <Tag color={v === "approved" ? "green" : v === "rejected" ? "red" : "gold"}>{v}</Tag> },
      { title: "审核人", dataIndex: "reviewer", render: (v: string | null) => v || "-" },
      { title: "审核时间", dataIndex: "reviewed_at", render: (v: string | null) => v || "-" },
      { title: "操作", render: (_: unknown, r: P01EntityProposal) => r.status === "pending" ? <Space wrap><Select size="small" value={actions[r.id] || "approve"} onChange={(v) => setActions((old) => ({ ...old, [r.id]: v }))} options={["approve", "reject", "correct", "merge", "split", "rename", "adjust_project_asset_level", "adjust_commodity", "adjust_ownership", "adjust_operator"].map((v) => ({ value: v, label: v }))} style={{ width: 180 }} /><Input size="small" placeholder='修改 JSON，例如 {"proposed_commodity":"copper"}' value={corrections[r.id] || ""} onChange={(e) => setCorrections((old) => ({ ...old, [r.id]: e.target.value }))} style={{ width: 240 }} /><Button size="small" onClick={() => void review(r.id, actions[r.id] || "approve")}>提交</Button></Space> : null },
    ]} />
  </Card><P3EntityMappingReview reviewer={reviewer} /><P3UpdateProposalReview reviewer={reviewer} /></Space>;
}
