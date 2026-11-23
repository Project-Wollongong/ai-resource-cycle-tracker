import { Tooltip } from "antd";

/**
 * A stock's Cycle Score band.
 *
 * `null` means two different things depending on where the label came from, and
 * the component used to render both as the word "replay": on a signal row a
 * missing label genuinely means the signal was replayed from history and
 * carries no score, but on the ranking page it means the stock has not been
 * scored at all. Showing "replay" there was simply wrong, so callers now say
 * which they mean via `missing`.
 *
 * The bands keep their English values because that is what the API stores and
 * what the column filters match on; only the display is Chinese.
 */
const BANDS: Record<string, { text: string; color: string }> = {
  "High Priority": { text: "高优先", color: "var(--gossan)" },
  "Watch Closely": { text: "需关注", color: "var(--ochre)" },
  Monitor: { text: "监控", color: "var(--ink-soft)" },
  Ignore: { text: "忽略", color: "var(--ink-faint)" },
};

export default function LabelTag({
  label,
  missing = "unscored",
}: {
  label: string | null | undefined;
  /** What a missing label means here: no score yet, or a replayed signal. */
  missing?: "unscored" | "replay";
}) {
  if (!label) {
    const unscored = missing === "unscored";
    return (
      <Tooltip
        title={
          unscored
            ? "尚未评分。并非评分为零，而是当日没有产生评分快照。"
            : "历史回放信号，不含评分与标签。"
        }
      >
        <span
          className="mono"
          style={{
            fontSize: 10,
            letterSpacing: "0.07em",
            padding: "2px 7px",
            color: "var(--ink-faint)",
            border: "1px dashed var(--c-absent)",
            cursor: "help",
            whiteSpace: "nowrap",
          }}
        >
          {unscored ? "未评分" : "回放"}
        </span>
      </Tooltip>
    );
  }

  const band = BANDS[label] ?? { text: label, color: "var(--ink-soft)" };
  return (
    <span
      className="mono"
      style={{
        fontSize: 10,
        letterSpacing: "0.07em",
        padding: "2px 7px",
        color: band.color,
        border: `1px solid ${band.color}`,
        whiteSpace: "nowrap",
      }}
    >
      {band.text}
    </span>
  );
}
