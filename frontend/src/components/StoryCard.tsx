import type { ReactNode } from "react";
import { useState } from "react";
import { Alert, Button, Card, Col, Descriptions, Divider, Drawer, Empty, List, Row, Space, Tag, Typography } from "antd";

import type { Announcement, ScoreBrief, Signal, StockWithScore } from "../api/types";
import LabelTag from "./LabelTag";

const { Text } = Typography;

interface AnnouncementComponentItem {
  ann_id?: string | null;
  headline?: string;
  type?: string;
  url?: string | null;
  ai_summary?: string | null;
  base?: number;
  qualitative_bonus?: number;
  adjusted_base?: number;
  age_days?: number;
  decay?: number;
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
    best?: number;
    bonus?: number;
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
    value?: number;
    lookback_days?: number;
    context_count?: number;
    used_count?: number;
    best_context_score?: number;
    avg_context_score?: number;
    items?: {
      ann_id?: string | null;
      date?: string;
      headline?: string;
      score?: number;
      interval_quality_label?: string | null;
      materiality_label?: string | null;
      trend_vs_previous?: string | null;
      depth_category?: string | null;
      grade_thickness?: number | null;
      percentile?: number | null;
      quality_score?: number;
      materiality_adjust?: number;
      trend_adjust?: number;
      depth_adjust?: number;
      percentile_adjust?: number;
      assessment?: string | null;
      url?: string | null;
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
  const [activeDetail, setActiveDetail] = useState<"announcement" | "resource" | "signal" | null>(null);
  if (!latest) {
    return <Alert type="info" message="No Story Card yet. Run the pipeline to generate a score first." />;
  }

  const components = (latest.components ?? {}) as StoryComponents;
  const recentLiveSignal = signals.find((signal) => signal.source === "live");
  const thesis = buildThesis(stock, latest, components, announcements, recentLiveSignal, {
    openAnnouncementDetail: () => setActiveDetail("announcement"),
    openResourceDetail: () => setActiveDetail("resource"),
    openSignalDetail: () => setActiveDetail("signal"),
  });
  const market = buildMarketConfirmation(latest, components, stock, signals);
  const risk = buildRisk(latest, components);
  const watchNext = buildWatchNext(latest, components, signals);
  const announcementDetail = buildAnnouncementScoreDetail(latest, components, announcements);
  const resourceDetail = buildResourceScoreDetail(latest, components, announcements);
  const signalDetail = recentLiveSignal ? buildSignalDetail(recentLiveSignal, announcements) : null;

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
            <StorySection title="Market Confirmation" color="purple" items={toStoryItems(market, "market")} />
          </Col>
          <Col span={12}>
            <StorySection title="Risk" color={risk.color} items={toStoryItems(risk.items, "risk")} />
          </Col>
          <Col span={12}>
            <StorySection title="Watch Next" color="green" items={toStoryItems(watchNext, "watch")} />
          </Col>
        </Row>
        <Text type="secondary">
          This card is a research triage summary, not a buy/sell recommendation. It explains why the stock is ranked
          here using stored announcements, market data, commodity proxy data, and observable risk rules.
        </Text>
      </Space>
      <Drawer
        title={detailTitle(activeDetail, latest, recentLiveSignal)}
        open={activeDetail !== null}
        onClose={() => setActiveDetail(null)}
        width={620}
      >
        {activeDetail === "announcement" && <AnnouncementDetailPanel detail={announcementDetail} />}
        {activeDetail === "resource" && <ResourceDetailPanel detail={resourceDetail} />}
        {activeDetail === "signal" && signalDetail && <SignalDetailPanel detail={signalDetail} />}
      </Drawer>
    </Card>
  );
}

interface StoryItem {
  key: string;
  content: ReactNode;
}

function StorySection({ title, color, items }: { title: string; color: string; items: StoryItem[] }) {
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
              {typeof item.content === "string" ? <Text>{item.content}</Text> : item.content}
            </List.Item>
          )}
        />
      ) : (
        <Text type="secondary">No clear signal yet.</Text>
      )}
    </Card>
  );
}

