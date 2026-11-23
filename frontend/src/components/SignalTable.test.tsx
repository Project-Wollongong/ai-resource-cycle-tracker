import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { Signal } from "../api/types";
import SignalTable from "./SignalTable";

const signal: Signal = {
  id: 1,
  code: "DYL",
  stock_name: "Deep Yellow",
  date: "2026-07-20",
  signal_type: "REL_VOL_SPIKE",
  source: "live",
  label: "High Priority",
  reason: "relative volume spike",
  evidence: {},
  price_at_signal: 1.234,
  cycle_score_at_signal: 82,
  returns: [
    {
      horizon_days: 5,
      entry_price: 1.234,
      return_pct: 12.3,
      benchmark_return_pct: 3.1,
      status: "filled",
    },
    {
      horizon_days: 20,
      entry_price: null,
      return_pct: null,
      benchmark_return_pct: null,
      status: "pending",
    },
  ],
};

describe("SignalTable", () => {
  it("renders signal rows with stock links and filled returns", () => {
    render(
      <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <SignalTable signals={[signal]} />
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: "DYL" });
    expect(link).toHaveAttribute("href", "/stocks/DYL");
    expect(screen.getByText("REL_VOL_SPIKE")).toBeInTheDocument();
    // labels now display in Chinese while the API value drives filters
    expect(screen.getByText("高优先")).toBeInTheDocument();
    expect(screen.getByText("relative volume spike")).toBeInTheDocument();
    expect(screen.getByText("+12.3%")).toBeInTheDocument();
  });

  it("can hide the stock column", () => {
    render(
      <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <SignalTable signals={[signal]} showStock={false} />
      </MemoryRouter>,
    );

    const table = screen.getByRole("table");
    expect(within(table).queryByRole("link", { name: "DYL" })).not.toBeInTheDocument();
  });
});
