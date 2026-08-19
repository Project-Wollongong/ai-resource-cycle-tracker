import { Collapse, Descriptions, Empty, Space, Tag, Tooltip, Typography } from "antd";

import type { QualitativeContext } from "../api/types";

const QUALITY_COLORS: Record<QualitativeContext["interval_quality_label"], string> = {
  exceptional: "magenta",
  strong: "green",
  moderate: "blue",
  weak: "default",
  insufficient_history: "warning",
};

const MATERIALITY_COLORS: Record<QualitativeContext["materiality_label"], string> = {
  high: "red",
  medium: "orange",
  low: "default",
  insufficient_history: "warning",
};

const TREND_COLORS: Record<QualitativeContext["trend_vs_previous"], string> = {
  improving: "green",
  flat: "blue",
  deteriorating: "red",
  insufficient_history: "warning",
};

function percentile(value: number | null) {
  return value == null ? "Insufficient history" : `${value.toFixed(1)}th`;
}

function label(value: string) {
  return value.replaceAll("_", " ");
}

function compactNumber(value: number) {
  return Number.isInteger(value) ? value.toFixed(0) : value.toFixed(2);
}

function historyScope(context: QualitativeContext) {
  if (context.project_percentile != null) return "Project history";
  if (context.company_percentile != null) return "Company history";
  if (context.regional_percentile != null) return "Regional history";
  return "Insufficient history";
}

export default function QualitativeContextPanel({
  context,
  contexts,
}: {
  context?: QualitativeContext | null;
  contexts?: QualitativeContext[] | null;
}) {
  const items = contexts?.length ? contexts : context ? [context] : [];

  if (!items.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No qualitative context available" />;
  }

  if (items.length > 1) {
    return (
      <Collapse
        size="small"
        defaultActiveKey={["0"]}
        items={items.map((item) => ({
          key: String(item.intercept_index),
          label: (
            <Space wrap>
              <Typography.Text strong>
                Intercept {item.intercept_index + 1}: {compactNumber(item.width_m)}m at{" "}
                {compactNumber(item.grade)} {item.unit}
              </Typography.Text>
              <Tag color={QUALITY_COLORS[item.interval_quality_label]}>
                {label(item.interval_quality_label)}
              </Tag>
              <Tag color={MATERIALITY_COLORS[item.materiality_label]}>
                {label(item.materiality_label)}
              </Tag>
            </Space>
          ),
          children: <QualitativeContextDetail context={item} />,
        }))}
      />
    );
  }

  return <QualitativeContextDetail context={items[0]} />;
}

function QualitativeContextDetail({ context }: { context: QualitativeContext }) {
  return (
    <Space direction="vertical" size={8} style={{ width: "100%" }}>
      <Space wrap>
        <Tag color={context.extraction_quality === "complete" ? "green" : "warning"}>
          Extraction: {context.extraction_quality}
        </Tag>
        <Tag color={QUALITY_COLORS[context.interval_quality_label]}>
          Quality: {label(context.interval_quality_label)}
        </Tag>
        <Tag color={MATERIALITY_COLORS[context.materiality_label]}>
          Materiality: {label(context.materiality_label)}
        </Tag>
        <Tag color={TREND_COLORS[context.trend_vs_previous]}>
          Trend: {label(context.trend_vs_previous)}
        </Tag>
        <Tooltip title="Percentiles compare only stored intercepts with the same stock, commodity, and unit. Project history is used first when available.">
          <Tag>{historyScope(context)}</Tag>
        </Tooltip>
      </Space>
      <Typography.Text strong>{context.qualitative_assessment}</Typography.Text>
      <Descriptions size="small" column={{ xs: 1, sm: 2, md: 3 }} bordered>
        <Descriptions.Item label="Intercept">
          {context.width_m.toFixed(2)}m at {context.grade.toFixed(2)} {context.unit}
        </Descriptions.Item>
        <Descriptions.Item label="Normalized unit">
          {context.normalized_unit}
        </Descriptions.Item>
        <Descriptions.Item label="Commodity">
          {context.commodity}
        </Descriptions.Item>
        <Descriptions.Item label="Project">
          {context.project ?? "Unknown"}
        </Descriptions.Item>
        <Descriptions.Item label="Region">
          {context.region ?? "Unknown"}
        </Descriptions.Item>
        <Descriptions.Item label="Missing fields">
          {context.missing_fields.length ? context.missing_fields.join(", ") : "None"}
        </Descriptions.Item>
        <Descriptions.Item label="Grade-thickness">
          {context.grade_thickness.toFixed(2)}
        </Descriptions.Item>
        <Descriptions.Item label="Depth">
          <Tag>{label(context.depth_category)}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Interval quality">
          <Tag color={QUALITY_COLORS[context.interval_quality_label]}>
            {label(context.interval_quality_label)}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Company history percentile">
          {percentile(context.company_percentile)}
        </Descriptions.Item>
        <Descriptions.Item label="Project history percentile">
          {percentile(context.project_percentile)}
        </Descriptions.Item>
        <Descriptions.Item label="Regional history percentile">
          {percentile(context.regional_percentile)}
        </Descriptions.Item>
        <Descriptions.Item label="Trend">
          <Tag color={TREND_COLORS[context.trend_vs_previous]}>
            {label(context.trend_vs_previous)}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Trend basis">
          {label(context.trend_basis)}
        </Descriptions.Item>
        <Descriptions.Item label="Materiality">
          <Tag color={MATERIALITY_COLORS[context.materiality_label]}>
            {label(context.materiality_label)}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Company comparables">
          {context.company_history_count}
        </Descriptions.Item>
        <Descriptions.Item label="Project comparables">
          {context.project_history_count}
        </Descriptions.Item>
        <Descriptions.Item label="Regional comparables">
          {context.regional_history_count}
        </Descriptions.Item>
        <Descriptions.Item label="Comparison scope">
          Same stock, commodity, and unit
        </Descriptions.Item>
      </Descriptions>
      {context.comparison_warnings.length > 0 && (
        <Space size={4} wrap>
          {context.comparison_warnings.map((warning) => (
            <Tag key={warning} color="warning">
              {warning}
            </Tag>
          ))}
        </Space>
      )}
      <Typography.Text type="secondary">{context.reason}</Typography.Text>
    </Space>
  );
}
