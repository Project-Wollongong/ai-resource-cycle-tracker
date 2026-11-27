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
  exchange: string;
  trading_currency: string;
  listing_status: string;
  sector: string | null;
  business_type: string | null;
  pilot_universe_member: boolean;
  identity_history: StockIdentity[];
}

export interface StockIdentity {
  id: number;
  kind: "ticker" | "company_name" | "alias";
  value: string;
  exchange: string | null;
  valid_from: string | null;
  valid_to: string | null;
  is_current: boolean;
  source: string;
}

export interface StockProject {
  id: number;
  project_key: string;
  name: string;
  relationship_type: string;
  ownership_pct: number | null;
  operator_name: string | null;
  effective_from: string | null;
  effective_to: string | null;
  asset_units: {
    id: number;
    name: string;
    unit_type: string | null;
    parent_asset_unit_id: number | null;
  }[];
}

export interface ProjectRelationship {
  id: number;
  project_id: number;
  stock_id: number;
  relationship_type: string;
  ownership_pct: number | null;
  operator_name: string | null;
  effective_from: string | null;
  effective_to: string | null;
  source: string;
}

export interface ProjectDetail {
  id: number;
  project_key: string;
  name: string;
  commodity: string | null;
  region: string | null;
  jurisdiction: string | null;
  stage: string | null;
  active: boolean;
  asset_units: {
    id: number;
    name: string;
    unit_type: string | null;
    parent_asset_unit_id: number | null;
    country: string | null;
    region: string | null;
    commodity_override: string | null;
    ownership_override_pct: number | null;
    operator_override: string | null;
    active: boolean;
  }[];
  relationships: ProjectRelationship[];
}

export interface P01EntityProposal {
  id: number;
  stock_id: number;
  target_level: "project" | "asset_unit";
  proposed_project_name: string;
  proposed_asset_name: string | null;
  proposed_asset_type: string | null;
  proposed_commodity: string | null;
  proposed_ownership_pct: number | null;
  proposed_operator: string | null;
  source_type: string;
  source_ref: string;
  source_page: number | null;
  source_excerpt: string;
  status: "pending" | "approved" | "rejected" | "superseded";
  reviewer: string | null;
  reviewed_at: string | null;
  review_note: string;
  correction_json: string;
  project_id: number | null;
  asset_unit_id: number | null;
}

export interface P3UpdateProposalEvidence {
  mention_id: number;
  mapping_id: number;
  announcement_id: number;
  evidence_document_id: number;
  p3_event_id: number | null;
  p3_fact_id: number | null;
  source_section: string;
  source_page_start: number | null;
  source_page_end: number | null;
  mention_text_raw: string;
  source_excerpt: string;
  announcement: { id: number; ann_id: string; headline: string; ann_date: string; url: string } | null;
  evidence_document: { id: number; title: string; page_count: number | null; pdf_url: string } | null;
}

export interface P3UpdateProposal {
  id: number;
  proposal_type: string;
  status: "pending" | "approved" | "rejected" | "superseded";
  stock_id: number;
  stock: { id: number; code: string; name: string } | null;
  proposed_name: string;
  proposed_name_normalized: string | null;
  proposed_entity_type: string | null;
  proposed_project_name: string;
  proposed_asset_name: string | null;
  proposed_asset_type: string | null;
  proposed_commodity: string | null;
  proposed_parent_project_id: number | null;
  candidate_parent_project: { id: number; name: string; project_key: string } | null;
  proposed_payload: Record<string, unknown>;
  supporting_announcement_count: number;
  supporting_evidence_count: number;
  supporting_event_count: number;
  supporting_fact_count: number;
  confidence: number | null;
  created_by: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string;
  correction_history: Record<string, unknown>;
  resulting_entity: { type: string; id: number; name: string; project_key?: string; project_id?: number } | null;
  evidence: P3UpdateProposalEvidence[];
  created_at: string;
  updated_at: string | null;
}

