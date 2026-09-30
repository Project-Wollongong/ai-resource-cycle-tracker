import { Button, Card, Descriptions, Space, Table, Tag, Typography, message } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { PipelineRun } from "../api/types";

export default function DataRuns() {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  const load = useCallback(async () => setRuns(await api.get<PipelineRun[]>("/admin/pipeline-runs?limit=50")), []);
  useEffect(() => { void load(); }, [load]);
  const retry = async (id: number, failedOnly: boolean) => {
    setBusy(id);
    try { await api.post(`/admin/pipeline-runs/${id}/${failedOnly ? "retry-failed" : "retry"}`); message.success("重跑已提交"); await load(); }
    catch (e) { message.error((e as Error).message); }
    finally { setBusy(null); }
  };
  return <Card title="数据运行状态">
    <Table rowKey="id" dataSource={runs} expandable={{ expandedRowRender: (run) => <Descriptions size="small" column={2} bordered><Descriptions.Item label="Provider">{run.provider}</Descriptions.Item><Descriptions.Item label="配置快照">{JSON.stringify(run.configuration_snapshot ?? {})}</Descriptions.Item><Descriptions.Item label="失败摘要" span={2}>{run.error_summary ?? "-"}</Descriptions.Item></Descriptions> }} columns={[
      { title: "类型", render: (_, r) => `${r.pipeline_type ?? "daily"} / ${r.provider ?? "-"}` },
      { title: "开始", dataIndex: "started_at", render: (v: string | null) => v?.replace("T", " ").slice(0, 19) ?? "-" },
      { title: "状态", dataIndex: "status", render: (s: string) => <Tag color={s === "success" ? "green" : s === "partial" ? "orange" : s === "running" ? "blue" : "red"}>{s}</Tag> },
      { title: "成功/跳过/失败", render: (_, r) => `${r.succeeded_items ?? 0} / ${r.skipped_items ?? 0} / ${r.failed_items ?? 0}` },
      { title: "操作", render: (_, r) => <Space><Button size="small" loading={busy === r.id} onClick={() => void retry(r.id, true)}>重跑失败项</Button><Button size="small" onClick={() => void retry(r.id, false)}>重跑</Button></Space> },
    ]} />
    <Typography.Text type="secondary">Provider 凭证不会显示在此页面。</Typography.Text>
  </Card>;
}
