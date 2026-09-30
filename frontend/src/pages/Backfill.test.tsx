import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import { BackfillPanel } from "./Backfill";

vi.mock("../api/client", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

describe("BackfillPanel", () => {
  it("requires a read-only preview before execution and shows the bounded-scope warning", async () => {
    vi.mocked(api.get).mockResolvedValue([]);
    vi.mocked(api.post).mockResolvedValue({
      preview_token: "a".repeat(64), filters: {}, total_announcements: 3, skipped_count: 1,
      existing_pdf: 2, missing_pdf: 1, existing_raw_text: 2, missing_raw_text: 1,
      parsed: 1, unparsed: 2, estimated_downloads: 0, estimated_reparse: 2,
      possible_failure: 0, by_stock: { CVV: 1, AGY: 2 }, by_family: { F04: 1, F08: 2 },
      actions: ["parse_document", "extract_facts"], notice: "本次只处理管理员选定范围，不会自动处理全部历史公告。", read_only: true,
    });
    render(<BackfillPanel />);
    expect(screen.getByText("本次只处理管理员选定范围，不会自动处理全部历史公告。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "执行回填" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("股票代码"), { target: { value: "CVV,AGY" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "执行回填" })).toBeEnabled());
    expect(screen.getByText("3")).toBeInTheDocument();
  });
});