export interface P01SourceSearchResult {
  source_type: string;
  source_id: string;
  title: string;
  url: string;
  stock_id: number | null;
  project_id: number | null;
  source_page: number | null;
  excerpt: string;
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
  evidence_document_id?: number | null;
  evidence_status?: string;
  download_status?: string;
  text_status?: string;
  local_pdf_available?: boolean;
  page_count?: number | null;
  file_size_bytes?: number | null;
  hash_prefix?: string | null;
  fetched_at?: string | null;
  evidence_error?: string | null;
  evidence_retryable?: boolean;
  document_category?: string;
  official_header_type?: string | null;
  official_subtype?: string | null;
  standard_form?: string | null;
  event_families?: string[];
  event_labels?: string[];
  revision_tags?: string[];
  classification_source?: string;
}

export interface P3Event {
  id: number;
  event_id: number;
  event_type: string;
  event_family: string;
  primary_family: string;
  secondary_families: string[];
  event_title: string;
  event_status: string;
  classification_status: string;
  classification_source: string;
  classification_confidence: number | null;
  revision_tags: string[];
  classification_reason: string;
  active_result: boolean;
  validity_status?: P3ValidityStatus;
  display_validity_status?: P3ValidityStatus;
  validity_reason?: string;
  has_pending_version_relation?: boolean;
  source_section: string;
  source_page_start: number | null;
  source_page_end: number | null;
  source_excerpt: string;
  confidence: number | null;
  parse_run_id: number;
  mapped_project_id?: number | null;
  mapped_asset_unit_id?: number | null;
  project_mapping_id?: number | null;
  asset_unit_mapping_id?: number | null;
  project_mapping_status?: "confirmed" | "review_needed" | "unknown";
  asset_unit_mapping_status?: "confirmed" | "review_needed" | "unknown";
  project: { id: number; name: string; project_key: string } | null;
  asset_unit: { id: number; name: string } | null;
  review_needed: boolean;
}

export interface P3ParseStatus {
  announcement_id: string;
  parse_status: string;
  event_count: number;
  fact_count: number;
  information_point_count: number;
  atomic_fact_count: number;
  target_min: number;
  target_max: number;
  count_status: "source_insufficient" | "target_range" | "high_density";
  source_insufficient: boolean;
  summary_point_count: number;
  standard_form_point_count: number;
  body_fallback_point_count: number;
  review_needed_count: number;
  summary_coverage_ratio: number;
  review_needed: boolean;
  fact_extraction?: {
    policy: string;
    summary_priority: string[];
    summary_bullet_count: number;
    summary_fact_count: number;
    fields_after_summary: string[];
    missing_after_summary: string[];
    standard_form_used: boolean;
    standard_form_pages: number[];
    standard_form_fact_count: number;
    missing_after_standard_form: string[];
    body_fallback_used: boolean;
    body_fallback_pages: number[];
    body_fallback_fact_count: number;
    remaining_missing_fields: string[];
    source_fact_counts: Record<string, number>;
  };
  information_point_grouping?: {
    schema: string;
    information_point_count: number;
    atomic_fact_count: number;
    grouped_fact_count: number;
    all_facts_preserved: boolean;
    point_types: Record<string, number>;
    display_reduction: number;
    no_padding: boolean;
    no_truncation: boolean;
  };
  latest_parse_run?: { parser_version: string; source_scope: string; error_message: string | null } | null;
}

export interface P3InformationPointFact {
  id: number;
  fact_type: string;
  field_name: string;
  value_raw: string;
  unit_raw: string | null;
  status: string;
  role: string;
  display_order: number;
  information_point_group_id: number | null;
  information_point_type: string | null;
  parent_fact_id: number | null;
}

export interface P3InformationPoint {
  id: number;
  event_id: number;
  announcement_id: number | null;
  evidence_document_id: number;
  parse_run_id: number;
  family: string;
  point_type: string;
  information_point_group_id: number;
  information_point_type: string;
  primary_fact_id: number | null;
  point_title: string;
  fact_count: number;
  status: string;
  source_section: string;
  source_page_start: number | null;
  source_page_end: number | null;
  source_excerpt: string;
  review_status: string;
  active_result: boolean;
  facts: P3InformationPointFact[];
  project: { id: number; name: string; project_key: string } | null;
  asset_unit: { id: number; name: string } | null;
  created_at: string;
}

