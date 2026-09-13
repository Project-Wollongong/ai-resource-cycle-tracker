"""P9 Position Management.

P9 starts only after a user-confirmed real position exists. It manages the
position lifecycle and records every material change as a PositionEvent.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import AttentionState, FusionRecord, Position, PositionEvent, PriceBar, Stock, TradeDecision

P9_RULE_VERSION = "position_management_rules_v1"
DEFAULT_PORTFOLIO_GUARDRAILS = {
    "max_open_positions": 10,
    "max_single_position_value": 25_000.0,
    "max_commodity_exposure_value": 75_000.0,
}


def open_position_from_execution(
    session: Session,
    stock: Stock,
    *,
    entry_price: float,
    quantity: float,
    opened_at: datetime,
    trade_decision: TradeDecision | None = None,
    strategy_profile: str = "balanced",
    original_thesis: dict[str, Any] | None = None,
) -> Position:
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    if quantity <= 0:
        raise ValueError("quantity must be positive")

    _enforce_portfolio_guardrails(session, stock, entry_price * quantity)

    position = Position(
        stock_id=stock.id,
        trade_decision_id=trade_decision.id if trade_decision is not None else None,
        opened_at=opened_at,
        entry_price=entry_price,
        quantity=quantity,
        current_price=entry_price,
        price_stop=_initial_price_stop(entry_price, strategy_profile),
        thesis_stop_json=json.dumps(_initial_thesis_stops(trade_decision)),
        target_logic_json=trade_decision.target_logic_json if trade_decision is not None else "{}",
        original_thesis_json=json.dumps(original_thesis or _original_thesis_from_decision(trade_decision)),
        strategy_profile=strategy_profile,
        metadata_json=json.dumps({"rule_version": P9_RULE_VERSION}),
    )
    session.add(position)
    session.flush()
    _add_event(
        session,
        position,
        stock,
        event_time=opened_at,
        event_type="initial_buy",
        action="hold",
        price=entry_price,
        quantity_delta=quantity,
        reason="User-confirmed execution opened the position.",
        trade_decision=trade_decision,
    )
    session.commit()
    return position


def update_position_from_current_state(
    session: Session,
    position: Position,
    stock: Stock,
    *,
    fusion: FusionRecord | None = None,
    attention: AttentionState | None = None,
    trade_decision: TradeDecision | None = None,
    as_of: datetime | None = None,
) -> Position:
    as_of = as_of or datetime.utcnow()
    latest_price = _latest_close(session, stock.id, as_of)
    if latest_price is not None:
        position.current_price = latest_price

    thesis_delta = _thesis_delta(fusion, attention, trade_decision)
    position.thesis_delta_json = json.dumps(thesis_delta)
    position.thesis_status = _thesis_status(thesis_delta)
    position.catalyst_status = _catalyst_status(fusion, attention)
    position.risk_status = _risk_status(fusion, trade_decision)
    position.suggested_action = _suggested_action(position, fusion, trade_decision)

    event_type = "position_review"
    if position.suggested_action == "exit":
        event_type = "exit_review"
    elif position.suggested_action == "review":
        event_type = "thesis_review"
    elif position.suggested_action == "add":
        event_type = "add_review"
    elif latest_price is not None:
        event_type = "price_update"

    _add_event(
        session,
        position,
        stock,
        event_time=as_of,
        event_type=event_type,
        action=position.suggested_action,
        price=latest_price,
        quantity_delta=0,
        thesis_status=position.thesis_status,
        catalyst_status=position.catalyst_status,
        risk_status=position.risk_status,
        reason=_review_reason(position, fusion, trade_decision),
        trade_decision=trade_decision,
        evidence={
            "fusion_record_id": fusion.id if fusion is not None else None,
            "attention_state_id": attention.id if attention is not None else None,
            "trade_decision_id": trade_decision.id if trade_decision is not None else None,
        },
    )
    session.commit()
    return position


def close_position(
    session: Session,
    position: Position,
    stock: Stock,
    *,
    exit_price: float,
    closed_at: datetime,
    reason: str,
) -> Position:
    if exit_price <= 0:
        raise ValueError("exit_price must be positive")
    position.status = "closed"
    position.closed_at = closed_at
    position.current_price = exit_price
    position.suggested_action = "closed"
    _add_event(
        session,
        position,
        stock,
        event_time=closed_at,
        event_type="exit",
        action="closed",
        price=exit_price,
        quantity_delta=-position.quantity,
        reason=reason,
    )
    session.commit()
    return position


def _enforce_portfolio_guardrails(session: Session, stock: Stock, new_position_value: float) -> None:
    open_positions = session.query(Position).filter_by(status="open").all()
    if len(open_positions) >= DEFAULT_PORTFOLIO_GUARDRAILS["max_open_positions"]:
        raise ValueError("portfolio guardrail exceeded: max_open_positions")
    if new_position_value > DEFAULT_PORTFOLIO_GUARDRAILS["max_single_position_value"]:
        raise ValueError("portfolio guardrail exceeded: max_single_position_value")

    commodity_exposure = 0.0
    for position in open_positions:
        pos_stock = session.get(Stock, position.stock_id)
        if pos_stock is None or pos_stock.commodity != stock.commodity:
            continue
        price = position.current_price or position.entry_price
        commodity_exposure += price * position.quantity
    if commodity_exposure + new_position_value > DEFAULT_PORTFOLIO_GUARDRAILS["max_commodity_exposure_value"]:
        raise ValueError("portfolio guardrail exceeded: max_commodity_exposure_value")


def _initial_price_stop(entry_price: float, strategy_profile: str) -> float:
    stop_pct = {"conservative": 0.15, "balanced": 0.20, "aggressive": 0.28}.get(strategy_profile, 0.20)
    return round(entry_price * (1 - stop_pct), 4)


def _initial_thesis_stops(trade_decision: TradeDecision | None) -> list[str]:
    if trade_decision is None:
        return [
            "thesis-breaking announcement",
            "funding deterioration",
            "expected catalyst materially delayed",
        ]
    try:
        invalidation = json.loads(trade_decision.invalidation_json)
    except json.JSONDecodeError:
        invalidation = []
    return invalidation if isinstance(invalidation, list) else []


def _original_thesis_from_decision(trade_decision: TradeDecision | None) -> dict[str, Any]:
    if trade_decision is None:
        return {}
    return {
        "decision_id": trade_decision.id,
        "decision": trade_decision.decision,
        "action": trade_decision.action,
        "conviction": trade_decision.conviction,
        "reason": trade_decision.reason,
    }


def _latest_close(session: Session, stock_id: int, as_of: datetime) -> float | None:
    row = (
        session.query(PriceBar)
        .filter(PriceBar.stock_id == stock_id, PriceBar.date <= as_of.date())
        .order_by(PriceBar.date.desc())
        .first()
    )
    return row.close if row is not None else None


def _thesis_delta(
    fusion: FusionRecord | None,
    attention: AttentionState | None,
    trade_decision: TradeDecision | None,
) -> dict[str, Any]:
    blockers = _json_list(fusion.blocking_conditions_json if fusion is not None else None)
    risks = _json_list(trade_decision.key_risks_json if trade_decision is not None else None)
    return {
        "fundamental": "unknown",
        "catalyst": "unknown" if fusion is None else fusion.signal_structure,
        "risk": "worsened" if blockers or risks else "unchanged",
        "attention_state": attention.state_level if attention is not None else None,
        "opportunity_strength": fusion.opportunity_strength if fusion is not None else None,
        "blocking_conditions": blockers,
        "decision_risks": risks,
    }


def _thesis_status(delta: dict[str, Any]) -> str:
    if delta["blocking_conditions"]:
        return "invalidated"
    if delta["risk"] == "worsened":
        return "weakened"
    if delta["opportunity_strength"] in {"strong", "exceptional"}:
        return "strengthened"
    return "intact"


def _catalyst_status(fusion: FusionRecord | None, attention: AttentionState | None) -> str:
    if fusion is None:
        return "unknown"
    if fusion.signal_structure in {"confirmation", "fundamental_led_early_formation"}:
        return "on_track"
    if attention is not None and attention.state_level in {"L1", "L2"}:
        return "needs_review"
    return "unknown"


def _risk_status(fusion: FusionRecord | None, trade_decision: TradeDecision | None) -> str:
    blockers = _json_list(fusion.blocking_conditions_json if fusion is not None else None)
    risks = _json_list(trade_decision.key_risks_json if trade_decision is not None else None)
    if blockers:
        return "critical"
    if any("overheating" in risk or "limited independent evidence" in risk for risk in risks):
        return "elevated"
    return "normal"


def _suggested_action(
    position: Position,
    fusion: FusionRecord | None,
    trade_decision: TradeDecision | None,
) -> str:
    current_price = position.current_price
    if position.thesis_status == "invalidated" or position.risk_status == "critical":
        return "exit"
    if current_price is not None and position.price_stop is not None and current_price <= position.price_stop:
        return "review"
    if trade_decision is not None and trade_decision.decision == "pass":
        return "review"
    if (
        fusion is not None
        and fusion.opportunity_strength in {"strong", "exceptional"}
        and position.thesis_status in {"intact", "strengthened"}
        and position.risk_status == "normal"
    ):
        return "add"
    return "hold"


def _review_reason(
    position: Position,
    fusion: FusionRecord | None,
    trade_decision: TradeDecision | None,
) -> str:
    if position.suggested_action == "exit":
        return "Thesis or risk status indicates exit review is required."
    if position.suggested_action == "review":
        return "Position requires review due to stop, risk, or latest trade decision state."
    if position.suggested_action == "add":
        return "Opportunity remains strong and current position thesis is intact."
    if fusion is not None:
        return f"Position reviewed against P6 {fusion.opportunity_strength} opportunity."
    if trade_decision is not None:
        return f"Position reviewed against P8 {trade_decision.decision} decision."
    return "Position reviewed with latest available market data."


def _add_event(
    session: Session,
    position: Position,
    stock: Stock,
    *,
    event_time: datetime,
    event_type: str,
    action: str,
    price: float | None,
    quantity_delta: float | None,
    reason: str,
    trade_decision: TradeDecision | None = None,
    thesis_status: str | None = None,
    catalyst_status: str | None = None,
    risk_status: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> None:
    session.add(
        PositionEvent(
            position_id=position.id,
            stock_id=stock.id,
            trade_decision_id=trade_decision.id if trade_decision is not None else None,
            event_time=event_time,
            event_type=event_type,
            action=action,
            price=price,
            quantity_delta=quantity_delta,
            thesis_status=thesis_status,
            catalyst_status=catalyst_status,
            risk_status=risk_status,
            reason=reason,
            evidence_json=json.dumps(evidence or {}),
            metadata_json=json.dumps({"rule_version": P9_RULE_VERSION}),
        )
    )


def _json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
