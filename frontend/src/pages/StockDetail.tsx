import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  InputNumber,
  Row,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { Announcement, P3EntityMapping, P3Event, P3Fact, P3InformationPoint, P3ParseStatus, PriceBar, ScoreBrief, Signal, StockProject, StockWithScore } from "../api/types";
import LabelTag from "../components/LabelTag";
import Pct from "../components/Pct";
import { P3EventDetails, P3EventTags } from "../components/P3EventClassification";
import P3FactsTable, { hasDrillContext, neutralFactSummary } from "../components/P3FactsTable";
import P3InformationPoints from "../components/P3InformationPoints";
import P3EntityMappings from "../components/P3EntityMappings";
import PriceVolumeChart from "../components/PriceVolumeChart";
import QualitativeContextPanel from "../components/QualitativeContextPanel";
import ScoreBreakdown from "../components/ScoreBreakdown";
import ScoreHistoryChart from "../components/ScoreHistoryChart";
import SignalTable from "../components/SignalTable";
import StoryCard from "../components/StoryCard";

const QUALITY_FILTERS = ["exceptional", "strong", "moderate", "weak", "insufficient_history"].map((value) => ({
  text: value.replaceAll("_", " "),
  value,
}));

const MATERIALITY_FILTERS = ["high", "medium", "low", "insufficient_history"].map((value) => ({
  text: value.replaceAll("_", " "),
  value,
}));

function readable(value: string) {
  return value.replaceAll("_", " ");
}

