import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Pct from "./Pct";

describe("Pct", () => {
  it("renders positive values with a plus sign", () => {
    render(<Pct value={12.345} digits={2} />);

    expect(screen.getByText("+12.35%").getAttribute("style")).toContain("var(--up)");
  });

  it("renders negative and zero values without a plus sign", () => {
    const { rerender } = render(<Pct value={-1.2} />);
    expect(screen.getByText("-1.2%").getAttribute("style")).toContain("var(--down)");

    rerender(<Pct value={0} />);
    expect(screen.getByText("0.0%").getAttribute("style")).toContain("var(--ink-faint)");
  });

  it("renders a muted placeholder for missing values", () => {
    render(<Pct value={null} />);

    expect(screen.getByText("–")).toHaveStyle({ color: "#999" });
  });
});