function detailTitle(activeDetail: "announcement" | "resource" | "signal" | null, latest: ScoreBrief, signal?: Signal) {
  if (activeDetail === "announcement") return `Announcement Score ${latest.announcement_score.toFixed(1)}`;
  if (activeDetail === "resource") return `Resource Score ${latest.resource_score.toFixed(1)}`;
  if (activeDetail === "signal") return signal ? `Recent live signal ${signal.signal_type}` : "Recent live signal";
  return "";
}

function AnnouncementDetailPanel({ detail }: { detail: ReturnType<typeof buildAnnouncementScoreDetail> }) {
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <DetailSection title="Highlights" items={detail.highlights} empty="No recent announcement driver." />
      <section>
        <Typography.Title level={5}>Summary</Typography.Title>
        <Text>{detail.summary}</Text>
      </section>
      <section>
        <Typography.Title level={5}>Reasoning</Typography.Title>
        {detail.items.length ? (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            {detail.items.map((item, index) => (
              <Card key={`${item.ann_id ?? item.headline ?? index}`} size="small">
                <Space direction="vertical" size={8} style={{ width: "100%" }}>
                  <Space wrap>
                    <Tag color={item.effective === detail.best ? "magenta" : "blue"}>{item.type ?? "ANNOUNCEMENT"}</Tag>
                    {item.price_sensitive && <Tag color="red">price sensitive</Tag>}
                    {item.interval_quality_label && <Tag>{readable(item.interval_quality_label)}</Tag>}
                    {item.materiality_label && <Tag>{readable(item.materiality_label)}</Tag>}
                  </Space>
                  <Text strong>{item.headline ?? "Announcement"}</Text>
                  {item.ai_summary && <Text type="secondary">{item.ai_summary}</Text>}
                  <Descriptions size="small" column={2}>
                    <Descriptions.Item label="Base score">{formatNumber(item.base)}</Descriptions.Item>
                    <Descriptions.Item label="Qualitative bonus">{formatSigned(item.qualitative_bonus)}</Descriptions.Item>
                    <Descriptions.Item label="Adjusted base">{formatNumber(item.adjusted_base)}</Descriptions.Item>
                    <Descriptions.Item label="Age">{item.age_days ?? "-"} days</Descriptions.Item>
                    <Descriptions.Item label="Time decay">{formatNumber(item.decay)}</Descriptions.Item>
                    <Descriptions.Item label="Effective score">{formatNumber(item.effective)}</Descriptions.Item>
                  </Descriptions>
                  {item.qualitative_assessment && <Text>{item.qualitative_assessment}</Text>}
                  {item.url && (
                    <a href={item.url} target="_blank" rel="noreferrer">
                      Source announcement
                    </a>
                  )}
                </Space>
              </Card>
            ))}
          </Space>
        ) : (
          <Text type="secondary">No announcement contributed to the current 30-day score window.</Text>
        )}
        <Divider />
        <Descriptions size="small" column={1}>
          <Descriptions.Item label="Best effective score">{formatNumber(detail.best)}</Descriptions.Item>
          <Descriptions.Item label="Additional key-announcement bonus">{formatNumber(detail.bonus)}</Descriptions.Item>
          <Descriptions.Item label="Final rule">
            Final score is the best effective announcement score plus the capped key-announcement bonus.
          </Descriptions.Item>
        </Descriptions>
      </section>
    </Space>
  );
}

