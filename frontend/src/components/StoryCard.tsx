import { Alert, Card, Col, List, Row, Space, Tag, Typography } from "antd";

import type { Announcement, ScoreBrief, Signal, StockWithScore } from "../api/types";
import LabelTag from "./LabelTag";

const { Text } = Typography;

interface AnnouncementComponentItem {
  headline?: string;
  type?: string;
  base?: number;
  effective?: number;
  price_sensitive?: boolean;
  interval_quality_label?: string | null;
  materiality_label?: string | null;
  qualitative_assessment?: string | null;
}

interface RiskEvent {
  headline?: string;
  type?: string;
  age_days?: number;
  adjustment?: number;
  reason?: string;
}

interface StoryComponents {
  funding?: {
    rel_vol?: {
      value?: number | null;
      day_change_pct?: number | null;
      dollar_turnover?: number | null;
      note?: string | null;
    };
    breakout?: {
      window?: number | null;
    };
    consecutive_up?: {
      days?: number;
    };
    vol_trend?: {
      value?: number | null;
    };
  };
  announcement?: {
    announcements?: AnnouncementComponentItem[];
    note?: string;
  };
  commodity?: {
    instrument?: string;
    r20_pct?: number;
    r60_pct?: number;
    note?: string;
  };
  resource?: {
    source?: string;
    note?: string;
    context_count?: number;
    best_context_score?: number;
    items?: {
      headline?: string;
      score?: number;
      interval_quality_label?: string | null;
      materiality_label?: string | null;
      trend_vs_previous?: string | null;
      assessment?: string | null;
    }[];
  };
  risk?: {
    source?: string;
    label?: string;
    liquidity_adjust?: number;
    event_adjust?: number;
    liquidity?: {
      label?: string;
      dollar_turnover?: number;
    };
    events?: RiskEvent[];
    note?: string;
  };
  sentiment?: {
    source?: string;
    label?: string;
    note?: string;
  };
}

export default function StoryCard({
  stock,
  announcements,
  signals,
}: {
  stock: StockWithScore;
  announcements: Announcement[];
  signals: Signal[];
}) {
  const latest = stock.latest_score;
  if (!latest) {
    return <Alert type="info" message="No Story Card yet. Run the pipeline to generate a score first." />;
  }

  const components = (latest.components ?? {}) as StoryComponents;
  const thesis = buildThesis(stock, latest, components, announcements, signals);
  const market = buildMarketConfirmation(latest, components, stock, signals);
  const risk = buildRisk(latest, components);
  const watchNext = buildWatchNext(latest, components, signals);

  return (
    <Card
      size="small"
      title="Story Card"
      extra={
        <Space>
          <Text strong>{latest.cycle_score.toFixed(1)}</Text>
          <LabelTag label={latest.label} />
        </Space>
      }
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Alert
          type={latest.cycle_score >= 70 ? "success" : latest.cycle_score >= 55 ? "warning" : "info"}
          message={thesis.title}
          description={thesis.description}
          showIcon
        />
        <Row gutter={[12, 12]}>
          <Col span={12}>
            <StorySection title="Story" color="blue" items={thesis.items} />
          </Col>
          <Col span={12}>
            <StorySection title="Market Confirmation" color="purple" items={market} />
          </Col>
          <Col span={12}>
            <StorySection title="Risk" color={risk.color} items={risk.items} />
          </Col>
          <Col span={12}>
            <StorySection title="Watch Next" color="green" items={watchNext} />
          </Col>
        </Row>
        <Text type="secondary">
          This card is a research triage summary, not a buy/sell recommendation. It explains why the stock is ranked
          here using stored announcements, market data, commodity proxy data, and observable risk rules.
        </Text>
      </Space>
    </Card>
  );
}

function StorySection({ title, color, items }: { title: string; color: string; items: string[] }) {
  return (
    <Card
      size="small"
      type="inner"
      title={
        <Space>
          <Tag color={color}>{title}</Tag>
          <Text type="secondary">{items.length}</Text>
        </Space>
      }
      style={{ height: "100%" }}
    >
      {items.length ? (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => (
            <List.Item>
              <Text>{item}</Text>
            </List.Item>
          )}
        />
      ) : (
        <Text type="secondary">No clear signal yet.</Text>
      )}
    </Card>
  );
}

function buildThesis(
  stock: StockWithScore,
  latest: ScoreBrief,
  components: StoryComponents,
  announcements: Announcement[],
  signals: Signal[],
) {
  const bestAnn = bestAnnouncement(components, announcements);
  const title =
    latest.cycle_score >= 70
      ? `${stock.code} is a high-priority resource story candidate.`
      : latest.cycle_score >= 55
        ? `${stock.code} is worth monitoring, but needs confirmation.`
        : `${stock.code} is not a priority yet.`;

  const description = bestAnn
    ? `Current ranking is mainly driven by ${bestAnn.type}: ${bestAnn.headline}.`
    : `No strong recent announcement is driving the story; the current score is mostly background data.`;

  const items = [
    bestAnn ? `Latest important story: ${bestAnn.type} - ${bestAnn.headline}.` : "No strong recent story detected.",
    `Announcement Score is ${latest.announcement_score.toFixed(1)}.`,
    commodityLine(latest, components),
    resourceLine(latest, components),
  ];

  if (signals.length > 0) {
    items.push(`Recent live signal: ${signals[0].signal_type} - ${signals[0].reason}`);
  }

  return { title, description, items: items.filter(Boolean) };
}

