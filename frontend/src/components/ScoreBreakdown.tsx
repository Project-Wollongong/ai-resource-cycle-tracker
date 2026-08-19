import { Descriptions, Tag, Typography } from "antd";

import type { ScoreBrief } from "../api/types";

const { Text } = Typography;

interface FundingComponent {
  points: number;
  max: number;
  value?: number | null;
  note?: string | null;
  window?: number | null;
  days?: number;
  day_change_pct?: number | null;
  dollar_turnover?: number;
}

interface AnnComponentItem {
  headline: string;
  type: string;
  base: number;
  qualitative_bonus?: number;
  adjusted_base?: number;
  age_days: number;
  decay: number;
  price_sensitive: boolean;
  effective: number;
  interval_quality_label?: string | null;
  materiality_label?: string | null;
  grade_thickness?: number | null;
  qualitative_assessment?: string | null;
}

interface ResourceContextItem {
  ann_id: string;
  date: string;
  headline: string;
  score: number;
  interval_quality_label?: string | null;
  materiality_label?: string | null;
  trend_vs_previous?: string | null;
  depth_category?: string | null;
  grade_thickness?: number | null;
  percentile?: number | null;
  assessment?: string | null;
}

interface ResourceComponent {
  value?: number;
  source?: string;
  note?: string;
  lookback_days?: number;
  context_count?: number;
  used_count?: number;
  best_context_score?: number;
  avg_context_score?: number;
  items?: ResourceContextItem[];
}

/** Renders the persisted components JSON: the explainability contract. */
export default function ScoreBreakdown({ score }: { score: ScoreBrief }) {
  const comps = (score.components ?? {}) as Record<string, unknown>;
  const funding = (comps.funding ?? {}) as Record<string, FundingComponent>;
  const announcement = (comps.announcement ?? {}) as {
    announcements?: AnnComponentItem[];
    best?: number;
    bonus?: number;
    note?: string;
  };
  const commodity = (comps.commodity ?? {}) as {
    instrument?: string;
    r20_pct?: number;
    r60_pct?: number;
    note?: string;
  };
  const resource = (comps.resource ?? {}) as ResourceComponent;
  const risk = (comps.risk ?? {}) as { value?: number; source?: string };

  const fundingRow = (name: string, c?: FundingComponent, extra?: string) =>
    c ? (
      <div key={name}>
        <Text strong>
          {name}: {c.points}/{c.max}
        </Text>{" "}
        {extra && <Text type="secondary">{extra}</Text>}
        {c.note && <Tag style={{ marginLeft: 6 }}>{c.note}</Tag>}
      </div>
    ) : null;

  const qualitativeContext = (a: AnnComponentItem) =>
    a.interval_quality_label || a.materiality_label ? (
      <div style={{ marginLeft: 28 }}>
        {a.interval_quality_label && <Tag color="blue">quality: {a.interval_quality_label}</Tag>}
        {a.materiality_label && <Tag color="orange">materiality: {a.materiality_label}</Tag>}
        {a.qualitative_bonus ? <Tag color="purple">qualitative +{a.qualitative_bonus}</Tag> : null}
        {a.grade_thickness != null && <Tag>GT {a.grade_thickness}</Tag>}
        {a.qualitative_assessment && <Text type="secondary">{a.qualitative_assessment}</Text>}
      </div>
    ) : null;

  return (
    <Descriptions column={1} size="small" bordered>
      <Descriptions.Item label={`Funding ${score.funding_score.toFixed(0)}`}>
        {fundingRow(
          "Relative volume",
          funding.rel_vol,
          funding.rel_vol?.value != null
            ? `rel_vol=${funding.rel_vol.value}x, day=${funding.rel_vol.day_change_pct ?? "-"}%, turnover A$${(
                (funding.rel_vol.dollar_turnover ?? 0) / 1000
              ).toFixed(0)}k`
            : undefined,
        )}
        {fundingRow(
          "Breakout",
          funding.breakout,
          funding.breakout?.window ? `${funding.breakout.window}d high` : "no breakout",
        )}
        {fundingRow("Consecutive up", funding.consecutive_up, `${funding.consecutive_up?.days ?? 0}d`)}
        {fundingRow(
          "Volume trend",
          funding.vol_trend,
          funding.vol_trend?.value != null ? `MA5/MA20=${funding.vol_trend.value}` : undefined,
        )}
      </Descriptions.Item>
      <Descriptions.Item label={`Announcement ${score.announcement_score.toFixed(0)}`}>
        {announcement.note === "no_announcements_30d" && (
          <Text type="secondary">No announcements in 30 days.</Text>
        )}
        {(announcement.announcements ?? []).slice(0, 5).map((a, i) => (
          <div key={i}>
            <Tag>{a.type}</Tag>
            {a.price_sensitive && "PS"} {a.headline}{" "}
            <Text type="secondary">
              base {a.base}
              {a.qualitative_bonus ? ` + qualitative ${a.qualitative_bonus}` : ""}
              {a.adjusted_base != null && a.adjusted_base !== a.base ? ` = ${a.adjusted_base}` : ""} x decay{" "}
              {a.decay}
              {a.price_sensitive ? " x 1.2" : ""} = {a.effective}
            </Text>
            {qualitativeContext(a)}
          </div>
        ))}
        {announcement.bonus ? (
          <div>
            <Text type="secondary">bonus +{announcement.bonus}</Text>
          </div>
        ) : null}
      </Descriptions.Item>
      <Descriptions.Item label={`Resource ${score.resource_score.toFixed(0)}`}>
        <ResourceBreakdown resource={resource} />
      </Descriptions.Item>
      <Descriptions.Item label={`Commodity ${score.commodity_score.toFixed(0)}`}>
        {commodity.note ? (
          <Text type="secondary">Insufficient commodity data; neutral 50.</Text>
        ) : (
          <Text type="secondary">
            {commodity.instrument}: 20d {commodity.r20_pct}%, 60d {commodity.r60_pct}%
          </Text>
        )}
      </Descriptions.Item>
      <Descriptions.Item label={`Risk ${score.risk_score.toFixed(0)}`}>
        <Text type="secondary">
          {risk.source === "manual_override" ? "Manual override. Higher is safer." : "Neutral default 50."}
        </Text>
      </Descriptions.Item>
    </Descriptions>
  );
}

