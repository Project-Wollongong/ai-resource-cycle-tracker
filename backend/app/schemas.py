from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Message(BaseModel):
    detail: str


class BackfillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_codes: list[str] = Field(default_factory=list)
    announcement_ids: list[str] = Field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    event_families: list[str] = Field(default_factory=list)
    download_missing_pdf: bool = False
    extract_raw_text: bool = True
    parse_document: bool = True
    classify_events: bool = True
    extract_facts: bool = True
    map_entities: bool = True
    check_version_relations: bool = True
    only_failed: bool = False
    only_unparsed: bool = False
    parser_version: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        return self


class BackfillRunRequest(BackfillRequest):
    preview_token: str = Field(min_length=64, max_length=64)
    requested_by: str = Field(default="admin", min_length=1, max_length=120)


# ---------- stocks ----------

ListingStatus = Literal["Listed", "Suspended", "Delisted", "Unknown"]
IdentityKind = Literal["ticker", "company_name", "alias"]


class StockIdentityInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    kind: IdentityKind
    value: str = Field(min_length=1, max_length=160)
    valid_from: date | None = None
    valid_to: date | None = None
    exchange: str | None = Field(default=None, min_length=1, max_length=20)
    source: str = Field(default="manual", min_length=1, max_length=120)

    @model_validator(mode="after")
    def valid_interval(self):
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValueError("valid_to must be after valid_from")
        return self


class StockIdentityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stock_id: int
    kind: IdentityKind
    value: str
    exchange: str | None
    valid_from: date | None
    valid_to: date | None
    is_current: bool
    source: str


