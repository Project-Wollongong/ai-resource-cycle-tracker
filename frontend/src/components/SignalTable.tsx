import { Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link } from "react-router-dom";

import type { Signal, SignalReturn } from "../api/types";
import LabelTag from "./LabelTag";
import Pct from "./Pct";

const TYPE_COLORS: Record<string, string> = {
  REL_VOL_SPIKE: "purple",
  BREAKOUT_60D: "cyan",
  BREAKOUT_252D: "geekblue",
  KEY_ANNOUNCEMENT: "magenta",
  SCORE_CROSS_UP: "orange",
};

// Rules the forward-return backtest found non-predictive. They still fire and
// are still shown — hiding them would lose information — but the table says so
// on the row, so a reader never mistakes one for a buy confirmation.
const WATCH_ONLY_NOTES: Record<string, string> = {
  BREAKOUT_252D:
    "回测 n=119（+120 天）：胜率 30.3%，相对 OZR.AX 平均超额 -29.78%。" +
    "仅 +5 天为正。按历史表现，这是「值得看一眼」的关注提示，不是买入确认。",
};

function ReturnCell({ ret }: { ret: SignalReturn | undefined }) {
  if (!ret || ret.status === "pending") return <span style={{ color: "#999" }}>-</span>;
  if (ret.status === "unavailable")
    return (
      <Tooltip title="股票停牌或退市，无法回填">
        <span style={{ color: "#999" }}>n/a</span>
      </Tooltip>
    );
  const excess =
    ret.benchmark_return_pct !== null && ret.return_pct !== null
      ? ret.return_pct - ret.benchmark_return_pct
      : null;
  return (
    <Tooltip title={excess !== null ? `超额 vs 基准: ${excess > 0 ? "+" : ""}${excess.toFixed(1)}%` : "无基准数据"}>
      <span>
        <Pct value={ret.return_pct} />
      </span>
    </Tooltip>
  );
}

export default function SignalTable({
  signals,
  loading,
  showStock = true,
}: {
  signals: Signal[];
  loading?: boolean;
  showStock?: boolean;
}) {
  const horizonCol = (h: number): ColumnsType<Signal>[number] => ({
    title: `+${h}d`,
    key: `h${h}`,
    width: 80,
    render: (_, sig) => <ReturnCell ret={sig.returns.find((r) => r.horizon_days === h)} />,
  });

  const columns: ColumnsType<Signal> = [
    { title: "日期", dataIndex: "date", width: 110, sorter: (a, b) => a.date.localeCompare(b.date), defaultSortOrder: "descend" },
    ...(showStock
      ? [
          {
            title: "股票",
            key: "code",
            width: 90,
            render: (_: unknown, sig: Signal) => <Link to={`/stocks/${sig.code}`}>{sig.code}</Link>,
          },
        ]
      : []),
    {
      title: "信号",
      dataIndex: "signal_type",
      width: 220,
      render: (t: string) => (
        <>
          <Tag color={TYPE_COLORS[t] ?? "default"}>{t}</Tag>
          {WATCH_ONLY_NOTES[t] && (
            <Tooltip title={WATCH_ONLY_NOTES[t]}>
              <Tag color="warning" style={{ cursor: "help" }}>
                仅关注
              </Tag>
            </Tooltip>
          )}
        </>
      ),
    },
    {
      title: "来源",
      dataIndex: "source",
      width: 80,
      render: (s: string) => <Tag>{s === "live" ? "实时" : "回放"}</Tag>,
    },
    {
      title: "标签",
      dataIndex: "label",
      width: 120,
      // a replayed signal carries no score by design, which is a different
      // thing from a stock that has not been scored
      render: (l: string | null) => <LabelTag label={l} missing="replay" />,
    },
    {
      title: "原因",
      dataIndex: "reason",
      ellipsis: { showTitle: false },
      render: (r: string) => (
        <Tooltip title={r}>
          <Typography.Text style={{ maxWidth: 360 }} ellipsis>
            {r}
          </Typography.Text>
        </Tooltip>
      ),
    },
    { title: "信号价", dataIndex: "price_at_signal", width: 90, render: (p: number) => p?.toFixed(3) },
    horizonCol(5),
    horizonCol(20),
    horizonCol(60),
    horizonCol(120),
  ];

  return (
    <Table
      size="small"
      rowKey="id"
      columns={columns}
      dataSource={signals}
      loading={loading}
      pagination={{ pageSize: 20, showSizeChanger: false }}
      scroll={{ x: 1100 }}
    />
  );
}