function buildMarketConfirmation(
  latest: ScoreBrief,
  components: StoryComponents,
  stock: StockWithScore,
  signals: Signal[],
) {
  const funding = components.funding ?? {};
  const relVol = funding.rel_vol;
  const items = [
    `Market Confirmation/Funding Score is ${latest.funding_score.toFixed(1)}. It is tracked separately from Cycle Score.`,
  ];

  if (stock.day_change_pct != null) {
    items.push(`Latest session move: ${stock.day_change_pct >= 0 ? "+" : ""}${stock.day_change_pct.toFixed(2)}%.`);
  }
  if (relVol?.value != null) {
    const turnover = relVol.dollar_turnover == null ? "" : ` with A$${compactMoney(relVol.dollar_turnover)} turnover`;
    items.push(`Relative volume is ${relVol.value}x${turnover}.`);
  }
  if (funding.breakout?.window) {
    items.push(`Price closed at a new ${funding.breakout.window}-day high.`);
  }
  if (funding.consecutive_up?.days && funding.consecutive_up.days >= 3) {
    items.push(`${funding.consecutive_up.days} consecutive up days.`);
  }
  const marketSignals = signals.filter((s) =>
    ["REL_VOL_SPIKE", "BREAKOUT_60D", "BREAKOUT_252D", "SCORE_CROSS_UP"].includes(s.signal_type),
  );
  marketSignals.slice(0, 2).forEach((signal) => items.push(`${signal.signal_type}: ${signal.reason}`));

  if (latest.funding_score < 30 && marketSignals.length === 0) {
    items.push("Market confirmation is still weak; this may be a story without capital follow-through yet.");
  }

  return items;
}

function buildRisk(latest: ScoreBrief, components: StoryComponents) {
  const risk = components.risk;
  const items = [`Risk Score is ${latest.risk_score.toFixed(1)}. Higher means safer.`];
  let color = "green";

  if (latest.risk_score < 40) {
    color = "red";
    items.push("Risk is elevated and should be checked manually before further research.");
  } else if (latest.risk_score < 50) {
    color = "orange";
    items.push("Risk is slightly weak; review liquidity and recent corporate actions.");
  } else {
    items.push("No major observable risk penalty dominates the current score.");
  }

  if (risk?.liquidity?.label) {
    const turnover = risk.liquidity.dollar_turnover == null ? "" : `, A$${compactMoney(risk.liquidity.dollar_turnover)}`;
    items.push(`Liquidity: ${risk.liquidity.label}${turnover}.`);
  }
  (risk?.events ?? []).slice(0, 3).forEach((event) => {
    if (event.reason) {
      items.push(`${event.reason}: ${event.headline ?? event.type ?? "risk event"}.`);
    }
  });
  if (risk?.note) {
    items.push(`Limitation: ${risk.note}.`);
  }

  return { color, items };
}

function buildWatchNext(latest: ScoreBrief, components: StoryComponents, signals: Signal[]) {
  const items = [
    "Read the primary ASX announcement before making any decision.",
    "Watch whether volume persists for 2-3 sessions instead of fading after one spike.",
  ];

  if (latest.announcement_score >= 70 && latest.funding_score < 40) {
    items.push("Important story detected, but market confirmation is still limited.");
  }
  if (latest.funding_score >= 60) {
    items.push("Check whether the move is accumulation or just a short-term reaction.");
  }
  if ((components.risk?.events ?? []).length > 0 || latest.risk_score < 45) {
    items.push("Review financing, halt, and liquidity details manually.");
  }
  if (components.sentiment?.source === "neutral_default") {
    items.push("Forum/social sentiment is not connected yet, so community consensus is unknown.");
  }
  if (signals.some((s) => s.signal_type === "SCORE_CROSS_UP")) {
    items.push("Score has crossed into a higher-priority band; compare it with the previous report.");
  }

  return Array.from(new Set(items)).slice(0, 6);
}

function bestAnnouncement(components: StoryComponents, announcements: Announcement[]) {
  const fromScore = components.announcement?.announcements?.[0];
  if (fromScore?.headline) {
    return {
      headline: fromScore.headline,
      type: fromScore.type ?? "ANNOUNCEMENT",
    };
  }

  const fromList = announcements.find((ann) => ann.price_sensitive || ann.type_score >= 70);
  if (!fromList) return null;
  return {
    headline: fromList.headline,
    type: fromList.ann_type,
  };
}

function commodityLine(latest: ScoreBrief, components: StoryComponents) {
  const commodity = components.commodity;
  if (!commodity || commodity.note) {
    return `Commodity Score is neutral at ${latest.commodity_score.toFixed(1)} due to limited proxy data.`;
  }
  return `${commodity.instrument ?? "Commodity proxy"} trend: 20d ${pct(commodity.r20_pct)}, 60d ${pct(
    commodity.r60_pct,
  )}; Commodity Score ${latest.commodity_score.toFixed(1)}.`;
}

function resourceLine(latest: ScoreBrief, components: StoryComponents) {
  const resource = components.resource;
  if (resource?.source === "qualitative_context_auto") {
    const best = resource.items?.[0];
    return best
      ? `Resource context is ${latest.resource_score.toFixed(1)}; best stored context ${best.score}: ${
          best.headline ?? "resource result"
        }.`
      : `Resource context is ${latest.resource_score.toFixed(1)} from stored qualitative mining metrics.`;
  }
  return `Resource Score is ${latest.resource_score.toFixed(1)}; deep resource context is limited or neutral.`;
}

function pct(value: number | undefined) {
  if (value == null) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function compactMoney(value: number) {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}m`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(0)}k`;
  return value.toFixed(0);
}
