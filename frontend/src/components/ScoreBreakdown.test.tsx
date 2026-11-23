import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ScoreBreakdown from "./ScoreBreakdown";
import type { ScoreBrief } from "../api/types";

function score(components: Record<string, unknown>): ScoreBrief {
  return {
    date: "2026-10-01",
    funding_score: 0,
    announcement_score: 90,
    resource_score: 50,
    commodity_score: 62,
    risk_score: 50,
    sentiment_score: 50,
    cycle_score: 68.5,
    label: "Watch Closely",
    components,
  };
}

describe("ScoreBreakdown", () => {
  it("marks a defaulted sub-score as absent, not as a middling one", () => {
    // A defaulted 50 and a measured 50 are the same number meaning opposite
    // things. The scorer records which in `source`, and this is the only screen
    // that marker reaches — the ranking endpoint returns components as null.
    render(
      <ScoreBreakdown
        score={score({
          resource: { value: 50, source: "neutral_default", note: "no_qualitative_context" },
          sentiment: { value: 50, source: "neutral_default" },
        })}
      />,
    );

    // one Absent tag for resource, one for sentiment
    expect(screen.getAllByText("Absent")).toHaveLength(2);
  });

  it("leaves a measured sub-score unmarked", () => {
    render(
      <ScoreBreakdown
        score={score({
          resource: { value: 62, source: "qualitative_context_auto" },
          sentiment: { value: 55, source: "forum_v1", label: "positive" },
        })}
      />,
    );

    expect(screen.queryByText("Absent")).not.toBeInTheDocument();
  });

  it("states each sub-score's weight so the total can be followed", () => {
    render(<ScoreBreakdown score={score({})} />);

    expect(screen.getByText("权重 40%")).toBeInTheDocument();
    expect(screen.getByText("不计入 Cycle Score")).toBeInTheDocument();
  });

  it("says sentiment has no source at all rather than calling it neutral", () => {
    render(<ScoreBreakdown score={score({ sentiment: { value: 50, source: "neutral_default" } })} />);

    expect(screen.getByText(/尚未接入/)).toBeInTheDocument();
    expect(screen.getByText(/不参与判断/)).toBeInTheDocument();
  });
});
