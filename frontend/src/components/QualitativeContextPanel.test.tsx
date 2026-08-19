import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { QualitativeContext } from "../api/types";
import QualitativeContextPanel from "./QualitativeContextPanel";

const context: QualitativeContext = {
  intercept_index: 0,
  width_m: 10,
  grade: 4.5,
  unit: "g/t",
  normalized_unit: "g/t",
  commodity: "gold",
  project: "Bankan",
  region: "Pilbara",
  extraction_quality: "complete",
  missing_fields: [],
  comparison_warnings: ["trend uses project history"],
  grade_thickness: 45,
  depth_category: "shallow",
  interval_quality_label: "strong",
  company_percentile: 78,
  project_percentile: 80,
  regional_percentile: 76,
  trend_vs_previous: "improving",
  trend_basis: "project",
  materiality_label: "high",
  company_history_count: 12,
  project_history_count: 5,
  regional_history_count: 9,
  reason: "grade-thickness is 45; sufficient project history",
  qualitative_assessment:
    "Within the stored project history, this interval ranks as strong, with grade-thickness in the 80th percentile.",
};

describe("QualitativeContextPanel", () => {
  it("renders qualitative mining context fields", () => {
    render(<QualitativeContextPanel context={context} />);

    expect(screen.getByText(context.qualitative_assessment)).toBeInTheDocument();
    expect(screen.getByText("Extraction: complete")).toBeInTheDocument();
    expect(screen.getByText("10.00m at 4.50 g/t")).toBeInTheDocument();
    expect(screen.getByText("gold")).toBeInTheDocument();
    expect(screen.getByText("Bankan")).toBeInTheDocument();
    expect(screen.getByText("Pilbara")).toBeInTheDocument();
    expect(screen.getByText("None")).toBeInTheDocument();
    expect(screen.getByText("45.00")).toBeInTheDocument();
    expect(screen.getByText("shallow")).toBeInTheDocument();
    expect(screen.getByText("strong")).toBeInTheDocument();
    expect(screen.getByText("78.0th")).toBeInTheDocument();
    expect(screen.getByText("80.0th")).toBeInTheDocument();
    expect(screen.getByText("76.0th")).toBeInTheDocument();
    expect(screen.getByText("improving")).toBeInTheDocument();
    expect(screen.getByText("project")).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
    expect(screen.getByText("trend uses project history")).toBeInTheDocument();
    expect(screen.getByText(context.reason)).toBeInTheDocument();
  });

  it("renders an empty state when context is missing", () => {
    render(<QualitativeContextPanel context={null} />);

    expect(screen.getByText("No qualitative context available")).toBeInTheDocument();
  });

  it("renders multiple intercept contexts in collapsible sections", () => {
    render(
      <QualitativeContextPanel
        contexts={[
          context,
          {
            ...context,
            intercept_index: 1,
            width_m: 20,
            grade: 1.5,
            grade_thickness: 30,
            depth_category: "medium",
            qualitative_assessment:
              "Within the stored project history, this interval ranks as moderate.",
          },
        ]}
      />,
    );

    expect(screen.getByText("Intercept 1: 10m at 4.50 g/t")).toBeInTheDocument();
    expect(screen.getByText("Intercept 2: 20m at 1.50 g/t")).toBeInTheDocument();
  });
});
