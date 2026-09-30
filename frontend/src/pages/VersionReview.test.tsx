import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { P3VersionRelation } from "../api/types";
import { P3VersionReviewTable } from "./VersionReview";

const relation: P3VersionRelation = {
  id: 9, predecessor_type: "fact", predecessor_id: 1, successor_type: "fact", successor_id: 2,
  relation_type: "revises", status: "proposed", source_announcement_id: 20,
  source_evidence_document_id: 30, source_page_start: 1, source_page_end: 1,
  source_excerpt: "Highlights: DFS completion revised to Q4 2026.", withdrawal_reason: "",
  detected_by: "rule", confidence: 0.9, reviewed_by: null, reviewed_at: null, review_note: "",
  predecessor: { id: 1, type: "fact", validity_status: "current", fact_type: "dfs_completion", field_name: "DFS Completion Timing", value_raw: "September 2026", family: "F04" },
  successor: { id: 2, type: "fact", validity_status: "current", fact_type: "dfs_completion", field_name: "DFS Completion Timing", value_raw: "Q4 2026", family: "F04" },
  stock: { id: 1, code: "CVV", name: "Caravel Minerals" },
  source_announcement: { id: 20, ann_id: "2924-03136859-6A1344354", headline: "PS DFS Revised Completion Timing", ann_date: "2026-09-10", url: "https://example.test/cvv.pdf" },
  evidence_document: { id: 30, title: "DFS Revised", page_count: 4, pdf_url: "/api/announcements/evidence/30/original" },
};

describe("P3VersionReviewTable", () => {
  it("shows old/new values, evidence and human review actions", () => {
    const onAction = vi.fn();
    render(<P3VersionReviewTable rows={[relation]} notes={{ 9: "confirmed from Highlights" }} corrections={{}}
      onNote={() => undefined} onCorrection={() => undefined} onAction={onAction} />);
    expect(screen.getByText("DFS Completion Timing：September 2026")).toBeInTheDocument();
    expect(screen.getByText("DFS Completion Timing：Q4 2026")).toBeInTheDocument();
    expect(screen.getByText("待审核")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /expand row/i }));
    expect(screen.getByText("Highlights: DFS completion revised to Q4 2026.")).toBeInTheDocument();
    expect(screen.getByText(/打开原始 PDF/)).toHaveAttribute("href", "/api/announcements/evidence/30/original");
    fireEvent.click(screen.getByRole("button", { name: /确\s*认/ }));
    expect(onAction).toHaveBeenCalledWith(relation, "confirm");
  });

  it("does not show mutation actions for a confirmed relation", () => {
    render(<P3VersionReviewTable rows={[{ ...relation, status: "confirmed", predecessor: { ...relation.predecessor!, validity_status: "superseded" } }]}
      notes={{}} corrections={{}} onNote={() => undefined} onCorrection={() => undefined} onAction={() => undefined} />);
    expect(screen.getByText("已确认")).toBeInTheDocument();
    expect(screen.getByText("superseded")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /确\s*认/ })).not.toBeInTheDocument();
  });
});
