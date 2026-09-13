from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    detail: str


# ---------- stocks ----------

class StockCreate(BaseModel):
    code: str
    name: str
    commodity: str
    stage: str = "explorer"
    notes: str = ""


class StockUpdate(BaseModel):
    name: str | None = None
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


class ConfigHistoryOut(BaseModel):
    id: int
    key: str
    old_value: Any | None
    new_value: Any
    changed_by: str
    source: str
    changed_at: datetime
