from datetime import datetime

import pytest

from app.models import PositionEvent, Stock, StrategyLearningCandidate
from app.services.position_management import close_position, open_position_from_execution
from app.services.trade_review import create_trade_review_for_position


def test_trade_review_requires_closed_position(db_session):
    stock = Stock(code="R10", name="Review Test", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    position = open_position_from_execution(
        db_session,
        stock,
        entry_price=0.10,
        quantity=10_000,
        opened_at=datetime(2026, 9, 10, 10, 0),
    )

    with pytest.raises(ValueError, match="closed position"):
        create_trade_review_for_position(db_session, position, stock)


def test_trade_review_creates_five_dimension_review_and_candidate(db_session):
    stock = Stock(code="R11", name="Review Positive", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    position = open_position_from_execution(
        db_session,
        stock,
        entry_price=0.10,
        quantity=10_000,
        opened_at=datetime(2026, 9, 10, 10, 0),
        original_thesis={"core": "resource growth"},
    )
    close_position(
        db_session,
        position,
        stock,
        exit_price=0.14,
        closed_at=datetime(2026, 10, 10, 10, 0),
        reason="User closed after catalyst move.",
    )

    review = create_trade_review_for_position(db_session, position, stock)
    same_review = create_trade_review_for_position(db_session, position, stock)

    assert review.id == same_review.id
    assert review.return_pct == 40.0
    assert review.outcome_quality == "strong_profit"
    assert review.decision_quality == "supported"
    assert "thesis_review" not in review.thesis_review_json

    candidates = db_session.query(StrategyLearningCandidate).filter_by(trade_review_id=review.id).all()
    assert len(candidates) == 1
    assert candidates[0].target_layer == "P8"
    assert candidates[0].status == "proposed"
    assert candidates[0].requires_human_approval is True
    assert candidates[0].applied_at is None


def test_trade_review_invalidated_thesis_creates_p9_observation(db_session):
    stock = Stock(code="R12", name="Review Invalidated", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    position = open_position_from_execution(
        db_session,
        stock,
        entry_price=0.10,
        quantity=10_000,
        opened_at=datetime(2026, 9, 10, 10, 0),
    )
    position.thesis_status = "invalidated"
    position.risk_status = "critical"
    db_session.add(
        PositionEvent(
            position_id=position.id,
            stock_id=stock.id,
            event_time=datetime(2026, 9, 20, 10, 0),
            event_type="exit_review",
            action="exit",
            thesis_status="invalidated",
            risk_status="critical",
            reason="Thesis failure.",
        )
    )
    close_position(
        db_session,
        position,
        stock,
        exit_price=0.09,
        closed_at=datetime(2026, 9, 25, 10, 0),
        reason="Closed after thesis failure.",
    )

    review = create_trade_review_for_position(db_session, position, stock)

    assert review.decision_quality == "poor_or_invalidated"
    candidate = db_session.query(StrategyLearningCandidate).filter_by(trade_review_id=review.id).one()
    assert candidate.target_layer == "P9"
    assert candidate.candidate_type == "observation"


# --- tracing a trade back to the evidence behind it -------------------------

import json  # noqa: E402
from datetime import date  # noqa: E402

from app.models import AttentionState, FusionRecord  # noqa: E402


def _stock_with_state(db_session, code, level="L4", strength="strong"):
    stock = Stock(code=code, name=f"{code} Co", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    fusion = FusionRecord(
        stock_id=stock.id, fusion_date=date(2026, 9, 1), opportunity_strength=strength,
        confidence="high", signal_structure="confirmation", evidence_independence="high",
        official_result=strength, analytical_signal_ids_json="[]",
        rule_version="fusion_adapter_v1",
    )
    db_session.add(fusion)
    db_session.commit()
    state = AttentionState(
        stock_id=stock.id, fusion_record_id=fusion.id, state_level=level,
        state_label="Decision Ready", transition="promote", reason="test",
        compute_profile="manual", rule_version="attention_rules_v1",
    )
    db_session.add(state)
    db_session.commit()
    return stock, fusion, state


def test_entry_and_exit_record_the_state_standing_behind_them(db_session):
    """P10 reads these ids off the position's events, and entry and exit were
    the two event types that never wrote them -- so a trade held without a
    periodic review in between could not be traced to any evidence at all."""
    stock, fusion, state = _stock_with_state(db_session, "R20")

    position = open_position_from_execution(
        db_session, stock, entry_price=0.10, quantity=1_000,
        opened_at=datetime(2026, 9, 10, 10, 0),
    )
    close_position(db_session, position, stock, exit_price=0.12,
                   closed_at=datetime(2026, 10, 10, 10, 0), reason="closed")

    events = db_session.query(PositionEvent).filter_by(position_id=position.id).all()
    for event in events:
        evidence = json.loads(event.evidence_json)
        assert evidence["attention_state_id"] == state.id
        assert evidence["fusion_record_id"] == fusion.id


def test_the_review_names_both_ends_of_the_hold(db_session):
    """"Which evidence led me in, and had it changed by the time I left" is
    what a review exists to answer; a bag of ids cannot answer it."""
    stock, fusion, _ = _stock_with_state(db_session, "R21")
    position = open_position_from_execution(
        db_session, stock, entry_price=0.10, quantity=1_000,
        opened_at=datetime(2026, 9, 10, 10, 0),
    )
    close_position(db_session, position, stock, exit_price=0.12,
                   closed_at=datetime(2026, 10, 10, 10, 0), reason="closed")

    review = create_trade_review_for_position(db_session, position, stock)
    transition = json.loads(review.state_transition_review_json)

    assert transition["entry_state"]["attention_state_level"] == "L4"
    assert transition["entry_state"]["opportunity_strength"] == "strong"
    assert transition["exit_state"]["attention_state_level"] == "L4"
    assert transition["state_changed_during_hold"] is False
    assert "stayed at L4" in transition["assessment"]


def test_a_state_change_during_the_hold_is_reported(db_session):
    stock, _, state = _stock_with_state(db_session, "R22")
    position = open_position_from_execution(
        db_session, stock, entry_price=0.10, quantity=1_000,
        opened_at=datetime(2026, 9, 10, 10, 0),
    )
    # the engine steps the stock down while the position is held
    state.ended_at = datetime(2026, 9, 20)
    db_session.add(AttentionState(
        stock_id=stock.id, state_level="L2", state_label="Active Watch",
        transition="demote", reason="cooled", compute_profile="standard",
        rule_version="attention_rules_v1",
    ))
    db_session.commit()
    close_position(db_session, position, stock, exit_price=0.12,
                   closed_at=datetime(2026, 10, 10, 10, 0), reason="closed")

    review = create_trade_review_for_position(db_session, position, stock)
    transition = json.loads(review.state_transition_review_json)

    assert transition["state_changed_during_hold"] is True
    assert "L4 to L2" in transition["assessment"]


def test_a_position_with_no_state_behind_it_says_so(db_session):
    """Silence here would read as "the evidence was fine"."""
    stock = Stock(code="R23", name="No State", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    position = open_position_from_execution(
        db_session, stock, entry_price=0.10, quantity=1_000,
        opened_at=datetime(2026, 9, 10, 10, 0),
    )
    close_position(db_session, position, stock, exit_price=0.12,
                   closed_at=datetime(2026, 10, 10, 10, 0), reason="closed")

    review = create_trade_review_for_position(db_session, position, stock)
    transition = json.loads(review.state_transition_review_json)

    assert transition["entry_state"]["attention_state_id"] is None
    assert "cannot be traced" in transition["assessment"]
