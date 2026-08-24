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
import type { Announcement, PriceBar, ScoreBrief, Signal, StockWithScore } from "../api/types";
import LabelTag from "../components/LabelTag";
import Pct from "../components/Pct";
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
  const [signals, setSignals] = useState<Signal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [resourceOverride, setResourceOverride] = useState<number | null>(null);
  const [riskOverride, setRiskOverride] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, p, sc, a, sg] = await Promise.all([
        api.get<StockWithScore>(`/stocks/${code}`),
        api.get<PriceBar[]>(`/stocks/${code}/prices?days=250`),
        api.get<ScoreBrief[]>(`/stocks/${code}/scores?days=120`),
        api.get<Announcement[]>(`/stocks/${code}/announcements?limit=50`),
        api.get<Signal[]>(`/stocks/${code}/signals?limit=200`),
      ]);
      setStock(s);
      setBars(p);
      setScores(sc);
      setAnnouncements(a);
      setSignals(sg);
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
      </Card>

      <StoryCard stock={stock} announcements={announcements} signals={signals} />

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
              width: 170,
              render: (t: string, a) => (
                <Tag color={a.type_score >= 70 ? "magenta" : a.type_score >= 50 ? "blue" : "default"}>
                  {t} {a.type_score}
                </Tag>
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
              title: "Context",
              key: "context",
              width: 230,
              filters: [
                { text: "Quality", value: "__quality", children: QUALITY_FILTERS },
                { text: "Materiality", value: "__materiality", children: MATERIALITY_FILTERS },
              ],
              onFilter: (value, a) => {
                const context = a.ai_metrics?.qualitative_context;
                if (!context) return false;
                return context.interval_quality_label === value || context.materiality_label === value;
              },
              render: (_, a) => {
                const context = a.ai_metrics?.qualitative_context;
                if (!context) return <Typography.Text type="secondary">No context</Typography.Text>;
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
              <QualitativeContextPanel
                context={a.ai_metrics?.qualitative_context ?? null}
                contexts={a.ai_metrics?.qualitative_contexts ?? null}
              />
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
