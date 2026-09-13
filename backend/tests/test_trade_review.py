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