function ResourceDetailPanel({ detail }: { detail: ReturnType<typeof buildResourceScoreDetail> }) {
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <DetailSection title="Highlights" items={detail.highlights} empty="No resource context driver." />
      <section>
        <Typography.Title level={5}>Summary</Typography.Title>
        <Text>{detail.summary}</Text>
      </section>
      <section>
        <Typography.Title level={5}>Reasoning</Typography.Title>
        <Descriptions size="small" column={1}>
          <Descriptions.Item label="Source">{detail.source}</Descriptions.Item>
          <Descriptions.Item label="Contexts used">
            {detail.usedCount} of {detail.contextCount}
          </Descriptions.Item>
          <Descriptions.Item label="Lookback">{detail.lookbackDays ? `${detail.lookbackDays} days` : "-"}</Descriptions.Item>
          <Descriptions.Item label="Final rule">
            Resource Score weights the strongest stored mining context most heavily, then blends in the average of used
            contexts.
          </Descriptions.Item>
        </Descriptions>
        <Divider />
        {detail.items.length ? (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            {detail.items.map((item, index) => (
              <Card key={`${item.ann_id ?? item.headline ?? index}`} size="small">
                <Space direction="vertical" size={8} style={{ width: "100%" }}>
                  <Space wrap>
                    <Tag color={index === 0 ? "magenta" : "blue"}>context score {formatNumber(item.score)}</Tag>
                    {item.interval_quality_label && <Tag>{readable(item.interval_quality_label)}</Tag>}
                    {item.materiality_label && <Tag>{readable(item.materiality_label)}</Tag>}
                    {item.trend_vs_previous && <Tag>{readable(item.trend_vs_previous)}</Tag>}
                  </Space>
                  <Text strong>{item.headline ?? "Resource result"}</Text>
                  {item.assessment && <Text>{item.assessment}</Text>}
                  <Descriptions size="small" column={2}>
                    <Descriptions.Item label="Grade thickness">{formatNumber(item.grade_thickness)}</Descriptions.Item>
                    <Descriptions.Item label="Percentile">{formatPercentile(item.percentile)}</Descriptions.Item>
                    <Descriptions.Item label="Quality score">{formatNumber(item.quality_score)}</Descriptions.Item>
                    <Descriptions.Item label="Materiality adjust">{formatSigned(item.materiality_adjust)}</Descriptions.Item>
                    <Descriptions.Item label="Trend adjust">{formatSigned(item.trend_adjust)}</Descriptions.Item>
                    <Descriptions.Item label="Depth adjust">{formatSigned(item.depth_adjust)}</Descriptions.Item>
                    <Descriptions.Item label="Percentile adjust">{formatSigned(item.percentile_adjust)}</Descriptions.Item>
                    <Descriptions.Item label="Depth">{item.depth_category ? readable(item.depth_category) : "-"}</Descriptions.Item>
                  </Descriptions>
                  {item.url && (
                    <a href={item.url} target="_blank" rel="noreferrer">
                      Source announcement
                    </a>
                  )}
                </Space>
              </Card>
            ))}
          </Space>
        ) : (
          <Text type="secondary">No stored qualitative mining context contributed to this score.</Text>
        )}
      </section>
    </Space>
  );
}

function SignalDetailPanel({ detail }: { detail: ReturnType<typeof buildSignalDetail> }) {
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <DetailSection title="Highlights" items={detail.highlights} empty="No live signal evidence." />
      <section>
        <Typography.Title level={5}>Summary</Typography.Title>
        <Text>{detail.summary}</Text>
      </section>
      <section>
        <Typography.Title level={5}>Reasoning</Typography.Title>
        <Descriptions size="small" column={1}>
          <Descriptions.Item label="Date">{detail.signal.date}</Descriptions.Item>
          <Descriptions.Item label="Signal type">{detail.signal.signal_type}</Descriptions.Item>
          <Descriptions.Item label="Reason">{detail.signal.reason}</Descriptions.Item>
          <Descriptions.Item label="Price at signal">{formatNumber(detail.signal.price_at_signal)}</Descriptions.Item>
          <Descriptions.Item label="Cycle score at signal">
            {formatNumber(detail.signal.cycle_score_at_signal)}
          </Descriptions.Item>
        </Descriptions>
        <Divider />
        <Descriptions size="small" column={2}>
          {detail.evidenceRows.map((row) => (
            <Descriptions.Item key={row.label} label={row.label}>
              {row.value}
            </Descriptions.Item>
          ))}
        </Descriptions>
        {detail.sourceLinks.length > 0 && (
          <>
            <Divider />
            <Space direction="vertical" size={4}>
              {detail.sourceLinks.map((link) => (
                <a key={link.url} href={link.url} target="_blank" rel="noreferrer">
                  {link.label}
                </a>
              ))}
            </Space>
          </>
        )}
      </section>
    </Space>
  );
}

function DetailSection({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <section>
      <Typography.Title level={5}>{title}</Typography.Title>
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
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={empty} />
      )}
    </section>
  );
}