export interface P3Fact {
  id: number;
  event_id: number | null;
  announcement_id: number | null;
  evidence_document_id: number;
  parse_run_id: number | null;
  mapped_project_id?: number | null;
  mapped_asset_unit_id?: number | null;
  project_mapping_id?: number | null;
  asset_unit_mapping_id?: number | null;
  project_mapping_status?: "confirmed" | "review_needed" | "unknown";
  asset_unit_mapping_status?: "confirmed" | "review_needed" | "unknown";
  family: string;
  fact_type: string;
  field_name: string;
  value_raw: string;
  value_numeric: number | null;
  value_text: string | null;
  unit_raw: string | null;
  unit_normalized: string | null;
  currency_raw: string | null;
  currency_normalized: string | null;
  quantity_type: string;
  period_start: string | null;
  period_end: string | null;
  as_of_date: string | null;
  effective_date: string | null;
  status: string;
  project_attribution_status: string;
  source_section: string;
  source_page: number | null;
  source_page_start: number | null;
  source_page_end: number | null;
  source_excerpt: string;
  extractor_name: string;
  extractor_version: string;
  extraction_confidence: number | null;
  review_status: string;
  validity_status?: P3ValidityStatus;
  display_validity_status?: P3ValidityStatus;
  validity_reason?: string;
  has_pending_version_relation?: boolean;
  active_result: boolean;
  information_point_group_id: number | null;
  information_point_type: string | null;
  parent_fact_id: number | null;
  display_order: number | null;
  event: { id: number; event_type: string; event_title: string; family: string } | null;
  stock: { id: number; code: string; name: string } | null;
  project: { id: number; name: string; project_key: string } | null;
  asset_unit: { id: number; name: string } | null;
  evidence_document: { id: number; title: string; source_url: string; page_count: number | null } | null;
  created_at: string;
  updated_at: string | null;
}

export type P3ValidityStatus = "current" | "historical" | "superseded" | "withdrawn" | "correction_pending_review" | "rejected";

export interface P3VersionObject {
  id: number;
  type: "event" | "fact" | "statement";
  validity_status: P3ValidityStatus;
  announcement_id?: number | null;
  project_id?: number | null;
  asset_unit_id?: number | null;
  family?: string;
  fact_type?: string;
  field_name?: string;
  event_type?: string;
  title?: string;
  value_raw?: string;
}

export interface P3VersionRelation {
  id: number;
  predecessor_type: "event" | "fact" | "statement";
  predecessor_id: number;
  successor_type: "event" | "fact" | "statement" | null;
  successor_id: number | null;
  relation_type: "corrects" | "restates" | "revises" | "replaces" | "supersedes" | "withdraws" | "retracts" | "related_to";
  status: "proposed" | "confirmed" | "rejected";
  source_announcement_id: number;
  source_evidence_document_id: number;
  source_page_start: number | null;
  source_page_end: number | null;
  source_excerpt: string;
  withdrawal_reason: string;
  detected_by: "parser" | "rule" | "model" | "manual";
  confidence: number | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string;
  predecessor: P3VersionObject | null;
  successor: P3VersionObject | null;
  stock: { id: number; code: string; name: string } | null;
  source_announcement: { id: number; ann_id: string; headline: string; ann_date: string; url: string } | null;
  evidence_document: { id: number; title: string; page_count: number | null; pdf_url: string } | null;
  change_log?: Array<{ id: number; action: string; before: Record<string, unknown>; after: Record<string, unknown>; reviewer: string; review_note: string; created_at: string }>;
}

export interface P3EntityMapping {
  id: number;
  entity_mention_id: number;
  announcement_id: number;
  evidence_document_id: number;
  parse_run_id: number;
  p3_event_id: number | null;
  p3_fact_id: number | null;
  mention_type: "stock" | "project" | "asset_unit" | "commodity";
  mention_text_raw: string;
  mention_text_normalized: string;
  source_section: string;
  source_page_start: number | null;
  source_page_end: number | null;
  source_page: number | null;
  source_excerpt: string;
  matched_entity_type: "stock" | "project" | "asset_unit" | "commodity";
  matched_entity_id: number | null;
  matched_entity: { id: number; type: string; name: string; code?: string; project_key?: string; project_id?: number } | null;
  candidate_entity?: { id: number; type: string; name: string; code?: string; project_key?: string; project_id?: number } | null;
  matched_alias: { id: number; value: string; kind: string; is_current: boolean } | null;
  match_method: "exact_match" | "alias_match" | "former_name_match" | "unresolved_candidate" | "fuzzy_match" | "model_suggestion" | "manual_confirmation" | "p01_proposal_approved";
  match_confidence: number;
  status: "confirmed" | "review_needed" | "ambiguous" | "rejected" | "superseded";
  stock_validation_result: string;
  parent_validation_result: string;
  matching_reason: string;
  review_needed: boolean;
  candidate_parent_project_id?: number | null;
  proposal_id?: number | null;
  candidate_payload?: Record<string, unknown>;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  review_note?: string;
  human_locked?: boolean;
  created_at: string;
  updated_at: string | null;
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
  pipeline_type?: string;
  provider?: string;
  started_at?: string | null;
  total_items?: number;
  succeeded_items?: number;
  skipped_items?: number;
  failed_items?: number;
  configuration_snapshot?: Record<string, unknown>;
  error_summary?: string | null;
}

