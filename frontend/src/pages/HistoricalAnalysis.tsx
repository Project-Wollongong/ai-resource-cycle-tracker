import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Divider,
  Empty,
  Form,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import ReactECharts from "echarts-for-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { HistoricalAnalysisReturn, HistoricalAnalysisSnapshot, StockWithScore } from "../api/types";
import LabelTag from "../components/LabelTag";
import Pct from "../components/Pct";

const { Text } = Typography;

const SCORE_COLORS = {
  high: "#b42318",
  watch: "#b54708",
  monitor: "#175cd3",
  muted: "#667085",
};

function scoreColor(score: number) {
  if (score >= 75) return SCORE_COLORS.high;
  if (score >= 60) return SCORE_COLORS.watch;
  if (score >= 45) return SCORE_COLORS.monitor;
  return SCORE_COLORS.muted;
}

function returnStatusColor(status: HistoricalAnalysisReturn["status"]) {
  if (status === "filled") return "green";
  if (status === "unavailable") return "red";
  return "gold";
}

export default function HistoricalAnalysis() {
  const [form] = Form.useForm();
  const [stocks, setStocks] = useState<StockWithScore[]>([]);
  const [snapshots, setSnapshots] = useState<HistoricalAnalysisSnapshot[]>([]);
  const [selected, setSelected] = useState<HistoricalAnalysisSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const stockRows = await api.get<StockWithScore[]>("/stocks");
      setStocks(stockRows);
      const snapshotRows = await api.get<HistoricalAnalysisSnapshot[]>("/historical-analysis?limit=100");
      setSnapshots(snapshotRows);
      setSelected((current) => current ?? snapshotRows[0] ?? null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (values: { code: string; as_of_date: dayjs.Dayjs; mode: string }) => {
    setRunning(true);
    setError(null);
    try {
      const snapshot = await api.post<HistoricalAnalysisSnapshot>("/historical-analysis/run", {
        code: values.code,
        as_of_date: values.as_of_date.format("YYYY-MM-DD"),
        mode: values.mode,
      });
      setSelected(snapshot);
      await load();
      setSelected(snapshot);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const refreshReturns = async () => {
    if (!selected) return;
    setRunning(true);
    setError(null);
    try {
      const snapshot = await api.post<HistoricalAnalysisSnapshot>(`/historical-analysis/${selected.id}/returns`);
      setSelected(snapshot);
      setSnapshots((rows) => rows.map((row) => (row.id === snapshot.id ? snapshot : row)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const stockOptions = stocks.map((stock) => ({
    value: stock.code,
    label: `${stock.code} · ${stock.name}`,
  }));

  const returnChart = useMemo(() => {
    if (!selected) return null;
    return {
      animation: false,
      tooltip: { trigger: "axis" },
      grid: { left: 46, right: 22, top: 34, bottom: 34 },
      legend: { top: 0 },
      xAxis: {
        type: "category",
        data: selected.returns.map((row) => `+${row.horizon_days}d`),
      },
      yAxis: { type: "value", name: "%" },
      series: [
        {
          name: "实际收益",
          type: "bar",
          data: selected.returns.map((row) => row.return_pct ?? 0),
          itemStyle: {
            color: (params: { value: number }) => (params.value >= 0 ? "#12b76a" : "#f04438"),
          },
        },
        {
          name: "基准收益",
          type: "bar",
          data: selected.returns.map((row) => row.benchmark_return_pct ?? 0),
          itemStyle: { color: "#475467" },
        },
        {
          name: "最大回撤",
          type: "line",
          data: selected.returns.map((row) => row.max_drawdown_pct ?? 0),
          smooth: true,
          lineStyle: { color: "#b42318", width: 2 },
          itemStyle: { color: "#b42318" },
        },
      ],
    };
  }, [selected]);

  const snapshotColumns: ColumnsType<HistoricalAnalysisSnapshot> = [
    {
      title: "代码",
      dataIndex: "code",
      width: 86,
      render: (code: string) => <Text strong>{code}</Text>,
    },
    { title: "公司", dataIndex: "stock_name", ellipsis: true },
    { title: "历史日期", dataIndex: "as_of_date", width: 120 },
    { title: "行情截止", dataIndex: "market_data_as_of", width: 120 },
    {
      title: "评分",
      dataIndex: "cycle_score",
      width: 150,
      sorter: (a, b) => a.cycle_score - b.cycle_score,
      render: (score: number) => (
        <Space>
          <Text strong style={{ color: scoreColor(score), width: 42, display: "inline-block" }}>
            {score.toFixed(1)}
          </Text>
          <Progress percent={score} showInfo={false} size="small" style={{ width: 72 }} strokeColor={scoreColor(score)} />
        </Space>
      ),
    },
    {
      title: "标签",
      dataIndex: "label",
      width: 130,
      render: (label: string) => <LabelTag label={label} />,
    },
    {
      title: "+20d",
      width: 112,
      render: (_, row) => {
        const ret = row.returns.find((item) => item.horizon_days === 20);
        return ret?.status === "filled" ? <Pct value={ret.return_pct} /> : <Tag color={returnStatusColor(ret?.status ?? "pending")}>{ret?.status ?? "pending"}</Tag>;
      },
    },
    {
      title: "边界",
      dataIndex: "boundary_status",
      width: 120,
      render: (status: string, row) => (
        <Tooltip title={row.data_warnings.join("\n") || status}>
          <Tag color={status === "strict" ? "green" : status === "incomplete" ? "red" : "gold"}>{status}</Tag>
        </Tooltip>
      ),
    },
  ];

  return (
    <div>
      <Space align="start" style={{ justifyContent: "space-between", width: "100%", marginBottom: 16 }} wrap>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>
            历史评分验证台
          </Typography.Title>
          <Text type="secondary">
            按历史时点重建 Cycle Score，再用后续真实走势检验评分是否有研究价值。
          </Text>
        </div>
        <Tag color="blue">Point-in-time audit</Tag>
      </Space>

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      <Row gutter={[16, 16]} align="stretch">
        <Col xs={24} lg={8}>
          <Card title="运行历史评分" loading={loading} styles={{ body: { minHeight: 322 } }}>
            <Form
              form={form}
              layout="vertical"
              initialValues={{ mode: "approximate", as_of_date: dayjs().subtract(30, "day") }}
              onFinish={run}
            >
              <Form.Item name="code" label="股票" rules={[{ required: true, message: "请选择股票" }]}>
                <Select
                  showSearch
                  placeholder="选择 ASX 股票"
                  options={stockOptions}
                  optionFilterProp="label"
                />
              </Form.Item>
              <Form.Item name="as_of_date" label="历史分析日期" rules={[{ required: true, message: "请选择日期" }]}>
                <DatePicker style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="mode" label="数据边界模式">
                <Select
                  options={[
                    { value: "approximate", label: "Approximate · 当前可用字段近似" },
                    { value: "strict", label: "Strict · 仅限完整 available_at" },
                  ]}
                />
              </Form.Item>
              <Button type="primary" htmlType="submit" block loading={running}>
                生成评分快照
              </Button>
            </Form>
            <Divider />
            <Text type="secondary">
              当前版本会阻断未来价格和未来公告；由于系统还没有统一 available_at，默认结果会标记为 approximate。
            </Text>
          </Card>
        </Col>

        <Col xs={24} lg={16}>
          {selected ? (
            <SnapshotDashboard snapshot={selected} chartOption={returnChart} onRefreshReturns={refreshReturns} busy={running} />
          ) : (
            <Card styles={{ body: { minHeight: 322, display: "grid", placeItems: "center" } }}>
              <Empty description="还没有历史评分快照" />
            </Card>
          )}
        </Col>
      </Row>

      <Card title="历史快照记录" style={{ marginTop: 16 }}>
        <Table
          size="small"
          rowKey="id"
          columns={snapshotColumns}
          dataSource={snapshots}
          loading={loading}
          pagination={{ pageSize: 10 }}
          scroll={{ x: 980 }}
          onRow={(record) => ({
            onClick: () => setSelected(record),
            style: { cursor: "pointer" },
          })}
        />
      </Card>
    </div>
  );
}

function SnapshotDashboard({
  snapshot,
  chartOption,
  onRefreshReturns,
  busy,
}: {
  snapshot: HistoricalAnalysisSnapshot;
  chartOption: object | null;
  onRefreshReturns: () => void;
  busy: boolean;
}) {
  const ret20 = snapshot.returns.find((row) => row.horizon_days === 20);
  const filled = snapshot.returns.filter((row) => row.status === "filled");
  const bestReturn = filled.length ? Math.max(...filled.map((row) => row.return_pct ?? -Infinity)) : null;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card
        title={
          <Space wrap>
            <Text strong>{snapshot.code}</Text>
            <Text>{snapshot.stock_name}</Text>
            <LabelTag label={snapshot.label} />
            <Tag color={snapshot.boundary_status === "strict" ? "green" : "gold"}>{snapshot.boundary_status}</Tag>
          </Space>
        }
        extra={
          <Button size="small" onClick={onRefreshReturns} loading={busy}>
            刷新表现
          </Button>
        }
      >
        <Row gutter={[16, 16]}>
          <Col xs={12} md={6}>
            <Statistic
              title="历史评分"
              value={snapshot.cycle_score}
              precision={1}
              valueStyle={{ color: scoreColor(snapshot.cycle_score), fontWeight: 700 }}
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="+20d 收益" value={ret20?.return_pct ?? undefined} precision={1} suffix="%" valueStyle={{ color: (ret20?.return_pct ?? 0) >= 0 ? "#12b76a" : "#f04438" }} />
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="最佳已验证收益" value={bestReturn ?? undefined} precision={1} suffix="%" />
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="快照 ID" value={snapshot.id} />
          </Col>
        </Row>

        <Descriptions size="small" column={{ xs: 1, sm: 2, md: 4 }} style={{ marginTop: 16 }}>
          <Descriptions.Item label="历史日期">{snapshot.as_of_date}</Descriptions.Item>
          <Descriptions.Item label="行情截止">{snapshot.market_data_as_of ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="运行时间">{dayjs(snapshot.run_at).format("YYYY-MM-DD HH:mm")}</Descriptions.Item>
          <Descriptions.Item label="输入 Hash">{snapshot.input_hash.slice(0, 12)}</Descriptions.Item>
        </Descriptions>

        <Text type="secondary">{snapshot.ai_reason}</Text>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="后续表现">
            <ReturnsTable rows={snapshot.returns} />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="收益曲线对比">
            {chartOption ? <ReactECharts option={chartOption} style={{ height: 286 }} notMerge /> : <Empty />}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="子分结构">
            <SubscoreGrid snapshot={snapshot} />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="数据边界审计">
            <BoundaryAudit snapshot={snapshot} />
          </Card>
        </Col>
      </Row>
    </Space>
  );
}

function ReturnsTable({ rows }: { rows: HistoricalAnalysisReturn[] }) {
  const columns: ColumnsType<HistoricalAnalysisReturn> = [
    { title: "周期", dataIndex: "horizon_days", width: 70, render: (v: number) => `+${v}d` },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (status: HistoricalAnalysisReturn["status"]) => <Tag color={returnStatusColor(status)}>{status}</Tag>,
    },
    { title: "入场", dataIndex: "entry_price", width: 96, render: (v: number | null, r) => (v == null ? "-" : `${r.entry_date} / ${v.toFixed(3)}`) },
    { title: "收益", dataIndex: "return_pct", width: 86, render: (v: number | null) => <Pct value={v} /> },
    { title: "基准", dataIndex: "benchmark_return_pct", width: 86, render: (v: number | null) => <Pct value={v} /> },
    { title: "最大回撤", dataIndex: "max_drawdown_pct", width: 96, render: (v: number | null) => <Pct value={v} /> },
  ];
  return <Table size="small" rowKey="horizon_days" columns={columns} dataSource={rows} pagination={false} scroll={{ x: 620 }} />;
}

function SubscoreGrid({ snapshot }: { snapshot: HistoricalAnalysisSnapshot }) {
  const items = [
    ["Announcement", snapshot.announcement_score, "公告驱动"],
    ["Resource", snapshot.resource_score, "资源质量"],
    ["Commodity", snapshot.commodity_score, "商品周期"],
    ["Risk", snapshot.risk_score, "风险安全边际"],
    ["Sentiment", snapshot.sentiment_score, "情绪热度"],
    ["Funding", snapshot.funding_score, "资金确认"],
  ] as const;
  return (
    <Row gutter={[12, 12]}>
      {items.map(([name, score, label]) => (
        <Col xs={12} md={8} key={name}>
          <div style={{ border: "1px solid #eaecf0", borderRadius: 6, padding: 10, minHeight: 86 }}>
            <Text type="secondary">{name}</Text>
            <div style={{ color: scoreColor(score), fontSize: 24, fontWeight: 700, lineHeight: "30px" }}>
              {score.toFixed(1)}
            </div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {label}
            </Text>
          </div>
        </Col>
      ))}
    </Row>
  );
}

function BoundaryAudit({ snapshot }: { snapshot: HistoricalAnalysisSnapshot }) {
  const summary = snapshot.input_summary;
  return (
    <Space direction="vertical" size={10} style={{ width: "100%" }}>
      <Descriptions size="small" column={1}>
        <Descriptions.Item label="价格记录">{String(summary.price_bar_count ?? "-")}</Descriptions.Item>
        <Descriptions.Item label="公告记录">{String(summary.announcement_count ?? "-")}</Descriptions.Item>
        <Descriptions.Item label="商品记录">{String(summary.commodity_bar_count ?? "-")}</Descriptions.Item>
        <Descriptions.Item label="Live 信号">{String(summary.live_signal_count ?? "-")}</Descriptions.Item>
      </Descriptions>
      {snapshot.data_warnings.length ? (
        snapshot.data_warnings.map((warning) => (
          <Alert key={warning} type="warning" showIcon message={warning} />
        ))
      ) : (
        <Alert type="success" showIcon message="数据边界完整" />
      )}
    </Space>
  );
}
