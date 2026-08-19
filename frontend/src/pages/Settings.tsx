import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type {
  AppConfig,
  ConfigHistory,
  PipelineRun,
  StockWithScore,
  WeightCalibration,
} from "../api/types";

const COMMODITIES = ["gold", "copper", "lithium", "uranium", "rare_earth"];

function WatchlistCard({ onChanged }: { onChanged: () => void }) {
  const [stocks, setStocks] = useState<StockWithScore[]>([]);
  const [adding, setAdding] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    const [active, inactive] = await Promise.all([
      api.get<StockWithScore[]>("/stocks?active=true"),
      api.get<StockWithScore[]>("/stocks?active=false"),
    ]);
    setStocks([...active, ...inactive].sort((a, b) => a.code.localeCompare(b.code)));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const add = async () => {
    const values = await form.validateFields();
    try {
      await api.post("/stocks", values);
      message.success(`${values.code.toUpperCase()} 已加入`);
      setAdding(false);
      form.resetFields();
      await load();
      onChanged();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const deactivate = async (code: string) => {
    await api.del(`/stocks/${code}`);
    await load();
    onChanged();
  };

  const reactivate = async (code: string) => {
    await api.put(`/stocks/${code}`, { active: true });
    await load();
    onChanged();
  };

  return (
    <Card
      size="small"
      title="股票池管理"
      extra={
        <Button size="small" type="primary" onClick={() => setAdding(true)}>
          添加
        </Button>
      }
    >
      <Table
        size="small"
        rowKey="code"
        dataSource={stocks}
        pagination={{ pageSize: 10, showSizeChanger: false }}
        columns={[
          { title: "代码", dataIndex: "code", width: 80 },
          { title: "公司", dataIndex: "name", ellipsis: true },
          { title: "品种", dataIndex: "commodity", width: 110, render: (c: string) => <Tag>{c}</Tag> },
          { title: "阶段", dataIndex: "stage", width: 100 },
          {
            title: "状态",
            dataIndex: "active",
            width: 80,
            render: (a: boolean) => (a ? <Tag color="green">活跃</Tag> : <Tag>停用</Tag>),
          },
          {
            title: "操作",
            key: "op",
            width: 100,
            render: (_, s) =>
              s.active ? (
                <Popconfirm title={`停用 ${s.code}?`} onConfirm={() => deactivate(s.code)}>
                  <Button size="small" danger type="link">
                    停用
                  </Button>
                </Popconfirm>
              ) : (
                <Button size="small" type="link" onClick={() => reactivate(s.code)}>
                  启用
                </Button>
              ),
          },
        ]}
      />
      <Modal title="添加股票" open={adding} onOk={add} onCancel={() => setAdding(false)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="code" label="ASX 代码" rules={[{ required: true }]}>
            <Input placeholder="例如 DYL" />
          </Form.Item>
          <Form.Item name="name" label="公司名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="commodity" label="品种" rules={[{ required: true }]}>
            <Select options={COMMODITIES.map((c) => ({ value: c, label: c }))} />
          </Form.Item>
          <Form.Item name="stage" label="阶段" initialValue="explorer">
            <Select
              options={[
                { value: "explorer", label: "explorer" },
                { value: "developer", label: "developer" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

function compactJson(value: unknown) {
  if (value === null || value === undefined) return "empty";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > 120 ? `${text.slice(0, 120)}...` : text;
}

function ConfigHistoryCard({ refreshKey }: { refreshKey: number }) {
  const [rows, setRows] = useState<ConfigHistory[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await api.get<ConfigHistory[]>("/config/history?limit=50"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <Card size="small" title="配置变更历史">
      <Table
        size="small"
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={{ pageSize: 8, showSizeChanger: false }}
        columns={[
          {
            title: "时间",
            dataIndex: "changed_at",
            width: 170,
            render: (d: string) => d.replace("T", " ").slice(0, 19),
          },
          { title: "配置项", dataIndex: "key", width: 170 },
          {
            title: "旧值",
            dataIndex: "old_value",
            ellipsis: true,
            render: (v: unknown) => <Typography.Text code>{compactJson(v)}</Typography.Text>,
          },
          {
            title: "新值",
            dataIndex: "new_value",
            ellipsis: true,
            render: (v: unknown) => <Typography.Text code>{compactJson(v)}</Typography.Text>,
          },
          { title: "来源", dataIndex: "source", width: 120 },
          { title: "操作者", dataIndex: "changed_by", width: 120 },
        ]}
      />
    </Card>
  );
}

function WeightCalibrationCard({
  onApply,
}: {
  onApply: (weights: Record<string, number>) => void;
}) {
  const [horizon, setHorizon] = useState(20);
  const [target, setTarget] = useState("excess");
  const [result, setResult] = useState<WeightCalibration | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setResult(
        await api.get<WeightCalibration>(
          `/backtest/weight-calibration?horizon_days=${horizon}&target=${target}`,
        ),
      );
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [horizon, target]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card
      size="small"
      title="回测权重校准"
      extra={
        <Space>
          <Select
            size="small"
            value={horizon}
            style={{ width: 90 }}
            onChange={setHorizon}
            options={[5, 20, 60, 120].map((v) => ({ value: v, label: `+${v}d` }))}
          />
          <Select
            size="small"
            value={target}
            style={{ width: 110 }}
            onChange={setTarget}
            options={[
              { value: "excess", label: "超额收益" },
              { value: "return", label: "绝对收益" },
            ]}
          />
          <Button size="small" onClick={load} loading={loading}>
            重新计算
          </Button>
        </Space>
      }
    >
      {result && (
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Space wrap>
            <Tag>样本 {result.sample_size}</Tag>
            {result.low_sample && <Tag color="warning">低样本，保持当前权重</Tag>}
            <Typography.Text type="secondary">
              推荐权重只作为建议，点击应用后仍需保存参数才会生效。
            </Typography.Text>
          </Space>
          <Space wrap>
            {Object.entries(result.recommended_weights).map(([k, v]) => (
              <Tag key={k}>
                {k}: {(v * 100).toFixed(1)}%
              </Tag>
            ))}
            <Button size="small" type="primary" onClick={() => onApply(result.recommended_weights)}>
              应用推荐权重
            </Button>
          </Space>
          <Table
            size="small"
            rowKey="subscore"
            dataSource={result.diagnostics}
            pagination={false}
            columns={[
              { title: "子分", dataIndex: "subscore", width: 140 },
              {
                title: "相关性",
                dataIndex: "correlation",
                width: 110,
                render: (v: number | null) => (v == null ? "-" : v.toFixed(3)),
              },
              {
                title: "高低分收益差",
                dataIndex: "top_bottom_spread",
                width: 130,
                render: (v: number | null) => (v == null ? "-" : `${v.toFixed(2)}%`),
              },
              {
                title: "原始信号",
                dataIndex: "raw_signal",
                width: 100,
                render: (v: number) => v.toFixed(3),
              },
            ]}
          />
          <Typography.Text type="secondary">{result.method}</Typography.Text>
        </Space>
      )}
    </Card>
  );
}

function ConfigCard({ onSaved }: { onSaved: () => void }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setConfig(await api.get<AppConfig>("/config"));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (!config) return <Card size="small" title="评分与信号参数" loading />;

  const setWeight = (k: string, v: number | null) =>
    setConfig({ ...config, weights: { ...config.weights, [k]: v ?? 0 } });
  const setThreshold = (group: "label_thresholds" | "signal_thresholds", k: string, v: number | null) =>
    setConfig({ ...config, [group]: { ...config[group], [k]: v ?? 0 } });

  const weightSum = Object.values(config.weights).reduce((a, b) => a + b, 0);

  const setCommodityInstrument = (k: string, v: string) =>
    setConfig({
      ...config,
      commodity_instruments: { ...config.commodity_instruments, [k]: v.trim() },
    });

  const applyRecommendedWeights = (weights: Record<string, number>) => {
    setConfig({ ...config, weights });
    message.info("推荐权重已填入，点击保存参数后生效");
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/config", {
        weights: config.weights,
        label_thresholds: config.label_thresholds,
        signal_thresholds: config.signal_thresholds,
        commodity_instruments: config.commodity_instruments,
        benchmark_instrument: config.benchmark_instrument,
      });
      message.success("已保存，下次 pipeline 生效");
      await load();
      onSaved();
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card size="small" title="评分与信号参数">
      <Typography.Text strong>权重（需合计为 1.0，当前 {weightSum.toFixed(2)}）</Typography.Text>
      <Space wrap style={{ margin: "8px 0 16px" }}>
        {Object.entries(config.weights).map(([k, v]) => (
          <span key={k}>
            {k}{" "}
            <InputNumber size="small" min={0} max={1} step={0.05} value={v} onChange={(nv) => setWeight(k, nv)} />
          </span>
        ))}
      </Space>
      <br />
      <Typography.Text strong>标签阈值</Typography.Text>
      <Space wrap style={{ margin: "8px 0 16px" }}>
        {Object.entries(config.label_thresholds).map(([k, v]) => (
          <span key={k}>
            {k}{" "}
            <InputNumber size="small" min={0} max={100} value={v} onChange={(nv) => setThreshold("label_thresholds", k, nv)} />
          </span>
        ))}
      </Space>
      <br />
      <Typography.Text strong>信号阈值</Typography.Text>
      <Space wrap style={{ margin: "8px 0 16px" }}>
        {Object.entries(config.signal_thresholds).map(([k, v]) => (
          <span key={k}>
            {k}{" "}
            <InputNumber size="small" value={v} onChange={(nv) => setThreshold("signal_thresholds", k, nv)} />
          </span>
        ))}
      </Space>
      <br />
      <Typography.Text strong>商品映射</Typography.Text>
      <Space wrap style={{ margin: "8px 0 16px" }}>
        {Object.entries(config.commodity_instruments).map(([k, v]) => (
          <span key={k}>
            {k}{" "}
            <Input
              size="small"
              style={{ width: 120 }}
              value={v}
              onChange={(e) => setCommodityInstrument(k, e.target.value)}
            />
          </span>
        ))}
      </Space>
      <br />
      <Typography.Text strong>回测基准</Typography.Text>
      <Space wrap style={{ margin: "8px 0 16px" }}>
        <Input
          size="small"
          style={{ width: 140 }}
          value={config.benchmark_instrument}
          onChange={(e) => setConfig({ ...config, benchmark_instrument: e.target.value.trim() })}
        />
      </Space>
      <br />
      <Button type="primary" onClick={save} loading={saving} style={{ marginTop: 12 }}>
        保存参数
      </Button>
      <div style={{ marginTop: 16 }}>
        <WeightCalibrationCard onApply={applyRecommendedWeights} />
      </div>
    </Card>
  );
}

function OpsCard() {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setRuns(await api.get<PipelineRun[]>("/admin/runs?limit=10"));
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const run = async (path: string, label: string) => {
    setBusy(true);
    try {
      const res = await api.post<{ detail: string }>(path);
      message.info(`${label}: ${res.detail}`);
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setBusy(false);
      await load();
    }
  };

  return (
    <Card size="small" title="运维">
      <Space wrap style={{ marginBottom: 12 }}>
        <Button type="primary" loading={busy} onClick={() => run("/admin/run-pipeline", "pipeline")}>
          立即跑 Pipeline
        </Button>
        <Button loading={busy} onClick={() => run("/admin/run-replay?days=400", "replay")}>
          重放历史信号
        </Button>
        <Button loading={busy} onClick={() => run("/admin/test-telegram", "telegram")}>
          测试 Telegram
        </Button>
      </Space>
      <Table
        size="small"
        rowKey="id"
        dataSource={runs}
        pagination={false}
        columns={[
          { title: "时间", dataIndex: "run_at", width: 170, render: (d: string) => d.replace("T", " ").slice(0, 19) },
          { title: "触发", dataIndex: "trigger", width: 90 },
          {
            title: "状态",
            dataIndex: "status",
            width: 90,
            render: (s: string) => (
              <Tag color={s === "success" ? "green" : s === "partial" ? "orange" : s === "running" ? "blue" : "red"}>
                {s}
              </Tag>
            ),
          },
          {
            title: "统计",
            key: "stats",
            ellipsis: true,
            render: (_, r) => {
              const s = r.stats as Record<string, unknown>;
              return `bars+${s.prices_added ?? "-"} 公告+${s.announcements_added ?? "-"} 信号+${s.signals_added ?? "-"} 用时${s.duration_s ?? "-"}s`;
            },
          },
        ]}
      />
    </Card>
  );
}

function AdminTokenCard({ onChanged }: { onChanged: () => void }) {
  const [token, setToken] = useState(() => globalThis.localStorage?.getItem("adminApiToken") ?? "");

  const save = () => {
    const trimmed = token.trim();
    if (trimmed) {
      localStorage.setItem("adminApiToken", trimmed);
      setToken(trimmed);
      message.success("Admin token saved locally");
      onChanged();
    } else {
      localStorage.removeItem("adminApiToken");
      setToken("");
      message.info("Admin token cleared");
      onChanged();
    }
  };

  const clear = () => {
    localStorage.removeItem("adminApiToken");
    setToken("");
    message.info("Admin token cleared");
    onChanged();
  };

  return (
    <Card size="small" title="Admin API Token">
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="Pipeline、replay、Telegram 测试和评分/配置编辑需要 backend/.env 中的 ADMIN_API_TOKEN。"
      />
      <Space.Compact style={{ width: "100%", maxWidth: 640 }}>
        <Input.Password
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Paste ADMIN_API_TOKEN"
          onPressEnter={save}
        />
        <Button type="primary" onClick={save}>
          Save
        </Button>
        <Button onClick={clear}>Clear</Button>
      </Space.Compact>
      <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
        Token 只保存在当前浏览器，并作为 X-Admin-Token 发送。
      </Typography.Paragraph>
    </Card>
  );
}

export default function Settings() {
  const [tick, setTick] = useState(0);
  const [hasAdminToken, setHasAdminToken] = useState(
    () => !!globalThis.localStorage?.getItem("adminApiToken")?.trim(),
  );
  const refreshAdminTokenState = () => {
    setHasAdminToken(!!localStorage.getItem("adminApiToken")?.trim());
    setTick((t) => t + 1);
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        设置
      </Typography.Title>
      <Alert
        type="info"
        showIcon
        message="Telegram 推送配置在 backend/.env（TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID），未配置时日报仍会生成并入库。"
      />
      <AdminTokenCard onChanged={refreshAdminTokenState} />
      {!hasAdminToken && (
        <Alert
          type="warning"
          showIcon
          message="输入并保存 ADMIN_API_TOKEN 后，才能使用 pipeline、replay、Telegram 测试和配置编辑。"
        />
      )}
      {hasAdminToken && <OpsCard />}
      <WatchlistCard onChanged={() => setTick((t) => t + 1)} />
      {hasAdminToken && <ConfigCard onSaved={() => setTick((t) => t + 1)} />}
      {hasAdminToken && <ConfigHistoryCard refreshKey={tick} />}
    </Space>
  );
}
