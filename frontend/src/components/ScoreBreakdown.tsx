import { Descriptions, Space, Tag, Typography } from "antd";

import ConfidenceTag from "./ConfidenceTag";

import type { ScoreBrief } from "../api/types";
import StatusPill from "./StatusPill";

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

interface SentimentComponent {
  value?: number;
  source?: string;
  label?: string;
  note?: string;
}

interface RiskComponent {
  value?: number;
  source?: string;
  label?: string;
  note?: string;
  liquidity_adjust?: number;
  event_adjust?: number;
  liquidity?: {
    dollar_turnover?: number;
    min_dollar_turnover?: number;
    label?: string;
  };
  events?: {
    headline: string;
    type: string;
    age_days: number;
    price_sensitive: boolean;
    adjustment: number;
    reason: string;
  }[];
}

/** Renders the persisted components JSON: the explainability contract. */
/**
 * A sub-score heading that says how much it counts and whether it was measured.
 *
 * A defaulted 50 and a measured 50 are the same number and mean opposite
 * things: one is "we looked and it is middling", the other is "we have no
 * source at all". The scorer records which in `source`, and the detail page is
 * the one place that marker reaches the screen, so it is spent here.
 */
function SubScoreLabel({
  name,
  weight,
  value,
  defaulted,
  note,
}: {
  name: string;
  weight?: string;
  value: number;
  defaulted?: boolean;
  note?: string;
}) {
  return (
    <Space size={7} align="baseline" wrap>
      <span style={{ fontWeight: 580 }}>{name}</span>
      {weight && <span className="micro">{weight}</span>}
      <span className="num" style={{ color: defaulted ? "var(--ink-faint)" : "var(--ink)" }}>
        {value.toFixed(0)}
      </span>
      {defaulted && <ConfidenceTag level="absent" note={note} />}
    </Space>
  );
}

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
  const risk = (comps.risk ?? {}) as RiskComponent;
  const sentiment = (comps.sentiment ?? {}) as SentimentComponent;

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
      <Descriptions.Item
        label={<SubScoreLabel name="资金确认" weight="不计入 Cycle Score" value={score.funding_score} />}
      >
        <div>
          <Tag color="purple">Funding confirmation</Tag>
          <Text style={{ color: "var(--ink-faint)" }}>单独跟踪，不计入 Cycle Score。</Text>
        </div>
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
      <Descriptions.Item
        label={<SubScoreLabel name="公告" weight="权重 40%" value={score.announcement_score} />}
      >
        {announcement.note === "no_announcements_30d" && (
          <Text style={{ color: "var(--ink-faint)" }}>近 30 天无公告。</Text>
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
      <Descriptions.Item
        label={
          <SubScoreLabel
            name="资源"
            weight="权重 20%"
            value={score.resource_score}
            defaulted={resource.source === "neutral_default"}
            note="无定性上下文可用，取中性默认值"
          />
        }
      >
        <ResourceBreakdown resource={resource} />
      </Descriptions.Item>
      <Descriptions.Item
        label={
          <SubScoreLabel
            name="商品"
            weight="权重 20%"
            value={score.commodity_score}
            defaulted={Boolean(commodity.note)}
            note="商品价格数据不足，取中性默认值"
          />
        }
      >
        {commodity.note ? (
          <Text style={{ color: "var(--ink-faint)" }}>商品价格数据不足，取中性默认值 50。</Text>
        ) : (
          <Text type="secondary">
            {commodity.instrument}: 20d {commodity.r20_pct}%, 60d {commodity.r60_pct}%
          </Text>
        )}
      </Descriptions.Item>
      <Descriptions.Item
        label={<SubScoreLabel name="风险" weight="权重 10% · 越高越安全" value={score.risk_score} />}
      >
        <RiskBreakdown risk={risk} />
      </Descriptions.Item>
      <Descriptions.Item
        label={
          <SubScoreLabel
            name="情绪"
            weight="权重 10%"
            value={score.sentiment_score}
            defaulted={sentiment.source === "neutral_default"}
            note="尚未接入任何情绪数据源"
          />
        }
      >
        <Text type="secondary">
          {sentiment.source === "neutral_default"
            ? "固定为中性默认值 50 —— 论坛与社交情绪数据尚未接入，此项目前不参与判断。"
            : `${sentiment.label ?? "情绪"}（来源 ${sentiment.source ?? "未知"}）`}
        </Text>
        {sentiment.label && <Tag style={{ marginLeft: 6 }}>{sentiment.label}</Tag>}
      </Descriptions.Item>
    </Descriptions>
  );
}

function RiskBreakdown({ risk }: { risk: RiskComponent }) {
  if (risk.source === "manual_override") {
    return <Text type="secondary">Manual override. Higher is safer.</Text>;
  }
  if (risk.source !== "rules_v1") {
    return <Text type="secondary">Neutral default 50.</Text>;
  }

  return (
    <div>
      <div>
        <Tag color={risk.label === "elevated_risk" ? "red" : risk.label === "watch_risk" ? "orange" : "green"}>
          {risk.label ?? "neutral"}
        </Tag>
        <Tag>liquidity {risk.liquidity_adjust ?? 0}</Tag>
        <Tag>events {risk.event_adjust ?? 0}</Tag>
        {risk.liquidity?.label && <Tag>{risk.liquidity.label}</Tag>}
      </div>
      {risk.liquidity && (
        <div>
          <Text type="secondary">
            Turnover A${((risk.liquidity.dollar_turnover ?? 0) / 1000).toFixed(0)}k; floor A$
            {((risk.liquidity.min_dollar_turnover ?? 0) / 1000).toFixed(0)}k.
          </Text>
        </div>
      )}
      {(risk.events ?? []).slice(0, 4).map((event) => (
        <div key={`${event.type}-${event.headline}`} style={{ marginTop: 4 }}>
          <StatusPill level="caution" hint="Risk 子分的扣减项">{event.adjustment}</StatusPill>
          <Tag>{event.type}</Tag>
          <Text type="secondary">
            {event.age_days}d ago: {event.reason}. {event.headline}
          </Text>
        </div>
      ))}
      {risk.note && (
        <div>
          <Text type="secondary">{risk.note}</Text>
        </div>
      )}
    </div>
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
        <span className="micro">定性上下文 · 自动</span>
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
