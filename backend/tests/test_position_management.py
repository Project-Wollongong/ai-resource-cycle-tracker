import json
from datetime import date, datetime

import pytest

from app.models import AttentionState, FusionRecord, Position, PositionEvent, PriceBar, Stock, TradeDecision
from app.services.position_management import (
    close_position,
    open_position_from_execution,
    update_position_from_current_state,
)


def make_stock_with_price(db_session, code="P9A", commodity="gold", close=0.11):
    stock = Stock(code=code, name=f"{code} Resources", commodity=commodity)
    db_session.add(stock)
    db_session.commit()
    db_session.add(
        PriceBar(
            stock_id=stock.id,
            date=date(2026, 9, 10),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1_000_000,
        )
    )
    db_session.commit()
    return stock


def make_decision(db_session, stock_id, decision="act", action="starter_buy"):
    decision_row = TradeDecision(
        stock_id=stock_id,
        decision_date=date(2026, 9, 10),
        decision=decision,
        action=action,
        conviction="medium",
        reason="Test decision",
        invalidation_json=json.dumps(["thesis-breaking announcement"]),
        target_logic_json=json.dumps({"basis": "test"}),
        rule_version="test_trade_decision",
    )
    db_session.add(decision_row)
    db_session.commit()
    return decision_row


def make_fusion(db_session, stock_id, *, strength="strong", blockers=None):
    fusion = FusionRecord(
        stock_id=stock_id,
        fusion_date=date(2026, 9, 10),
        opportunity_strength=strength,
        confidence="high",
        signal_structure="confirmation",
        evidence_independence="medium",
        official_result="blocked" if blockers else strength,
        blocking_conditions_json=json.dumps(blockers or []),
        conflicts_json="[]",
        overheating_risk="low",
        analytical_signal_ids_json="[]",
        rule_version="test_fusion",
    )
    db_session.add(fusion)
    db_session.commit()
    return fusion


def make_attention(db_session, stock_id, fusion_id, level="L5"):
    attention = AttentionState(
        stock_id=stock_id,
        fusion_record_id=fusion_id,
        state_level=level,
        state_label="Position" if level == "L5" else "Decision Ready",
        transition="hold",
        rule_version="attention_rules_v1",
    )
    db_session.add(attention)
    db_session.commit()
    return attention


def test_open_position_requires_user_execution_and_records_initial_buy(db_session):
    stock = make_stock_with_price(db_session)
    decision = make_decision(db_session, stock.id)

    position = open_position_from_execution(
        db_session,
        stock,
        entry_price=0.10,
        quantity=100_000,
        opened_at=datetime(2026, 9, 10, 10, 0),
        trade_decision=decision,
        original_thesis={"core": "resource growth"},
    )

    assert position.status == "open"
    assert position.trade_decision_id == decision.id
    assert position.price_stop == 0.08
    assert json.loads(position.original_thesis_json) == {"core": "resource growth"}
    event = db_session.query(PositionEvent).filter_by(position_id=position.id).one()
    assert event.event_type == "initial_buy"
    assert event.quantity_delta == 100_000


def test_update_position_suggests_add_when_thesis_strengthens_without_risk(db_session):
    stock = make_stock_with_price(db_session)
    decision = make_decision(db_session, stock.id)
    position = open_position_from_execution(
        db_session,
        stock,
        entry_price=0.10,
        quantity=50_000,
        opened_at=datetime(2026, 9, 10, 10, 0),
        trade_decision=decision,
    )
    fusion = make_fusion(db_session, stock.id, strength="strong")
    attention = make_attention(db_session, stock.id, fusion.id)

    update_position_from_current_state(
        db_session,
        position,
        stock,
        fusion=fusion,
        attention=attention,
        trade_decision=decision,
        as_of=datetime(2026, 9, 10, 16, 0),
    )

    assert position.current_price == 0.11
    assert position.thesis_status == "strengthened"
    assert position.suggested_action == "add"
    latest_event = db_session.query(PositionEvent).order_by(PositionEvent.id.desc()).first()
    assert latest_event.event_type == "add_review"
    assert latest_event.action == "add"


def test_blocking_condition_invalidates_thesis_and_suggests_exit(db_session):
    stock = make_stock_with_price(db_session)
    decision = make_decision(db_session, stock.id)
    position = open_position_from_execution(
        db_session,
        stock,
        entry_price=0.10,
        quantity=50_000,
        opened_at=datetime(2026, 9, 10, 10, 0),
        trade_decision=decision,
    )
    fusion = make_fusion(db_session, stock.id, blockers=["risk_score_below_30"])
    attention = make_attention(db_session, stock.id, fusion.id)

    update_position_from_current_state(db_session, position, stock, fusion=fusion, attention=attention)

    assert position.thesis_status == "invalidated"
    assert position.risk_status == "critical"
    assert position.suggested_action == "exit"


def test_price_stop_is_review_not_automatic_exit(db_session):
    stock = make_stock_with_price(db_session, close=0.07)
    decision = make_decision(db_session, stock.id)
    position = open_position_from_execution(
        db_session,
        stock,
        entry_price=0.10,
        quantity=50_000,
        opened_at=datetime(2026, 9, 10, 10, 0),
        trade_decision=decision,
    )
    position.price_stop = 0.08
    fusion = make_fusion(db_session, stock.id, strength="moderate")

    update_position_from_current_state(
        db_session,
        position,
        stock,
        fusion=fusion,
        trade_decision=decision,
        as_of=datetime(2026, 9, 10, 16, 0),
    )

    assert position.suggested_action == "review"
    assert position.status == "open"


def test_close_position_records_exit_event(db_session):
    stock = make_stock_with_price(db_session)
    position = open_position_from_execution(
        db_session,
        stock,
        entry_price=0.10,
        quantity=50_000,
        opened_at=datetime(2026, 9, 10, 10, 0),
    )

    close_position(
        db_session,
        position,
        stock,
        exit_price=0.13,
        closed_at=datetime(2026, 9, 20, 10, 0),
        reason="User closed the trade.",
    )

    assert position.status == "closed"
    assert position.current_price == 0.13
    exit_event = db_session.query(PositionEvent).order_by(PositionEvent.id.desc()).first()
    assert exit_event.event_type == "exit"
    assert exit_event.quantity_delta == -50_000


def test_single_position_guardrail_blocks_oversized_open(db_session):
    stock = make_stock_with_price(db_session)

    with pytest.raises(ValueError, match="max_single_position_value"):
        open_position_from_execution(
            db_session,
            stock,
            entry_price=1.0,
            quantity=30_000,
            opened_at=datetime(2026, 9, 10, 10, 0),
        )


def test_p8_decision_does_not_auto_create_position(db_session):
    stock = make_stock_with_price(db_session)
    make_decision(db_session, stock.id, decision="act", action="buy")

    assert db_session.query(Position).filter_by(stock_id=stock.id).count() == 0
