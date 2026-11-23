import { Alert, Space, Typography } from "antd";
import { Link } from "react-router-dom";

import type { TodayBoard as Board, TodayItem, TodayReason } from "../api/types";
import StatusPill, { StatusStripe } from "./StatusPill";

/**
 * The morning briefing: which stocks have something to say, and what it is.
 *
 * A ranking answers "which scores highest", which is not the question asked each
 * morning. This answers "what changed, and does anything need attention" — and
 * names the quiet ones too, so it is clear the whole universe was checked rather
 * than three rows arbitrarily shown.
 */

const LEVEL_TEXT: Record<TodayReason["level"], string> = {
  critical: "严重",
  caution: "注意",
  watch: "关注",
  unconfirmed: "未确证",
};

function Change({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="num" style={{ color: "var(--ink-faint)" }}>—</span>;
  // The sign is carried in the text, not only the colour: roughly one man in
  // twelve cannot separate the two hues.
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  const color = pct > 0 ? "var(--up)" : pct < 0 ? "var(--down)" : "var(--ink-faint)";
  return (
    <span className="num" style={{ color }}>
      {sign}
      {Math.abs(pct).toFixed(2)}%
    </span>
  );
}

function evidenceLine(reason: TodayReason) {
  const e = reason.evidence ?? {};
  const pairs: [string, unknown][] = [];

  if (reason.kind === "funding") {
    pairs.push(["跑道", `${Number(e.runway_quarters).toFixed(2)} 季度`]);
    if (e.entity_reported != null) pairs.push(["公司自报", `${Number(e.entity_reported).toFixed(2)}`]);
    if (e.source_page != null) pairs.push(["来源", `5B · 第 ${e.source_page} 页`]);
  } else if (reason.kind === "dilution") {
    pairs.push(["配售价", String(e.issue_price)]);
    pairs.push(["前收盘", String(e.prior_close)]);
    pairs.push(["折价", `${Number(e.discount_pct).toFixed(2)}%`]);
  } else if (reason.kind === "resource") {
    pairs.push(["偏差", `${Number(e.variance_pct).toFixed(0)}%`]);
  } else if (reason.kind === "signal") {
    pairs.push(["信号", String(e.signal_type)]);
    const secondary = e.secondary as string[] | undefined;
    if (secondary?.length) pairs.push(["次级", secondary.join(", ")]);
  } else if (reason.kind === "announcement" && e.ann_id) {
    pairs.push(["公告", String(e.ann_id)]);
  }

  if (reason.as_of) pairs.push(["截至", reason.as_of]);
  return pairs;
}

function Reason({ reason }: { reason: TodayReason }) {
  const pairs = evidenceLine(reason);
  // A standing state measured months ago is recessed, so it is never read as
  // something that happened today.
  const standing = reason.kind === "funding" || reason.kind === "dilution" || reason.kind === "resource";

  return (
    <div style={{ paddingTop: 8 }}>
      <Space size={9} align="baseline" wrap style={{ marginBottom: 4 }}>
        <StatusPill
          level={reason.level}
          hint={reason.level === "unconfirmed" ? "回测未能支持该规则，不计入买入确认" : undefined}
        >
          {reason.title}
        </StatusPill>
        {reason.level === "unconfirmed" && (
          <span className="micro">{LEVEL_TEXT[reason.level]}</span>
        )}
      </Space>
      <div style={{ fontSize: 13.5, color: "var(--ink-soft)" }}>{reason.detail}</div>
      {pairs.length > 0 && (
        <div
          className={standing ? "num stale" : "num"}
          style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 6, display: "flex", flexWrap: "wrap", gap: "4px 16px" }}
        >
          {pairs.map(([key, value]) => (
            <span key={key}>
              <span style={{ color: "var(--ink-soft)" }}>{key}</span> {String(value)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Item({ item }: { item: TodayItem }) {
  return (
    <div style={{ display: "flex", border: "1px solid var(--line)", background: "var(--surface)" }}>
      <StatusStripe level={item.top_level} />
      <div style={{ padding: "13px 16px 15px", flex: 1, minWidth: 0 }}>
        <Space size={10} align="baseline" wrap style={{ width: "100%" }}>
          <Link to={`/stocks/${item.code}`} className="num" style={{ fontWeight: 650, fontSize: 15 }}>
            {item.code}
          </Link>
          <span style={{ color: "var(--ink-faint)", fontSize: 13 }}>{item.name}</span>
          <span style={{ marginLeft: "auto" }} className="num">
            {item.last_close?.toFixed(3) ?? "—"} <Change pct={item.day_change_pct} />
          </span>
        </Space>
        {item.reasons.map((reason, index) => (
          <Reason key={`${reason.kind}-${index}`} reason={reason} />
        ))}
      </div>
    </div>
  );
}

export default function TodayBoard({ board }: { board: Board }) {
  if (!board.as_of) {
    return (
      <Alert
        type="info"
        showIcon
        message="还没有行情数据"
        description="先运行一次 pipeline 采集价格与公告。"
      />
    );
  }

  const count = board.items.length;
  return (
    <Space direction="vertical" size={14} style={{ width: "100%" }}>
      <Space align="baseline" wrap style={{ width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={4} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          {count > 0 ? `今天值得看 ${count} 支` : "今天没有需要注意的变化"}
        </Typography.Title>
        <span className="micro">
          {board.as_of} · 已评分 {board.scored}/{board.universe} · 值得看的新公告{" "}
          {board.new_announcements}
        </span>
      </Space>

      {board.items.map((item) => (
        <Item key={item.code} item={item} />
      ))}

      {board.quiet.length > 0 && (
        <div
          style={{
            border: "1px dashed var(--line)",
            padding: "11px 15px",
            display: "flex",
            gap: 14,
            flexWrap: "wrap",
            justifyContent: "space-between",
            fontSize: 13,
            color: "var(--ink-faint)",
          }}
        >
          <span>其余 {board.quiet.length} 支今日无实质变化</span>
          <span className="num" style={{ color: "var(--ink-soft)" }}>
            {board.quiet.join("  ")}
          </span>
        </div>
      )}
    </Space>
  );
}
