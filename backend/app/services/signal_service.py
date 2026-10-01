"""Persist detected signals + create pending forward-return rows. Idempotent."""

import json
from datetime import date

from sqlalchemy.orm import Session

from ..analysis.signals import SignalCandidate, assign_event_roles
from ..models import Signal, SignalReturn, Stock

RETURN_HORIZONS = (5, 20, 60, 120)


def persist_signals(
    session: Session,
    stock: Stock,
    signal_date: date,
    candidates: list[SignalCandidate],
    price_at_signal: float,
    source: str = "live",
    label: str | None = None,
    cycle_score: float | None = None,
) -> int:
    """Insert new signals (unique on stock+date+type, so reruns are no-ops)
    and their 4 pending signal_returns. Replay signals carry no label/score:
    historical announcement data is unavailable, so a historical Cycle Score
    cannot be honestly reconstructed."""
    added = 0
    for cand, mechanism, role in assign_event_roles(candidates):
        exists = (
            session.query(Signal.id)
            .filter_by(stock_id=stock.id, date=signal_date, signal_type=cand.signal_type)
            .first()
        )
        if exists:
            continue
        signal = Signal(
            stock_id=stock.id,
            date=signal_date,
            signal_type=cand.signal_type,
            source=source,
            label=label if source == "live" else None,
            reason=cand.reason,
            evidence=json.dumps(cand.evidence),
            price_at_signal=price_at_signal,
            cycle_score_at_signal=cycle_score if source == "live" else None,
            event_key=f"{stock.id}|{signal_date.isoformat()}|{mechanism}",
            role=role,
        )
        session.add(signal)
        session.flush()
        for horizon in RETURN_HORIZONS:
            session.add(SignalReturn(signal_id=signal.id, horizon_days=horizon))
        added += 1
    session.commit()
    return added
