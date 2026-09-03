"""Service entry points for historical point-in-time analysis."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..models import HistoricalAnalysisSnapshot, Stock
from .historical_input import build_historical_analysis_input
from .historical_returns import evaluate_historical_snapshot_returns
from .historical_scoring import score_historical_analysis_input
from .historical_snapshots import save_historical_analysis_snapshot


def run_historical_analysis(
    session: Session,
    stock: Stock,
    as_of_date: date,
    mode: str = "approximate",
) -> HistoricalAnalysisSnapshot:
    """Build, score, and persist one historical analysis snapshot."""

    payload = build_historical_analysis_input(session, stock, as_of_date, mode=mode)
    score = score_historical_analysis_input(payload)
    if score.get("status") != "success":
        reason = score.get("reason", "unknown")
        raise ValueError(f"historical analysis incomplete: {reason}")
    snapshot = save_historical_analysis_snapshot(session, stock, payload, score)
    evaluate_historical_snapshot_returns(session, snapshot)
    return snapshot


def run_historical_analysis_for_code(
    session: Session,
    code: str,
    as_of_date: date,
    mode: str = "approximate",
) -> HistoricalAnalysisSnapshot:
    """Run historical analysis by stock code."""

    stock = session.query(Stock).filter_by(code=code.strip().upper()).one_or_none()
    if stock is None:
        raise ValueError(f"stock {code.strip().upper()} not found")
    return run_historical_analysis(session, stock, as_of_date, mode=mode)
