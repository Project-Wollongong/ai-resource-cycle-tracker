import { Alert, Descriptions, Space, Statistic, Tooltip, Typography } from "antd";

import type { P4Feature } from "../api/types";
import NoData from "./NoData";
import StatusPill from "./StatusPill";

// Under two quarters the ASX makes the entity answer Appendix 5B item 8.8
// ("how will you fund operations?"), which is also the level at which a
// dilutive raise stops being a risk and becomes a near-certainty.
const CRITICAL_QUARTERS = 2;
const CAUTION_QUARTERS = 4;

function runwayTone(quarters: number): { color: string; label: string } {
  if (quarters < CRITICAL_QUARTERS) return { color: "#cf1322", label: "紧张" };
  if (quarters < CAUTION_QUARTERS) return { color: "#d46b08", label: "需关注" };
  return { color: "#389e0d", label: "宽裕" };
}

function find(features: P4Feature[], name: string) {
  return features.find((item) => item.feature_name === name);
}

// one reconciliation row per table row, so the names carry a classification and
// row suffix; match on the prefix and show the worst offender first
function resourceChecks(features: P4Feature[]) {
  return features
    .filter((item) => item.feature_name.startsWith("contained_metal_reconciliation_pct"))
    .sort((a, b) => Math.abs(b.value ?? 0) - Math.abs(a.value ?? 0));
}

function PlacementDiscount({ feature }: { feature: P4Feature }) {
  const pct = feature.value ?? 0;
  const deep = feature.metadata?.deep_discount;
  const evidence = feature.evidence || {};
  return (
    <Descriptions size="small" column={1} bordered title="最近一次配售">
      <Descriptions.Item label="折价">
        <Space size={8}>
          <Typography.Text strong style={{ color: deep ? "#cf1322" : "#d46b08" }}>
            {pct.toFixed(2)}%
          </Typography.Text>
          {deep && (
            <StatusPill level="caution" hint="折让 20% 或以上，融资代价偏高">
              深度折价
            </StatusPill>
          )}
        </Space>
      </Descriptions.Item>
      <Descriptions.Item label="计算式">
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          配售价 {evidence.inputs?.issue_price} / 公告前收盘{" "}
          {evidence.inputs?.prior_close}（{evidence.prior_close_date}） - 1
        </Typography.Text>
      </Descriptions.Item>
      <Descriptions.Item label="公告">
        <Typography.Text style={{ fontSize: 12 }}>
          {evidence.announcement_date} · {evidence.announcement_headline || "-"}
        </Typography.Text>
      </Descriptions.Item>
    </Descriptions>
  );
}

function ResourceCheck({ feature, total, inconsistent }: { feature: P4Feature; total: number; inconsistent: number }) {
  const consistent = feature.metadata?.consistent;
  const misread = feature.metadata?.likely_column_misread;
  const evidence = feature.evidence || {};
  if (consistent) {
    return (
      <Alert
        type="success"
        showIcon
        message={`资源量自洽（${total} 行全部通过）`}
        description={`最大偏差 ${feature.value?.toFixed(1)}%：${evidence.classification} 行按吨位 × 品位推算 ${evidence.implied} ${evidence.implied_unit}，公告披露 ${evidence.inputs?.reported} ${evidence.inputs?.reported_unit}。`}
      />
    );
  }
  return (
    <Alert
      type="error"
      showIcon
      message={`${misread ? "资源量数据不可信 — 疑似表格列错位" : "资源量与公告披露不符"}（${inconsistent}/${total} 行）`}
      description={
        <Space direction="vertical" size={4}>
          <span>
            {evidence.classification} 行按吨位 × 品位推算为 {evidence.implied}{" "}
            {evidence.implied_unit}，公告披露 {evidence.inputs?.reported}{" "}
            {evidence.inputs?.reported_unit}，相差 {feature.value?.toFixed(0)}%。
          </span>
          {misread && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              多元素矿体的 JORC 表格里每种元素各占一列，解析可能取错了列（例如把
              Ta2O5 的 ppm 当成了黄金盎司）。此处的品位与金属量请勿用于判断。
            </Typography.Text>
          )}
          {evidence.source_excerpt && (
            <Typography.Text code style={{ fontSize: 11 }}>
              {evidence.source_excerpt.slice(0, 120)}
            </Typography.Text>
          )}
        </Space>
      }
    />
  );
}

