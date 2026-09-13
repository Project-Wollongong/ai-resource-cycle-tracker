from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    commodity: Mapped[str] = mapped_column(String(30))  # gold/copper/lithium/uranium/rare_earth
    stage: Mapped[str] = mapped_column(String(20), default="explorer")  # explorer/developer
    resource_score_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    price_bars: Mapped[list["PriceBar"]] = relationship(back_populates="stock", cascade="all, delete-orphan")
    announcements: Mapped[list["Announcement"]] = relationship(back_populates="stock", cascade="all, delete-orphan")
    signals: Mapped[list["Signal"]] = relationship(back_populates="stock", cascade="all, delete-orphan")
    project_links: Mapped[list["StockProject"]] = relationship(back_populates="stock", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    commodity: Mapped[str | None] = mapped_column(String(30), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(80), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    stock_links: Mapped[list["StockProject"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class StockProject(Base):
    __tablename__ = "stock_projects"
    __table_args__ = (UniqueConstraint("stock_id", "project_id", name="uq_stock_project"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(40), default="owner")
    ownership_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    stock: Mapped[Stock] = relationship(back_populates="project_links")
    project: Mapped[Project] = relationship(back_populates="stock_links")


class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("stock_id", "date", name="uq_price_stock_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)

    stock: Mapped[Stock] = relationship(back_populates="price_bars")


class CommodityBar(Base):
    """Daily closes for commodity proxies and the backtest benchmark instrument."""

    __tablename__ = "commodity_bars"
    __table_args__ = (UniqueConstraint("instrument", "date", name="uq_commodity_instrument_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument: Mapped[str] = mapped_column(String(20), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    close: Mapped[float] = mapped_column(Float)


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (UniqueConstraint("stock_id", "ann_id", name="uq_ann_stock_annid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    ann_id: Mapped[str] = mapped_column(String(64))
    headline: Mapped[str] = mapped_column(Text)
    ann_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    url: Mapped[str] = mapped_column(Text, default="")
    price_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    ann_type: Mapped[str] = mapped_column(String(30), default="OTHER")
    type_score: Mapped[float] = mapped_column(Float, default=20.0)
    matched_keywords: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    raw_payload: Mapped[str] = mapped_column(Text, default="{}")  # raw source JSON, for traceability
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # phase-2 AI analysis layer
    ai_metrics: Mapped[str | None] = mapped_column(Text, nullable=True)  # phase-2, JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    stock: Mapped[Stock] = relationship(back_populates="announcements")


class EvidenceDocument(Base):
    __tablename__ = "evidence_documents"
    __table_args__ = (UniqueConstraint("source_type", "source_id", name="uq_evidence_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    announcement_id: Mapped[int | None] = mapped_column(ForeignKey("announcements.id"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(Text, default="")
    document_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    url: Mapped[str] = mapped_column(Text, default="")
    raw_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class P3Fact(Base):
    __tablename__ = "p3_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_document_id: Mapped[int] = mapped_column(ForeignKey("evidence_documents.id"), index=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    fact_type: Mapped[str] = mapped_column(String(60), index=True)
    schema_name: Mapped[str] = mapped_column(String(80), default="generic")
    field_name: Mapped[str] = mapped_column(String(80), index=True)
    value_json: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    extractor_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class P3Statement(Base):
    __tablename__ = "p3_statements"

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_document_id: Mapped[int] = mapped_column(ForeignKey("evidence_documents.id"), index=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    statement_type: Mapped[str] = mapped_column(String(60), index=True)
    statement_text: Mapped[str] = mapped_column(Text)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extractor_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class P4Feature(Base):
    __tablename__ = "p4_features"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    evidence_document_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_documents.id"), nullable=True, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    feature_group: Mapped[str] = mapped_column(String(60), index=True)
    feature_name: Mapped[str] = mapped_column(String(80), index=True)
    value_json: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    input_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    formula_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ScoreSnapshot(Base):
    __tablename__ = "score_snapshots"
    __table_args__ = (UniqueConstraint("stock_id", "date", name="uq_score_stock_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    funding_score: Mapped[float] = mapped_column(Float)
    announcement_score: Mapped[float] = mapped_column(Float)
    resource_score: Mapped[float] = mapped_column(Float)
    commodity_score: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[float] = mapped_column(Float)
    sentiment_score: Mapped[float] = mapped_column(Float, default=50.0)
    cycle_score: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(20))
    components: Mapped[str] = mapped_column(Text, default="{}")  # JSON: per-sub-score explanation
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class HistoricalAnalysisSnapshot(Base):
    __tablename__ = "historical_analysis_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "stock_id",
            "as_of_date",
            "input_hash",
            name="uq_historical_snapshot_stock_asof_input",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    as_of_cutoff: Mapped[datetime] = mapped_column(DateTime)
    market_data_as_of: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    mode: Mapped[str] = mapped_column(String(20), default="approximate")
    status: Mapped[str] = mapped_column(String(20), default="success")
    boundary_status: Mapped[str] = mapped_column(String(20), default="approximate")
    data_warnings: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    input_summary: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    funding_score: Mapped[float] = mapped_column(Float)
    announcement_score: Mapped[float] = mapped_column(Float)
    resource_score: Mapped[float] = mapped_column(Float)
    commodity_score: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[float] = mapped_column(Float)
    sentiment_score: Mapped[float] = mapped_column(Float, default=50.0)
    cycle_score: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(20))
    components: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    ai_reason: Mapped[str] = mapped_column(Text, default="")
    config_snapshot: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class HistoricalAnalysisReturn(Base):
    __tablename__ = "historical_analysis_returns"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "horizon_days",
            name="uq_historical_return_snapshot_horizon",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("historical_analysis_snapshots.id"),
        index=True,
    )
    horizon_days: Mapped[int] = mapped_column(Integer)
    entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(15), default="pending")
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (UniqueConstraint("stock_id", "date", "signal_type", name="uq_signal_stock_date_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    signal_type: Mapped[str] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(10), default="live")  # live / replay
    label: Mapped[str | None] = mapped_column(String(20), nullable=True)  # NULL for replay
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    price_at_signal: Mapped[float] = mapped_column(Float)  # signal-day close, reference only
    cycle_score_at_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    stock: Mapped[Stock] = relationship(back_populates="signals")
    returns: Mapped[list["SignalReturn"]] = relationship(back_populates="signal", cascade="all, delete-orphan")


class AnalyticalSignal(Base):
    __tablename__ = "analytical_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    engine: Mapped[str] = mapped_column(String(30), index=True)  # fundamental/technical/sentiment/catalyst
    signal_date: Mapped[date] = mapped_column(Date, index=True)
    direction: Mapped[str] = mapped_column(String(20))
    magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    persistence: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    dependency_group: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    evidence_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    feature_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    key_drivers_json: Mapped[str] = mapped_column(Text, default="[]")
    key_risks_json: Mapped[str] = mapped_column(Text, default="[]")
    logic_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FusionRecord(Base):
    __tablename__ = "fusion_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    fusion_date: Mapped[date] = mapped_column(Date, index=True)
    opportunity_strength: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    signal_structure: Mapped[str | None] = mapped_column(String(40), nullable=True)
    evidence_independence: Mapped[str | None] = mapped_column(String(30), nullable=True)
    dominant_drivers_json: Mapped[str] = mapped_column(Text, default="[]")
    conflicts_json: Mapped[str] = mapped_column(Text, default="[]")
    blocking_conditions_json: Mapped[str] = mapped_column(Text, default="[]")
    overheating_risk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    official_result: Mapped[str] = mapped_column(String(30))
    shadow_result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    conflict_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    analytical_signal_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    rule_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    model_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AttentionState(Base):
    __tablename__ = "attention_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    fusion_record_id: Mapped[int | None] = mapped_column(ForeignKey("fusion_records.id"), nullable=True, index=True)
    state_level: Mapped[str] = mapped_column(String(2), index=True)  # L0-L5
    state_label: Mapped[str] = mapped_column(String(40))
    previous_state_level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    transition: Mapped[str] = mapped_column(String(20), default="hold")
    reason: Mapped[str] = mapped_column(Text, default="")
    manual_lock: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    pinned_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    compute_profile: Mapped[str] = mapped_column(String(40), default="standard")
    alert_priority: Mapped[str] = mapped_column(String(30), default="dashboard")
    rule_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    effective_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TradeDecision(Base):
    __tablename__ = "trade_decisions"
    __table_args__ = (UniqueConstraint("stock_id", "decision_date", "rule_version", name="uq_trade_decision_stock_date_rule"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    fusion_record_id: Mapped[int | None] = mapped_column(ForeignKey("fusion_records.id"), nullable=True, index=True)
    attention_state_id: Mapped[int | None] = mapped_column(ForeignKey("attention_states.id"), nullable=True, index=True)
    decision_date: Mapped[date] = mapped_column(Date, index=True)
    decision: Mapped[str] = mapped_column(String(20))  # act/wait/pass
    action: Mapped[str] = mapped_column(String(30))  # none/starter_buy/buy
    conviction: Mapped[str] = mapped_column(String(20), default="low")
    reason: Mapped[str] = mapped_column(Text, default="")
    entry_logic: Mapped[str] = mapped_column(Text, default="")
    entry_range_json: Mapped[str] = mapped_column(Text, default="{}")
    position_size_json: Mapped[str] = mapped_column(Text, default="{}")
    add_trigger_json: Mapped[str] = mapped_column(Text, default="[]")
    invalidation_json: Mapped[str] = mapped_column(Text, default="[]")
    target_logic_json: Mapped[str] = mapped_column(Text, default="{}")
    key_risks_json: Mapped[str] = mapped_column(Text, default="[]")
    review_trigger_json: Mapped[str] = mapped_column(Text, default="[]")
    strategy_profile: Mapped[str] = mapped_column(String(40), default="balanced")
    rule_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    trade_decision_id: Mapped[int | None] = mapped_column(ForeignKey("trade_decisions.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open/closed
    opened_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    entry_price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    thesis_status: Mapped[str] = mapped_column(String(30), default="intact")
    catalyst_status: Mapped[str] = mapped_column(String(30), default="on_track")
    risk_status: Mapped[str] = mapped_column(String(30), default="normal")
    suggested_action: Mapped[str] = mapped_column(String(20), default="hold")
    price_stop: Mapped[float | None] = mapped_column(Float, nullable=True)
    thesis_stop_json: Mapped[str] = mapped_column(Text, default="[]")
    target_logic_json: Mapped[str] = mapped_column(Text, default="{}")
    original_thesis_json: Mapped[str] = mapped_column(Text, default="{}")
    thesis_delta_json: Mapped[str] = mapped_column(Text, default="{}")
    strategy_profile: Mapped[str] = mapped_column(String(40), default="balanced")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    events: Mapped[list["PositionEvent"]] = relationship(back_populates="position", cascade="all, delete-orphan")


class PositionEvent(Base):
    __tablename__ = "position_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    trade_decision_id: Mapped[int | None] = mapped_column(ForeignKey("trade_decisions.id"), nullable=True, index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    action: Mapped[str] = mapped_column(String(30), default="hold")
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    thesis_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    catalyst_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    risk_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    position: Mapped[Position] = relationship(back_populates="events")


class TradeReview(Base):
    __tablename__ = "trade_reviews"
    __table_args__ = (UniqueConstraint("position_id", "review_version", name="uq_trade_review_position_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    closed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    return_pct: Mapped[float] = mapped_column(Float)
    outcome_quality: Mapped[str] = mapped_column(String(30))
    decision_quality: Mapped[str] = mapped_column(String(30))
    thesis_review_json: Mapped[str] = mapped_column(Text, default="{}")
    signal_review_json: Mapped[str] = mapped_column(Text, default="{}")
    decision_review_json: Mapped[str] = mapped_column(Text, default="{}")
    position_management_review_json: Mapped[str] = mapped_column(Text, default="{}")
    outcome_attribution_json: Mapped[str] = mapped_column(Text, default="{}")
    state_transition_review_json: Mapped[str] = mapped_column(Text, default="{}")
    review_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class StrategyLearningCandidate(Base):
    __tablename__ = "strategy_learning_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_review_id: Mapped[int] = mapped_column(ForeignKey("trade_reviews.id"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    candidate_type: Mapped[str] = mapped_column(String(40), index=True)  # observation/hypothesis/change_candidate
    target_layer: Mapped[str] = mapped_column(String(20), index=True)  # P3-P9
    title: Mapped[str] = mapped_column(String(160))
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="proposed", index=True)
    requires_backtest: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SignalReturn(Base):
    __tablename__ = "signal_returns"
    __table_args__ = (UniqueConstraint("signal_id", "horizon_days", name="uq_return_signal_horizon"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), index=True)
    horizon_days: Mapped[int] = mapped_column(Integer)  # 5 / 20 / 60 / 120 trading days
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # first close AFTER signal day
    return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(15), default="pending")  # pending/filled/unavailable
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    signal: Mapped[Signal] = relationship(back_populates="returns")


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    content_json: Mapped[str] = mapped_column(Text)
    content_text: Mapped[str] = mapped_column(Text)  # Telegram HTML
    pushed: Mapped[bool] = mapped_column(Boolean, default=False)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    push_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AppConfig(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # JSON
    description: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AppConfigHistory(Base):
    __tablename__ = "app_config_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), index=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    new_value: Mapped[str] = mapped_column(Text)  # JSON
    changed_by: Mapped[str] = mapped_column(String(60), default="system")
    source: Mapped[str] = mapped_column(String(60), default="api")
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    trigger: Mapped[str] = mapped_column(String(20))  # scheduled/manual/cli/replay
    status: Mapped[str] = mapped_column(String(15), default="running")  # running/success/partial/failed
    stats_json: Mapped[str] = mapped_column(Text, default="{}")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
