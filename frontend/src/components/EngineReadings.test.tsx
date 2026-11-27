import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import EngineReadings from "./EngineReadings";
import type { EngineReadings as Readings } from "../api/types";

function reading(overrides = {}) {
  return {
    lens: "trend",
    direction: "negative",
    magnitude: "strong",
    confidence: "high",
    persistence: "long",
    summary: "均线完全空头排列，50 日均线 -27.4% 下行。",
    drivers: [],
    risks: ["下跌趋势中反弹频繁，单日转强不构成反转"],
    dependency_group: "price_action:2026-11-26",
    ...overrides,
  };
}

function data(overrides: Partial<Readings> = {}): Readings {
  return {
    as_of: "2026-11-26",
    fusion: {
      opportunity_strength: "weak",
      confidence: "high",
      signal_structure: "confirmation",
      evidence_independence: "high",
      conflicts: [],
      blocking_conditions: [],
      strength_basis: {
        positive_sources: 1,
        negative_sources: 2,
        strongest_positive_magnitude: 0.5,
        engines_positive: ["fundamental"],
        engines_negative: ["catalyst", "technical"],
        cap_applied: "contradicted_by_equally_sourced_negative",
      },
      cycle_score_strength: "weak",
    },
    engines: [
      {
        engine: "technical",
        logic_version: "technical_seven_lens_v1",
        narrative: "技术面七视角（截至 2026-11-26）\n· trend｜偏空·strong：…",
        readings: [reading()],
      },
    ],
    ...overrides,
  };
}

describe("EngineReadings", () => {
  it("shows the verdict with the sources behind it", () => {
    const { container } = render(<EngineReadings data={data()} />);

    expect(screen.getByText("弱")).toBeInTheDocument();
    expect(container.textContent).toContain("正向来源 1 个");
    expect(container.textContent).toContain("负向来源 2 个");
  });

  it("says when the strength was capped rather than leaving it unexplained", () => {
    const { container } = render(<EngineReadings data={data()} />);

    expect(container.textContent).toContain("已因反向证据封顶");
  });

  it("puts a cross-engine divergence in plain language", () => {
    // "cross_engine_divergence:fundamental_vs_catalyst+technical" is the
    // stored form; nobody should have to parse that on screen.
    const payload = data();
    payload.fusion!.conflicts = ["cross_engine_divergence:fundamental_vs_catalyst+technical"];

    const { container } = render(<EngineReadings data={payload} />);

    expect(container.textContent).toContain("基本面 看多");
    expect(container.textContent).toContain("项目催化 + 技术面 看空");
  });

  it("names an internal divergence as a different finding", () => {
    const payload = data();
    payload.fusion!.conflicts = ["engine_internal_divergence:technical"];

    const { container } = render(<EngineReadings data={payload} />);

    expect(container.textContent).toContain("技术面 引擎内部不一致");
  });

  it("explains that disagreement lowers the strength", () => {
    const payload = data();
    payload.fusion!.conflicts = ["engine_internal_divergence:technical"];

    const { container } = render(<EngineReadings data={payload} />);

    expect(container.textContent).toContain("诚实的读法是不确定");
  });

  it("shows each lens reading with its direction and its caveat", () => {
    const { container } = render(<EngineReadings data={data()} />);

    expect(container.textContent).toContain("trend");
    expect(container.textContent).toContain("负向");
    expect(container.textContent).toContain("均线完全空头排列");
    expect(container.textContent).toContain("单日转强不构成反转");
  });

  it("marks an engine that is still a projection", () => {
    // Fundamental has no agent yet; presenting it like the real two would
    // overstate what the system is doing.
    const payload = data();
    payload.engines = [
      { engine: "fundamental", logic_version: "cycle_score_adapter_v1", narrative: null,
        readings: [reading({ lens: null, summary: null, risks: [] })] },
    ];

    const { container } = render(<EngineReadings data={payload} />);

    expect(container.textContent).toContain("投影（尚未实现为独立 Agent）");
  });

  it("compares against what the retired lookup would have said", () => {
    const payload = data();
    payload.fusion!.cycle_score_strength = "moderate";

    const { container } = render(<EngineReadings data={payload} />);

    expect(container.textContent).toContain("旧版 Cycle Score 查表会判为「中等」");
  });

  it("says nothing changed when the two agree", () => {
    const { container } = render(<EngineReadings data={data()} />);

    expect(container.textContent).not.toContain("旧版 Cycle Score");
  });

  it("asks for a pipeline run instead of rendering an empty panel", () => {
    render(<EngineReadings data={{ as_of: null, fusion: null, engines: [] }} />);

    expect(screen.getByText(/还没有融合记录/)).toBeInTheDocument();
  });
});