export default function FundingRunwayPanel({ features }: { features: P4Feature[] }) {
  const runway = find(features, "cash_runway_quarters");
  const burn = find(features, "quarterly_burn");
  const discount = find(features, "placement_discount_pct");
  const checks = resourceChecks(features);
  const resourceCheck = checks[0];
  const inconsistent = checks.filter((item) => item.metadata?.consistent === false).length;

  if (!runway || runway.value === null) {
    // the dilution and resource groups are derived independently, so a stock
    // can have a placement or a reconciliation on record with no quarterly yet
    const missing = (
      <NoData reason="需要一份 Appendix 5B 季度现金流报告。ASX 接口每支股票仅返回最近 5 份文件，该公司当前 5 份中不含季报。" />
    );
    if (discount || resourceCheck) {
      return (
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          {resourceCheck && (
            <ResourceCheck feature={resourceCheck} total={checks.length} inconsistent={inconsistent} />
          )}
          {discount && <PlacementDiscount feature={discount} />}
          {missing}
        </Space>
      );
    }
    return missing;
  }

  const quarters = runway.value;
  const tone = runwayTone(quarters);
  const months = Math.round(quarters * 3);
  const evidence = runway.evidence || {};
  const reported = evidence.entity_reported_quarters;
  const variance = evidence.variance_vs_entity_reported;
  const page = evidence.source_pages?.total_relevant_outgoings;
  // A gap between our arithmetic and the entity's own item 8.7 means either the
  // parser misread the form or the company's own figure is off — either way it
  // should be visible rather than silently averaged away.
  const disagrees = variance !== null && variance !== undefined && Math.abs(variance) >= 0.1;

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Space size={32} wrap align="start">
        <Statistic
          title="现金跑道"
          value={quarters}
          precision={2}
          suffix="季度"
          valueStyle={{ color: tone.color }}
        />
        <Statistic title="约合" value={months} suffix="个月" />
        {burn?.value != null && (
          <Statistic
            title="季度烧钱"
            value={burn.value}
            precision={0}
            suffix={burn.unit || ""}
          />
        )}
        <Space direction="vertical" size={4}>
          <span className="micro">状态</span>
          <StatusPill
            level={quarters < CRITICAL_QUARTERS ? "critical" : quarters < CAUTION_QUARTERS ? "caution" : "watch"}
            hint={`${quarters.toFixed(2)} 个季度 · 低于 2 个季度时 ASX 要求公司在第 8.8 项说明融资安排`}
          >
            {tone.label}
          </StatusPill>
        </Space>
      </Space>

      {runway.metadata?.below_asx_disclosure_threshold && (
        <Alert
          type="error"
          showIcon
          message="跑道不足 2 个季度"
          description="ASX 要求公司在 Appendix 5B 第 8.8 项说明如何继续融资。此水平下稀释性融资几乎必然发生。"
        />
      )}

      {disagrees && (
        <Alert
          type="warning"
          showIcon
          message={`与公司自报数字不一致（相差 ${variance?.toFixed(2)} 季度）`}
          description={`我们按第 8.6 / 8.3 项算得 ${quarters.toFixed(2)}，公司在第 8.7 项自报 ${reported?.toFixed(2)}。可能是解析有误或公司口径不同，建议核对原文。`}
        />
      )}

      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="计算式">
          <Typography.Text code style={{ fontSize: 12 }}>
            {evidence.formula || "-"}
          </Typography.Text>
          {evidence.inputs && (
            <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
              = {evidence.inputs.total_available_funding?.toLocaleString()} /{" "}
              {Math.abs(evidence.inputs.total_relevant_outgoings ?? 0).toLocaleString()}
            </Typography.Text>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="数据截至">{runway.as_of_date}</Descriptions.Item>
        <Descriptions.Item label="公司自报（8.7）">
          {reported != null ? (
            <Space size={6}>
              <span>{reported.toFixed(2)} 季度</span>
              {!disagrees && (
                <span className="micro" style={{ letterSpacing: "0.08em" }}>
                  与本系统推算一致
                </span>
              )}
            </Space>
          ) : (
            <Typography.Text type="secondary">未披露</Typography.Text>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="来源">
          <Space size={6} wrap>
            <Tooltip title="Appendix 5B 中用于计算的条目">
              <span>
                第 {runway.metadata?.appendix_5b_items?.join(" / ") || "?"} 项
                {page != null && ` · 第 ${page} 页`}
              </span>
            </Tooltip>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              公式版本 {runway.formula_version}
            </Typography.Text>
          </Space>
        </Descriptions.Item>
      </Descriptions>

      {discount && <PlacementDiscount feature={discount} />}
    </Space>
  );
}
