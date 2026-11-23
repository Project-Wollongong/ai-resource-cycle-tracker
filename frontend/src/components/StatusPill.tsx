import { Tooltip } from "antd";

/**
 * Severity of a state, encoded in colour *and* shape.
 *
 * Risk deliberately avoids red and green: those belong to price direction, and
 * a red pill that might mean either "fell" or "dangerous" means neither. The
 * two risk levels are ochre and gossan — the oxidised tones — and intensity is
 * reinforced by the border, so the distinction survives greyscale and the
 * red-green colour deficiency that affects roughly one man in twelve.
 *
 * `unconfirmed` is the important one: it marks a reading the evidence does not
 * support — a rule the backtest found non-predictive, or a fact still awaiting
 * review. A dashed border says "this is not a settled judgement" without having
 * to be read as either good or bad.
 */
export type StatusLevel = "critical" | "caution" | "watch" | "unconfirmed" | "none";

const STYLE: Record<StatusLevel, { color: string; dashed: boolean }> = {
  critical: { color: "var(--gossan)", dashed: false },
  caution: { color: "var(--ochre)", dashed: false },
  watch: { color: "var(--azurite)", dashed: false },
  unconfirmed: { color: "var(--ochre)", dashed: true },
  none: { color: "var(--ink-faint)", dashed: true },
};

export default function StatusPill({
  level,
  children,
  hint,
}: {
  level: StatusLevel;
  children: React.ReactNode;
  /** Why this level was assigned — shown on hover. */
  hint?: string;
}) {
  const { color, dashed } = STYLE[level];
  const pill = (
    <span
      className="mono"
      style={{
        fontSize: 10,
        letterSpacing: "0.08em",
        padding: "2px 7px",
        color,
        border: `1px ${dashed ? "dashed" : "solid"} ${color}`,
        whiteSpace: "nowrap",
        cursor: hint ? "help" : undefined,
      }}
    >
      {children}
    </span>
  );
  return hint ? <Tooltip title={hint}>{pill}</Tooltip> : pill;
}

/** 3px stripe down the left of a card, matching a StatusPill level. */
export function StatusStripe({ level }: { level: StatusLevel }) {
  const background = level === "none" ? "var(--c-absent)" : STYLE[level].color;
  return <div aria-hidden style={{ width: 3, background, flex: "none" }} />;
}
