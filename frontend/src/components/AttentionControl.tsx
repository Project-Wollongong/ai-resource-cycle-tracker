import { Alert, Button, Input, Modal, Select, Space, Tag, Typography } from "antd";
import { useState } from "react";

import { api } from "../api/client";
import type { AttentionView } from "../api/types";

/**
 * The step P07 reserves for a person.
 *
 * The engine recommends and never promotes to Decision Ready on its own. The
 * API for taking that step exists; without a control it could only be reached
 * with curl, which meant P08's decision, P09's position and P10's review were
 * unreachable in normal use.
 *
 * The level set here is held against the engine until released, so the control
 * says plainly what the engine would otherwise be reading.
 */

const LEVEL_LABELS: Record<string, string> = {
  L0: "L0 全域",
  L1: "L1 观察",
  L2: "L2 重点观察",
  L3: "L3 调查",
  L4: "L4 可决策",
  L5: "L5 持仓",
};

const DECISION_LABELS: Record<string, string> = {
  act: "可执行",
  wait: "等待",
  pass: "不操作",
};

export default function AttentionControl({
  code,
  state,
  onChange,
}: {
  code: string;
  state: AttentionView | null;
  onChange: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [level, setLevel] = useState("L4");
  const [actor, setActor] = useState(
    () => globalThis.localStorage?.getItem("attentionActor") ?? "",
  );
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!state) {
    return <Typography.Text type="secondary">还没有注意力状态。</Typography.Text>;
  }

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setOpen(false);
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const submit = () =>
    run(async () => {
      globalThis.localStorage?.setItem("attentionActor", actor.trim());
      await api.put(`/attention/${code}`, { level, actor: actor.trim(), note: note.trim() });
    });

  const release = () =>
    run(() => api.del(`/attention/${code}?actor=${encodeURIComponent(actor.trim() || "unknown")}`));

  return (
    <Space direction="vertical" size={10} style={{ width: "100%" }}>
      <Space size={10} wrap align="center">
        <Typography.Text strong style={{ fontSize: 16 }}>
          {LEVEL_LABELS[state.state_level] || state.state_level}
        </Typography.Text>
        {state.manual_override && <Tag color="gold">人工持有</Tag>}
        {state.trade_decision && (
          <Tag>
            {DECISION_LABELS[state.trade_decision.decision] || state.trade_decision.decision}
            {state.trade_decision.action !== "none" ? ` · ${state.trade_decision.action}` : ""}
          </Tag>
        )}
        <Button size="small" onClick={() => setOpen(true)}>
          人工设定
        </Button>
        {state.manual_override && (
          <Button size="small" loading={busy} onClick={release}>
            交回引擎
          </Button>
        )}
      </Space>

      <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
        {state.reason}
      </Typography.Text>

      {state.manual_override && (
        <Alert
          type="info"
          showIcon
          message="该状态由人工持有，引擎不会改动它"
          description="交回引擎后它会按迟滞逐级回落，而不是一步归位——一个弱势日不足以抹掉一次晋升。"
        />
      )}

      {error && !open && <Alert type="error" showIcon message={error} />}

      <Modal
        open={open}
        title={`人工设定 ${code} 的注意力状态`}
        okText="设定"
        cancelText="取消"
        confirmLoading={busy}
        okButtonProps={{ disabled: !actor.trim() }}
        onOk={submit}
        onCancel={() => setOpen(false)}
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Alert
            type="warning"
            showIcon
            message="L4 会让下游产生可执行的交易决策"
            description="引擎按设计从不自动晋升到 L4——这一步由你负责。设定会立刻重算交易决策。"
          />
          <div>
            <div className="micro" style={{ marginBottom: 4 }}>层级</div>
            <Select
              value={level}
              onChange={setLevel}
              style={{ width: "100%" }}
              options={Object.entries(LEVEL_LABELS).map(([value, label]) => ({ value, label }))}
            />
          </div>
          <div>
            <div className="micro" style={{ marginBottom: 4 }}>设定人（必填，会记入历史）</div>
            <Input value={actor} onChange={(e) => setActor(e.target.value)} placeholder="你的名字" />
          </div>
          <div>
            <div className="micro" style={{ marginBottom: 4 }}>理由</div>
            <Input.TextArea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              placeholder="为什么现在把它提到这一级"
            />
          </div>
          {error && <Alert type="error" showIcon message={error} />}
        </Space>
      </Modal>
    </Space>
  );
}
