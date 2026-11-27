import { Tooltip } from "antd";

import type { LensRosterEntry } from "../api/types";

/**
 * All seven lenses at once, including the quiet ones.
 *
 * A list of the readings that fired says what happened but not how much was
 * looked at: four catalyst findings read the same whether the other three
 * lenses found nothing or never had enough history to run. The engines keep
 * those apart internally and the narrative says which, buried in a fold. Here
 * the three states are three different marks, so the shape of a day's reading
 * is one glance rather than six lines of prose.
 *
 * Strength is carried by how many marks, direction by which. No new hue: the
 * up/down pair already means price direction elsewhere, and it means engine
 * direction here for the same reason — more or less of the thing.
 */

const LENS_LABELS: Record<string, string> = {
  trend: "趋势",
  momentum: "动量",
  participation: "量价",
  volatility: "波动",
  structure: "结构",
  breakout: "突破",
  exhaustion: "衰竭",
  lifecycle: "阶段",
  milestone: "里程碑",
  derisking: "去风险",
  bottleneck: "瓶颈",
  timeline: "时间",
  forward: "未来催化",
  dependency: "依赖",
};

const MARKS: Record<string, number> = { minor: 1, moderate: 2, strong: 3, exceptional: 4 };

function glyph(entry: LensRosterEntry): { text: string; color: string; title: string } {
  if (entry.status === "insufficient_data") {
    return { text: "—", color: "var(--c-absent)", title: "证据不足" };
  }
  if (entry.status === "no_material_change") {
    return { text: "·", color: "var(--ink-faint)", title: "算过了，无实质变化" };
  }
  const count = MARKS[entry.magnitude] ?? 1;
  if (entry.direction === "positive") {
    return { text: "▲".repeat(count), color: "var(--up)", title: `正向 · ${entry.magnitude}` };
  }
  if (entry.direction === "negative") {
    return { text: "▼".repeat(count), color: "var(--down)", title: `负向 · ${entry.magnitude}` };
  }
  // a neutral reading is a real finding that carries no direction — a rule the
  // backtest did not support still reports, and must not look like agreement
  return { text: "◆".repeat(count), color: "var(--ink-soft)", title: `中性 · ${entry.magnitude}` };
}

export default function LensMatrix({ roster }: { roster: LensRosterEntry[] }) {
  if (!roster.length) return null;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 2, marginBottom: 10 }}>
      {roster.map((entry) => {
        const mark = glyph(entry);
        return (
          <Tooltip
            key={entry.lens}
            title={`${LENS_LABELS[entry.lens] || entry.lens}｜${mark.title}${
              entry.summary ? `\n${entry.summary}` : ""
            }`}
          >
            <div
              style={{
                minWidth: 58,
                border: "1px solid var(--line)",
                padding: "4px 6px",
                textAlign: "center",
                cursor: "help",
                background: entry.status === "reported" ? "var(--surface)" : "transparent",
              }}
            >
              <div className="micro" style={{ marginBottom: 2 }}>
                {LENS_LABELS[entry.lens] || entry.lens}
              </div>
              <div data-testid="lens-mark" style={{ color: mark.color, fontSize: 12, lineHeight: 1.1 }}>
                {mark.text}
              </div>
            </div>
          </Tooltip>
        );
      })}
    </div>
  );
}
