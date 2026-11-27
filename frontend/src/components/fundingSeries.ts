import type { P4Feature } from "../api/types";

/**
 * One quarterly funding reading, whichever of the two forms it took.
 *
 * A company that turns cash-flow positive stops producing a runway: item 8.3
 * goes positive, ASX has it answer item 8.7 "N/A", and P04 records a net
 * inflow instead. Reading only `cash_runway_quarters` therefore kept showing
 * MEK's June 2025 figure of 75.1 quarters as if it were current, seventeen
 * months after the company began funding itself. A stale number presented as
 * the present is worse than a blank.
 */

export const CRITICAL_QUARTERS = 2;
export const CAUTION_QUARTERS = 4;
/** A quarter plus the ASX's filing window. Past this, the reading is old. */
export const STALE_AFTER_DAYS = 150;

export type FundingPoint = {
  asOf: string;
  kind: "runway" | "self_funding";
  /** quarters of runway, or the net inflow in the filing's own units */
  value: number;
  burn: number | null;
  reported: number | null;
  variance: number | null;
  feature: P4Feature;
};

function numeric(feature: P4Feature): number | null {
  return typeof feature.value === "number" ? feature.value : null;
}

export function buildFundingSeries(features: P4Feature[]): FundingPoint[] {
  const burnByQuarter = new Map<string, number>();
  for (const feature of features) {
    if (feature.feature_name === "quarterly_burn" && feature.as_of_date) {
      const value = numeric(feature);
      if (value !== null) burnByQuarter.set(feature.as_of_date, value);
    }
  }

  const points: FundingPoint[] = [];
  for (const feature of features) {
    const value = numeric(feature);
    if (value === null || !feature.as_of_date) continue;
    const kind =
      feature.feature_name === "cash_runway_quarters"
        ? "runway"
        : feature.feature_name === "net_operating_inflow"
          ? "self_funding"
          : null;
    if (kind === null) continue;
    const evidence = feature.evidence || {};
    points.push({
      asOf: feature.as_of_date,
      kind,
      value,
      burn: burnByQuarter.get(feature.as_of_date) ?? null,
      reported: evidence.entity_reported_quarters ?? null,
      variance: evidence.variance_vs_entity_reported ?? null,
      feature,
    });
  }
  // oldest first: a funding history reads as a story, and the shape of the
  // decline is the finding rather than any single quarter
  return points.sort((a, b) => a.asOf.localeCompare(b.asOf));
}

export function latestPoint(series: FundingPoint[]): FundingPoint | null {
  return series.length ? series[series.length - 1] : null;
}

export function daysSince(asOf: string, today: Date = new Date()): number {
  const then = new Date(`${asOf}T00:00:00Z`).getTime();
  if (Number.isNaN(then)) return 0;
  return Math.floor((today.getTime() - then) / 86_400_000);
}

export function isStale(asOf: string, today?: Date): boolean {
  return daysSince(asOf, today) > STALE_AFTER_DAYS;
}

export function runwayTone(quarters: number): { token: string; label: string } {
  if (quarters < CRITICAL_QUARTERS) return { token: "var(--down)", label: "紧张" };
  if (quarters < CAUTION_QUARTERS) return { token: "var(--ochre)", label: "需关注" };
  return { token: "var(--up)", label: "宽裕" };
}
