import { ReloadOutlined } from "@ant-design/icons";
import { Alert, Badge, Button, Progress, Space, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { StockWithScore } from "../api/types";
import LabelTag from "../components/LabelTag";
import Pct from "../components/Pct";

const COMMODITY_COLORS: Record<string, string> = {
  gold: "gold",
  copper: "orange",
  lithium: "green",
  uranium: "lime",
  rare_earth: "purple",
};

function SubScores({ s }: { s: StockWithScore }) {
  if (!s.latest_score) return null;
  const parts: [string, number][] = [
    ["F", s.latest_score.funding_score],
    ["A", s.latest_score.announcement_score],
    ["R", s.latest_score.resource_score],
    ["C", s.latest_score.commodity_score],
    ["K", s.latest_score.risk_score],
  ];
  const names = ["Funding 35%", "Announcement 30%", "Resource 20%", "Commodity 10%", "Risk 5%"];
  return (
    <Space size={6}>
      {parts.map(([k, v], i) => (
        <Tooltip key={k} title={`${names[i]}: ${v.toFixed(1)}`}>
          <span style={{ fontSize: 12, color: v >= 60 ? "#cf1322" : v >= 30 ? "#d48806" : "#8c8c8c" }}>
            {k}
            {Math.round(v)}
          </span>
        </Tooltip>
      ))}
    </Space>
  );
}

export default function Ranking() {
  const [stocks, setStocks] = useState<StockWithScore[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setStocks(await api.get<StockWithScore[]>("/stocks"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const columns: ColumnsType<StockWithScore> = [
    {
      title: "#",
      key: "rank",
      width: 46,
      render: (_v, _r, i) => <Typography.Text type="secondary">{i + 1}</Typography.Text>,
    },
    {
      title: "代码",
      key: "code",
      width: 90,
      render: (_, s) => (
        <Link to={`/stocks/${s.code}`}>
          <b>{s.code}</b>
        </Link>
      ),
    },
    { title: "公司", dataIndex: "name", ellipsis: true },
    {
      title: "品种",
      dataIndex: "commodity",
      width: 100,
      filters: Object.keys(COMMODITY_COLORS).map((c) => ({ text: c, value: c })),
      onFilter: (v, s) => s.commodity === v,
      render: (c: string) => <Tag color={COMMODITY_COLORS[c]}>{c}</Tag>,
    },
    {
      title: "收盘",
      key: "close",
      width: 90,
      render: (_, s) => (s.last_close != null ? s.last_close.toFixed(3) : "-"),
    },
    {
      title: "涨跌",
      key: "chg",
      width: 90,
      sorter: (a, b) => (a.day_change_pct ?? -999) - (b.day_change_pct ?? -999),
      render: (_, s) => <Pct value={s.day_change_pct} />,
    },
    {
      title: "Cycle Score",
      key: "score",
      width: 170,
      sorter: (a, b) => (a.latest_score?.cycle_score ?? -1) - (b.latest_score?.cycle_score ?? -1),
      defaultSortOrder: "descend",
      render: (_, s) =>
        s.latest_score ? (
          <Space>
            <b style={{ width: 38, display: "inline-block" }}>{s.latest_score.cycle_score.toFixed(1)}</b>
            <Progress
              percent={s.latest_score.cycle_score}
              showInfo={false}
              size="small"
              style={{ width: 80 }}
              strokeColor={s.latest_score.cycle_score >= 75 ? "#cf1322" : s.latest_score.cycle_score >= 60 ? "#d48806" : "#1677ff"}
            />
          </Space>
        ) : (
          <Typography.Text type="secondary">未评分</Typography.Text>
        ),
    },
    { title: "子分", key: "subs", width: 190, render: (_, s) => <SubScores s={s} /> },
    {
      title: "标签",
      key: "label",
      width: 130,
      filters: ["High Priority", "Watch Closely", "Monitor", "Ignore"].map((l) => ({ text: l, value: l })),
      onFilter: (v, s) => s.latest_score?.label === v,
      render: (_, s) => <LabelTag label={s.latest_score?.label} />,
    },
    {
      title: "当日信号",
      key: "signals",
      width: 130,
      render: (_, s) =>
        s.today_signals.length ? (
          <Tooltip title={s.today_signals.join(", ")}>
            <Badge count={s.today_signals.length} color="#722ed1" />
          </Tooltip>
        ) : null,
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 12, justifyContent: "space-between", width: "100%" }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          ASX 资源股雷达
        </Typography.Title>
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
          刷新
        </Button>
      </Space>
      {error && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      <Table
        size="small"
        rowKey="code"
        columns={columns}
        dataSource={stocks}
        loading={loading}
        pagination={false}
        scroll={{ x: 1100 }}
      />
    </div>
  );
}
