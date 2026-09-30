import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { P3Fact } from "../api/types";
import P3FactsTable, { hasDrillContext, neutralFactSummary } from "./P3FactsTable";

const fact: P3Fact = {
  id: 1, event_id: 2, announcement_id: 3, evidence_document_id: 4, parse_run_id: 5,
  family: "F04", fact_type: "dfs_completion", field_name: "DFS Completion", value_raw: "Q4 2026",
  value_numeric: null, value_text: "Q4 2026", unit_raw: null, unit_normalized: null,
  currency_raw: null, currency_normalized: null, quantity_type: "date", period_start: "2026-10-01",
  period_end: "2026-12-31", as_of_date: null, effective_date: null, status: "targeted",
  project_attribution_status: "confirmed", source_section: "highlights", source_page: 1,
  source_page_start: 1, source_page_end: 1, source_excerpt: "DFS rescheduled to Q4 2026", extractor_name: "deterministic",
  extractor_version: "v1", extraction_confidence: 0.94, review_status: "proposed", active_result: true,
  validity_status: "current", display_validity_status: "current", validity_reason: "", has_pending_version_relation: false,
  information_point_group_id: 7, information_point_type: "timeline_change", parent_fact_id: null, display_order: 0,
  event: { id: 2, event_type: "Project Schedule / Timeline Update", event_title: "Project Schedule Update", family: "F04" },
  stock: null, project: { id: 1, name: "Caravel Copper Project", project_key: "caravel" }, asset_unit: null,
  evidence_document: { id: 4, title: "DFS update", source_url: "https://example.test", page_count: 4 },
  created_at: "2026-09-18T00:00:00", updated_at: null,
};

describe("P3FactsTable", () => {
  it("shows neutral fact, status, project and PDF evidence page", () => {
    render(<P3FactsTable facts={[fact]} />);
    expect(screen.getByText("DFS Completion")).toBeInTheDocument();
    expect(screen.getByText("Q4 2026")).toBeInTheDocument();
    expect(screen.getByText("targeted")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看版本" })).toHaveAttribute("href", "/api/p3/facts/1/history");
    expect(screen.getByText("Caravel Copper Project")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "第 1 页原文" })).toHaveAttribute("href", "/api/announcements/evidence/4/original");
  });

  it("shows superseded, withdrawn, historical and pending-review status labels neutrally", () => {
    const rows: P3Fact[] = [
      { ...fact, id: 11, validity_status: "superseded", display_validity_status: "superseded" },
      { ...fact, id: 12, validity_status: "withdrawn", display_validity_status: "withdrawn" },
      { ...fact, id: 13, validity_status: "historical", display_validity_status: "historical" },
      { ...fact, id: 14, validity_status: "current", display_validity_status: "correction_pending_review", has_pending_version_relation: true },
    ];
    render(<P3FactsTable facts={rows} />);
    expect(screen.getByText("Superseded · 已由后续披露替代")).toBeInTheDocument();
    expect(screen.getByText("Withdrawn · 公司已撤回")).toBeInTheDocument();
    expect(screen.getByText("Historical")).toBeInTheDocument();
    expect(screen.getByText("可能修正，待人工复核")).toBeInTheDocument();
  });

  it("uses a neutral empty state and summary", () => {
    render(<P3FactsTable facts={[]} />);
    expect(screen.getByText("尚未提取事实")).toBeInTheDocument();
    expect(neutralFactSummary([])).toBe("尚未提取事实");
    expect(neutralFactSummary([fact])).not.toMatch(/利好|利空|买入|卖出/);
    expect(hasDrillContext([{ primary_family: "F04" }])).toBe(false);
    expect(hasDrillContext([{ primary_family: "F01" }])).toBe(true);
  });
});
