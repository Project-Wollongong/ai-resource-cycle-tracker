import {
  Alert,
  Button,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Position } from "../api/types";
import Pct from "../components/Pct";

const ACTION_COLORS: Record<string, string> = {
  hold: "default",
  add: "green",
  review: "orange",
  exit: "red",
  closed: "default",
};

const STATUS_COLORS: Record<string, string> = {
  intact: "blue",
  strengthened: "green",
  weakened: "orange",
  invalidated: "red",
  normal: "green",
  elevated: "orange",
  critical: "red",
  on_track: "green",
  needs_review: "orange",
  unknown: "default",
};

export default function Positions() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [status, setStatus] = useState<string>("open");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openModal, setOpenModal] = useState(false);
  const [closeTarget, setCloseTarget] = useState<Position | null>(null);
  const [detail, setDetail] = useState<Position | null>(null);
  const [form] = Form.useForm();
  const [closeForm] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ limit: "500" });
    if (status) params.set("status", status);
    try {
      setPositions(await api.get<Position[]>(`/positions?${params.toString()}`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    void load();
  }, [load]);

  const openPosition = async () => {
    const values = await form.validateFields();
    try {
      await api.post<Position>("/positions", {
        code: values.code.trim().toUpperCase(),
        entry_price: values.entry_price,
        quantity: values.quantity,
        strategy_profile: values.strategy_profile,
        original_thesis: values.original_thesis ? { note: values.original_thesis } : undefined,
      });
      message.success("Position opened");
      setOpenModal(false);
      form.resetFields();
      await load();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const refreshPosition = async (position: Position) => {
    try {
      const updated = await api.post<Position>(`/positions/${position.id}/refresh`);
      setDetail(updated);
      await load();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const closePosition = async () => {
    if (!closeTarget) return;
    const values = await closeForm.validateFields();
    try {
      const closed = await api.post<Position>(`/positions/${closeTarget.id}/close`, {
        exit_price: values.exit_price,
        reason: values.reason,
      });
      message.success("Position closed");
      setCloseTarget(null);
      setDetail(closed);
      closeForm.resetFields();
      await load();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const loadDetail = async (position: Position) => {
    try {
      setDetail(await api.get<Position>(`/positions/${position.id}`));
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const columns: ColumnsType<Position> = [
    {
      title: "Code",
      key: "code",
      width: 95,
      render: (_, p) => <Link to={`/stocks/${p.code}`}>{p.code}</Link>,
    },
    { title: "Company", dataIndex: "stock_name", ellipsis: true },
    {
      title: "Status",
      dataIndex: "status",
      width: 90,
      render: (v: string) => <Tag color={v === "open" ? "green" : "default"}>{v}</Tag>,
    },
    {
      title: "Action",
      dataIndex: "suggested_action",
      width: 110,
      render: (v: string) => <Tag color={ACTION_COLORS[v] ?? "default"}>{v}</Tag>,
    },
    {
      title: "Thesis",
      dataIndex: "thesis_status",
      width: 120,
      render: (v: string) => <Tag color={STATUS_COLORS[v] ?? "default"}>{v}</Tag>,
    },
    {
      title: "Risk",
      dataIndex: "risk_status",
      width: 110,
      render: (v: string) => <Tag color={STATUS_COLORS[v] ?? "default"}>{v}</Tag>,
    },
    {
      title: "Entry",
      dataIndex: "entry_price",
      width: 90,
      render: (v: number) => v.toFixed(4),
    },
    {
      title: "Current",
      dataIndex: "current_price",
      width: 95,
      render: (v: number | null) => (v == null ? "-" : v.toFixed(4)),
    },
    {
      title: "P&L",
      dataIndex: "unrealized_pnl_pct",
      width: 90,
      render: (v: number | null) => <Pct value={v} />,
    },
    {
      title: "Value",
      dataIndex: "market_value",
      width: 115,
      render: (v: number | null) => (v == null ? "-" : v.toLocaleString(undefined, { maximumFractionDigits: 0 })),
    },
    {
      title: "Opened",
      dataIndex: "opened_at",
      width: 120,
      render: (v: string) => v.slice(0, 10),
    },
    {
      title: "",
      key: "ops",
      width: 210,
      render: (_, p) => (
        <Space size={6}>
          <Button size="small" onClick={() => loadDetail(p)}>
            View
          </Button>
          {p.status === "open" && (
            <>
              <Button size="small" onClick={() => refreshPosition(p)}>
                Refresh
              </Button>
              <Button size="small" danger onClick={() => setCloseTarget(p)}>
                Close
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 12, justifyContent: "space-between", width: "100%" }} wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Position Monitor
        </Typography.Title>
        <Space>
          <Select
            value={status}
            style={{ width: 130 }}
            onChange={setStatus}
            options={[
              { value: "open", label: "Open" },
              { value: "closed", label: "Closed" },
              { value: "", label: "All" },
            ]}
          />
          <Button onClick={load} loading={loading}>
            Refresh
          </Button>
          <Button type="primary" onClick={() => setOpenModal(true)}>
            Open Position
          </Button>
        </Space>
      </Space>
      {error && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      <Table
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={positions}
        loading={loading}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        scroll={{ x: 1250 }}
      />

      <PositionDetail position={detail} onClose={() => setDetail(null)} />

      <Modal title="Open Position" open={openModal} onOk={openPosition} onCancel={() => setOpenModal(false)}>
        <Form form={form} layout="vertical" initialValues={{ strategy_profile: "balanced" }}>
          <Form.Item name="code" label="Code" rules={[{ required: true }]}>
            <Input placeholder="OD6" />
          </Form.Item>
          <Form.Item name="entry_price" label="Entry Price" rules={[{ required: true }]}>
            <InputNumber min={0.0001} step={0.001} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="quantity" label="Quantity" rules={[{ required: true }]}>
            <InputNumber min={1} step={1000} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="strategy_profile" label="Strategy Profile">
            <Select
              options={[
                { value: "conservative", label: "Conservative" },
                { value: "balanced", label: "Balanced" },
                { value: "aggressive", label: "Aggressive" },
              ]}
            />
          </Form.Item>
          <Form.Item name="original_thesis" label="Original Thesis">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={`Close ${closeTarget?.code ?? ""}`} open={!!closeTarget} onOk={closePosition} onCancel={() => setCloseTarget(null)}>
        <Form form={closeForm} layout="vertical">
          <Form.Item name="exit_price" label="Exit Price" rules={[{ required: true }]}>
            <InputNumber min={0.0001} step={0.001} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="reason" label="Reason" initialValue="User closed the position.">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function PositionDetail({ position, onClose }: { position: Position | null; onClose: () => void }) {
  return (
    <Modal title={position ? `${position.code} Position` : "Position"} open={!!position} onCancel={onClose} footer={null} width={900}>
      {position && (
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Descriptions size="small" bordered column={3}>
            <Descriptions.Item label="Status">{position.status}</Descriptions.Item>
            <Descriptions.Item label="Suggested">{position.suggested_action}</Descriptions.Item>
            <Descriptions.Item label="Strategy">{position.strategy_profile}</Descriptions.Item>
            <Descriptions.Item label="Entry">{position.entry_price.toFixed(4)}</Descriptions.Item>
            <Descriptions.Item label="Current">{position.current_price?.toFixed(4) ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="P&L"><Pct value={position.unrealized_pnl_pct} /></Descriptions.Item>
            <Descriptions.Item label="Thesis">{position.thesis_status}</Descriptions.Item>
            <Descriptions.Item label="Catalyst">{position.catalyst_status}</Descriptions.Item>
            <Descriptions.Item label="Risk">{position.risk_status}</Descriptions.Item>
            <Descriptions.Item label="Price Stop">{position.price_stop?.toFixed(4) ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="Quantity">{position.quantity.toLocaleString()}</Descriptions.Item>
            <Descriptions.Item label="Market Value">
              {position.market_value?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? "-"}
            </Descriptions.Item>
          </Descriptions>
          <Typography.Text strong>Position Events</Typography.Text>
          <Table
            size="small"
            rowKey="id"
            dataSource={position.events}
            pagination={false}
            columns={[
              { title: "Time", dataIndex: "event_time", width: 155, render: (v: string) => v.replace("T", " ").slice(0, 16) },
              { title: "Type", dataIndex: "event_type", width: 130 },
              { title: "Action", dataIndex: "action", width: 90 },
              { title: "Price", dataIndex: "price", width: 90, render: (v: number | null) => (v == null ? "-" : v.toFixed(4)) },
              { title: "Reason", dataIndex: "reason" },
            ]}
          />
        </Space>
      )}
    </Modal>
  );
}
