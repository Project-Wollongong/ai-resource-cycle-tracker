import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LensMatrix from "./LensMatrix";
import type { LensRosterEntry } from "../api/types";

function entry(overrides: Partial<LensRosterEntry> = {}): LensRosterEntry {
  return {
    lens: "trend", status: "reported", direction: "negative",
    magnitude: "strong", summary: "均线完全空头排列", ...overrides,
  };
}

function marks(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('[data-testid="lens-mark"]'))
    .map((node) => node.textContent?.trim() ?? "");
}

describe("LensMatrix", () => {
  it("shows a lens that looked and found nothing differently from one that could not look", () => {
    // Four findings read the same whether the other three lenses were quiet or
    // never had the history to run. The engines keep those apart; so must this.
    const { container } = render(
      <LensMatrix roster={[
        entry({ lens: "momentum", status: "no_material_change", direction: "neutral", magnitude: "minor" }),
        entry({ lens: "volatility", status: "insufficient_data", direction: "neutral", magnitude: "minor" }),
      ]} />,
    );

    expect(marks(container)).toEqual(["·", "—"]);
  });

  it("carries strength in how many marks and direction in which", () => {
    const { container } = render(
      <LensMatrix roster={[
        entry({ lens: "trend", direction: "negative", magnitude: "strong" }),
        entry({ lens: "milestone", direction: "positive", magnitude: "moderate" }),
      ]} />,
    );

    expect(marks(container)).toEqual(["▼▼▼", "▲▲"]);
  });

  it("gives a neutral reading its own mark rather than hiding it", () => {
    // A rule the backtest did not support still reports; drawn as agreement
    // it would supply confirmation it is not entitled to.
    const { container } = render(
      <LensMatrix roster={[entry({ lens: "breakout", direction: "neutral", magnitude: "moderate" })]} />,
    );

    expect(marks(container)).toEqual(["◆◆"]);
  });

  it("names every lens so the quiet ones are visibly present", () => {
    render(
      <LensMatrix roster={[
        entry({ lens: "trend" }),
        entry({ lens: "exhaustion", status: "no_material_change" }),
      ]} />,
    );

    expect(screen.getByText("趋势")).toBeInTheDocument();
    expect(screen.getByText("衰竭")).toBeInTheDocument();
  });

  it("renders nothing when an engine has no roster", () => {
    const { container } = render(<LensMatrix roster={[]} />);

    expect(container.firstChild).toBeNull();
  });
});
