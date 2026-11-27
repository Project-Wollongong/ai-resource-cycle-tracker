import { useEffect, useState } from "react";

import { darkPalette, palette, resolveMode, type ThemeMode } from "./theme";

/**
 * ECharts, dressed from the same palette as everything else.
 *
 * The charts were the one place the theme did not reach: AntD and the CSS
 * variables both switched, and the candles, axes and tooltips stayed on a
 * white ground with their own hues. In dark mode that is not a cosmetic
 * mismatch — a white chart in a dark page is the brightest thing on screen.
 *
 * The colour discipline carries over. Up and down are the price pair and
 * nothing else; azurite marks what the reader can act on; the ochre pair is
 * reserved for states worth noticing. Where a chart needs to separate
 * categories it does so by shape and label rather than by spending hues it
 * does not have.
 */

export type ChartPalette = ReturnType<typeof chartPalette>;

export function chartPalette(mode: "light" | "dark") {
  const p = mode === "dark" ? darkPalette : palette;
  return {
    mode,
    ink: p.ink,
    inkSoft: p.inkSoft,
    inkFaint: p.inkFaint,
    line: p.line,
    surface: p.surface,
    sunk: p.sunk,
    azurite: p.azurite,
    up: p.up,
    down: p.down,
    ochre: p.ochre,
    gossan: p.gossan,
    absent: p.absent,
  };
}

/**
 * The resolved mode, kept in step with the rest of the page.
 *
 * `applyPaletteVars` stamps data-theme on the root whenever the mode changes,
 * including when the machine's own preference flips while "follow the system"
 * is selected, so watching that attribute covers every path without the chart
 * having to know which one happened.
 */
export function useThemeMode(): "light" | "dark" {
  const [mode, setMode] = useState<"light" | "dark">(() =>
    (document.documentElement.dataset.theme as "light" | "dark") ||
    resolveMode((globalThis.localStorage?.getItem("themeMode") as ThemeMode) ?? "system"),
  );

  useEffect(() => {
    const root = document.documentElement;
    const observer = new MutationObserver(() => {
      const next = root.dataset.theme;
      if (next === "light" || next === "dark") setMode(next);
    });
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  return mode;
}

/** Axes, grid, tooltip and legend, shared by every chart. */
export function baseChartOption(c: ChartPalette) {
  const axis = {
    axisLine: { lineStyle: { color: c.line } },
    axisTick: { lineStyle: { color: c.line } },
    axisLabel: { color: c.inkFaint, fontSize: 11 },
    splitLine: { lineStyle: { color: c.line, opacity: c.mode === "dark" ? 0.5 : 1 } },
  };
  return {
    backgroundColor: "transparent",
    textStyle: { color: c.inkSoft },
    axis,
    tooltip: {
      backgroundColor: c.surface,
      borderColor: c.line,
      textStyle: { color: c.ink },
      extraCssText: "box-shadow: none;",
    },
    legend: { textStyle: { color: c.inkSoft }, inactiveColor: c.absent },
    dataZoom: {
      borderColor: c.line,
      fillerColor: c.mode === "dark" ? "#6FA8DC22" : "#17568F14",
      handleStyle: { color: c.azurite },
      textStyle: { color: c.inkFaint },
      dataBackground: { lineStyle: { color: c.line }, areaStyle: { color: c.sunk } },
    },
  };
}

/**
 * How a signal marker is drawn.
 *
 * Previously five arbitrary hues, which both broke the four-colour budget and
 * gave a rule the backtest falsified the same visual weight as one it
 * supported. The letter already separates the categories, so the colour is
 * free to carry the thing that matters: whether the rule is confirming.
 */
const WATCH_ONLY = new Set(["BREAKOUT_252D"]);

export function signalMarkerColour(signalType: string, c: ChartPalette): string {
  return WATCH_ONLY.has(signalType) ? c.absent : c.azurite;
}
