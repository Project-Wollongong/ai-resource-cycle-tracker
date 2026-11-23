import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ConfidenceTag from "./ConfidenceTag";
import NoData from "./NoData";
import StatusPill from "./StatusPill";

describe("NoData", () => {
  it("names what is missing instead of rendering a blank", () => {
    render(<NoData reason="需要一份 Appendix 5B 季度现金流报告。" />);

    expect(screen.getByText("尚无法计算")).toBeInTheDocument();
    expect(screen.getByText(/Appendix 5B/)).toBeInTheDocument();
  });

  it("states that an absence is not a cleared check", () => {
    // An empty panel reads as reassurance. Most stocks have no quarterly on
    // file, and that says nothing whatsoever about their funding — so the panel
    // has to say so rather than leaving the reader to infer it.
    render(<NoData reason="缺季报" />);

    expect(screen.getByText(/无告警不代表状况良好/)).toBeInTheDocument();
  });

  it("keeps the reason available on hover in the compact form", () => {
    render(<NoData title="未评分" reason="当日没有产生评分快照" inline />);

    expect(screen.getByText("未评分")).toHaveAttribute("title", "当日没有产生评分快照");
  });
});

describe("StatusPill", () => {
  it("marks an unconfirmed reading differently from a settled one", () => {
    // A rule the backtest found non-predictive must not look like a verdict,
    // in either direction — hence the dashed border rather than a colour.
    const { container: settled } = render(<StatusPill level="critical">资金紧张</StatusPill>);
    const { container: unsettled } = render(<StatusPill level="unconfirmed">仅关注</StatusPill>);

    // asserted on the style attribute because the shorthand carries a var(),
    // which jsdom cannot expand into borderStyle
    expect(settled.querySelector("span")?.getAttribute("style")).toContain("solid");
    expect(unsettled.querySelector("span")?.getAttribute("style")).toContain("dashed");
  });

  it("keeps risk off the price hues", () => {
    // Red and green belong to price direction. A red risk pill would have to be
    // read as either "fell" or "dangerous", so risk uses the oxidised tones.
    const { container } = render(<StatusPill level="critical">严重</StatusPill>);

    expect(container.innerHTML).toContain("--gossan");
    expect(container.innerHTML).not.toContain("--down");
  });
});

describe("ConfidenceTag", () => {
  it("spells out that absent is not a passed check", () => {
    render(<ConfidenceTag level="absent" />);

    expect(screen.getByText("Absent")).toBeInTheDocument();
  });

  it("draws absent as an outline, since --c-absent cannot carry text", () => {
    const { container } = render(<ConfidenceTag level="absent" />);
    const tag = container.querySelector("span");

    expect(tag?.getAttribute("style")).toContain("transparent");
    expect(tag?.getAttribute("style")).toContain("dashed");
  });

  it("fills the tag for levels that are backed by evidence", () => {
    const { container } = render(<ConfidenceTag level="measured" />);

    expect(container.querySelector("span")?.getAttribute("style")).toContain("--c-measured");
  });
});

describe("palette discipline", () => {
  it("leaves red and green to price direction alone", async () => {
    // Risk, status and verification markers all used AntD's red/green before
    // this phase. A red pill that might mean "fell" or "dangerous" means
    // neither, so the rule has to hold everywhere or it teaches the wrong one.
    const files = import.meta.glob("../**/*.tsx", { query: "?raw", import: "default", eager: true });
    const offenders: string[] = [];

    for (const [path, source] of Object.entries(files)) {
      if (path.includes(".test.")) continue;
      if (/Tag\s+color="(red|green|volcano)"/.test(source as string)) offenders.push(path);
    }

    expect(offenders).toEqual([]);
  });
});
