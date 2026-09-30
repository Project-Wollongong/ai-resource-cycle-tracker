import { Alert, Button, Card, Checkbox, Col, DatePicker, Descriptions, Input, Modal, Row, Select, Space, Statistic, Table, Tag, Typography, message } from "antd";
import type { Dayjs } from "dayjs";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { BackfillPreview, BackfillRun, BackfillRunItem } from "../api/types";

const FAMILIES = ["F01", "F02", "F03", "F04", "F05", "F06", "F07", "F08"];
const PARSER_VERSION = "p3_reported_fact_v7_version_relations";

type Options = {
  download_missing_pdf: boolean; extract_raw_text: boolean; parse_document: boolean;
  classify_events: boolean; extract_facts: boolean; map_entities: boolean;
  check_version_relations: boolean; only_failed: boolean; only_unparsed: boolean;
};

export function BackfillPanel() {
  const [stocks, setStocks] = useState("");
  const [announcements, setAnnouncements] = useState("");
  const [dates, setDates] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [families, setFamilies] = useState<string[]>([]);
  const [parserVersion, setParserVersion] = useState(PARSER_VERSION);
  const [options, setOptions] = useState<Options>({ download_missing_pdf: false, extract_raw_text: true, parse_document: true, classify_events: true, extract_facts: true, map_entities: true, check_version_relations: true, only_failed: false, only_unparsed: true });
  const [preview, setPreview] = useState<BackfillPreview | null>(null);
  const [runs, setRuns] = useState<BackfillRun[]>([]);
  const [items, setItems] = useState<BackfillRunItem[] | null>(null);
  const [busy, setBusy] = useState(false);
  const loadRuns = useCallback(async () => setRuns(await api.get<BackfillRun[]>("/admin/backfill/runs")), []);
  useEffect(() => { void loadRuns(); }, [loadRuns]);
  const payload = useMemo(() => ({
    stock_codes: stocks.split(/[\s,]+/).filter(Boolean),
    announcement_ids: announcements.split(/[\s,]+/).filter(Boolean),
    date_from: dates?.[0]?.format("YYYY-MM-DD") ?? null,
    date_to: dates?.[1]?.format("YYYY-MM-DD") ?? null,
    event_families: families, parser_version: parserVersion, ...options,
  }), [stocks, announcements, dates, families, parserVersion, options]);
  const updateOption = (name: keyof Options, checked: boolean) => { setOptions((old) => ({ ...old, [name]: checked })); setPreview(null); };
  const doPreview = async () => {
    setBusy(true);
    try { setPreview(await api.post<BackfillPreview>("/admin/backfill/preview", payload)); }
    catch (error) { message.error((error as Error).message); }
    finally { setBusy(false); }
  };
  const execute = async () => {
    if (!preview) return;
    setBusy(true);
    try { await api.post("/admin/backfill/run", { ...payload, preview_token: preview.preview_token, requested_by: "admin-ui" }); message.success("回填运行完成"); setPreview(null); await loadRuns(); }
    catch (error) { message.error((error as Error).message); }
    finally { setBusy(false); }
  };
  const retry = async (id: number) => { setBusy(true); try { await api.post(`/admin/backfill/runs/${id}/retry-failed?requested_by=admin-ui`); await loadRuns(); } catch (error) { message.error((error as Error).message); } finally { setBusy(false); } };
  const viewItems = async (id: number) => { setBusy(true); try { setItems(await api.get<BackfillRunItem[]>(`/admin/backfill/runs/${id}/items`)); } catch (error) { message.error((error as Error).message); } finally { setBusy(false); } };
  const cancel = async (id: number) => { setBusy(true); try { await api.post(`/admin/backfill/runs/${id}/cancel`); await loadRuns(); } catch (error) { message.error((error as Error).message); } finally { setBusy(false); } };
  return <Space direction="vertical" size="large" style={{ width: "100%" }}>
    <Alert type="warning" showIcon message="本次只处理管理员选定范围，不会自动处理全部历史公告。" description="必须先 Preview；Preview 不下载 PDF、不调用模型、不写入 P3 Fact 或状态。" />
    <Card title="历史回填条件">
      <Row gutter={[16, 16]}>
        <Col span={8}><Typography.Text>股票代码（逗号分隔）</Typography.Text><Input aria-label="股票代码" value={stocks} onChange={(e) => { setStocks(e.target.value); setPreview(null); }} placeholder="CVV, AGY, WC8" /></Col>
        <Col span={8}><Typography.Text>公告 ID（逗号分隔）</Typography.Text><Input aria-label="公告 ID" value={announcements} onChange={(e) => { setAnnouncements(e.target.value); setPreview(null); }} /></Col>
        <Col span={8}><Typography.Text>日期范围</Typography.Text><DatePicker.RangePicker value={dates} onChange={(value) => { setDates(value as [Dayjs | null, Dayjs | null] | null); setPreview(null); }} /></Col>
        <Col span={8}><Typography.Text>Event Family</Typography.Text><Select mode="multiple" style={{ width: "100%" }} value={families} options={FAMILIES.map((value) => ({ value }))} onChange={(value) => { setFamilies(value); setPreview(null); }} /></Col>
        <Col span={8}><Typography.Text>Parser Version</Typography.Text><Input value={parserVersion} onChange={(e) => { setParserVersion(e.target.value); setPreview(null); }} /></Col>
      </Row>
      <Space wrap style={{ marginTop: 16 }}>
        {Object.entries({ download_missing_pdf: "下载缺失 PDF", extract_raw_text: "提取 Raw Text", parse_document: "运行解析", classify_events: "分类 Event", extract_facts: "提取 Fact", map_entities: "映射实体", check_version_relations: "检查修订关系", only_failed: "仅失败项", only_unparsed: "仅未解析" }).map(([key, label]) => <Checkbox key={key} checked={options[key as keyof Options]} onChange={(e) => updateOption(key as keyof Options, e.target.checked)}>{label}</Checkbox>)}
      </Space>
      <div style={{ marginTop: 16 }}><Button type="primary" loading={busy} onClick={() => void doPreview()}>Preview</Button></div>
    </Card>
    {preview && <Card title="Preview（只读）">
      <Row gutter={16}>{[
        ["预计处理", preview.total_announcements], ["跳过", preview.skipped_count], ["缺失 PDF", preview.missing_pdf], ["缺失 Raw Text", preview.missing_raw_text], ["未解析", preview.unparsed], ["预计下载", preview.estimated_downloads],
      ].map(([title, value]) => <Col span={4} key={String(title)}><Statistic title={title} value={value} /></Col>)}</Row>
      <Descriptions size="small" bordered column={2} style={{ marginTop: 16 }}><Descriptions.Item label="按股票">{JSON.stringify(preview.by_stock)}</Descriptions.Item><Descriptions.Item label="按 Family">{JSON.stringify(preview.by_family)}</Descriptions.Item><Descriptions.Item label="执行动作" span={2}>{preview.actions.join(" → ") || "无"}</Descriptions.Item></Descriptions>
      <Button type="primary" danger style={{ marginTop: 16 }} disabled={!preview.read_only || preview.total_announcements === 0} loading={busy} onClick={() => void execute()}>执行回填</Button>
    </Card>}
    <Card title="回填运行">
      <Table rowKey="id" dataSource={runs} columns={[
        { title: "Run", dataIndex: "id" }, { title: "状态", dataIndex: "status", render: (value: string) => <Tag>{value}</Tag> },
        { title: "范围", render: (_, row) => row.total_announcements }, { title: "成功/跳过/部分/失败", render: (_, row) => `${row.succeeded_announcements}/${row.skipped_announcements}/${row.partial_announcements}/${row.failed_announcements}` },
        { title: "Event / Fact / Mapping", render: (_, row) => `${row.created_events} / ${row.created_facts} / ${row.mapped_entities}` },
        { title: "版本", render: (_, row) => <>{row.parser_version}<br />{row.pipeline_version}</> },
        { title: "操作", render: (_, row) => <Space><Button size="small" loading={busy} onClick={() => void viewItems(row.id)}>查看运行详情</Button><Button size="small" disabled={!row.failed_announcements && !row.partial_announcements} loading={busy} onClick={() => void retry(row.id)}>重试失败项</Button>{row.status === "running" && <Button size="small" danger onClick={() => void cancel(row.id)}>取消</Button>}</Space> },
      ]} />
    </Card>
    <Modal open={items !== null} width={1000} title="BackfillRunItem 详情" footer={null} onCancel={() => setItems(null)}>
      <Table size="small" rowKey="id" dataSource={items ?? []} pagination={false} columns={[
        { title: "Announcement", dataIndex: "announcement_id" }, { title: "状态", dataIndex: "status" },
        { title: "失败阶段", dataIndex: "stage" }, { title: "Event", dataIndex: "created_event_count" },
        { title: "Fact", dataIndex: "created_fact_count" }, { title: "Mapping", dataIndex: "mapped_count" },
        { title: "错误原因", dataIndex: "error_message", render: (value: string | null) => value ?? "-" },
      ]} />
    </Modal>
  </Space>;
}

export default function Backfill() { return <BackfillPanel />; }
