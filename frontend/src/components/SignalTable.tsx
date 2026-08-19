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
      width: 160,
      render: (t: string) => <Tag color={TYPE_COLORS[t] ?? "default"}>{t}</Tag>,
    },
    {
      title: "来源",
      dataIndex: "source",
      width: 80,
      render: (s: string) => (s === "live" ? <Tag color="green">live</Tag> : <Tag>replay</Tag>),
    },
    { title: "标签", dataIndex: "label", width: 120, render: (l: string | null) => <LabelTag label={l} /> },
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