export interface BackfillPreview {
  preview_token: string;
  filters: Record<string, unknown>;
  total_announcements: number;
  skipped_count: number;
  existing_pdf: number;
  missing_pdf: number;
  existing_raw_text: number;
  missing_raw_text: number;
  parsed: number;
  unparsed: number;
  estimated_downloads: number;
  estimated_reparse: number;
  possible_failure: number;
  by_stock: Record<string, number>;
  by_family: Record<string, number>;
  actions: string[];
  notice: string;
  read_only: boolean;
}

export interface BackfillRun {
  id: number;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  requested_by: string;
  parser_version: string;
  pipeline_version: string;
  total_announcements: number;
  succeeded_announcements: number;
  skipped_announcements: number;
  partial_announcements: number;
  failed_announcements: number;
  downloaded_files: number;
  extracted_texts: number;
  parsed_documents: number;
  created_events: number;
  created_facts: number;
  mapped_entities: number;
  review_needed_count: number;
  error_summary: string | null;
  retry_of_run_id: number | null;
}

export interface BackfillRunItem {
  id: number;
  backfill_run_id: number;
  announcement_id: number;
  stock_id: number;
  evidence_document_id: number | null;
  status: string;
  stage: string;
  parser_version: string;
  input_hash: string | null;
  created_event_count: number;
  created_fact_count: number;
  mapped_count: number;
  review_needed_count: number;
  error_message: string | null;
  started_at: string | null;
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

export interface HistoricalAnalysisReturn {
  horizon_days: number;
  entry_date: string | null;
  entry_price: number | null;
  exit_date: string | null;
  exit_price: number | null;
  return_pct: number | null;
  benchmark_return_pct: number | null;
  max_drawdown_pct: number | null;
  status: "pending" | "filled" | "unavailable";
}

export interface HistoricalAnalysisSnapshot {
  id: number;
  code: string;
  stock_name: string;
  as_of_date: string;
  as_of_cutoff: string;
  market_data_as_of: string | null;
  run_at: string;
  mode: "strict" | "approximate";
  status: string;
  boundary_status: string;
  data_warnings: string[];
  input_hash: string;
  input_summary: Record<string, unknown>;
  funding_score: number;
  announcement_score: number;
  resource_score: number;
  commodity_score: number;
  risk_score: number;
  sentiment_score: number;
  cycle_score: number;
  label: string;
  components: Record<string, unknown>;
  ai_reason: string;
  config_snapshot: Record<string, unknown>;
  returns: HistoricalAnalysisReturn[];
  created_at: string;
}

export interface PositionEvent {
  id: number;
  event_time: string;
  event_type: string;
  action: string;
  price: number | null;
  quantity_delta: number | null;
  thesis_status: string | null;
  catalyst_status: string | null;
  risk_status: string | null;
  reason: string;
  evidence: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface Position {
  id: number;
  code: string;
  stock_name: string;
  commodity: string;
  trade_decision_id: number | null;
  status: "open" | "closed";
  opened_at: string;
  closed_at: string | null;
  entry_price: number;
  quantity: number;
  current_price: number | null;
  market_value: number | null;
  unrealized_pnl_pct: number | null;
  thesis_status: string;
  catalyst_status: string;
  risk_status: string;
  suggested_action: string;
  price_stop: number | null;
  thesis_stop: string[];
  target_logic: Record<string, unknown>;
  original_thesis: Record<string, unknown>;
  thesis_delta: Record<string, unknown>;
  strategy_profile: string;
  metadata: Record<string, unknown>;
  events: PositionEvent[];
}

export interface StrategyLearningCandidate {
  id: number;
  trade_review_id: number;
  code: string;
  candidate_type: string;
  target_layer: string;
  title: string;
  rationale: string;
  evidence: Record<string, unknown>;
  status: string;
  requires_backtest: boolean;
  requires_human_approval: boolean;
  approved_at: string | null;
  applied_at: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface TradeReview {
  id: number;
  position_id: number;
  code: string;
  stock_name: string;
  opened_at: string;
  closed_at: string;
  entry_price: number;
  exit_price: number;
  return_pct: number;
  outcome_quality: string;
  decision_quality: string;
  thesis_review: Record<string, unknown>;
  signal_review: Record<string, unknown>;
  decision_review: Record<string, unknown>;
  position_management_review: Record<string, unknown>;
  outcome_attribution: Record<string, unknown>;
  state_transition_review: Record<string, unknown>;
  review_version: string;
  metadata: Record<string, unknown>;
  learning_candidates: StrategyLearningCandidate[];
  created_at: string;
}

export interface P4FeatureEvidence {
  formula?: string;
  inputs?: Record<string, number>;
  prior_close_date?: string;
  announcement_date?: string;
  announcement_headline?: string | null;
  implied?: number;
  implied_unit?: string;
  classification?: string;
  source_excerpt?: string;
  source_pages?: Record<string, number | null>;
  entity_reported_quarters?: number | null;
  variance_vs_entity_reported?: number | null;
}

export interface P4Feature {
  feature_group: string;
  feature_name: string;
  value: number | null;
  unit: string | null;
  as_of_date: string;
  formula_version: string;
  input_fact_ids: number[];
  evidence: P4FeatureEvidence;
  metadata: {
    appendix_5b_items?: string[];
    below_asx_disclosure_threshold?: boolean;
    deep_discount?: boolean;
    document_category?: string | null;
    consistent?: boolean;
    classification?: string;
    likely_column_misread?: boolean;
  // set when item 8.3 reported a net inflow, in which case there is no runway
  cash_direction?: string;
  runway_not_applicable?: boolean;
  };
}

export interface TodayReason {
  kind: "signal" | "announcement" | "funding" | "dilution" | "resource";
  level: "critical" | "caution" | "watch" | "unconfirmed";
  title: string;
  detail: string;
  /** When the state was measured — a standing risk is not today's news. */
  as_of: string | null;
  evidence: Record<string, unknown>;
}

export interface TodayItem {
  code: string;
  name: string;
  commodity: string;
  last_close: number | null;
  last_bar_date: string | null;
  day_change_pct: number | null;
  cycle_score: number | null;
  label: string | null;
  top_level: TodayReason["level"];
  reasons: TodayReason[];
}

export interface TodayBoard {
  as_of: string | null;
  scored: number;
  universe: number;
  new_announcements: number;
  items: TodayItem[];
  quiet: string[];
}


export interface EngineReading {
  lens: string | null;
  direction: string;
  magnitude: string | null;
  confidence: string | null;
  persistence: string | null;
  summary: string | null;
  drivers: string[];
  risks: string[];
  dependency_group: string | null;
}

export interface EngineBlock {
  engine: string;
  logic_version: string | null;
  narrative: string | null;
  readings: EngineReading[];
}

export interface EngineReadings {
  as_of: string | null;
  fusion: {
    opportunity_strength: string;
    confidence: string | null;
    signal_structure: string | null;
    evidence_independence: string | null;
    conflicts: string[];
    blocking_conditions: string[];
    strength_basis: {
      positive_sources: number;
      negative_sources: number;
      strongest_positive_magnitude: number;
      engines_positive: string[];
      engines_negative: string[];
      cap_applied?: string | null;
      reason?: string;
    } | null;
    cycle_score_strength: string | null;
  } | null;
  engines: EngineBlock[];
}


export interface AttentionView {
  state_level: string;
  state_label: string;
  previous_state_level: string | null;
  transition: string;
  reason: string;
  manual_override: boolean;
  manual_lock: boolean;
  alert_priority: string | null;
  effective_at: string | null;
  trade_decision: {
    decision: string;
    action: string;
    conviction: string | null;
    reason: string | null;
  } | null;
}
