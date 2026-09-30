import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { P3InformationPoint, P3ParseStatus } from "../api/types";
import P3InformationPoints, { informationPointCountLabel } from "./P3InformationPoints";

const status = {
  information_point_count: 9, count_status: "source_insufficient", summary_point_count: 9,
  standard_form_point_count: 0, body_fallback_point_count: 0, atomic_fact_count: 12,
} as P3ParseStatus;

const point = {
  id: 1, event_id: 2, announcement_id: 3, evidence_document_id: 4, parse_run_id: 5,
  family: "F04", point_type: "timeline_change", point_title: "Project schedule changed from September 2026 to Q4 2026",
  fact_count: 3, status: "mixed", source_section: "highlights", source_page_start: 1, source_page_end: 1,
  source_excerpt: "rescheduled to the fourth quarter", review_status: "proposed", active_result: true,
  facts: [], project: null, asset_unit: null, created_at: "2026-09-18T00:00:00",
  information_point_group_id: 1, information_point_type: "timeline_change", primary_fact_id: null,
} as P3InformationPoint;

describe("P3InformationPoints", () => {
  it("shows source insufficiency without padding the count", () => {
    render(<P3InformationPoints points={[point]} status={status} />);
    expect(screen.getByText("9 个信息点 · 来源不足")).toBeInTheDocument();
    expect(screen.getByText(/20–50 是覆盖目标，不补数、不截断/)).toBeInTheDocument();
    expect(screen.getByText(point.point_title)).toBeInTheDocument();
    expect(informationPointCountLabel(status)).toContain("来源不足");
  });

  it("shows the audited summary-first escalation path", () => {
    const withAudit = {
      ...status,
      fact_extraction: {
        policy: "summary_bullets_then_missing_fields_standard_form_then_body_v1",
        summary_priority: ["summary", "highlights", "key_results", "executive_summary"],
        summary_bullet_count: 3, summary_fact_count: 2, fields_after_summary: ["funding_method"],
        missing_after_summary: ["F06.issue_price"], standard_form_used: false,
        standard_form_pages: [], standard_form_fact_count: 0,
        missing_after_standard_form: ["F06.issue_price"], body_fallback_used: true,
        body_fallback_pages: [1], body_fallback_fact_count: 1,
        remaining_missing_fields: [], source_fact_counts: { highlights: 2, body_fallback: 1 },
      },
    } as P3ParseStatus;
    render(<P3InformationPoints points={[point]} status={withAudit} />);
    expect(screen.getByText(/Summary\/Highlights bullets 3 条/)).toBeInTheDocument();
    expect(screen.getByText(/标准表格未读取/)).toBeInTheDocument();
    expect(screen.getByText(/正文补缺 1 个/)).toBeInTheDocument();
    expect(screen.getByText(/Family 字段检查已通过/)).toBeInTheDocument();
  });

  it("expands one logical group into ordered atomic facts", () => {
    const grouped = {
      ...point,
      information_point_group_id: 8,
      information_point_type: "drill_intersection",
      primary_fact_id: 101,
      facts: [
        { id: 101, fact_type: "hole_id", field_name: "Hole ID", value_raw: "BCRC115", unit_raw: null, status: "reported", role: "primary", display_order: 0, information_point_group_id: 8, information_point_type: "drill_intersection", parent_fact_id: null },
        { id: 102, fact_type: "interval_length", field_name: "Interval Length", value_raw: "8", unit_raw: "m", status: "reported", role: "component", display_order: 1, information_point_group_id: 8, information_point_type: "drill_intersection", parent_fact_id: 101 },
      ],
    } as P3InformationPoint;
    const groupedStatus = {
      ...status,
      information_point_grouping: {
        schema: "logical_information_point_v2", information_point_count: 1, atomic_fact_count: 2,
        grouped_fact_count: 2, all_facts_preserved: true, point_types: { drill_intersection: 1 },
        display_reduction: 1, no_padding: true, no_truncation: true,
      },
    } as P3ParseStatus;
    const { container } = render(<P3InformationPoints points={[grouped]} status={groupedStatus} />);
    const expand = container.querySelector(".ant-table-row-expand-icon") as HTMLElement;
    expect(expand).toBeTruthy();
    fireEvent.click(expand);
    expect(screen.getByText("Hole ID")).toBeInTheDocument();
    expect(screen.getByText("Interval Length")).toBeInTheDocument();
    expect(screen.getByText("主 Fact")).toBeInTheDocument();
    expect(screen.getByText("组成 Fact")).toBeInTheDocument();
    expect(screen.getByText(/2 个原子 Fact → 1 个信息点/)).toBeInTheDocument();
    expect(screen.getByText(/底层 Fact 全部保留/)).toBeInTheDocument();
  });
});
