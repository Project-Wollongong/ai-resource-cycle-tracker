"""Persistence helpers for historical analysis snapshots."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from sqlalchemy.orm import Session

from ..models import HistoricalAnalysisSnapshot, Stock


def save_historical_analysis_snapshot(
    session: Session,
    stock: Stock,
    payload: dict[str, Any],
    score: dict[str, Any],
) -> HistoricalAnalysisSnapshot:
    """Persist a successful historical score snapshot, idempotent by input hash."""

    if score.get("status") != "success":
        raise ValueError("only successful historical scores can be saved")
    input_hash = score.get("input_hash") or payload.get("input_hash")
    if not input_hash:
        raise ValueError("historical snapshot requires input_hash")

    as_of = payload.get("as_of") or {}
    existing = (
        session.query(HistoricalAnalysisSnapshot)
        .filter_by(
            stock_id=stock.id,
            as_of_date=as_of["as_of_date"],
            input_hash=input_hash,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing

    snapshot = HistoricalAnalysisSnapshot(
        stock_id=stock.id,
        as_of_date=as_of["as_of_date"],
        as_of_cutoff=as_of["as_of_cutoff"],
        market_data_as_of=as_of.get("market_data_as_of"),
        run_at=datetime.utcnow(),
        mode=as_of.get("mode", "approximate"),
        status=score["status"],
        boundary_status=as_of.get("boundary_status", "approximate"),
        data_warnings=_dumps(as_of.get("warnings", [])),
        input_hash=input_hash,
        input_summary=_dumps(score.get("input_summary") or payload.get("input_summary") or {}),
        funding_score=score["funding_score"],
        announcement_score=score["announcement_score"],
        resource_score=score["resource_score"],
        commodity_score=score["commodity_score"],
        risk_score=score["risk_score"],
        sentiment_score=score["sentiment_score"],
        cycle_score=score["cycle_score"],
        label=score["label"],
        components=_dumps(score.get("components", {})),
        ai_reason=score.get("reason", ""),
        config_snapshot=_dumps(payload.get("config", {})),
    )
    session.add(snapshot)
    session.commit()
    return snapshot


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
