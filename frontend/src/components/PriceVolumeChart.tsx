import ReactECharts from "echarts-for-react";

import { baseChartOption, chartPalette, signalMarkerColour, useThemeMode } from "../chartTheme";
import type { PriceBar, Signal } from "../api/types";

export default function PriceVolumeChart({
  bars,
  signals,
}: {
  bars: PriceBar[];
  signals: Signal[];
}) {
  const c = chartPalette(useThemeMode());
  const base = baseChartOption(c);

  const dates = bars.map((b) => b.date);
  const candles = bars.map((b) => [b.open, b.close, b.low, b.high]);
  // the volume bar takes the day's direction, which is the same pair the
  // candle uses — green and red mean price and nothing else here
  const volumes = bars.map((b, i) => ({
    value: b.volume,
    itemStyle: { color: `${i > 0 && b.close >= bars[i - 1].close ? c.up : c.down}99` },
  }));

  const markPoints = signals
    .filter((s) => dates.includes(s.date))
    .map((s) => {
      const bar = bars[dates.indexOf(s.date)];
      return {
        coord: [s.date, bar.high],
        value: s.signal_type.split("_")[0][0] + (s.signal_type.includes("BREAKOUT") ? "B" : ""),
        itemStyle: { color: signalMarkerColour(s.signal_type, c) },
        tooltipText: `${s.date} ${s.signal_type}: ${s.reason}`,
      };
    });

  const option = {
    animation: false,
    backgroundColor: base.backgroundColor,
    textStyle: base.textStyle,
    tooltip: { ...base.tooltip, trigger: "axis", axisPointer: { type: "cross" } },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    grid: [
      { left: 60, right: 20, top: 20, height: "55%" },
      { left: 60, right: 20, top: "72%", height: "18%" },
    ],
    xAxis: [
      { ...base.axis, type: "category", data: dates, boundaryGap: true, axisLine: { onZero: false, lineStyle: { color: c.line } } },
      { ...base.axis, type: "category", gridIndex: 1, data: dates, axisLabel: { show: false } },
    ],
    yAxis: [
      { ...base.axis, scale: true, splitArea: { show: false } },
      { ...base.axis, gridIndex: 1, splitNumber: 2, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: 55, end: 100 },
      { ...base.dataZoom, type: "slider", xAxisIndex: [0, 1], top: "93%", start: 55, end: 100 },
    ],
    series: [
      {
        name: "price",
        type: "candlestick",
        data: candles,
        itemStyle: {
          color: c.up,
          color0: c.down,
          borderColor: c.up,
          borderColor0: c.down,
        },
        markPoint: {
          symbol: "pin",
          symbolSize: 34,
          label: { fontSize: 9, color: c.surface },
          data: markPoints,
          tooltip: {
            formatter: (p: { data?: { tooltipText?: string } }) => p.data?.tooltipText ?? "",
          },
        },
      },
      { name: "volume", type: "bar", xAxisIndex: 1, yAxisIndex: 1, data: volumes },
    ],
  };

  return <ReactECharts option={option} style={{ height: 420 }} notMerge />;
}
