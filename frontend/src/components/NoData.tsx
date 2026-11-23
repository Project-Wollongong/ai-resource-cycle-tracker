import { Typography } from "antd";

/**
 * "We have nothing to show" — stated as what is missing, never as a blank.
 *
 * An empty panel and a grey dash both read as reassurance: the eye takes "no
 * warning" for "nothing wrong". That is wrong here often enough to matter —
 * most stocks have no quarterly on file, so most funding panels are empty, and
 * none of that says anything about their funding. Every absence therefore names
 * the document or fact it is waiting on, and is drawn with a dashed border so
 * it never resembles a cleared check.
 */
export default function NoData({
  title = "尚无法计算",
  reason,
  action,
  inline = false,
}: {
  /** What cannot be shown. */
  title?: string;
  /** Which document or fact is missing, in the reader's words. */
  reason?: string;
  /** Optional next step, e.g. a link to import a document. */
  action?: React.ReactNode;
  /** Compact form for a table cell. */
  inline?: boolean;
}) {
  if (inline) {
    return (
      <span
        className="mono"
        style={{
          fontSize: 11,
          letterSpacing: "0.04em",
          color: "var(--ink-faint)",
          border: "1px dashed var(--c-absent)",
          padding: "1px 6px",
          whiteSpace: "nowrap",
        }}
        title={reason}
      >
        {title}
      </span>
    );
  }

  return (
    <div
      style={{
        border: "1px dashed var(--line-strong)",
        background: "var(--sunk)",
        padding: "18px 16px",
      }}
    >
      <div style={{ fontSize: 14, fontWeight: 580, marginBottom: 5 }}>{title}</div>
      {reason && (
        <Typography.Text style={{ fontSize: 13, color: "var(--ink-soft)" }}>{reason}</Typography.Text>
      )}
      {action && <div style={{ marginTop: 11 }}>{action}</div>}
      <div
        className="mono"
        style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 12, lineHeight: 1.7 }}
      >
        此处无告警不代表状况良好，仅表示系统没有可用于判断的数据。
      </div>
    </div>
  );
}