class StockProfileFields(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    exchange: str = Field(default="ASX", min_length=1, max_length=20)
    trading_currency: str = Field(default="AUD", pattern=r"^[A-Za-z]{3}$")
    listing_status: ListingStatus = "Unknown"
    sector: str | None = Field(default=None, min_length=1, max_length=120)
    business_type: str | None = Field(default=None, min_length=1, max_length=120)
    pilot_universe_member: bool = True

    @field_validator("exchange", "trading_currency")
    @classmethod
    def uppercase(cls, value):
        return value.upper()


class StockCreate(StockProfileFields):
    code: str
    name: str = Field(min_length=1, max_length=160)
    commodity: str
    stage: str = "explorer"
    notes: str = ""
    identity_effective_from: date | None = None


class StockUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str | None = Field(default=None, min_length=1, max_length=10)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    exchange: str | None = Field(default=None, min_length=1, max_length=20)
    trading_currency: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")
    listing_status: ListingStatus | None = None
    sector: str | None = Field(default=None, min_length=1, max_length=120)
    business_type: str | None = Field(default=None, min_length=1, max_length=120)
    pilot_universe_member: bool | None = None
    identity_effective_from: date | None = None
    commodity: str | None = None
    stage: str | None = None
    notes: str | None = None
    active: bool | None = None
    resource_score_override: float | None = None
    risk_score_override: float | None = None
    # explicit sentinels: a PATCH with value None is ambiguous, so clearing is opt-in
    clear_resource_override: bool = False
    clear_risk_override: bool = False


class ScoreBrief(BaseModel):
    date: date
    funding_score: float
    announcement_score: float
    resource_score: float
    commodity_score: float
    risk_score: float
    sentiment_score: float
    cycle_score: float
    label: str
    components: dict[str, Any] | None = None


class StockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    exchange: str
    trading_currency: str
    listing_status: ListingStatus
    sector: str | None
    business_type: str | None
    pilot_universe_member: bool
    identity_history: list[StockIdentityOut] = Field(default_factory=list)
    commodity: str
    stage: str
    active: bool
    notes: str
    resource_score_override: float | None
    risk_score_override: float | None


class StockWithScore(StockOut):
    latest_score: ScoreBrief | None = None
    last_close: float | None = None
    last_bar_date: date | None = None
    day_change_pct: float | None = None
    today_signals: list[str] = []


class EntityIdentitySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    value: str
    normalized_value: str
    is_current: bool
    source: str


class CommodityRelationshipSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    commodity: str
    relationship_type: str
    is_economic: bool


class ProposalSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str


class AssetUnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    unit_type: str | None
    parent_asset_unit_id: int | None
    country: str | None
    region: str | None
    commodity_override: str | None
    ownership_override_pct: float | None
    operator_override: str | None
    active: bool
    identities: list[EntityIdentitySummary] = Field(default_factory=list)
    commodities: list[CommodityRelationshipSummary] = Field(default_factory=list)


class StockProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_key: str
    name: str
    relationship_type: str
    ownership_pct: float | None
    operator_name: str | None = None
    effective_from: date | None
    effective_to: date | None
    asset_units: list[AssetUnitOut] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    project_key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    commodity: str | None = None
    region: str | None = None
    jurisdiction: str | None = None
    stage: str | None = None
    stock_ids: list[int] = Field(default_factory=list)


class ProjectRelationshipCreate(BaseModel):
    stock_id: int
    relationship_type: str = "owner"
    ownership_pct: float | None = None
    operator_name: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    source: str = "manual"
    source_page: int | None = Field(default=None, ge=1)
    source_excerpt: str = ""


class ProjectRelationshipOut(ProjectRelationshipCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_key: str
    name: str
    commodity: str | None
    region: str | None
    jurisdiction: str | None
    stage: str | None
    active: bool
    asset_units: list[AssetUnitOut] = Field(default_factory=list)
    relationships: list[ProjectRelationshipOut] = Field(default_factory=list)
    identities: list[EntityIdentitySummary] = Field(default_factory=list)
    commodities: list[CommodityRelationshipSummary] = Field(default_factory=list)
    proposals: list[ProposalSummary] = Field(default_factory=list)


class AssetUnitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    unit_type: str | None = None
    parent_asset_unit_id: int | None = None
    country: str | None = None
    region: str | None = None
    commodity_override: str | None = None
    ownership_override_pct: float | None = None
    operator_override: str | None = None


class AssetUnitProposalCreate(BaseModel):
    proposed_name: str = Field(min_length=1, max_length=160)
    proposed_type: str | None = None
    rationale: str = ""
    evidence_document_id: int | None = None
    source_page: int | None = Field(default=None, ge=1)
    source_excerpt: str = ""


class AssetUnitProposalOut(AssetUnitProposalCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    status: Literal["pending", "approved", "rejected"]
    asset_unit_id: int | None


class P01EntityProposalCreate(BaseModel):
    stock_id: int
    target_level: Literal["project", "asset_unit"] = "project"
    proposed_project_name: str = Field(min_length=1, max_length=160)
    proposed_asset_name: str | None = None
    proposed_asset_type: str | None = None
    proposed_commodity: str | None = None
    proposed_ownership_pct: float | None = Field(default=None, ge=0, le=100)
    proposed_operator: str | None = None
    source_type: str = "manual"
    source_ref: str = ""
    source_page: int | None = Field(default=None, ge=1)
    source_excerpt: str = ""
    proposal_type: str = "new_project_candidate"
    proposed_name: str | None = None
    proposed_entity_type: str | None = None
    proposed_parent_project_id: int | None = None
    proposed_payload_json: str = "{}"
    confidence: float | None = Field(default=None, ge=0, le=1)
    created_by: Literal["parser", "rule", "model", "manual"] = "manual"


class P01EntityProposalReview(BaseModel):
    action: Literal["approve", "reject", "correct", "merge", "split", "rename", "adjust_project_asset_level", "adjust_commodity", "adjust_ownership", "adjust_operator"]
    reviewer: str = Field(min_length=1, max_length=120)
    review_note: str = ""
    correction: dict[str, Any] = Field(default_factory=dict)


class P01ProposalDecision(BaseModel):
    reviewer: str = Field(min_length=1, max_length=120)
    review_note: str = Field(min_length=1)


class P01ProposalCorrection(P01ProposalDecision):
    correction: dict[str, Any] = Field(default_factory=dict)


class P01EntityProposalOut(P01EntityProposalCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: Literal["pending", "approved", "rejected", "superseded"]
    reviewer: str | None
    reviewed_at: datetime | None
    review_note: str
    correction_json: str
    project_id: int | None
    asset_unit_id: int | None
    proposed_name_normalized: str | None = None
    source_p3_event_ids_json: str = "[]"
    source_p3_fact_ids_json: str = "[]"
    source_evidence_document_ids_json: str = "[]"
    source_announcement_ids_json: str = "[]"
    supporting_mentions_json: str = "[]"
    supporting_announcement_count: int = 0
    supporting_evidence_count: int = 0
    supporting_event_count: int = 0
    supporting_fact_count: int = 0
    source_pages_json: str = "[]"
    source_excerpts_json: str = "[]"
    reviewed_by: str | None = None
    resulting_entity_type: str | None = None
    resulting_entity_id: int | None = None
    created_at: datetime | None
    updated_at: datetime | None = None


class P01SourceSearchResult(BaseModel):
    source_type: str
    source_id: str
    title: str
    url: str
    stock_id: int | None = None
    project_id: int | None = None
    source_page: int | None = None
    excerpt: str = ""


class ProjectIdentityInput(BaseModel):
    kind: Literal["name", "alias"] = "alias"
    value: str = Field(min_length=1, max_length=160)
    valid_from: date | None = None
    valid_to: date | None = None
    is_current: bool = False
    source: str = "manual"

    @model_validator(mode="after")
    def validate_dates(self):
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValueError("valid_to must be after valid_from")
        if self.is_current and self.kind == "alias":
            raise ValueError("alias cannot be current")
        return self


class ProjectIdentityOut(ProjectIdentityInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    normalized_value: str


class AssetUnitIdentityInput(ProjectIdentityInput):
    pass


class AssetUnitIdentityOut(AssetUnitIdentityInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    asset_unit_id: int
    normalized_value: str


class CommodityRelationshipInput(BaseModel):
    commodity: str = Field(min_length=1, max_length=80)
    relationship_type: str = Field(default="economic_exposure", min_length=1, max_length=40)
    is_economic: bool = True
    effective_from: date | None = None
    effective_to: date | None = None
    source: str = Field(default="manual", min_length=1, max_length=120)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_from and self.effective_to and self.effective_from >= self.effective_to:
            raise ValueError("effective_to must be after effective_from")
        return self


class CommodityRelationshipOut(CommodityRelationshipInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int | None
    asset_unit_id: int | None


# ---------- market data ----------

class PriceBarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class AnnouncementOut(BaseModel):
    id: int
    code: str
    ann_id: str
    headline: str
    ann_date: datetime
    url: str
    price_sensitive: bool
    ann_type: str
    type_score: float
    matched_keywords: list[str]
    ai_summary: str | None = None
    ai_metrics: dict[str, Any] | None = None
    evidence_document_id: int | None = None
    evidence_status: str = "metadata_only"
    download_status: str = "pending"
    text_status: str = "pending"
    local_pdf_available: bool = False
    page_count: int | None = None
    file_size_bytes: int | None = None
    hash_prefix: str | None = None
    fetched_at: datetime | None = None
    evidence_error: str | None = None
    evidence_retryable: bool = False
    document_category: str = "Other / Needs Review"
    official_header_type: str | None = None
    official_subtype: str | None = None
    standard_form: str | None = None
    event_families: list[str] = []
    event_labels: list[str] = []
    revision_tags: list[str] = []
    classification_source: str = "title_routing"


class EvidenceDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    announcement_id: int | None
    source_id: str
    title: str
    source_url: str
    local_original_path: str | None
    local_raw_text_path: str | None
    file_hash_sha256: str | None
    file_size_bytes: int | None
    content_type: str | None
    page_count: int | None
    downloaded_at: datetime | None
    text_extracted_at: datetime | None
    evidence_status: str
    download_status: str
    text_status: str
    error_message: str | None
    retry_count: int
    last_retry_at: datetime | None
    duplicate_of_id: int | None
    historical_baseline: bool = False
    review_status: str = "pending_review"
    imported_at: datetime | None = None


class P3ParseRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    evidence_document_id: int
    announcement_id: int | None
    parser_name: str
    parser_version: str
    input_hash: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    source_scope: str
    pages_examined_json: str
    error_message: str | None
    output_summary_json: str
    created_at: datetime


class P3EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_id: int
    announcement_id: int | None
    evidence_document_id: int
    parse_run_id: int
    stock_id: int | None
    project_id: int | None
    asset_unit_id: int | None
    mapped_project_id: int | None = None
    mapped_asset_unit_id: int | None = None
    project_mapping_id: int | None = None
    asset_unit_mapping_id: int | None = None
    project_mapping_status: str = "unknown"
    asset_unit_mapping_status: str = "unknown"
    event_type: str
    event_family: str = "OTHER"
    primary_family: str = "OTHER"
    secondary_families: list[str] = Field(default_factory=list)
    event_title: str
    event_status: str
    classification_status: str = "auto_classified"
    classification_source: str = "summary_confirmation"
    classification_confidence: float | None = None
    revision_tags: list[str] = Field(default_factory=list)
    classification_reason: str = ""
    active_result: bool = True
    validity_status: str = "current"
    display_validity_status: str = "current"
    validity_reason: str = ""
    has_pending_version_relation: bool = False
    source_section: str
    source_page_start: int | None
    source_page_end: int | None
    source_page: int | None
    source_excerpt: str
    confidence: float | None
    project: dict[str, Any] | None = None
    asset_unit: dict[str, Any] | None = None
    review_needed: bool = False
    occurred_on: date | None
    reported_on: datetime | None
    created_at: datetime


class P3ClassificationReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    p3_event_id: int
    action: str
    before_json: str
    after_json: str
    reviewer: str
    review_note: str
    created_at: datetime


class P3EventReviewAction(BaseModel):
    reviewer: str
    review_note: str = ""


class P3EventCorrection(P3EventReviewAction):
    primary_family: str | None = None
    secondary_families: list[str] | None = None
    event_type: str | None = None
    event_title: str | None = None
    event_status: str | None = None
    project_id: int | None = None
    asset_unit_id: int | None = None


class P3FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_id: int | None
    announcement_id: int | None
    evidence_document_id: int
    parse_run_id: int | None
    stock_id: int | None
    project_id: int | None
    asset_unit_id: int | None
    mapped_project_id: int | None = None
    mapped_asset_unit_id: int | None = None
    project_mapping_id: int | None = None
    asset_unit_mapping_id: int | None = None
    project_mapping_status: str = "unknown"
    asset_unit_mapping_status: str = "unknown"
    family: str
    fact_type: str
    field_name: str
    value_raw: str
    value_numeric: float | None
    value_text: str | None
    unit_raw: str | None
    unit_normalized: str | None
    currency_raw: str | None
    currency_normalized: str | None
    quantity_type: str
    period_start: date | None
    period_end: date | None
    as_of_date: date | None
    effective_date: date | None
    status: str
    project_attribution_status: str
    source_section: str
    source_page_start: int | None
    source_page_end: int | None
    source_page: int | None
    source_excerpt: str
    extractor_name: str
    extractor_version: str
    extraction_confidence: float | None
    review_status: str
    validity_status: str = "current"
    display_validity_status: str = "current"
    validity_reason: str = ""
    has_pending_version_relation: bool = False
    active_result: bool
    superseded_by_id: int | None
    information_point_group_id: int | None
    information_point_type: str | None
    parent_fact_id: int | None
    display_order: int | None
    event: dict[str, Any] | None = None
    stock: dict[str, Any] | None = None
    project: dict[str, Any] | None = None
    asset_unit: dict[str, Any] | None = None
    evidence_document: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime | None


class P3FactReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    p3_fact_id: int
    action: str
    before_json: str
    after_json: str
    reviewer: str
    review_note: str
    created_at: datetime


class P3FactReviewAction(BaseModel):
    reviewer: str
    review_note: str = ""


class P3FactCorrection(P3FactReviewAction):
    field_name: str | None = None
    value_raw: str | None = None
    value_numeric: float | None = None
    value_text: str | None = None
    unit_raw: str | None = None
    unit_normalized: str | None = None
    currency_raw: str | None = None
    currency_normalized: str | None = None
    quantity_type: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    as_of_date: date | None = None
    effective_date: date | None = None
    status: str | None = None
    project_id: int | None = None
    asset_unit_id: int | None = None
    project_attribution_status: str | None = None


class P3VersionRelationReviewAction(BaseModel):
    reviewer: str = Field(min_length=1, max_length=120)
    review_note: str = Field(min_length=1)


class P3EntityMappingReviewAction(BaseModel):
    reviewer: str = Field(min_length=1, max_length=120)
    review_note: str = Field(min_length=1)


class P3EntityMappingCorrection(P3EntityMappingReviewAction):
    matched_entity_type: Literal["stock", "project", "asset_unit", "commodity"]
    matched_entity_id: int = Field(gt=0)


class P3EntityModelSuggestionCreate(BaseModel):
    entity_mention_id: int = Field(gt=0)
    matched_entity_type: Literal["stock", "project", "asset_unit", "commodity"]
    matched_entity_id: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    model_name: str = Field(min_length=1, max_length=120)
    model_version: str = Field(min_length=1, max_length=120)
    reasoning: str = Field(min_length=1)


class P3VersionRelationCorrection(P3VersionRelationReviewAction):
    predecessor_type: Literal["event", "fact", "statement"] | None = None
    predecessor_id: int | None = None
    successor_type: Literal["event", "fact", "statement"] | None = None
    successor_id: int | None = None
    relation_type: Literal["corrects", "restates", "revises", "replaces", "supersedes", "withdraws", "retracts", "related_to"] | None = None
    source_page_start: int | None = None
    source_page_end: int | None = None
    source_excerpt: str | None = None
    withdrawal_reason: str | None = None


class P3VersionRelationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    predecessor_type: str
    predecessor_id: int
    successor_type: str | None
    successor_id: int | None
    relation_type: str
    status: str
    source_announcement_id: int
    source_evidence_document_id: int
    source_page_start: int | None
    source_page_end: int | None
    source_excerpt: str
    withdrawal_reason: str
    detected_by: str
    confidence: float | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str
    created_at: datetime
    updated_at: datetime | None


class P3InformationPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_id: int
    announcement_id: int | None
    evidence_document_id: int
    parse_run_id: int
    stock_id: int | None
    project_id: int | None
    asset_unit_id: int | None
    family: str
    point_type: str
    information_point_group_id: int
    information_point_type: str
    primary_fact_id: int | None
    point_title: str
    fact_count: int
    status: str
    source_section: str
    source_page_start: int | None
    source_page_end: int | None
    source_excerpt: str
    review_status: str
    active_result: bool
    superseded_by_id: int | None
    facts: list[dict[str, Any]] = Field(default_factory=list)
    project: dict[str, Any] | None = None
    asset_unit: dict[str, Any] | None = None
    created_at: datetime


# ---------- signals & backtest ----------

class SignalReturnOut(BaseModel):
    horizon_days: int
    entry_price: float | None
    return_pct: float | None
    benchmark_return_pct: float | None
    status: str


class SignalOut(BaseModel):
    id: int
    code: str
    stock_name: str
    date: date
    signal_type: str
    source: str
    label: str | None
    reason: str
    evidence: dict[str, Any]
    price_at_signal: float
    cycle_score_at_signal: float | None
    returns: list[SignalReturnOut]


class BacktestCell(BaseModel):
    horizon_days: int
    n: int
    win_rate: float | None = None
    avg: float | None = None
    median: float | None = None
    max: float | None = None
    min: float | None = None
    avg_excess: float | None = None
    low_sample: bool = True


class BacktestGroup(BaseModel):
    group: str
    cells: list[BacktestCell]
    unavailable: int = 0


class BacktestSummary(BaseModel):
    group_by: str
    source: str
    total_signals: int
    # distinct stock-days behind those signals; a day that fired several
    # signals is one observation, not several
    total_signal_days: int
    groups: list[BacktestGroup]


class WeightCalibrationDiagnostic(BaseModel):
    subscore: str
    correlation: float | None
    top_bottom_spread: float | None
    raw_signal: float


class WeightCalibrationOut(BaseModel):
    horizon_days: int
    target: str
    sample_size: int
    low_sample: bool
    current_weights: dict[str, float]
    recommended_weights: dict[str, float]
    diagnostics: list[WeightCalibrationDiagnostic]
    method: str


# ---------- historical analysis ----------

class HistoricalAnalysisRunIn(BaseModel):
    code: str
    as_of_date: date
    mode: str = "approximate"


class HistoricalAnalysisReturnOut(BaseModel):
    horizon_days: int
    entry_date: date | None
    entry_price: float | None
    exit_date: date | None
    exit_price: float | None
    return_pct: float | None
    benchmark_return_pct: float | None
    max_drawdown_pct: float | None
    status: str


class HistoricalAnalysisSnapshotOut(BaseModel):
    id: int
    code: str
    stock_name: str
    as_of_date: date
    as_of_cutoff: datetime
    market_data_as_of: date | None
    run_at: datetime
    mode: str
    status: str
    boundary_status: str
    data_warnings: list[str]
    input_hash: str
    input_summary: dict[str, Any]
    funding_score: float
    announcement_score: float
    resource_score: float
    commodity_score: float
    risk_score: float
    sentiment_score: float
    cycle_score: float
    label: str
    components: dict[str, Any]
    ai_reason: str
    config_snapshot: dict[str, Any]
    returns: list[HistoricalAnalysisReturnOut] = []
    created_at: datetime


# ---------- positions ----------

class PositionOpenIn(BaseModel):
    code: str
    entry_price: float
    quantity: float
    opened_at: datetime | None = None
    trade_decision_id: int | None = None
    strategy_profile: str = "balanced"
    original_thesis: dict[str, Any] | None = None


class PositionCloseIn(BaseModel):
    exit_price: float
    closed_at: datetime | None = None
    reason: str = "User closed the position."


class PositionEventOut(BaseModel):
    id: int
    event_time: datetime
    event_type: str
    action: str
    price: float | None
    quantity_delta: float | None
    thesis_status: str | None
    catalyst_status: str | None
    risk_status: str | None
    reason: str
    evidence: dict[str, Any]
    metadata: dict[str, Any]


class PositionOut(BaseModel):
    id: int
    code: str
    stock_name: str
    commodity: str
    trade_decision_id: int | None
    status: str
    opened_at: datetime
    closed_at: datetime | None
    entry_price: float
    quantity: float
    current_price: float | None
    market_value: float | None
    unrealized_pnl_pct: float | None
    thesis_status: str
    catalyst_status: str
    risk_status: str
    suggested_action: str
    price_stop: float | None
    thesis_stop: list[str]
    target_logic: dict[str, Any]
    original_thesis: dict[str, Any]
    thesis_delta: dict[str, Any]
    strategy_profile: str
    metadata: dict[str, Any]
    events: list[PositionEventOut] = []


# ---------- trade reviews ----------

class StrategyLearningCandidateOut(BaseModel):
    id: int
    trade_review_id: int
    code: str
    candidate_type: str
    target_layer: str
    title: str
    rationale: str
    evidence: dict[str, Any]
    status: str
    requires_backtest: bool
    requires_human_approval: bool
    approved_at: datetime | None
    applied_at: datetime | None
    metadata: dict[str, Any]
    created_at: datetime


class TradeReviewOut(BaseModel):
    id: int
    position_id: int
    code: str
    stock_name: str
    opened_at: datetime
    closed_at: datetime
    entry_price: float
    exit_price: float
    return_pct: float
    outcome_quality: str
    decision_quality: str
    thesis_review: dict[str, Any]
    signal_review: dict[str, Any]
    decision_review: dict[str, Any]
    position_management_review: dict[str, Any]
    outcome_attribution: dict[str, Any]
    state_transition_review: dict[str, Any]
    review_version: str
    metadata: dict[str, Any]
    learning_candidates: list[StrategyLearningCandidateOut] = []
    created_at: datetime


# ---------- reports & admin ----------

class DailyReportOut(BaseModel):
    report_date: date
    content: dict[str, Any]
    pushed: bool
    pushed_at: datetime | None
    push_error: str | None


class PipelineRunOut(BaseModel):
    id: int
    run_at: datetime
    trigger: str
    status: str
    stats: dict[str, Any]
    finished_at: datetime | None
    pipeline_type: str = "daily"
    provider: str = "internal"
    started_at: datetime | None = None
    total_items: int = 0
    succeeded_items: int = 0
    skipped_items: int = 0
    failed_items: int = 0
    retry_of_run_id: int | None = None
    configuration_snapshot: dict[str, Any] = {}
    error_summary: str | None = None


class PipelineRunItemOut(BaseModel):
    id: int
    run_id: int
    stock_id: int | None
    announcement_id: int | None
    provider: str
    item_type: str
    status: str
    error_message: str | None
    attempt_count: int
    started_at: datetime
    finished_at: datetime | None
    metadata: dict[str, Any]


class AnnouncementVersionRelationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    predecessor_announcement_id: int
    successor_announcement_id: int
    relation_type: str
    confidence: float | None
    status: str
    source: str
    created_at: datetime
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str | None


class AnnouncementVersionRelationCreate(BaseModel):
    predecessor_announcement_id: int
    successor_announcement_id: int
    relation_type: str = "related_to"
    confidence: float | None = None
    source: str = "manual"


class AnnouncementVersionRelationReview(BaseModel):
    status: str
    reviewed_by: str
    review_note: str | None = None


class HistoricalBaselineCreate(BaseModel):
    stock_id: int
    title: str
    source_url: str = ""
    source_date: datetime | None = None
    local_pdf_path: str
    project_id: int | None = None
    review_status: str = "pending_review"


class ConfigHistoryOut(BaseModel):
    id: int
    key: str
    old_value: Any | None
    new_value: Any
    changed_by: str
    source: str
    changed_at: datetime
