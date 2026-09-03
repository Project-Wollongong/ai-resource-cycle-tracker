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
