import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LabelTag from "./LabelTag";

describe("LabelTag", () => {
  it("renders known bands in Chinese while keeping the API value for filters", () => {
    render(<LabelTag label="High Priority" />);

    expect(screen.getByText("高优先")).toBeInTheDocument();
  });

  it("says unscored, not replay, when a stock has no score", () => {
    // The previous behaviour rendered the word "replay" for every missing
    // label, which on the ranking page claimed a stock's score came from
    // historical playback when in fact no score had been produced at all.
    render(<LabelTag label={null} />);

    expect(screen.getByText("未评分")).toBeInTheDocument();
    expect(screen.queryByText("回放")).not.toBeInTheDocument();
  });

  it("says replay where a missing label genuinely means a replayed signal", () => {
    render(<LabelTag label={null} missing="replay" />);

    expect(screen.getByText("回放")).toBeInTheDocument();
    expect(screen.queryByText("未评分")).not.toBeInTheDocument();
  });

  it("passes an unrecognised band through rather than hiding it", () => {
    render(<LabelTag label="Some New Band" />);

    expect(screen.getByText("Some New Band")).toBeInTheDocument();
  });
});
