import { Alert, Space, Tag, Timeline, Typography } from "antd";

import type { CatalystMap as MapData, CatalystMapEntry } from "../api/types";
import NoData from "./NoData";

/**
 * Where the project stands, and what it is waiting for.
 *
 * P05 calls this the Catalyst Agent's persistent internal state rather than an
 * output, which is why it is appended per day instead of overwritten: the
 * change between two days is the finding. The panel leads with the current
 * entry and keeps the earlier ones underneath for the same reason.
 */

const STAGES: { key: string; label: string }[] = [
  { key: "exploration", label: "勘探" },
  { key: "resource_definition", label: "资源量" },
  { key: "study", label: "研究" },
  { key: "permitting", label: "审批" },
  { key: "development_decision", label: "投资决定" },
  { key: "construction", label: "建设" },
  { key: "production", label: "投产" },
];

const IMPORTANCE: Record<string, string> = { high: "高", medium: "中", low: "低" };

/** The ladder with the current rung marked. Stages are an ordering of
 *  evidence, not a track the project must run along — miners work several in
 *  parallel — so the reached ones are marked rather than drawn as a path. */
function StageLadder({ stage }: { stage: string | null }) {
  const index = STAGES.findIndex((item) => item.key === stage);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
      {STAGES.map((item, position) => {
        const reached = index >= 0 && position <= index;
        const current = position === index;
        return (
          <span
            key={item.key}
            style={{
              fontSize: 12,
              padding: "3px 9px",
              border: `1px solid ${current ? "var(--azurite)" : "var(--line)"}`,
              background: current ? "var(--azurite-weak)" : "transparent",
              color: current
                ? "var(--azurite)"
                : reached
                  ? "var(--ink-soft)"
                  : "var(--ink-faint)",
              fontWeight: current ? 600 : 400,
              opacity: reached ? 1 : 0.55,
            }}
          >
            {item.label}
          </span>
        );
      })}
    </div>
  );
}

function Entry({ entry }: { entry: CatalystMapEntry }) {
  const advanced =
    entry.previous_stage && entry.current_stage && entry.previous_stage !== entry.current_stage;

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <StageLadder stage={entry.current_stage} />

      {advanced && (
        <Alert
          type="success"
          showIcon
          message={`阶段推进：${entry.previous_stage} → ${entry.current_stage}`}
          description="阶段推进不等于价值兑现，后续仍可能倒退或停滞。"
        />
      )}

      <Space size={24} wrap align="start">
        <Space direction="vertical" size={2}>
          <span className="micro">下一关键事件</span>
          <Typography.Text strong>{entry.next_expected_event || "未知"}</Typography.Text>
        </Space>
        <Space direction="vertical" size={2}>
          <span className="micro">重要性</span>
          <span>{IMPORTANCE[entry.importance || ""] || entry.importance || "未评"}</span>
        </Space>
        <Space direction="vertical" size={2}>
          <span className="micro">预期时间窗</span>
          <span>{entry.expected_window || "公司未给出"}</span>
        </Space>
        <Space direction="vertical" size={2}>
          <span className="micro">完成概率</span>
          {/* The pilot builds no milestone probability model, and the PRD
              forbids inventing one; saying "not assessed" is the answer. */}
          <span style={{ color: "var(--ink-faint)" }}>
            {entry.probability === "not_assessed" ? "未评估" : entry.probability}
          </span>
        </Space>
      </Space>

      {entry.bottlenecks.length > 0 && (
        <div>
          <div className="micro" style={{ marginBottom: 4 }}>未解除的瓶颈</div>
          <Space direction="vertical" size={2}>
            {entry.bottlenecks.map((item) => (
              <span key={item} style={{ fontSize: 13, color: "var(--ink-soft)" }}>
                · {item}
              </span>
            ))}
          </Space>
          <div className="micro" style={{ marginTop: 4 }}>
            未见证据不等于不存在——也可能只是公告未被采集
          </div>
        </div>
      )}

      {entry.dependencies.length > 0 && (
        <div>
          <div className="micro" style={{ marginBottom: 4 }}>
            披露后长期未见结论（{entry.dependencies.length} 项）
          </div>
          <Space size={6} wrap>
            {entry.dependencies.slice(0, 6).map((item, index) => (
              <Tag key={`${item.event}-${index}`} style={{ marginInlineEnd: 0 }}>
                {item.event} · {item.days_open} 天
              </Tag>
            ))}
            {entry.dependencies.length > 6 && (
              <span className="micro">另有 {entry.dependencies.length - 6} 项</span>
            )}
          </Space>
        </div>
      )}
    </Space>
  );
}

export default function CatalystMap({ data }: { data: MapData }) {
  if (!data.current) {
    return (
      <NoData reason="还没有项目进度记录。Catalyst Agent 需要 P03 事件，先运行一次 pipeline。" />
    );
  }

  return (
    <Space direction="vertical" size={14} style={{ width: "100%" }}>
      <Space size={10} align="baseline" wrap>
        <span className="micro">截至</span>
        <span className="num">{data.current.as_of_date}</span>
        <span className="micro">{data.current.change_since_previous}</span>
      </Space>

      <Entry entry={data.current} />

      {data.history.length > 0 && (
        <details>
          <summary className="micro" style={{ cursor: "pointer" }}>
            查看历史（{data.history.length} 条）——两天之间的差异本身就是发现
          </summary>
          <Timeline
            style={{ marginTop: 12 }}
            items={data.history.map((entry) => ({
              children: (
                <Space direction="vertical" size={2}>
                  <span className="num">{entry.as_of_date}</span>
                  <span style={{ fontSize: 13 }}>
                    {entry.current_stage || "阶段未知"} · {entry.change_since_previous}
                  </span>
                </Space>
              ),
            }))}
          />
        </details>
      )}
    </Space>
  );
}
