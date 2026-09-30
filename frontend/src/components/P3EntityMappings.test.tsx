import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { P3EntityMapping } from "../api/types";
import P3EntityMappings from "./P3EntityMappings";

const mapping: P3EntityMapping = {
  id: 1, entity_mention_id: 1, announcement_id: 1, evidence_document_id: 9, parse_run_id: 2,
  p3_event_id: 3, p3_fact_id: null, mention_type: "project", mention_text_raw: "Project Alpha",
  mention_text_normalized: "project alpha", source_section: "highlights", source_page_start: 1,
  source_page_end: 1, source_page: 1, source_excerpt: "Project Alpha remains on schedule.",
  matched_entity_type: "project", matched_entity_id: 4,
  matched_entity: { id: 4, type: "project", name: "Alpha Copper Project", project_key: "alpha" },
  matched_alias: { id: 7, value: "Project Alpha", kind: "alias", is_current: false },
  match_method: "alias_match", match_confidence: 0.98, status: "confirmed",
  stock_validation_result: "stock_project_relationship_confirmed", parent_validation_result: "not_applicable",
  matching_reason: "confirmed", review_needed: false, created_at: "2026-09-29", updated_at: null,
};

describe("P3EntityMappings", () => {
  it("shows current entity, original alias, method, and page evidence", () => {
    render(<P3EntityMappings mappings={[mapping]} />);
    expect(screen.getByText("Alpha Copper Project")).toBeInTheDocument();
    expect(screen.getByText("别名匹配")).toBeInTheDocument();
    expect(screen.getByText("原名：Project Alpha")).toBeInTheDocument();
    expect(screen.getByText("第 1 页原文")).toBeInTheDocument();
  });

  it("hides a review candidate and displays pending confirmation", () => {
    render(<P3EntityMappings mappings={[{ ...mapping, id: 2, status: "review_needed", review_needed: true, matched_entity_id: null, matched_entity: null }]} />);
    expect(screen.queryByText("Alpha Copper Project")).not.toBeInTheDocument();
    expect(screen.getAllByText("待确认").length).toBeGreaterThan(0);
  });

  it("has a neutral empty state", () => {
    render(<P3EntityMappings mappings={[]} />);
    expect(screen.getByText("未识别到已知实体名称")).toBeInTheDocument();
  });
});
