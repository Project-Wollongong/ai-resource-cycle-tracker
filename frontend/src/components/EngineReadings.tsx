import { Alert, Space, Tag, Typography } from "antd";

import type { EngineReadings as Readings, EngineReading } from "../api/types";
import LensMatrix from "./LensMatrix";
import NoData from "./NoData";

/**
 * What each P05 engine read, and what P06 made of the set.
 *
 * The engines have been writing findings and narratives for a while and none
 * of it had a way onto the screen: the page showed a verdict with no way to
 * see the reasoning, which is not much better than no verdict. The engines
 * cannot see each other by design, so the interesting part is usually where
 * they disagree.
 */

const ENGINE_LABELS: Record<string, string> = {
  technical: "技术面",
  catalyst: "项目催化",
  fundamental: "基本面",
  sentiment: "市场情绪",
};

const STRENGTH_LABELS: Record<string, string> = {
  none: "无",
  weak: "弱",
  moderate: "中等",
  strong: "强",
  exceptional: "极强",
};

const DIRECTION: Record<string, { label: string; token: string }> = {
  positive: { label: "正向", token: "var(--up)" },
  negative: { label: "负向", token: "var(--down)" },
  neutral: { label: "中性", token: "var(--ink-faint)" },
};

/** A projection carries no lens and no narrative; saying so keeps it honest. */
function isProjection(engine: { logic_version: string | null }) {
  return (engine.logic_version || "").includes("adapter");
}

function describeConflict(entry: string): string {
  if (entry.startsWith("cross_engine_divergence:")) {
    const [up, down] = entry.split(":")[1].split("_vs_");
    return `跨引擎背离：${names(up)} 看多，${names(down)} 看空`;
  }
  if (entry.startsWith("engine_internal_divergence:")) {
    return `${names(entry.split(":")[1])} 引擎内部不一致（不同视角方向相反）`;
  }
  return entry;
}

function names(raw: string): string {
  return raw
    .split("+")
    .map((key) => ENGINE_LABELS[key] || key)
    .join(" + ");
}

function Reading({ reading }: { reading: EngineReading }) {
  const tone = DIRECTION[reading.direction] || DIRECTION.neutral;
  return (
    <div style={{ paddingTop: 8 }}>
      <Space size={8} align="baseline" wrap>
        <span className="num" style={{ fontWeight: 600, fontSize: 13 }}>
          {reading.lens}
        </span>
        <span style={{ color: tone.token, fontSize: 12 }}>
          {tone.label}
          {reading.magnitude ? ` · ${reading.magnitude}` : ""}
        </span>
      </Space>
      {reading.summary && (
        <div style={{ fontSize: 13.5, color: "var(--ink-soft)", marginTop: 2 }}>
          {reading.summary}
        </div>
      )}
      {reading.risks.map((risk) => (
        <div key={risk} className="micro" style={{ marginTop: 2 }}>
          留意：{risk}
        </div>
      ))}
    </div>
  );
}

export default function EngineReadings({ data }: { data: Readings }) {
  if (!data.as_of || !data.fusion) {
    return <NoData reason="还没有融合记录。先运行一次 pipeline 让各引擎读一遍。" />;
  }

  const { fusion } = data;
  const moved = fusion.cycle_score_strength && fusion.cycle_score_strength !== fusion.opportunity_strength;

  return (
    <Space direction="vertical" size={14} style={{ width: "100%" }}>
      <Space size={24} wrap align="start">
        <Space direction="vertical" size={2}>
          <span className="micro">机会强度</span>
          <Typography.Text strong style={{ fontSize: 18 }}>
            {STRENGTH_LABELS[fusion.opportunity_strength] || fusion.opportunity_strength}
          </Typography.Text>
        </Space>
        <Space direction="vertical" size={2}>
          <span className="micro">证据独立性</span>
          <span>{fusion.evidence_independence}</span>
        </Space>
        <Space direction="vertical" size={2}>
          <span className="micro">信号结构</span>
          <span>{fusion.signal_structure}</span>
        </Space>
        <Space direction="vertical" size={2}>
          <span className="micro">截至</span>
          <span className="num">{data.as_of}</span>
        </Space>
      </Space>

      {fusion.strength_basis && (
        <div className="micro">
          正向来源 {fusion.strength_basis.positive_sources} 个 · 负向来源{" "}
          {fusion.strength_basis.negative_sources} 个
          {fusion.strength_basis.cap_applied ? " · 已因反向证据封顶" : ""}
        </div>
      )}

      {moved && (
        <div className="micro">
          旧版 Cycle Score 查表会判为「{STRENGTH_LABELS[fusion.cycle_score_strength!] ??
            fusion.cycle_score_strength}
          」，当前结论由各引擎的读数推导。
        </div>
      )}

      {fusion.conflicts.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message="引擎之间存在分歧"
          description={
            <Space direction="vertical" size={2}>
              {fusion.conflicts.map((entry) => (
                <span key={entry}>{describeConflict(entry)}</span>
              ))}
              <span className="micro">
                分歧会压低机会强度——两个引擎指向相反时，诚实的读法是不确定，不是信心。
              </span>
            </Space>
          }
        />
      )}

      {fusion.narrative && (
        <details open style={{ border: "1px solid var(--line)", padding: "10px 14px",
                               background: "var(--sunk)" }}>
          <summary style={{ cursor: "pointer", fontWeight: 600 }}>综合研判</summary>
          <pre
            style={{
              whiteSpace: "pre-wrap",
              fontSize: 13,
              color: "var(--ink-soft)",
              margin: "10px 0 0",
              fontFamily: "inherit",
            }}
          >
            {fusion.narrative}
          </pre>
        </details>
      )}

      {data.engines.map((engine) => (
        <div
          key={engine.engine}
          style={{ border: "1px solid var(--line)", padding: "12px 14px", background: "var(--surface)" }}
        >
          <Space size={10} align="baseline" wrap>
            <Typography.Text strong>{ENGINE_LABELS[engine.engine] || engine.engine}</Typography.Text>
            {isProjection(engine) ? (
              <Tag color="default">投影（尚未实现为独立 Agent）</Tag>
            ) : (
              <span className="micro num">{engine.logic_version}</span>
            )}
          </Space>
          {engine.roster && <LensMatrix roster={engine.roster} />}
          {engine.readings.map((reading, index) => (
            <Reading key={`${reading.lens}-${index}`} reading={reading} />
          ))}
          {engine.narrative && (
            <details style={{ marginTop: 10 }}>
              <summary className="micro" style={{ cursor: "pointer" }}>
                查看完整七视角叙事
              </summary>
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  fontSize: 12.5,
                  color: "var(--ink-soft)",
                  marginTop: 8,
                  fontFamily: "inherit",
                }}
              >
                {engine.narrative}
              </pre>
            </details>
          )}
        </div>
      ))}
    </Space>
  );
}
