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
