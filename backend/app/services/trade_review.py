"""P10 Trade Review & Strategy Learning.

Reviews closed positions and creates learning candidates. This module never
applies rule/config changes directly; candidates stay proposed until a future
approval/backtest workflow consumes them.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..models import Position, PositionEvent, Stock, StrategyLearningCandidate, TradeReview

P10_REVIEW_VERSION = "trade_review_v1"


def create_trade_review_for_position(
    session: Session,
    position: Position,
    stock: Stock,
) -> TradeReview:
    if position.status != "closed" or position.closed_at is None or position.current_price is None:
        raise ValueError("trade review requires a closed position with an exit price")

    events = (
        session.query(PositionEvent)
        .filter_by(position_id=position.id)
        .order_by(PositionEvent.event_time.asc(), PositionEvent.id.asc())
        .all()
    )
    return_pct = round((position.current_price / position.entry_price - 1) * 100, 2)

    review = (
        session.query(TradeReview)
        .filter_by(position_id=position.id, review_version=P10_REVIEW_VERSION)
        .one_or_none()
    )
    if review is None:
        review = TradeReview(
            position_id=position.id,
            stock_id=stock.id,
            review_version=P10_REVIEW_VERSION,
        )
        session.add(review)

    thesis_review = _thesis_review(position, events)
    signal_review = _signal_review(position, events)
    decision_review = _decision_review(position, events)
    management_review = _position_management_review(position, events)
    attribution = _outcome_attribution(position, events, return_pct)
    transition_review = _state_transition_review(events)

    review.opened_at = position.opened_at
    review.closed_at = position.closed_at
    review.entry_price = position.entry_price
    review.exit_price = position.current_price
    review.return_pct = return_pct
    review.outcome_quality = _outcome_quality(return_pct)
    review.decision_quality = _decision_quality(position, return_pct, thesis_review, management_review)
    review.thesis_review_json = json.dumps(thesis_review, default=str)
    review.signal_review_json = json.dumps(signal_review, default=str)
    review.decision_review_json = json.dumps(decision_review, default=str)
    review.position_management_review_json = json.dumps(management_review, default=str)
    review.outcome_attribution_json = json.dumps(attribution, default=str)
    review.state_transition_review_json = json.dumps(transition_review, default=str)
    review.metadata_json = json.dumps(
        {
            "position_event_count": len(events),
            "strategy_profile": position.strategy_profile,
            "auto_rule_change": False,
        },
        default=str,
    )
    session.flush()

    _sync_learning_candidates(session, review, stock, position, return_pct, thesis_review, management_review)
    session.commit()
    return review


def _thesis_review(position: Position, events: list[PositionEvent]) -> dict[str, Any]:
    statuses = [event.thesis_status for event in events if event.thesis_status]
    final_status = position.thesis_status
    return {
        "original_thesis": _loads(position.original_thesis_json, {}),
        "final_thesis_status": final_status,
        "status_path": statuses,
        "assessment": (
            "Original thesis appears invalidated."
            if final_status == "invalidated"
            else "Original thesis remained broadly intact or improved."
        ),
    }


def _signal_review(position: Position, events: list[PositionEvent]) -> dict[str, Any]:
    action_counts: dict[str, int] = {}
    for event in events:
        action_counts[event.action] = action_counts.get(event.action, 0) + 1
    return {
        "event_count": len(events),
        "action_counts": action_counts,
        "notable_events": [
            {"type": event.event_type, "action": event.action, "reason": event.reason}
            for event in events
            if event.event_type in {"add_review", "thesis_review", "exit_review"}
        ],
    }


def _decision_review(position: Position, events: list[PositionEvent]) -> dict[str, Any]:
    initial = next((event for event in events if event.event_type == "initial_buy"), None)
    return {
        "trade_decision_id": position.trade_decision_id,
        "entry_price": position.entry_price,
        "initial_event_reason": initial.reason if initial is not None else None,
        "assessment": "Entry was user-confirmed; sizing and timing require qualitative review.",
    }


def _position_management_review(position: Position, events: list[PositionEvent]) -> dict[str, Any]:
    review_events = [event for event in events if event.event_type.endswith("_review")]
    exit_reviews = [event for event in events if event.event_type == "exit_review"]
    return {
        "review_event_count": len(review_events),
        "exit_review_count": len(exit_reviews),
        "final_suggested_action": position.suggested_action,
        "assessment": (
            "Position hit an exit-review condition before closure."
            if exit_reviews
            else "No exit-review condition was recorded before closure."
        ),
    }


def _outcome_attribution(position: Position, events: list[PositionEvent], return_pct: float) -> dict[str, Any]:
    return {
        "return_pct": return_pct,
        "price_return": "positive" if return_pct > 0 else "negative" if return_pct < 0 else "flat",
        "thesis_status_at_close": position.thesis_status,
        "risk_status_at_close": position.risk_status,
        "event_drivers": [
            {"type": event.event_type, "reason": event.reason}
            for event in events
            if event.event_type in {"add_review", "thesis_review", "exit_review", "exit"}
        ],
    }


def _state_transition_review(events: list[PositionEvent]) -> dict[str, Any]:
    evidence_refs = [_loads(event.evidence_json, {}) for event in events]
    attention_ids = [item.get("attention_state_id") for item in evidence_refs if isinstance(item, dict) and item.get("attention_state_id")]
    fusion_ids = [item.get("fusion_record_id") for item in evidence_refs if isinstance(item, dict) and item.get("fusion_record_id")]
    return {
        "attention_state_ids": attention_ids,
        "fusion_record_ids": fusion_ids,
        "assessment": "State transition effectiveness requires comparison against future outcomes.",
    }


def _sync_learning_candidates(
    session: Session,
    review: TradeReview,
    stock: Stock,
    position: Position,
    return_pct: float,
    thesis_review: dict[str, Any],
    management_review: dict[str, Any],
) -> None:
    existing = (
        session.query(StrategyLearningCandidate)
        .filter_by(trade_review_id=review.id)
        .all()
    )
    if existing:
        return

    candidates = []
    if position.thesis_status == "invalidated":
        candidates.append(
            _candidate(
                review,
                stock,
                candidate_type="observation",
                target_layer="P9",
                title="Review thesis-stop sensitivity",
                rationale="Closed trade had an invalidated thesis; verify whether P9 exit review fired early enough.",
                evidence={"position_id": position.id, "return_pct": return_pct, "thesis_review": thesis_review},
            )
        )
    if return_pct > 25 and management_review["review_event_count"] == 0:
        candidates.append(
            _candidate(
                review,
                stock,
                candidate_type="hypothesis",
                target_layer="P8",
                title="Evaluate whether entry sizing was too conservative",
                rationale="Strong positive outcome with no intermediate review events may indicate starter sizing rules should be tested.",
                evidence={"position_id": position.id, "return_pct": return_pct},
            )
        )
    if return_pct < -15:
        candidates.append(
            _candidate(
                review,
                stock,
                candidate_type="hypothesis",
                target_layer="P7",
                title="Evaluate downgrade and exit-review timing",
                rationale="Large negative outcome should be checked against attention-state and position-review timing.",
                evidence={"position_id": position.id, "return_pct": return_pct},
            )
        )
    if not candidates:
        candidates.append(
            _candidate(
                review,
                stock,
                candidate_type="observation",
                target_layer="P10",
                title="Archive trade outcome for future strategy sample",
                rationale="Single trade review is recorded as evidence; no production rule change is justified.",
                evidence={"position_id": position.id, "return_pct": return_pct},
                requires_backtest=False,
            )
        )
    session.add_all(candidates)


def _candidate(
    review: TradeReview,
    stock: Stock,
    *,
    candidate_type: str,
    target_layer: str,
    title: str,
    rationale: str,
    evidence: dict[str, Any],
    requires_backtest: bool = True,
) -> StrategyLearningCandidate:
    return StrategyLearningCandidate(
        trade_review_id=review.id,
        stock_id=stock.id,
        candidate_type=candidate_type,
        target_layer=target_layer,
        title=title,
        rationale=rationale,
        evidence_json=json.dumps(evidence, default=str),
        requires_backtest=requires_backtest,
        requires_human_approval=True,
        status="proposed",
        metadata_json=json.dumps({"auto_applied": False, "review_version": P10_REVIEW_VERSION}),
    )


def _outcome_quality(return_pct: float) -> str:
    if return_pct >= 25:
        return "strong_profit"
    if return_pct > 0:
        return "profit"
    if return_pct <= -20:
        return "large_loss"
    if return_pct < 0:
        return "loss"
    return "flat"


def _decision_quality(
    position: Position,
    return_pct: float,
    thesis_review: dict[str, Any],
    management_review: dict[str, Any],
) -> str:
    if thesis_review["final_thesis_status"] == "invalidated" and return_pct > 0:
        return "lucky_profit_after_thesis_failure"
    if thesis_review["final_thesis_status"] == "invalidated":
        return "poor_or_invalidated"
    if return_pct < -15 and management_review["exit_review_count"] == 0:
        return "needs_review"
    if return_pct > 0 and position.thesis_status in {"intact", "strengthened"}:
        return "supported"
    return "inconclusive"


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return default
    return value