export default function StockDetail() {
  const { code = "" } = useParams();
  const [stock, setStock] = useState<StockWithScore | null>(null);
  const [bars, setBars] = useState<PriceBar[]>([]);
  const [scores, setScores] = useState<ScoreBrief[]>([]);
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [parseStatuses, setParseStatuses] = useState<Record<string, P3ParseStatus>>({});
  const [parseEvents, setParseEvents] = useState<Record<string, P3Event[]>>({});
  const [parseFacts, setParseFacts] = useState<Record<string, P3Fact[]>>({});
  const [informationPoints, setInformationPoints] = useState<Record<string, P3InformationPoint[]>>({});
  const [entityMappings, setEntityMappings] = useState<Record<string, P3EntityMapping[]>>({});
  const [signals, setSignals] = useState<Signal[]>([]);
  const [projects, setProjects] = useState<StockProject[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [resourceOverride, setResourceOverride] = useState<number | null>(null);
  const [riskOverride, setRiskOverride] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [retryingEvidence, setRetryingEvidence] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, p, sc, a, sg, ps] = await Promise.all([
        api.get<StockWithScore>(`/stocks/${code}`),
        api.get<PriceBar[]>(`/stocks/${code}/prices?days=250`),
        api.get<ScoreBrief[]>(`/stocks/${code}/scores?days=120`),
        api.get<Announcement[]>(`/stocks/${code}/announcements?limit=50`),
        api.get<Signal[]>(`/stocks/${code}/signals?limit=200`),
        api.get<StockProject[]>(`/stocks/${code}/projects`),
      ]);
      setStock(s);
      setBars(p);
      setScores(sc);
      setAnnouncements(a);
      const parseEntries = await Promise.all(a.map(async (item) => {
        try { return [item.ann_id, await api.get<P3ParseStatus>(`/announcements/${item.ann_id}/parse-status`)] as const; }
        catch { return [item.ann_id, { announcement_id: item.ann_id, parse_status: "unparsed", event_count: 0, fact_count: 0, information_point_count: 0, atomic_fact_count: 0, target_min: 20, target_max: 50, count_status: "source_insufficient", source_insufficient: true, summary_point_count: 0, standard_form_point_count: 0, body_fallback_point_count: 0, review_needed_count: 0, summary_coverage_ratio: 0, review_needed: false } as P3ParseStatus] as const; }
      }));
      setParseStatuses(Object.fromEntries(parseEntries));
      const eventEntries = await Promise.all(a.map(async (item) => {
        try { return [item.ann_id, await api.get<P3Event[]>(`/announcements/${item.ann_id}/events`)] as const; }
        catch { return [item.ann_id, []] as const; }
      }));
      setParseEvents(Object.fromEntries(eventEntries));
      const factEntries = await Promise.all(a.map(async (item) => {
        try { return [item.ann_id, await api.get<P3Fact[]>(`/announcements/${item.ann_id}/facts`)] as const; }
        catch { return [item.ann_id, []] as const; }
      }));
      setParseFacts(Object.fromEntries(factEntries));
      const pointEntries = await Promise.all(a.map(async (item) => {
        try { return [item.ann_id, await api.get<P3InformationPoint[]>(`/announcements/${item.ann_id}/information-points`)] as const; }
        catch { return [item.ann_id, []] as const; }
      }));
      setInformationPoints(Object.fromEntries(pointEntries));
      const mappingEntries = await Promise.all(a.map(async (item) => {
        try { return [item.ann_id, await api.get<P3EntityMapping[]>(`/announcements/${item.ann_id}/entity-mappings`)] as const; }
        catch { return [item.ann_id, []] as const; }
      }));
      setEntityMappings(Object.fromEntries(mappingEntries));
      setSignals(sg);
      setProjects(ps);
      setResourceOverride(s.resource_score_override);
      setRiskOverride(s.risk_score_override);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [code]);

  useEffect(() => {
    void load();
  }, [load]);

  const saveOverrides = async () => {
    setSaving(true);
    try {
      await api.put(`/stocks/${code}`, {
        resource_score_override: resourceOverride,
        risk_score_override: riskOverride,
        clear_resource_override: resourceOverride === null,
        clear_risk_override: riskOverride === null,
      });
      message.success("已保存，下次评分生效");
      await load();
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const retryEvidence = async (evidenceId: number) => {
    setRetryingEvidence(evidenceId);
    try {
      await api.post(`/announcements/evidence/${evidenceId}/retry`);
      message.success("Evidence retry finished");
      await load();
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setRetryingEvidence(null);
    }
  };

  if (error) return <Alert type="error" message={error} />;
  if (!stock) return <Card loading />;

  const latest = stock.latest_score;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card size="small">
        <Space size="large" wrap>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {stock.code} · {stock.name}
          </Typography.Title>
          <Tag>{stock.commodity}</Tag>
          <Tag>{stock.stage}</Tag>
          <span>
            收盘 <b>{stock.last_close?.toFixed(3) ?? "-"}</b> <Pct value={stock.day_change_pct} />
          </span>
          {latest && (
            <span>
              Cycle Score <b>{latest.cycle_score.toFixed(1)}</b> <LabelTag label={latest.label} />
            </span>
          )}
          <Link to="/">返回雷达</Link>
        </Space>
        <Descriptions column={3} size="small" style={{ marginTop: 12 }}>
          <Descriptions.Item label="市场 / 货币">
            {stock.exchange} / {stock.trading_currency}
          </Descriptions.Item>
          <Descriptions.Item label="上市状态">{stock.listing_status}</Descriptions.Item>
          <Descriptions.Item label="Pilot Universe">
            {stock.pilot_universe_member ? "Included" : "Excluded"}
          </Descriptions.Item>
          <Descriptions.Item label="行业">{stock.sector || "暂无"}</Descriptions.Item>
          <Descriptions.Item label="公司类型">{stock.business_type || "暂无"}</Descriptions.Item>
          <Descriptions.Item label="历史身份" span={3}>
            {stock.identity_history.filter((item) => !item.is_current).length > 0 ? (
              <Space size={[4, 4]} wrap>
                {stock.identity_history
                  .filter((item) => !item.is_current)
                  .map((item) => (
                    <Tag key={item.id}>
                      {item.kind === "ticker" ? "代码" : "名称"}: {item.value}
                    </Tag>
                  ))}
              </Space>
            ) : (
              "暂无"
            )}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <StoryCard stock={stock} announcements={announcements} signals={signals} />

      <Card size="small" title={`项目与资产单元 (${projects.length})`}>
        {projects.length === 0 ? (
          <Typography.Text type="secondary">暂无已建立的项目关系</Typography.Text>
        ) : (
          <Space direction="vertical" style={{ width: "100%" }}>
            {projects.map((project) => (
              <div key={project.id}>
                <Typography.Text strong><Link to={`/projects/${encodeURIComponent(project.project_key)}`}>{project.name}</Link></Typography.Text>
                <Tag style={{ marginLeft: 8 }}>{project.relationship_type}</Tag>
                {project.ownership_pct != null && <Tag>{project.ownership_pct}% ownership</Tag>}
                {project.operator_name && <Tag>Operator: {project.operator_name}</Tag>}
                <div style={{ marginTop: 4 }}>
                  {project.asset_units.length === 0 ? (
                    <Typography.Text type="secondary">暂无 Asset Unit</Typography.Text>
                  ) : (
                    <Space size={[4, 4]} wrap>
                      {project.asset_units.map((unit) => <Tag key={unit.id}>{unit.name}{unit.unit_type ? ` · ${unit.unit_type}` : ""}</Tag>)}
                    </Space>
                  )}
                </div>
              </div>
            ))}
          </Space>
        )}
      </Card>

      <Card size="small" title="价格 / 成交量 / 信号点标注">
        <PriceVolumeChart bars={bars} signals={signals} />
      </Card>

      <Row gutter={16}>
        <Col span={12}>
          <Card size="small" title="评分拆解（可解释）" style={{ height: "100%" }}>
            {latest ? <ScoreBreakdown score={latest} /> : "未评分"}
            <Descriptions column={2} size="small" style={{ marginTop: 12 }}>
              <Descriptions.Item label="Resource 覆盖">
                <InputNumber
                  min={0}
                  max={100}
                  value={resourceOverride}
                  onChange={setResourceOverride}
                  placeholder="默认50"
                />
              </Descriptions.Item>
              <Descriptions.Item label="Risk 覆盖（越高越安全）">
                <InputNumber min={0} max={100} value={riskOverride} onChange={setRiskOverride} placeholder="默认50" />
              </Descriptions.Item>
            </Descriptions>
            <Button size="small" type="primary" onClick={saveOverrides} loading={saving}>
              保存覆盖值
            </Button>
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title="分数历史" style={{ height: "100%" }}>
            <ScoreHistoryChart scores={scores} />
          </Card>
        </Col>
      </Row>

      <Card size="small" title={`公告（${announcements.length}）`}>
        <Table
          size="small"
          rowKey="id"
          dataSource={announcements}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          columns={[
            {
              title: "日期",
              dataIndex: "ann_date",
              width: 120,
              render: (d: string) => d.slice(0, 10),
            },
            {
              title: "类型",
              dataIndex: "ann_type",
              width: 320,
              render: (t: string, a) => (
                <Space direction="vertical" size={3}>
                  <Tag color="blue">{a.document_category || t}</Tag>
                  <P3EventTags events={parseEvents[a.ann_id] ?? []} revisionTags={a.revision_tags ?? []} />
                </Space>
              ),
            },
            {
              title: "标题",
              dataIndex: "headline",
              render: (h: string, a) => (
                <a href={a.url} target="_blank" rel="noreferrer">
                  {a.price_sensitive && "PS "} {h}
                </a>
              ),
            },
            {
              title: "摘要",
              key: "fact_summary",
              width: 300,
              render: (_, a) => neutralFactSummary(parseFacts[a.ann_id] ?? []),
            },
            {
              title: "Evidence",
              key: "evidence",
              width: 190,
              render: (_, a) => {
                const status = a.text_status === "extracted" ? "Raw Text 已提取" : a.download_status === "downloaded" ? "系统已保存" : a.download_status === "failed" ? "下载失败" : "等待下载";
                const parsed = parseStatuses[a.ann_id];
                return (
                  <Space size={4} wrap>
                    <Tag color={a.text_status === "extracted" ? "green" : a.download_status === "failed" ? "red" : "blue"}>{status}</Tag>
                    <Tag color={parsed?.review_needed ? "orange" : parsed?.parse_status === "parsed" ? "cyan" : "default"}>{parsed?.parse_status === "parsed" ? `已解析 ${parsed.event_count} Event / ${parsed.information_point_count} 信息点 / ${parsed.fact_count} Fact` : parsed?.parse_status === "review_needed" ? `待人工复核 · ${parsed.information_point_count} 信息点` : parsed?.parse_status === "failed" ? "解析失败" : "未解析"}</Tag>
                    {a.local_pdf_available && a.evidence_document_id && <a href={`/api/announcements/evidence/${a.evidence_document_id}/original`} target="_blank" rel="noreferrer">原始 PDF</a>}
                    {a.evidence_retryable && a.evidence_document_id && <Button size="small" loading={retryingEvidence === a.evidence_document_id} onClick={() => void retryEvidence(a.evidence_document_id!)}>重试</Button>}
                  </Space>
                );
              },
            },
            {
              title: "Drill Context",
              key: "context",
              width: 230,
              filters: [
                { text: "Quality", value: "__quality", children: QUALITY_FILTERS },
                { text: "Materiality", value: "__materiality", children: MATERIALITY_FILTERS },
              ],
              onFilter: (value, a) => {
                if (!hasDrillContext(parseEvents[a.ann_id] ?? [])) return false;
                const context = a.ai_metrics?.qualitative_context;
                if (!context) return false;
                return context.interval_quality_label === value || context.materiality_label === value;
              },
              render: (_, a) => {
                const isDrilling = hasDrillContext(parseEvents[a.ann_id] ?? []);
                if (!isDrilling) return <Typography.Text type="secondary">不适用</Typography.Text>;
                const context = a.ai_metrics?.qualitative_context;
                if (!context) return <Typography.Text type="secondary">未找到钻探上下文</Typography.Text>;
                const contextCount = a.ai_metrics?.qualitative_contexts?.length ?? 1;
                return (
                  <Space size={4} wrap>
                    <Tag color={context.interval_quality_label === "insufficient_history" ? "warning" : "blue"}>
                      {readable(context.interval_quality_label)}
                    </Tag>
                    <Tag
                      color={
                        context.materiality_label === "high"
                          ? "red"
                          : context.materiality_label === "medium"
                            ? "orange"
                            : context.materiality_label === "insufficient_history"
                              ? "warning"
                              : "default"
                      }
                    >
                      {readable(context.materiality_label)}
                    </Tag>
                    {contextCount > 1 && <Tag>{contextCount} intercepts</Tag>}
                  </Space>
                );
              },
            },
          ]}
          expandable={{
            expandedRowRender: (a) => (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Descriptions size="small" column={3} bordered>
                  <Descriptions.Item label="ASX 公告编号">{a.ann_id}</Descriptions.Item>
                  <Descriptions.Item label="抓取时间">{a.fetched_at ?? "-"}</Descriptions.Item>
                  <Descriptions.Item label="页数">{a.page_count ?? "-"}</Descriptions.Item>
                  <Descriptions.Item label="文件大小">{a.file_size_bytes ? `${Math.round(a.file_size_bytes / 1024)} KB` : "-"}</Descriptions.Item>
                  <Descriptions.Item label="Hash">{a.hash_prefix ?? "-"}</Descriptions.Item>
                  <Descriptions.Item label="Evidence 状态">{a.evidence_status ?? "metadata_only"}</Descriptions.Item>
                  <Descriptions.Item label="官方文档类别">{a.document_category || "-"}</Descriptions.Item>
                  <Descriptions.Item label="ASX Header Type">{a.official_header_type || "-"}</Descriptions.Item>
                  <Descriptions.Item label="ASX Sub-type / Form">{a.official_subtype || a.standard_form || "-"}</Descriptions.Item>
                  <Descriptions.Item label="失败原因" span={3}>{a.evidence_error ?? "-"}</Descriptions.Item>
                  <Descriptions.Item label="外部 ASX 原链接" span={3}><a href={a.url} target="_blank" rel="noreferrer">打开外部链接</a></Descriptions.Item>
                </Descriptions>
                <P3EventTags events={parseEvents[a.ann_id] ?? []} revisionTags={a.revision_tags ?? []} />
                <P3EventDetails events={parseEvents[a.ann_id] ?? []} parserVersion={parseStatuses[a.ann_id]?.latest_parse_run?.parser_version} />
                <Typography.Title level={5} style={{ margin: "8px 0 0" }}>实体映射</Typography.Title>
                <P3EntityMappings mappings={entityMappings[a.ann_id] ?? []} />
                <Typography.Title level={5} style={{ margin: "8px 0 0" }}>逻辑信息点</Typography.Title>
                <P3InformationPoints points={informationPoints[a.ann_id] ?? []} status={parseStatuses[a.ann_id]} />
                <Typography.Title level={5} style={{ margin: "8px 0 0" }}>已提取事实</Typography.Title>
                <P3FactsTable facts={parseFacts[a.ann_id] ?? []} />
                {hasDrillContext(parseEvents[a.ann_id] ?? []) && (
                  <QualitativeContextPanel
                    context={a.ai_metrics?.qualitative_context ?? null}
                    contexts={a.ai_metrics?.qualitative_contexts ?? null}
                  />
                )}
              </Space>
            ),
          }}
        />
      </Card>

      <Card size="small" title={`信号历史（${signals.length}）`}>
        <SignalTable signals={signals} showStock={false} />
      </Card>
    </Space>
  );
}
