import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SubScores } from "./Ranking";
import type { StockWithScore } from "../api/types";

function stock(sources: Record<string, string> | null): StockWithScore {
  return {
    id: 1, code: "WC8", name: "Wildcat", commodity: "lithium", stage: "explorer",
    active: true, notes: "",
    latest_score: {
      date: "2026-11-26",
      funding_score: 50, announcement_score: 100, resource_score: 50,
      commodity_score: 62, risk_score: 50, sentiment_score: 50,
      cycle_score: 61.4, label: "Watch Closely",
      component_sources: sources,
    },
  } as unknown as StockWithScore;
}

/** The chips carry the marker as a dashed underline; jsdom cannot expand a
 *  border shorthand containing var(), so the style attribute is the assertion. */
function markedAbsent(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("span.num"))
    .filter((node) => (node.getAttribute("style") || "").includes("dashed"))
    .map((node) => node.textContent?.slice(0, 1) ?? "");
}

describe("排名页分项", () => {
  it("marks a sub-score that fell back to the neutral default", () => {
    // A measured 50 and a defaulted 50 are the same number meaning opposite
    // things; the list response now carries which.
    const { container } = render(
      <SubScores s={stock({ resource: "neutral_default", commodity: "momentum_v1" })} />,
    );

    expect(markedAbsent(container)).toContain("R");
  });

  it("leaves a measured sub-score unmarked even when it reads 50", () => {
    const { container } = render(
      <SubScores s={stock({ resource: "qualitative_context_auto" })} />,
    );

    expect(markedAbsent(container)).not.toContain("R");
  });

  it("always marks sentiment, which has no source at all", () => {
    const { container } = render(<SubScores s={stock({ resource: "qualitative_context_auto" })} />);

    expect(markedAbsent(container)).toEqual(["S"]);
  });

  it("does not guess from the value when no sources arrived", () => {
    // Older responses carry no marker. Inferring "50 means defaulted" would
    // mislabel a genuine 50, which is the error this treatment exists to stop.
    const { container } = render(<SubScores s={stock(null)} />);

    expect(markedAbsent(container)).toEqual(["S"]);
  });
});
