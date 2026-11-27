import { describe, expect, it } from "vitest";

import { baseChartOption, chartPalette, signalMarkerColour } from "./chartTheme";
import { darkPalette, palette } from "./theme";

describe("图表主题", () => {
  it("takes its colours from the same palette as the rest of the page", () => {
    // The charts were the one surface the theme did not reach; in dark mode a
    // white chart is the brightest thing on screen.
    expect(chartPalette("dark").up).toBe(darkPalette.up);
    expect(chartPalette("light").up).toBe(palette.up);
    expect(chartPalette("dark").ink).not.toBe(chartPalette("light").ink);
  });

  it("never paints its own background over the page", () => {
    for (const mode of ["light", "dark"] as const) {
      expect(baseChartOption(chartPalette(mode)).backgroundColor).toBe("transparent");
    }
  });

  it("gives axes and tooltips the dark values in dark mode", () => {
    const option = baseChartOption(chartPalette("dark"));

    expect(option.axis.axisLabel.color).toBe(darkPalette.inkFaint);
    expect(option.tooltip.backgroundColor).toBe(darkPalette.surface);
    expect(option.tooltip.textStyle.color).toBe(darkPalette.ink);
  });

  it("recesses a rule the backtest did not support instead of colouring it like the rest", () => {
    // Five arbitrary hues both overspent the colour budget and gave
    // BREAKOUT_252D — measured at -29.78% excess — the same weight as a rule
    // the evidence backs. The letter already separates the categories.
    const c = chartPalette("light");

    expect(signalMarkerColour("BREAKOUT_252D", c)).toBe(c.absent);
    expect(signalMarkerColour("BREAKOUT_60D", c)).toBe(c.azurite);
    expect(signalMarkerColour("REL_VOL_SPIKE", c)).toBe(c.azurite);
  });

  it("keeps the price pair reserved for price", () => {
    // up/down are spent on direction and nothing else, so no marker may use them
    const c = chartPalette("light");
    for (const type of ["BREAKOUT_252D", "BREAKOUT_60D", "KEY_ANNOUNCEMENT"]) {
      expect([c.up, c.down]).not.toContain(signalMarkerColour(type, c));
    }
  });
});

describe("颜色纪律", () => {
  it("no component hard-codes a colour outside the palette files", async () => {
    // A hex literal anywhere else is a colour that cannot follow the theme:
    // it was how the charts stayed white in dark mode, and how four panels
    // kept their own reds long after the palette was introduced.
    const glob = import.meta.glob("./**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true });
    const allowed = /theme\.ts$|chartTheme\.ts$|\.test\.tsx?$/;
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(glob)) {
      if (allowed.test(path)) continue;
      if (/#[0-9a-fA-F]{6}\b/.test(source as string)) offenders.push(path);
    }
    expect(offenders).toEqual([]);
  });
});
