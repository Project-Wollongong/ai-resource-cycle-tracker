import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FundingRunwayPanel from "./FundingRunwayPanel";
import type { P4Feature } from "../api/types";

function feature(overrides: Partial<P4Feature> = {}): P4Feature {
  return {
    feature_group: "funding",
    feature_name: "cash_runway_quarters",
    value: 3.08,
    unit: "quarters",
    as_of_date: "2026-06-30",
    formula_version: "funding_runway_v1",
    input_fact_ids: [137, 138, 139],
    evidence: {
      formula: "total_available_funding / abs(total_relevant_outgoings)",
      inputs: { total_available_funding: 3761, total_relevant_outgoings: -1222 },
      source_pages: { total_relevant_outgoings: 17 },
      entity_reported_quarters: 3.08,
      variance_vs_entity_reported: 0,
    },
    metadata: { appendix_5b_items: ["8.3", "8.6", "8.7"], below_asx_disclosure_threshold: false },
    ...overrides,
  };
}

describe("FundingRunwayPanel", () => {
  it("shows the runway with the figures and page it was derived from", () => {
    // AntD Statistic splits a formatted number across elements, so assert on
    // the panel text rather than a single node
    const { container } = render(<FundingRunwayPanel features={[feature()]} />);

    expect(container.textContent).toContain("3.08");
    expect(container.textContent).toContain("现金跑道");
    expect(screen.getByText(/第 8.3 \/ 8.6 \/ 8.7 项 · 第 17 页/)).toBeInTheDocument();
    expect(screen.getByText("一致")).toBeInTheDocument();
  });

  it("warns when the runway is under the two-quarter disclosure threshold", () => {
    render(
      <FundingRunwayPanel
        features={[feature({ value: 1.5, metadata: { below_asx_disclosure_threshold: true } })]}
      />,
    );
    expect(screen.getByText("跑道不足 2 个季度")).toBeInTheDocument();
  });

  it("surfaces a disagreement with the entity's own stated figure", () => {
    render(
      <FundingRunwayPanel
        features={[
          feature({
            value: 5,
            evidence: { entity_reported_quarters: 2, variance_vs_entity_reported: 3 },
          }),
        ]}
      />,
    );
    expect(screen.getByText(/与公司自报数字不一致/)).toBeInTheDocument();
  });

  it("explains what is missing rather than rendering an empty box", () => {
    render(<FundingRunwayPanel features={[]} />);
    expect(screen.getByText("暂无现金跑道")).toBeInTheDocument();
    expect(screen.getByText(/需要一份 Appendix 5B/)).toBeInTheDocument();
  });
});

describe("FundingRunwayPanel · 配售折价", () => {
  const discount: P4Feature = {
    feature_group: "dilution",
    feature_name: "placement_discount_pct",
    value: -25.93,
    unit: "%",
    as_of_date: "2026-09-25",
    formula_version: "placement_discount_v1",
    input_fact_ids: [96],
    evidence: {
      formula: "issue_price / prior_close - 1",
      inputs: { issue_price: 0.1, prior_close: 0.135 },
      prior_close_date: "2026-09-24",
      announcement_date: "2026-09-25",
      announcement_headline: "Institutional Placement",
    },
    metadata: { deep_discount: true },
  };

  it("shows the discount with the two prices behind it", () => {
    const { container } = render(<FundingRunwayPanel features={[feature(), discount]} />);
    expect(container.textContent).toContain("-25.93%");
    expect(container.textContent).toContain("深度折价");
    expect(container.textContent).toContain("0.135");
  });

  it("still renders the placement when no quarterly has been filed", () => {
    const { container } = render(<FundingRunwayPanel features={[discount]} />);
    expect(container.textContent).toContain("-25.93%");
    expect(container.textContent).toContain("暂无现金跑道");
  });
});

describe("FundingRunwayPanel · 资源量交叉校验", () => {
  const check = (overrides: Partial<P4Feature> = {}): P4Feature => ({
    feature_group: "resource",
    feature_name: "contained_metal_reconciliation_pct_probable_p1_0",
    value: 1796.1,
    unit: "%",
    as_of_date: "2026-09-29",
    formula_version: "contained_metal_check_v1",
    input_fact_ids: [1, 2, 3],
    evidence: {
      inputs: { tonnage_mt: 36.8, grade: 1, reported: 62.4 },
      implied: 1183.1,
      implied_unit: "koz",
      classification: "Probable",
      source_excerpt: "Tonnes (Mt) Li2O (%) Ta2O5 (ppm) Fe2O3 (%)",
    },
    metadata: { consistent: false, likely_column_misread: true, classification: "Probable" },
    ...overrides,
  });

  it("warns loudly when the arithmetic says a column was misread", () => {
    const { container } = render(<FundingRunwayPanel features={[check()]} />);
    expect(container.textContent).toContain("疑似表格列错位");
    expect(container.textContent).toContain("1183.1");
    expect(container.textContent).toContain("请勿用于判断");
  });

  it("confirms the table when the two figures agree", () => {
    const { container } = render(
      <FundingRunwayPanel
        features={[check({ value: 0.5, metadata: { consistent: true, likely_column_misread: false, classification: "Probable" } })]}
      />,
    );
    expect(container.textContent).toContain("资源量自洽");
  });
});
