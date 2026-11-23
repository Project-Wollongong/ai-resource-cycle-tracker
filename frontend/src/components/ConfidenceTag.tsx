import { Tooltip } from "antd";

/**
 * How much a number can be relied on, borrowed from JORC's own vocabulary.
 *
 * Confidence spends no hue at all — the four hues are already committed to
 * interaction, price direction and risk. It is carried by how present the ink
 * is instead: a measured figure is full-strength, an inferred one recedes, and
 * an absent one is a dashed outline with no number in it. That keeps the
 * distinction the system most needs to make — what we read versus what we
 * worked out versus what we never had — legible without another colour.
 */
export type ConfidenceLevel = "measured" | "indicated" | "inferred" | "absent";

const LABEL: Record<ConfidenceLevel, string> = {
  measured: "Measured",
  indicated: "Indicated",
  inferred: "Inferred",
  absent: "Absent",
};

const MEANING: Record<ConfidenceLevel, string> = {
  measured: "公告原文直出，且已通过校验",
  indicated: "由已披露数值推算，可溯源到页码",
  inferred: "间接推断或样本不足，建议人工复核",
  absent: "无对应事实。并非「检查通过」。",
};

/** --c-absent sits at 1.65:1 on white: it outlines, it never carries text. */
const INK: Record<ConfidenceLevel, string> = {
  measured: "var(--c-measured)",
  indicated: "var(--c-indicated)",
  inferred: "var(--c-inferred)",
  absent: "var(--ink-faint)",
};

export default function ConfidenceTag({
  level,
  note,
}: {
  level: ConfidenceLevel;
  /** Extra context appended to the tooltip, e.g. the source page. */
  note?: string;
}) {
  const absent = level === "absent";
  return (
    <Tooltip title={note ? `${MEANING[level]} · ${note}` : MEANING[level]}>
      <span
        className="mono"
        style={{
          fontSize: 10,
          letterSpacing: "0.07em",
          padding: "2px 7px",
          cursor: "help",
          color: absent ? INK.absent : "var(--surface)",
          background: absent ? "transparent" : INK[level],
          border: absent ? "1px dashed var(--c-absent)" : "1px solid transparent",
        }}
      >
        {LABEL[level]}
      </span>
    </Tooltip>
  );
}
