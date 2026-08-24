export interface ScoreBrief {
  date: string;
  funding_score: number;
  announcement_score: number;
  resource_score: number;
  commodity_score: number;
  risk_score: number;
  sentiment_score: number;
  cycle_score: number;
  label: string;
  components?: Record<string, unknown> | null;
}

export interface StockWithScore {
  id: number;
  code: string;
  name: string;
  commodity: string;
  stage: string;
  active: boolean;
  notes: string;
  resource_score_override: number | null;
  risk_score_override: number | null;
  latest_score: ScoreBrief | null;
  last_close: number | null;
  last_bar_date: string | null;
  day_change_pct: number | null;
  today_signals: string[];
}

export interface PriceBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface QualitativeContext {
  intercept_index: number;
  width_m: number;
  grade: number;
  unit: string;
  normalized_unit: string;
  commodity: string;
  project: string | null;
  region: string | null;
  extraction_quality: "complete" | "partial";
  missing_fields: string[];
  comparison_warnings: string[];
  grade_thickness: number;
  depth_category: "shallow" | "medium" | "deep" | "unknown";
  interval_quality_label: "exceptional" | "strong" | "moderate" | "weak" | "insufficient_history";
  company_percentile: number | null;
  project_percentile: number | null;
  regional_percentile: number | null;
  trend_vs_previous: "improving" | "flat" | "deteriorating" | "insufficient_history";
  trend_basis: "project" | "company" | "insufficient_history";
  materiality_label: "high" | "medium" | "low" | "insufficient_history";
  company_history_count: number;
  project_history_count: number;
  regional_history_count: number;
  reason: string;
  qualitative_assessment: string;
}

export interface Announcement {
  id: number;
  code: string;
  ann_id: string;
  headline: string;
  ann_date: string;
  url: string;
  price_sensitive: boolean;
  ann_type: string;
  type_score: number;
  matched_keywords: string[];
  ai_summary: string | null;
  ai_metrics:
    | (Record<string, unknown> & {
        qualitative_context?: QualitativeContext;
        qualitative_contexts?: QualitativeContext[];
      })
    | null;
}

export interface SignalReturn {
  horizon_days: number;
  entry_price: number | null;
  return_pct: number | null;
  benchmark_return_pct: number | null;
  status: "pending" | "filled" | "unavailable";
}

export interface Signal {
  id: number;
  code: string;
  stock_name: string;
  date: string;
  signal_type: string;
  source: "live" | "replay";
  label: string | null;
  reason: string;
  evidence: Record<string, unknown>;
  price_at_signal: number;
  cycle_score_at_signal: number | null;
  returns: SignalReturn[];
}

export interface BacktestCell {
  horizon_days: number;
  n: number;
  win_rate?: number | null;
  avg?: number | null;
  median?: number | null;
  max?: number | null;
  min?: number | null;
  avg_excess?: number | null;
  low_sample: boolean;
}

export interface BacktestGroup {
  group: string;
  cells: BacktestCell[];
  unavailable: number;
}

export interface BacktestSummary {
  group_by: string;
  source: string;
  total_signals: number;
  groups: BacktestGroup[];
}

export interface ReportContent {
  report_date: string;
  daily_review?: {
    top_priority: DailyReviewItem[];
    new_story: DailyReviewItem[];
    market_confirmation: DailyReviewItem[];
    rising_fast: DailyReviewItem[];
    risk_alert: DailyReviewItem[];
  };
  top: {
    code: string;
    name: string;
    commodity: string;
    cycle_score: number;
    label: string;
    day_change_pct: number | null;
  }[];
  signals: { code: string; type: string; label: string | null; reason: string; price: number }[];
  announcements: {
    code: string;
    type: string;
    headline: string;
    price_sensitive: boolean;
    url: string;
    quality?: string | null;
    materiality?: string | null;
    assessment?: string | null;
    grade_thickness?: number | null;
  }[];
  movers: { code: string; day_change_pct: number }[];
  source_degraded: string[];
  disclaimer: string;
}

export interface DailyReviewItem {
  code: string;
  name: string;
  commodity: string;
  stage: string;
  cycle_score: number;
  label: string;
  score_change: number | null;
  day_change_pct: number | null;
  announcement_score: number;
  funding_score: number;
  commodity_score: number;
  risk_score: number;
  risk_severity: number;
  reasons: string[];
  watch_next: string[];
  headline?: string;
  announcement_type?: string;
}

export interface DailyReport {
  report_date: string;
  content: ReportContent;
  pushed: boolean;
  pushed_at: string | null;
  push_error: string | null;
}

export interface PipelineRun {
  id: number;
  run_at: string;
  trigger: string;
  status: string;
  stats: Record<string, unknown>;
  finished_at: string | null;
}

export interface AppConfig {
  weights: Record<string, number>;
  label_thresholds: Record<string, number>;
  signal_thresholds: Record<string, number>;
  commodity_instruments: Record<string, string>;
  benchmark_instrument: string;
  [key: string]: unknown;
}

export interface ConfigHistory {
  id: number;
  key: string;
  old_value: unknown;
  new_value: unknown;
  changed_by: string;
  source: string;
  changed_at: string;
}

export interface WeightCalibrationDiagnostic {
  subscore: string;
  correlation: number | null;
  top_bottom_spread: number | null;
  raw_signal: number;
}

export interface WeightCalibration {
  horizon_days: number;
  target: string;
  sample_size: number;
  low_sample: boolean;
  current_weights: Record<string, number>;
  recommended_weights: Record<string, number>;
  diagnostics: WeightCalibrationDiagnostic[];
  method: string;
}
