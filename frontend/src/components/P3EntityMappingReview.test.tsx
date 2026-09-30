import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { P3EntityMapping } from "../api/types";
import P3EntityMappingReview from "./P3EntityMappingReview";

const suggestion: P3EntityMapping = {
  id: 31, entity_mention_id: 11, announcement_id: 1, evidence_document_id: 9, parse_run_id: 2,
  p3_event_id: 3, p3_fact_id: null, mention_type: "asset_unit", mention_text_raw: "Nort Pipe",
  mention_text_normalized: "nort pipe", source_section: "highlights", source_page_start: 1,
  source_page_end: 1, source_page: 1, source_excerpt: "Drilling continued at Nort Pipe.",
  matched_entity_type: "asset_unit", matched_entity_id: null, matched_entity: null,
  candidate_entity: { id: 4, type: "asset_unit", name: "North Pipe", project_id: 2 },
  matched_alias: null, match_method: "fuzzy_match", match_confidence: 0.94,
  status: "review_needed", stock_validation_result: "stock_project_relationship_confirmed",
  parent_validation_result: "parent_project_confirmed", matching_reason: "review required",
  review_needed: true, created_at: "2026-09-30", updated_at: null,
};

afterEach(() => vi.unstubAllGlobals());

describe("P3EntityMappingReview", () => {
  it("shows fuzzy suggestions as review-only and confirms through the review API", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [suggestion] })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...suggestion, status: "confirmed" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [] });
    vi.stubGlobal("fetch", fetchMock);
    render(<P3EntityMappingReview reviewer="p01-owner" />);
    expect(await screen.findByText("North Pipe")).toBeInTheDocument();
    expect(screen.getByText("模糊匹配建议")).toBeInTheDocument();
    expect(screen.getByText(/仅是待确认建议/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /确\s*认/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/p3/entity-mappings/31/confirm",
      expect.objectContaining({ method: "POST" }),
    ));
  });
});
