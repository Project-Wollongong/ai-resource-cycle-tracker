import { describe, expect, it } from "vitest";

import { selectedNavKey } from "./App";

describe("selectedNavKey", () => {
  it("highlights the entry for each nav route", () => {
    expect(selectedNavKey("/")).toBe("/");
    expect(selectedNavKey("/signals")).toBe("/signals");
    expect(selectedNavKey("/positions")).toBe("/positions");
    expect(selectedNavKey("/trade-reviews")).toBe("/trade-reviews");
    expect(selectedNavKey("/historical-analysis")).toBe("/historical-analysis");
    expect(selectedNavKey("/p3/version-review")).toBe("/p3/version-review");
    expect(selectedNavKey("/admin/backfill")).toBe("/admin/backfill");
  });

  it("falls back to the ranking page for detail routes", () => {
    // "/" prefixes every path, so it has to be the fallback rather than a
    // candidate — otherwise it would win every match.
    expect(selectedNavKey("/stocks/HAS")).toBe("/");
    expect(selectedNavKey("/projects/tabba-tabba-lithium-project")).toBe("/");
  });

  it("has no colliding prefixes among nav routes", () => {
    // A future "/report" alongside "/reports" would silently highlight the
    // wrong entry; this catches it when the route is added, not in review.
    const keys = [
      "/",
      "/positions",
      "/signals",
      "/backtest",
      "/historical-analysis",
      "/trade-reviews",
      "/reports",
      "/data-runs",
      "/entity-review",
      "/p3/version-review",
      "/admin/backfill",
      "/settings",
    ];
    for (const key of keys) {
      expect(selectedNavKey(key), `${key} should select itself`).toBe(key);
    }
  });
});
