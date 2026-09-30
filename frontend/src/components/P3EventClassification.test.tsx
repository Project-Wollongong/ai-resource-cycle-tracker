import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import type { P3Event } from "../api/types";
import { P3EventDetails, P3EventTags } from "./P3EventClassification";

const event: P3Event = {
  id: 10,
  event_id: 10,
  event_type: "Project Delay",
  event_family: "F04",
  primary_family: "F04",
  secondary_families: [],
  event_title: "Project Delay",
  event_status: "reported",
  classification_status: "review_needed",
  classification_source: "summary_confirmation",
  classification_confidence: 0.95,
  revision_tags: ["Revised"],
  classification_reason: "specific delay phrase in Highlights",
  active_result: true,
  source_section: "highlights",
  source_page_start: 1,
  source_page_end: 1,
  source_excerpt: "rescheduled to the fourth quarter of 2026",
  confidence: 0.95,
  parse_run_id: 7,
  project: null,
  asset_unit: null,
  review_needed: true,
};

it("shows neutral family, event, revision and review tags", () => {
  render(<P3EventTags events={[event]} />);
  expect(screen.getByText("Development & Study")).toBeInTheDocument();
  expect(screen.getByText("Project Delay")).toBeInTheDocument();
  expect(screen.getByText("Revised")).toBeInTheDocument();
  expect(screen.getByText("待人工复核")).toBeInTheDocument();
});

it("shows source lineage and parser version in expanded details", () => {
  render(<P3EventDetails events={[event]} parserVersion="p3_family_v2" />);
  expect(screen.getByText("rescheduled to the fourth quarter of 2026")).toBeInTheDocument();
  expect(screen.getByText("specific delay phrase in Highlights")).toBeInTheDocument();
  expect(screen.getByText("p3_family_v2")).toBeInTheDocument();
});
