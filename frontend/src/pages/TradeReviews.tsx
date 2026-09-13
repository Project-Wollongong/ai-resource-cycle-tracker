import {
  Alert,
  Button,
  Descriptions,
  Form,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Position, StrategyLearningCandidate, TradeReview } from "../api/types";
import Pct from "../components/Pct";

const OUTCOME_COLORS: Record<string, string> = {
  strong_profit: "green",
  profit: "green",
  flat: "default",
  loss: "orange",
  large_loss: "red",
};

const DECISION_COLORS: Record<string, string> = {
  supported: "green",
  inconclusive: "default",
  needs_review: "orange",
  lucky_profit_after_thesis_failure: "gold",
  poor_or_invalidated: "red",
};

const CANDIDATE_COLORS: Record<string, string> = {
  observation: "blue",
  hypothesis: "purple",
  rule_adjustment: "orange",
};

export default function TradeReviews() {
  const [reviews, setReviews] = useState<TradeReview[]>([]);
  const [candidates, setCandidates] = useState<StrategyLearningCandidate[]>([]);
  const [closedPositions, setClosedPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<TradeReview | null>(null);
  const [createModal, setCreateModal] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextReviews, nextCandidates, nextClosedPositions] = await Promise.all([
        api.get<TradeReview[]>("/trade-reviews?limit=500"),
        api.get<StrategyLearningCandidate[]>("/trade-reviews/candidates/list?limit=500"),
        api.get<Position[]>("/positions?status=closed&limit=500"),
      ]);
      setReviews(nextReviews);
      setCandidates(nextCandidates);
      setClosedPositions(nextClosedPositions);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const reviewedPositionIds = useMemo(() => new Set(reviews.map((r) => r.position_id)), [reviews]);
  const creatablePositions = closedPositions.filter((p) => !reviewedPositionIds.has(p.id));

  const generateReview = async () => {
    const values = await form.validateFields();
    setCreating(true);
    try {
      const review = await api.post<TradeReview>(`/trade-reviews/positions/${values.position_id}`);
      message.success("Trade review generated");
      setCreateModal(false);
      form.resetFields();
      setDetail(review);
      await load();
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setCreating(false);
    }
  };

  const loadDetail = async (review: TradeReview) => {
    try {
      setDetail(await api.get<TradeReview>(`/trade-reviews/${review.id}`));
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const reviewColumns: ColumnsType<TradeReview> = [
    {
      title: "Code",
      key: "code",
      width: 95,
      render: (_, r) => <Link to={`/stocks/${r.code}`}>{r.code}</Link>,
    },
    { title: "Company", dataIndex: "stock_name", ellipsis: true },
    { title: "Position", dataIndex: "position_id", width: 95, render: (v: number) => `#${v}` },
    { title: "Return", dataIndex: "return_pct", width: 95, render: (v: number) => <Pct value={v} /> },
    {
      title: "Outcome",
      dataIndex: "outcome_quality",
      width: 135,
      render: (v: string) => <Tag color={OUTCOME_COLORS[v] ?? "default"}>{v}</Tag>,
    },
    {
      title: "Decision",
      dataIndex: "decision_quality",
      width: 190,
      render: (v: string) => <Tag color={DECISION_COLORS[v] ?? "default"}>{v}</Tag>,
    },
    {
      title: "Candidates",
      dataIndex: "learning_candidates",
      width: 105,
      render: (v: StrategyLearningCandidate[]) => v.length,
    },
    { title: "Closed", dataIndex: "closed_at", width: 120, render: (v: string) => v.slice(0, 10) },
    {
      title: "",
      key: "ops",
      width: 90,
      render: (_, r) => (
        <Button size="small" onClick={() => loadDetail(r)}>
          View
        </Button>
      ),
    },
  ];

  const candidateColumns: ColumnsType<StrategyLearningCandidate> = [
    {
      title: "Code",
      key: "code",
      width: 85,
      render: (_, c) => <Link to={`/stocks/${c.code}`}>{c.code}</Link>,
    },
    {
      title: "Type",
      dataIndex: "candidate_type",
      width: 120,
      render: (v: string) => <Tag color={CANDIDATE_COLORS[v] ?? "default"}>{v}</Tag>,
    },
    { title: "Layer", dataIndex: "target_layer", width: 80 },
    { title: "Title", dataIndex: "title", ellipsis: true },
    { title: "Status", dataIndex: "status", width: 100 },
    {
      title: "Backtest",
      dataIndex: "requires_backtest",
      width: 95,
      render: (v: boolean) => (v ? <Tag color="orange">required</Tag> : <Tag>no</Tag>),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 12, justifyContent: "space-between", width: "100%" }} wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Trade Reviews
        </Typography.Title>
        <Space>
          <Button onClick={load} loading={loading}>
            Refresh
          </Button>
          <Button type="primary" onClick={() => setCreateModal(true)}>
            Generate Review
          </Button>
        </Space>
      </Space>

      {error && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}

      <Table
        size="small"
        rowKey="id"
        columns={reviewColumns}
        dataSource={reviews}
        loading={loading}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        scroll={{ x: 1100 }}
      />

      <Typography.Title level={5} style={{ marginTop: 24 }}>
        Learning Candidates
      </Typography.Title>
      <Table
        size="small"
        rowKey="id"
        columns={candidateColumns}
        dataSource={candidates}
        loading={loading}
        pagination={{ pageSize: 10, showSizeChanger: false }}
      />

      <Modal
        title="Generate Trade Review"
        open={createModal}
        onOk={generateReview}
        confirmLoading={creating}
        onCancel={() => setCreateModal(false)}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="position_id" label="Closed Position" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={creatablePositions.map((p) => ({
                value: p.id,
                label: `${p.code} #${p.id} closed ${p.closed_at?.slice(0, 10) ?? ""}`,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      <ReviewDetail review={detail} onClose={() => setDetail(null)} />
    </div>
  );
}

function ReviewDetail({ review, onClose }: { review: TradeReview | null; onClose: () => void }) {
  return (
    <Modal title={review ? `${review.code} Trade Review` : "Trade Review"} open={!!review} onCancel={onClose} footer={null} width={980}>
      {review && (
        <Space direction="vertical" size={14} style={{ width: "100%" }}>
          <Descriptions size="small" bordered column={3}>
            <Descriptions.Item label="Position">#{review.position_id}</Descriptions.Item>
            <Descriptions.Item label="Return">
              <Pct value={review.return_pct} />
            </Descriptions.Item>
            <Descriptions.Item label="Version">{review.review_version}</Descriptions.Item>
            <Descriptions.Item label="Entry">{review.entry_price.toFixed(4)}</Descriptions.Item>
            <Descriptions.Item label="Exit">{review.exit_price.toFixed(4)}</Descriptions.Item>
            <Descriptions.Item label="Closed">{review.closed_at.slice(0, 10)}</Descriptions.Item>
            <Descriptions.Item label="Outcome">
              <Tag color={OUTCOME_COLORS[review.outcome_quality] ?? "default"}>{review.outcome_quality}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Decision" span={2}>
              <Tag color={DECISION_COLORS[review.decision_quality] ?? "default"}>{review.decision_quality}</Tag>
            </Descriptions.Item>
          </Descriptions>

          <ReviewSection title="Thesis" value={review.thesis_review} />
          <ReviewSection title="Signal" value={review.signal_review} />
          <ReviewSection title="Decision" value={review.decision_review} />
          <ReviewSection title="Position Management" value={review.position_management_review} />
          <ReviewSection title="Outcome Attribution" value={review.outcome_attribution} />
          <ReviewSection title="State Transition" value={review.state_transition_review} />

          <Typography.Text strong>Learning Candidates</Typography.Text>
          <Table
            size="small"
            rowKey="id"
            dataSource={review.learning_candidates}
            pagination={false}
            columns={[
              { title: "Layer", dataIndex: "target_layer", width: 80 },
              {
                title: "Type",
                dataIndex: "candidate_type",
                width: 125,
                render: (v: string) => <Tag color={CANDIDATE_COLORS[v] ?? "default"}>{v}</Tag>,
              },
              { title: "Title", dataIndex: "title" },
              { title: "Rationale", dataIndex: "rationale" },
            ]}
          />
        </Space>
      )}
    </Modal>
  );
}

function ReviewSection({ title, value }: { title: string; value: Record<string, unknown> }) {
  return (
    <div>
      <Typography.Text strong>{title}</Typography.Text>
      <pre
        style={{
          margin: "6px 0 0",
          padding: 10,
          background: "#fafafa",
          border: "1px solid #f0f0f0",
          borderRadius: 6,
          maxHeight: 180,
          overflow: "auto",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}
