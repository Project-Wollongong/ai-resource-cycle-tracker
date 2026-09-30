import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { P3UpdateProposal } from "../api/types";
import { P3UpdateProposalTable } from "./P3UpdateProposalReview";

const row: P3UpdateProposal = {
  id: 1, proposal_type: "new_asset_unit_candidate", status: "pending", stock_id: 1,
  stock: { id: 1, code: "NPP", name: "NPP Mining" }, proposed_name: "North Pipe",
  proposed_name_normalized: "north pipe", proposed_entity_type: "asset_unit", proposed_project_name: "Project A",
  proposed_asset_name: "North Pipe", proposed_asset_type: "pipe", proposed_commodity: null,
  proposed_parent_project_id: 2, candidate_parent_project: { id: 2, name: "Project A", project_key: "project-a" },
  proposed_payload: {}, supporting_announcement_count: 3, supporting_evidence_count: 3,
  supporting_event_count: 3, supporting_fact_count: 3, confidence: 0.95, created_by: "rule",
  reviewed_by: null, reviewed_at: null, review_note: "", correction_history: {}, resulting_entity: null,
  evidence: [{ mention_id: 1, mapping_id: 1, announcement_id: 1, evidence_document_id: 7,
    p3_event_id: 1, p3_fact_id: null, source_section: "highlights", source_page_start: 2,
    source_page_end: 2, mention_text_raw: "North Pipe", source_excerpt: "Independent drilling at North Pipe.",
    announcement: { id: 1, ann_id: "NPP-1", headline: "North Pipe drill results", ann_date: "2026-08-01", url: "https://example.test/npp.pdf" },
    evidence_document: { id: 7, title: "North Pipe drill results", page_count: 3, pdf_url: "/api/announcements/evidence/7/original" } }],
  created_at: "2026-09-29", updated_at: null,
};

describe("P3UpdateProposalTable", () => {
  it("shows candidate counts, parent, status, evidence, and review actions", () => {
    const onAction = vi.fn();
    render(<MemoryRouter><P3UpdateProposalTable rows={[row]} notes={{ 1: "review note" }} corrections={{}}
      onNote={() => undefined} onCorrection={() => undefined} onAction={onAction} /></MemoryRouter>);
    expect(screen.getByText("North Pipe")).toBeInTheDocument();
    expect(screen.getByText("3 公告 / 3 PDF / 3 Event / 3 Fact")).toBeInTheDocument();
    expect(screen.getByText("待审核")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /批\s*准/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /expand row/i }));
    expect(screen.getByText("North Pipe drill results")).toBeInTheDocument();
    expect(screen.getByText("第 2 页")).toBeInTheDocument();
    expect(screen.getByText("Independent drilling at North Pipe.")).toBeInTheDocument();
    expect(screen.getByText("打开原始 PDF")).toHaveAttribute("href", "/api/announcements/evidence/7/original");
    fireEvent.click(screen.getByRole("button", { name: /批\s*准/ }));
    expect(onAction).toHaveBeenCalledWith(row, "approve");
  });

  it("shows the resulting approved entity", () => {
    render(<MemoryRouter><P3UpdateProposalTable rows={[{ ...row, status: "approved", resulting_entity: { type: "asset_unit", id: 9, name: "North Pipe", project_id: 2 } }]}
      notes={{}} corrections={{}} onNote={() => undefined} onCorrection={() => undefined} onAction={() => undefined} /></MemoryRouter>);
    expect(screen.getByText("已批准")).toBeInTheDocument();
    expect(screen.getAllByText("North Pipe").length).toBeGreaterThan(1);
    expect(screen.queryByRole("button", { name: /批\s*准/ })).not.toBeInTheDocument();
  });
});
