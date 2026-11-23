import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import TodayBoard from "./TodayBoard";
import type { TodayBoard as Board, TodayItem, TodayReason } from "../api/types";

function reason(overrides: Partial<TodayReason> = {}): TodayReason {
  return {
    kind: "funding",
    level: "caution",
    title: "跑道偏短",
    detail: "现金跑道 3.08 个季度，约 9 个月后需要融资。",
    as_of: "2026-06-30",
    evidence: { runway_quarters: 3.08, entity_reported: 3.08, source_page: 17 },
    ...overrides,
  };
}

function item(overrides: Partial<TodayItem> = {}): TodayItem {
  return {
    code: "HAS",
    name: "Hastings Technology Metals",
    commodity: "rare_earth",
    last_close: 0.255,
    last_bar_date: "2026-10-01",
    day_change_pct: -2.11,
    cycle_score: 26,
    label: "Ignore",
    top_level: "caution",
    reasons: [reason()],
    ...overrides,
  };
}

function board(overrides: Partial<Board> = {}): Board {
  return {
    as_of: "2026-10-01",
    scored: 29,
    universe: 29,
    new_announcements: 1,
    items: [item()],
    quiet: ["AAR", "A1M", "AGE"],
    ...overrides,
  };
}

function show(b: Board) {
  return render(
    <MemoryRouter>
      <TodayBoard board={b} />
    </MemoryRouter>,
  );
}

describe("TodayBoard", () => {
  it("leads with how many stocks need looking at", () => {
    show(board());

    expect(screen.getByText("今天值得看 1 支")).toBeInTheDocument();
  });

  it("names the quiet stocks rather than hiding them", () => {
    // Three rows with no further context leaves the reader unsure whether the
    // other 26 were checked at all.
    const { container } = show(board());

    expect(screen.getByText(/其余 3 支今日无实质变化/)).toBeInTheDocument();
    expect(container.textContent).toContain("AAR");
  });

  it("shows the date a standing state was measured", () => {
    // The cash position is from June. Presenting it without that date would
    // make a three-month-old reading look like today's news.
    const { container } = show(board());

    expect(container.textContent).toContain("2026-06-30");
  });

  it("carries price direction in the sign, not only the colour", () => {
    const { container } = show(board());

    expect(container.textContent).toContain("−2.11%");
  });

  it("marks a rule the backtest did not support as unconfirmed", () => {
    const { container } = show(
      board({
        items: [
          item({
            top_level: "unconfirmed",
            reasons: [
              reason({
                kind: "signal",
                level: "unconfirmed",
                title: "突破年内高点（仅关注）",
                detail: "New 252-day closing high",
                as_of: "2026-10-01",
                evidence: { signal_type: "BREAKOUT_252D", secondary: [] },
              }),
            ],
          }),
        ],
      }),
    );

    expect(container.textContent).toContain("仅关注");
    expect(container.textContent).toContain("未确证");
  });

  it("reports a secondary signal as an annotation, not a separate reason", () => {
    const { container } = show(
      board({
        items: [
          item({
            reasons: [
              reason({
                kind: "signal",
                level: "watch",
                title: "突破 60 日高点",
                detail: "New 60-day closing high on 22.8x volume",
                as_of: "2026-10-01",
                evidence: { signal_type: "BREAKOUT_60D", secondary: ["REL_VOL_SPIKE"] },
              }),
            ],
          }),
        ],
      }),
    );

    expect(container.textContent).toContain("REL_VOL_SPIKE");
    expect(container.textContent).toContain("次级");
  });

  it("says so plainly when nothing needs attention", () => {
    show(board({ items: [], quiet: ["AAR"] }));

    expect(screen.getByText("今天没有需要注意的变化")).toBeInTheDocument();
  });

  it("asks for a pipeline run instead of rendering an empty board", () => {
    show(board({ as_of: null, items: [], quiet: [] }));

    expect(screen.getByText("还没有行情数据")).toBeInTheDocument();
  });
});
