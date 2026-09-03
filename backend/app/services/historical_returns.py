"""Forward performance evaluation for historical analysis snapshots."""

from __future__ import annotations

from bisect import bisect_right
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from ..models import (
    HistoricalAnalysisReturn,
    HistoricalAnalysisSnapshot,
    PriceBar,
)
from .backtest import _benchmark_return, _load_instrument_series
from .config_service import get_config

DEFAULT_HORIZONS = (5, 20, 60, 120)


def evaluate_historical_snapshot_returns(
    session: Session,
    snapshot: HistoricalAnalysisSnapshot,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    today: date | None = None,
) -> list[HistoricalAnalysisReturn]:
    """Create or update forward-return rows for one historical snapshot."""

    today = today or date.today()
    bars = (
        session.query(PriceBar.date, PriceBar.close)
        .filter(PriceBar.stock_id == snapshot.stock_id)
        .order_by(PriceBar.date.asc())
        .all()
    )
    dates = [row[0] for row in bars]
    closes = [row[1] for row in bars]
    bench = _load_instrument_series(session, get_config(session, "benchmark_instrument"))
    last_bar_date = dates[-1] if dates else None
    signal_date = snapshot.market_data_as_of or snapshot.as_of_date

    results = []
    for horizon in horizons:
        row = _get_or_create_return(session, snapshot.id, horizon)
        _fill_return_row(row, dates, closes, bench, signal_date, horizon, today, last_bar_date)
        results.append(row)
    session.commit()
    return results


def evaluate_pending_historical_returns(session: Session, today: date | None = None) -> dict:
    """Fill all pending historical analysis return rows."""

    today = today or date.today()
    rows = (
        session.query(HistoricalAnalysisReturn, HistoricalAnalysisSnapshot)
        .join(HistoricalAnalysisSnapshot, HistoricalAnalysisReturn.snapshot_id == HistoricalAnalysisSnapshot.id)
        .filter(HistoricalAnalysisReturn.status == "pending")
        .all()
    )
    filled = unavailable = pending = 0
    grouped: dict[int, list[tuple[HistoricalAnalysisReturn, HistoricalAnalysisSnapshot]]] = {}
    for ret, snapshot in rows:
        grouped.setdefault(snapshot.stock_id, []).append((ret, snapshot))

    bench = _load_instrument_series(session, get_config(session, "benchmark_instrument"))
    for stock_id, items in grouped.items():
        bars = (
            session.query(PriceBar.date, PriceBar.close)
            .filter(PriceBar.stock_id == stock_id)
            .order_by(PriceBar.date.asc())
            .all()
        )
        dates = [row[0] for row in bars]
        closes = [row[1] for row in bars]
        last_bar_date = dates[-1] if dates else None
        for ret, snapshot in items:
            old_status = ret.status
            signal_date = snapshot.market_data_as_of or snapshot.as_of_date
            _fill_return_row(
                ret,
                dates,
                closes,
                bench,
                signal_date,
                ret.horizon_days,
                today,
                last_bar_date,
            )
            if ret.status == "filled" and old_status != "filled":
                filled += 1
            elif ret.status == "unavailable" and old_status != "unavailable":
                unavailable += 1
            elif ret.status == "pending":
                pending += 1
    session.commit()
    return {"filled": filled, "unavailable": unavailable, "pending": pending}


def _get_or_create_return(
    session: Session,
    snapshot_id: int,
    horizon_days: int,
) -> HistoricalAnalysisReturn:
    row = (
        session.query(HistoricalAnalysisReturn)
        .filter_by(snapshot_id=snapshot_id, horizon_days=horizon_days)
        .one_or_none()
    )
    if row is None:
        row = HistoricalAnalysisReturn(snapshot_id=snapshot_id, horizon_days=horizon_days)
        session.add(row)
        session.flush()
    return row


def _fill_return_row(
    row: HistoricalAnalysisReturn,
    dates: list[date],
    closes: list[float],
    bench: tuple[list[date], list[float]],
    signal_date: date,
    horizon: int,
    today: date,
    last_bar_date: date | None,
) -> None:
    entry_idx = bisect_right(dates, signal_date)
    bars_after = len(dates) - entry_idx
    if bars_after >= horizon + 1:
        exit_idx = entry_idx + horizon
        entry_price = closes[entry_idx]
        exit_price = closes[exit_idx]
        row.entry_date = dates[entry_idx]
        row.entry_price = entry_price
        row.exit_date = dates[exit_idx]
        row.exit_price = exit_price
        row.return_pct = (exit_price / entry_price - 1) * 100 if entry_price > 0 else None
        row.benchmark_return_pct = _benchmark_return(bench, dates[entry_idx], dates[exit_idx])
        row.max_drawdown_pct = _max_drawdown_pct(closes[entry_idx : exit_idx + 1])
        row.status = "filled"
        row.filled_at = datetime.now(timezone.utc).replace(tzinfo=None)
        return

    calendar_elapsed = (today - signal_date).days
    stale = last_bar_date is None or (today - last_bar_date).days > 10
    if calendar_elapsed > horizon * 2 and stale:
        row.status = "unavailable"
        row.filled_at = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        row.status = "pending"


def _max_drawdown_pct(closes: list[float]) -> float | None:
    if not closes:
        return None
    peak = closes[0]
    max_drawdown = 0.0
    for close in closes:
        if close > peak:
            peak = close
        if peak > 0:
            max_drawdown = min(max_drawdown, (close / peak - 1) * 100)
    return round(max_drawdown, 2)
