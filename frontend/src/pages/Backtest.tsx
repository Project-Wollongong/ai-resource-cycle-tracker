import { Alert, Card, Radio, Segmented, Space, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import ReactECharts from "echarts-for-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { BacktestGroup, BacktestSummary } from "../api/types";
import Pct from "../components/Pct";

const HORIZONS = [5, 20, 60, 120];

export default function Backtest() {
  const [groupBy, setGroupBy] = useState("signal_type");
  const [source, setSource] = useState("all");
  const [horizon, setHorizon] = useState(20);
  const [summary, setSummary] = useState<BacktestSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setSummary(
        await api.get<BacktestSummary>(`/backtest/summary?group_by=${groupBy}&source=${source}`),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }, [groupBy, source]);

  useEffect(() => {
    void load();
  }, [load]);

  const columns: ColumnsType<BacktestGroup> = [
    { title: "分组", dataIndex: "group", width: 160, render: (g: string) => <b>{g}</b> },
    ...HORIZONS.map((h) => ({
      title: `+${h}d`,
      key: `h${h}`,
      render: (_: unknown, row: BacktestGroup) => {
        const cell = row.cells.find((c) => c.horizon_days === h);
        if (!cell || cell.n === 0) return <Typography.Text type="secondary">无样本</Typography.Text>;
        return (
          <Space direction="vertical" size={0}>
            <span>
              n={cell.n}
              {cell.low_sample && (
                <Tooltip title="样本量 < 10，结论不可靠">
                  <Tag color="warning" style={{ marginLeft: 6 }}>
                    低样本
                  </Tag>
                </Tooltip>
              )}
            </span>
            <span>
              胜率 {((cell.win_rate ?? 0) * 100).toFixed(0)}% · 均值 <Pct value={cell.avg} />
            </span>
            <span>
              中位 <Pct value={cell.median} /> · 超额 <Pct value={cell.avg_excess} />
            </span>
          </Space>
        );
      },
    })),
    {
      title: "无法回填",
      dataIndex: "unavailable",
      width: 100,
      render: (u: number) =>
        u > 0 ? (
          <Tooltip title="停牌或退市导致无法回填的信号数，用于暴露幸存者偏差">
            <Tag>{u}</Tag>
          </Tooltip>
        ) : null,
    },
  ];

  const chartOption = summary && {
    animation: false,
    tooltip: {},
    grid: { left: 50, right: 20, top: 30, bottom: 60 },
    xAxis: {
      type: "category",
      data: summary.groups.map((g) => g.group),
      axisLabel: { rotate: 20 },
    },
    yAxis: { name: "avg %" },
    series: [
      {
        name: `+${horizon}d 平均收益`,
        type: "bar",
        data: summary.groups.map((g) => {
          const cell = g.cells.find((c) => c.horizon_days === horizon);
          const v = cell?.avg ?? 0;
          return { value: v, itemStyle: { color: v >= 0 ? "#26a69a" : "#ef5350" } };
        }),
      },
      {
        name: `+${horizon}d 平均超额`,
        type: "bar",
        data: summary.groups.map((g) => {
          const cell = g.cells.find((c) => c.horizon_days === horizon);
          return cell?.avg_excess ?? 0;
        }),
        itemStyle: { color: "#1677ff88" },
      },
    ],
    legend: { top: 0 },
  };

  return (
    <div>
      <Typography.Title level={4}>回测：信号历史上有没有参考价值</Typography.Title>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="回测口径"
        description="入场价 = 信号后首个交易日收盘价；超额 = 信号收益 - 同期 OZR.AX（ASX 资源 ETF）收益。replay 信号由历史行情重放价格类规则产生，不含标签和公告信号。系统只度量公告标题和量价规则下的正面故事强度，存在负面消息盲区。仅供研究参考，不构成投资建议。"
      />
      <Space style={{ marginBottom: 12 }} wrap>
        <Segmented
          value={groupBy}
          onChange={(v) => setGroupBy(v as string)}
          options={[
            { value: "signal_type", label: "按信号类型" },
            { value: "label", label: "按标签（live）" },
            { value: "score_bucket", label: "按分数段（live）" },
            { value: "interval_quality", label: "By interval quality (live)" },
            { value: "materiality", label: "By materiality (live)" },
          ]}
        />
        <Radio.Group value={source} onChange={(e) => setSource(e.target.value)}>
          <Radio.Button value="all">全部</Radio.Button>
          <Radio.Button value="live">live</Radio.Button>
          <Radio.Button value="replay">replay</Radio.Button>
        </Radio.Group>
        <Segmented
          value={horizon}
          onChange={(v) => setHorizon(v as number)}
          options={HORIZONS.map((h) => ({ value: h, label: `图表 +${h}d` }))}
        />
        {summary && <Tag>共 {summary.total_signals} 个信号，实际统计口径 source={summary.source}</Tag>}
      </Space>
      {error && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      {summary && (
        <>
          <Table
            size="small"
            rowKey="group"
            columns={columns}
            dataSource={summary.groups}
            pagination={false}
            style={{ marginBottom: 16 }}
          />
          {chartOption && (
            <Card size="small" title="各组平均收益 vs 平均超额">
              <ReactECharts option={chartOption} style={{ height: 300 }} notMerge />
            </Card>
          )}
        </>
      )}
    </div>
  );
}
