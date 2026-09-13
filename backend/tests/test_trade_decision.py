import json
from datetime import date

from app.models import AttentionState, FusionRecord, PriceBar, Stock, TradeDecision
from app.services.trade_decision import write_trade_decision_from_state


def make_stock(db_session):
    stock = Stock(code="P8A", name="P8A Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    db_session.add(
        PriceBar(
            stock_id=stock.id,
            date=date(2026, 9, 10),
            open=0.1,
            high=0.12,
            low=0.095,
            close=0.11,
            volume=1_000_000,
        )
    )
    db_session.commit()
    return stock


def make_fusion(
    db_session,
    stock_id: int,
    *,
    strength="strong",
    confidence="high",
    independence="medium",
    structure="confirmation",
    official=None,
    blockers=None,
    overheating="low",
):
    fusion = FusionRecord(
        stock_id=stock_id,
        fusion_date=date(2026, 9, 10),
        opportunity_strength=strength,
        confidence=confidence,
        signal_structure=structure,
        evidence_independence=independence,
        official_result=official or strength,
        blocking_conditions_json=json.dumps(blockers or []),
        conflicts_json="[]",
        overheating_risk=overheating,
        analytical_signal_ids_json="[]",
        rule_version="test_fusion",
    )
    db_session.add(fusion)
    db_session.commit()
    return fusion


def make_attention(db_session, stock_id: int, fusion_id: int, level: str, metadata=None):
    labels = {
        "L1": "Watch",
        "L2": "Active Watch",
        "L3": "Investigation",
        "L4": "Decision Ready",
    }
    attention = AttentionState(
        stock_id=stock_id,
        fusion_record_id=fusion_id,
        state_level=level,
        state_label=labels[level],
        transition="hold",
        rule_version="attention_rules_v1",
        metadata_json=json.dumps(metadata or {}),
    )
    db_session.add(attention)
    db_session.commit()
    return attention


def test_l3_with_l4_recommendation_still_waits_for_human_confirmation(db_session):
    stock = make_stock(db_session)
    fusion = make_fusion(db_session, stock.id)
    attention = make_attention(
        db_session,
        stock.id,
        fusion.id,
        "L3",
        {"recommended_state": "L4", "human_review_required": True},
    )

    decision = write_trade_decision_from_state(db_session, stock, fusion, attention)

    assert decision.decision == "wait"
    assert decision.action == "none"
    assert decision.conviction == "medium"
    assert "L4 is recommended" in decision.reason
    metadata = json.loads(decision.metadata_json)
    assert metadata["requires_user_confirmation"] is False


def test_l4_strong_opportunity_creates_starter_buy_package(db_session):
    stock = make_stock(db_session)
    fusion = make_fusion(db_session, stock.id, strength="strong", confidence="high")
    attention = make_attention(db_session, stock.id, fusion.id, "L4")

    decision = write_trade_decision_from_state(db_session, stock, fusion, attention)

    assert decision.decision == "act"
    assert decision.action == "starter_buy"
    assert decision.conviction == "medium"
    assert json.loads(decision.entry_range_json)["reference_price"] == 0.11
    assert json.loads(decision.position_size_json)["requires_user_confirmation"] is True


def test_l4_exceptional_high_confidence_can_create_buy_package(db_session):
    stock = make_stock(db_session)
    fusion = make_fusion(
        db_session,
        stock.id,
        strength="exceptional",
        confidence="high",
        independence="high",
    )
    attention = make_attention(db_session, stock.id, fusion.id, "L4")

    decision = write_trade_decision_from_state(db_session, stock, fusion, attention)

    assert decision.decision == "act"
    assert decision.action == "buy"
    assert decision.conviction == "high"
    assert json.loads(decision.entry_range_json)["acceptable_now"] is True


def test_blocking_conditions_force_pass_even_if_attention_is_l4(db_session):
    stock = make_stock(db_session)
    fusion = make_fusion(db_session, stock.id, official="blocked", blockers=["risk_score_below_30"])
    attention = make_attention(db_session, stock.id, fusion.id, "L4")

    decision = write_trade_decision_from_state(db_session, stock, fusion, attention)

    assert decision.decision == "pass"
    assert decision.action == "none"
    assert "risk_score_below_30" in json.loads(decision.key_risks_json)


def test_trade_decision_is_idempotent_for_same_stock_date_rule(db_session):
    stock = make_stock(db_session)
    fusion = make_fusion(db_session, stock.id)
    attention = make_attention(db_session, stock.id, fusion.id, "L3")

    first = write_trade_decision_from_state(db_session, stock, fusion, attention)
    second = write_trade_decision_from_state(db_session, stock, fusion, attention)

    assert first.id == second.id
    assert db_session.query(TradeDecision).filter_by(stock_id=stock.id).count() == 1
