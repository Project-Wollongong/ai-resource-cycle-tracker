import ReactECharts from "echarts-for-react";

import type { ScoreBrief } from "../api/types";

const SERIES: { key: keyof ScoreBrief; name: string; color: string; selected: boolean }[] = [
  { key: "cycle_score", name: "Cycle", color: "#1677ff", selected: true },
  { key: "funding_score", name: "Funding", color: "#722ed1", selected: true },
  { key: "announcement_score", name: "Announcement", color: "#eb2f96", selected: true },
  { key: "resource_score", name: "Resource", color: "#8c8c8c", selected: false },
  { key: "commodity_score", name: "Commodity", color: "#faad14", selected: false },
  { key: "risk_score", name: "Risk", color: "#52c41a", selected: false },
  { key: "sentiment_score", name: "Sentiment", color: "#13c2c2", selected: false },
];

export default function ScoreHistoryChart({ scores }: { scores: ScoreBrief[] }) {
  const option = {
    animation: false,
    tooltip: { trigger: "axis" },
    legend: {
      data: SERIES.map((s) => s.name),
      selected: Object.fromEntries(SERIES.map((s) => [s.name, s.selected])),
    },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { type: "category", data: scores.map((s) => s.date) },
    yAxis: { min: 0, max: 100 },
    series: SERIES.map((s) => ({
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