function buildThesis(
  stock: StockWithScore,
  latest: ScoreBrief,
  components: StoryComponents,
  announcements: Announcement[],
  recentLiveSignal: Signal | undefined,
  actions: {
    openAnnouncementDetail: () => void;
    openResourceDetail: () => void;
    openSignalDetail: () => void;
  },
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

  const items: StoryItem[] = [
    {
      key: "latest-story",
      content: bestAnn
        ? `Latest important story: ${bestAnn.type} - ${bestAnn.headline}.`
        : "No strong recent story detected.",
    },
    {
      key: "announcement-score",
      content: (
        <Button type="link" size="small" onClick={actions.openAnnouncementDetail} style={{ height: "auto", padding: 0 }}>
          Announcement Score is {latest.announcement_score.toFixed(1)}.
        </Button>
      ),
    },
    { key: "commodity", content: commodityLine(latest, components) },
    {
      key: "resource",
      content: (
        <Button type="link" size="small" onClick={actions.openResourceDetail} style={{ height: "auto", padding: 0 }}>
          {resourceLine(latest, components)}
        </Button>
      ),
    },
  ];

  if (recentLiveSignal) {
    items.push({
      key: "recent-live-signal",
      content: (
        <Button type="link" size="small" onClick={actions.openSignalDetail} style={{ height: "auto", padding: 0 }}>
          Recent live signal: {recentLiveSignal.signal_type} - {recentLiveSignal.reason}
        </Button>
      ),
    });
  }

  return { title, description, items: items.filter((item) => Boolean(item.content)) };
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

function toStoryItems(items: string[], prefix: string): StoryItem[] {
  return items.map((content, index) => ({ key: `${prefix}-${index}`, content }));
}

function buildAnnouncementScoreDetail(
  latest: ScoreBrief,
  components: StoryComponents,
  announcements: Announcement[],
) {
  const annComponents = components.announcement ?? {};
  const items = (annComponents.announcements ?? []).map((item) => enrichAnnouncementItem(item, announcements));
  const best = annComponents.best ?? 0;
  const bonus = annComponents.bonus ?? 0;
  const top = items[0];
  const highlights: string[] = [];

  if (top) {
    highlights.push(
      `${top.type ?? "Announcement"} is the main driver with an effective score of ${formatNumber(top.effective)}.`,
    );
    if (top.price_sensitive) {
      highlights.push("The announcement is marked price sensitive, so the scoring rule applies a stronger weight.");
    }
    if (top.qualitative_bonus && top.qualitative_bonus > 0) {
      highlights.push(
        `Qualitative mining context adds ${formatNumber(top.qualitative_bonus)} points before recency and sensitivity adjustments.`,
      );
    }
    if (top.age_days != null) {
      highlights.push(`The announcement is ${top.age_days} days old, so the time-decay factor is ${formatNumber(top.decay)}.`);
    }
  }
  if (bonus > 0) {
    highlights.push(`Additional key announcements add a capped bonus of ${formatNumber(bonus)} points.`);
  }
  if (!items.length && annComponents.note === "no_announcements_30d") {
    highlights.push("There are no announcements inside the current 30-day scoring window.");
  }

  return {
    items,
    best,
    bonus,
    highlights,
    summary: announcementSummary(latest.announcement_score, top, bonus, annComponents.note),
  };
}

function enrichAnnouncementItem(item: AnnouncementComponentItem, announcements: Announcement[]): AnnouncementComponentItem {
  const match = announcements.find(
    (ann) =>
      (item.ann_id && ann.ann_id === item.ann_id) ||
      (item.url && ann.url === item.url) ||
      (item.headline && ann.headline.startsWith(item.headline)),
  );
  return {
    ...item,
    ann_id: item.ann_id ?? match?.ann_id,
    url: item.url ?? match?.url,
    ai_summary: item.ai_summary ?? match?.ai_summary,
  };
}

function announcementSummary(
  score: number,
  top: AnnouncementComponentItem | undefined,
  bonus: number,
  note?: string,
) {
  if (!top) {
    return note === "no_announcements_30d"
      ? "The Announcement Score is zero because no stored announcement falls within the active 30-day scoring window."
      : "The Announcement Score has no active announcement driver in the stored scoring components.";
  }

  const strength = score >= 75 ? "strong" : score >= 50 ? "moderate" : score > 0 ? "limited" : "inactive";
  const sensitivity = top.price_sensitive ? "price-sensitive status" : "standard sensitivity treatment";
  const quality =
    top.qualitative_bonus && top.qualitative_bonus > 0
      ? `, with resource-quality context adding ${formatNumber(top.qualitative_bonus)} points before adjustments`
      : "";
  const extra = bonus > 0 ? ` A further ${formatNumber(bonus)} points comes from other key announcements.` : "";

  return `The Announcement Score is ${strength} at ${formatNumber(score)}. It is mainly driven by ${
    top.type ?? "the leading announcement"
  }, using its base type score, ${sensitivity}, and recency decay${quality}.${extra}`;
}

function buildResourceScoreDetail(
  latest: ScoreBrief,
  components: StoryComponents,
  announcements: Announcement[],
) {
  const resource = components.resource ?? {};
  const items = (resource.items ?? []).map((item) => {
    const match = announcements.find(
      (ann) =>
        (item.ann_id && ann.ann_id === item.ann_id) ||
        (item.headline && ann.headline.startsWith(item.headline)),
    );
    return { ...item, url: item.url ?? match?.url };
  });
  const top = items[0];
  const source = resource.source ?? "unknown";
  const contextCount = resource.context_count ?? items.length;
  const usedCount = resource.used_count ?? items.length;
  const highlights: string[] = [];

  if (source === "manual_override") {
    highlights.push("This Resource Score is manually overridden, so stored mining context is not driving the value.");
  } else if (source === "neutral_default") {
    highlights.push("No usable qualitative mining context is stored, so the Resource Score stays at a neutral baseline.");
  } else if (top) {
    highlights.push(`The strongest resource context scores ${formatNumber(top.score)} and drives most of the score.`);
    if (top.interval_quality_label) highlights.push(`Interval quality is assessed as ${readable(top.interval_quality_label)}.`);
    if (top.materiality_label) highlights.push(`Materiality is assessed as ${readable(top.materiality_label)}.`);
    if (top.trend_vs_previous) highlights.push(`Trend versus previous comparable results is ${readable(top.trend_vs_previous)}.`);
  }
  if (contextCount > 0) {
    highlights.push(`${usedCount} of ${contextCount} stored resource contexts are included in the score blend.`);
  }

  return {
    items,
    source,
    contextCount,
    usedCount,
    lookbackDays: resource.lookback_days,
    highlights,
    summary: resourceSummary(latest.resource_score, source, top, contextCount),
  };
}

function resourceSummary(
  score: number,
  source: string,
  top: NonNullable<StoryComponents["resource"]>["items"] extends (infer Item)[] | undefined ? Item : never,
  contextCount: number,
) {
  if (source === "manual_override") {
    return `The Resource Score is ${formatNumber(score)} because a manual override is active. The automated qualitative context is bypassed for this snapshot.`;
  }
  if (source === "neutral_default" || !top) {
    return `The Resource Score is neutral at ${formatNumber(score)} because the system has no usable stored qualitative mining context for this scoring window.`;
  }
  return `The Resource Score is ${formatNumber(score)} based on ${contextCount} stored mining context record${
    contextCount === 1 ? "" : "s"
  }. The leading context is ${readable(top.interval_quality_label ?? "unclassified")} quality and ${readable(
    top.materiality_label ?? "unclassified",
  )} materiality, with the strongest result carrying most of the final score.`;
}

function buildSignalDetail(signal: Signal, announcements: Announcement[]) {
  const evidence = signal.evidence ?? {};
  const announcementEvidence = Array.isArray(evidence.announcements)
    ? (evidence.announcements as { ann_id?: string; headline?: string; type?: string; base?: number; price_sensitive?: boolean }[])
    : [];
  const sourceLinks = announcementEvidence
    .map((item) => {
      const ann = announcements.find(
        (candidate) =>
          (item.ann_id && candidate.ann_id === item.ann_id) ||
          (item.headline && candidate.headline.startsWith(item.headline)),
      );
      return ann ? { label: ann.headline, url: ann.url } : null;
    })
    .filter((item): item is { label: string; url: string } => item !== null);
  const highlights = signalHighlights(signal, evidence, announcementEvidence);

  return {
    signal,
    highlights,
    summary: signalSummary(signal, evidence),
    evidenceRows: evidenceRows(evidence),
    sourceLinks,
  };
}

function signalHighlights(
  signal: Signal,
  evidence: Record<string, unknown>,
  announcementEvidence: { type?: string; base?: number; price_sensitive?: boolean }[],
) {
  const items = [`This is a ${signal.source} signal generated on ${signal.date}.`];
  if (signal.signal_type === "REL_VOL_SPIKE") {
    items.push(`Relative volume reached ${formatUnknownNumber(evidence.rel_vol)}x with ${formatMoneyValue(evidence.dollar_turnover)} turnover.`);
  } else if (signal.signal_type.startsWith("BREAKOUT")) {
    items.push(`The close broke a ${formatUnknownNumber(evidence.window)}-day high with supporting volume.`);
  } else if (signal.signal_type === "KEY_ANNOUNCEMENT") {
    const best = announcementEvidence[0];
    items.push(
      `${best?.type ?? "A key announcement"} triggered the signal with base score ${formatUnknownNumber(best?.base)}.`,
    );
    if (best?.price_sensitive) items.push("The triggering announcement is marked price sensitive.");
  } else if (signal.signal_type === "SCORE_CROSS_UP") {
    items.push(
      `Cycle Score crossed the threshold from ${formatUnknownNumber(evidence.prev_score)} to ${formatUnknownNumber(evidence.today_score)}.`,
    );
  }
  return items;
}

function signalSummary(signal: Signal, evidence: Record<string, unknown>) {
  if (signal.signal_type === "REL_VOL_SPIKE") {
    return `The recent live signal is a volume-confirmation event. It means trading activity was materially above the 20-day average on an up day, which can indicate market attention following the story.`;
  }
  if (signal.signal_type.startsWith("BREAKOUT")) {
    return `The recent live signal is a price-breakout event. It indicates the latest close moved above the stored lookback high while volume met the confirmation rule.`;
  }
  if (signal.signal_type === "KEY_ANNOUNCEMENT") {
    return `The recent live signal is announcement-driven. It fired because a new announcement met the key-announcement threshold through its type score or price-sensitive status.`;
  }
  if (signal.signal_type === "SCORE_CROSS_UP") {
    return `The recent live signal is score-driven. It fired because Cycle Score crossed the configured priority threshold of ${formatUnknownNumber(
      evidence.threshold,
    )}.`;
  }
  return "The recent live signal records the rule that moved this stock onto the live monitoring list.";
}

function evidenceRows(evidence: Record<string, unknown>) {
  return Object.entries(evidence)
    .filter(([, value]) => !Array.isArray(value) && typeof value !== "object")
    .map(([key, value]) => ({ label: readable(key), value: formatEvidenceValue(value) }));
}

function readable(value: string) {
  return value.replaceAll("_", " ");
}

function formatNumber(value: number | null | undefined) {
  return value == null ? "-" : value.toFixed(1);
}

function formatSigned(value: number | null | undefined) {
  if (value == null) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

function formatPercentile(value: number | null | undefined) {
  return value == null ? "-" : `${value.toFixed(1)}th`;
}

function formatUnknownNumber(value: unknown) {
  return typeof value === "number" ? value.toFixed(1) : "-";
}

function formatMoneyValue(value: unknown) {
  if (typeof value !== "number") return "-";
  return `A$${compactMoney(value)}`;
}

function formatEvidenceValue(value: unknown) {
  if (typeof value === "number") return value.toFixed(Number.isInteger(value) ? 0 : 2);
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (value == null) return "-";
  return String(value);
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
  return `${commodityInstrumentLabel(commodity.instrument)} trend: 20d ${pct(commodity.r20_pct)}, 60d ${pct(
    commodity.r60_pct,
  )}; Commodity Score ${latest.commodity_score.toFixed(1)}.`;
}

function commodityInstrumentLabel(instrument: string | undefined) {
  if (instrument === "GC=F") return "Golden contract";
  return instrument ?? "Commodity proxy";
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
