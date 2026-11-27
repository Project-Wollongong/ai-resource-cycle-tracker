import ReactECharts from "echarts-for-react";

import { baseChartOption, chartPalette, useThemeMode, type ChartPalette } from "../chartTheme";
import type { ScoreBrief } from "../api/types";

/**
 * Cycle Score and its parts over time.
 *
 * Seven lines cannot each have a hue without spending the whole budget, so
 * only the total is drawn in the accent; the sub-scores are separated by
 * weight and by how present the ink is, which is the same device the rest of
 * the product uses for confidence.
 */
function series(c: ChartPalette): { key: keyof ScoreBrief; name: string; color: string; selected: boolean }[] {
  return [
    { key: "cycle_score", name: "Cycle", color: c.azurite, selected: true },
    { key: "funding_score", name: "Funding", color: c.ink, selected: true },
    { key: "announcement_score", name: "Announcement", color: c.inkSoft, selected: true },
    { key: "resource_score", name: "Resource", color: c.inkFaint, selected: false },
    { key: "commodity_score", name: "Commodity", color: c.ochre, selected: false },
    { key: "risk_score", name: "Risk", color: c.gossan, selected: false },
    { key: "sentiment_score", name: "Sentiment", color: c.absent, selected: false },
  ];
}

export default function ScoreHistoryChart({ scores }: { scores: ScoreBrief[] }) {
  const c = chartPalette(useThemeMode());
  const base = baseChartOption(c);
  const lines = series(c);

  const option = {
    animation: false,
    backgroundColor: base.backgroundColor,
    textStyle: base.textStyle,
    tooltip: { ...base.tooltip, trigger: "axis" },
    legend: {
      ...base.legend,
      data: lines.map((s) => s.name),
      selected: Object.fromEntries(lines.map((s) => [s.name, s.selected])),
    },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { ...base.axis, type: "category", data: scores.map((s) => s.date) },
    yAxis: { ...base.axis, min: 0, max: 100 },
    series: lines.map((s) => ({
      name: s.name,
      type: "line",
      showSymbol: false,
      lineStyle: { width: s.key === "cycle_score" ? 3 : 1.5, color: s.color },
      itemStyle: { color: s.color },
      data: scores.map((row) => Math.round((row[s.key] as number) * 10) / 10),
    })),
  };
  return <ReactECharts option={option} style={{ height: 260 }} notMerge />;
}
