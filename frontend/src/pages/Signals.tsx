import { Alert, Input, Select, Space, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { Signal } from "../api/types";
import SignalTable from "../components/SignalTable";

const TYPES = ["REL_VOL_SPIKE", "BREAKOUT_60D", "BREAKOUT_252D", "KEY_ANNOUNCEMENT", "SCORE_CROSS_UP"];
const LABELS = ["High Priority", "Watch Closely", "Monitor", "Ignore"];

export default function Signals() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [type, setType] = useState<string | undefined>();
  const [label, setLabel] = useState<string | undefined>();
  const [source, setSource] = useState<string | undefined>();
  const [code, setCode] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ limit: "500" });
    if (type) params.set("signal_type", type);
    if (label) params.set("label", label);
    if (source) params.set("source", source);
    if (code.trim()) params.set("code", code.trim().toUpperCase());
    try {
      setSignals(await api.get<Signal[]>(`/signals?${params.toString()}`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [type, label, source, code]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div>
      <Typography.Title level={4}>信号记录</Typography.Title>
      <Typography.Paragraph type="secondary">
        每次信号都会永久留痕，并追踪 +5/+20/+60/+120 交易日收益。入场价为信号后首个交易日收盘价，避免前视偏差。
      </Typography.Paragraph>
      <Space style={{ marginBottom: 12 }} wrap>
        <Select
          allowClear
          placeholder="信号类型"
          style={{ width: 180 }}
          value={type}
          onChange={setType}
          options={TYPES.map((t) => ({ value: t, label: t }))}
        />
        <Select
          allowClear
          placeholder="标签"
          style={{ width: 150 }}
          value={label}
          onChange={setLabel}
          options={LABELS.map((l) => ({ value: l, label: l }))}
        />
        <Select
          allowClear
          placeholder="来源"
          style={{ width: 120 }}
          value={source}
          onChange={setSource}
          options={[{ value: "live", label: "live" }, { value: "replay", label: "replay" }]}
        />
        <Input
          placeholder="代码"
          style={{ width: 100 }}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onPressEnter={load}
          allowClear
        />
      </Space>
      {error && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      <SignalTable signals={signals} loading={loading} />
    </div>
  );
}