function ResourceBreakdown({ resource }: { resource: ResourceComponent }) {
  if (resource.source === "manual_override") {
    return <Text type="secondary">Manual override.</Text>;
  }
  if (resource.source !== "qualitative_context_auto") {
    return (
      <Text type="secondary">
        Neutral default 50{resource.note ? ` (${resource.note})` : ""}.
      </Text>
    );
  }

  return (
    <div>
      <div>
        <Tag color="green">qualitative context auto</Tag>
        <Tag>lookback {resource.lookback_days}d</Tag>
        <Tag>contexts {resource.context_count}</Tag>
        <Tag>used {resource.used_count}</Tag>
        <Tag>best {resource.best_context_score}</Tag>
        <Tag>avg {resource.avg_context_score}</Tag>
      </div>
      {(resource.items ?? []).slice(0, 4).map((item) => (
        <div key={`${item.ann_id}-${item.score}`} style={{ marginTop: 6 }}>
          <Text strong>{item.score}</Text>{" "}
          <Text>{item.date} {item.headline}</Text>
          <div style={{ marginLeft: 28 }}>
            {item.interval_quality_label && <Tag color="blue">quality: {item.interval_quality_label}</Tag>}
            {item.materiality_label && <Tag color="orange">materiality: {item.materiality_label}</Tag>}
            {item.trend_vs_previous && <Tag>trend: {item.trend_vs_previous}</Tag>}
            {item.depth_category && <Tag>depth: {item.depth_category}</Tag>}
            {item.percentile != null && <Tag>pct {item.percentile}</Tag>}
            {item.grade_thickness != null && <Tag>GT {item.grade_thickness}</Tag>}
            {item.assessment && <Text type="secondary">{item.assessment}</Text>}
          </div>
        </div>
      ))}
    </div>
  );
}
