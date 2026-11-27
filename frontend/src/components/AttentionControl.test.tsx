import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AttentionControl from "./AttentionControl";
import { api } from "../api/client";
import type { AttentionView } from "../api/types";

function state(overrides: Partial<AttentionView> = {}): AttentionView {
  return {
    state_level: "L1",
    state_label: "Watch",
    previous_state_level: null,
    transition: "hold",
    reason: "Attention state is below the threshold for a trade decision workflow.",
    manual_override: false,
    manual_lock: false,
    alert_priority: "normal",
    effective_at: "2026-11-26T00:00:00",
    trade_decision: { decision: "pass", action: "none", conviction: "low", reason: "below threshold" },
    ...overrides,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  globalThis.localStorage?.clear();
});

describe("AttentionControl", () => {
  it("shows the level alongside the decision it produced", () => {
    const { container } = render(
      <AttentionControl code="WC8" state={state()} onChange={() => {}} />,
    );

    expect(screen.getByText("L1 观察")).toBeInTheDocument();
    expect(container.textContent).toContain("不操作");
  });

  it("marks a state a person is holding", () => {
    render(
      <AttentionControl
        code="WC8"
        state={state({ state_level: "L4", manual_override: true })}
        onChange={() => {}}
      />,
    );

    expect(screen.getByText("人工持有")).toBeInTheDocument();
    expect(screen.getByText("该状态由人工持有，引擎不会改动它")).toBeInTheDocument();
  });

  it("offers to hand a held state back, and not otherwise", () => {
    const { rerender } = render(
      <AttentionControl code="WC8" state={state()} onChange={() => {}} />,
    );
    expect(screen.queryByRole("button", { name: "交回引擎" })).not.toBeInTheDocument();

    rerender(
      <AttentionControl code="WC8" state={state({ manual_override: true })} onChange={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "交回引擎" })).toBeInTheDocument();
  });

  it("will not submit without a name to record", () => {
    // the override is an event in the history; an unattributed one is useless
    render(<AttentionControl code="WC8" state={state()} onChange={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "人工设定" }));

    expect(screen.getByRole("button", { name: "设 定" })).toBeDisabled();
  });

  it("warns that L4 produces an actionable decision before anyone confirms", () => {
    render(<AttentionControl code="WC8" state={state()} onChange={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "人工设定" }));

    expect(screen.getByText("L4 会让下游产生可执行的交易决策")).toBeInTheDocument();
  });

  it("sends the level, the actor and the note", async () => {
    const put = vi.spyOn(api, "put").mockResolvedValue({} as never);
    const onChange = vi.fn();
    render(<AttentionControl code="WC8" state={state()} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: "人工设定" }));
    fireEvent.change(screen.getByPlaceholderText("你的名字"), { target: { value: "Rachel" } });
    fireEvent.change(screen.getByPlaceholderText("为什么现在把它提到这一级"), {
      target: { value: "尽调已完成" },
    });
    fireEvent.click(screen.getByRole("button", { name: "设 定" }));

    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("/attention/WC8", {
        level: "L4",
        actor: "Rachel",
        note: "尽调已完成",
      }),
    );
    await waitFor(() => expect(onChange).toHaveBeenCalled());
  });

  it("shows the server's refusal rather than failing silently", async () => {
    vi.spyOn(api, "put").mockRejectedValue(new Error("unknown attention level 'L9'"));
    render(<AttentionControl code="WC8" state={state()} onChange={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "人工设定" }));
    fireEvent.change(screen.getByPlaceholderText("你的名字"), { target: { value: "Rachel" } });
    fireEvent.click(screen.getByRole("button", { name: "设 定" }));

    await waitFor(() =>
      expect(screen.getByText("unknown attention level 'L9'")).toBeInTheDocument(),
    );
  });

  it("says plainly when a stock has no attention state yet", () => {
    render(<AttentionControl code="WC8" state={null} onChange={() => {}} />);

    expect(screen.getByText("还没有注意力状态。")).toBeInTheDocument();
  });
});
