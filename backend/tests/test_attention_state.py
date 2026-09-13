import json
from datetime import date

from app.models import AttentionState, FusionRecord, Stock
from app.services.attention_state import update_attention_state_from_fusion


def make_fusion(
    db_session,
    stock_id: int,
    *,
    fusion_date=date(2026, 9, 10),
    strength="moderate",
    confidence="medium",
    independence="single_source",
    structure="single_signal",
    official=None,
    blockers=None,
):
    fusion = FusionRecord(
        stock_id=stock_id,
        fusion_date=fusion_date,
        opportunity_strength=strength,
        confidence=confidence,
        signal_structure=structure,
        evidence_independence=independence,
        official_result=official or strength,
        blocking_conditions_json=json.dumps(blockers or []),
        analytical_signal_ids_json="[]",
        rule_version=f"test_fusion_{fusion_date.isoformat()}",
    )
    db_session.add(fusion)
    db_session.commit()
    return fusion


def test_attention_state_promotes_to_l3_but_only_recommends_l4(db_session):
    stock = Stock(code="P7A", name="P7A Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    fusion = make_fusion(
        db_session,
        stock.id,
        strength="strong",
        confidence="high",
        independence="medium",
        structure="confirmation",
    )

    attention = update_attention_state_from_fusion(db_session, stock, fusion)

    assert attention.state_level == "L3"
    assert attention.transition == "upgrade"
    assert attention.alert_priority == "human_review"
    metadata = json.loads(attention.metadata_json)
    assert metadata["recommended_state"] == "L4"
    assert metadata["human_review_required"] is True


def test_attention_state_is_idempotent_for_same_fusion(db_session):
    stock = Stock(code="P7B", name="P7B Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    fusion = make_fusion(db_session, stock.id, strength="moderate", structure="confirmation")

    first = update_attention_state_from_fusion(db_session, stock, fusion)
    second = update_attention_state_from_fusion(db_session, stock, fusion)

    assert first.id == second.id
    assert db_session.query(AttentionState).filter_by(stock_id=stock.id).count() == 1


def test_attention_state_hysteresis_holds_l3_on_moderate_pullback(db_session):
    stock = Stock(code="P7C", name="P7C Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    first_fusion = make_fusion(
        db_session,
        stock.id,
        fusion_date=date(2026, 9, 10),
        strength="strong",
        confidence="high",
        independence="medium",
        structure="confirmation",
    )
    update_attention_state_from_fusion(db_session, stock, first_fusion)

    second_fusion = make_fusion(
        db_session,
        stock.id,
        fusion_date=date(2026, 9, 11),
        strength="moderate",
        confidence="medium",
        independence="single_source",
        structure="confirmation",
    )
    attention = update_attention_state_from_fusion(db_session, stock, second_fusion)

    assert attention.state_level == "L3"
    assert attention.transition == "hold"
    assert db_session.query(AttentionState).filter_by(stock_id=stock.id, ended_at=None).count() == 1


def test_attention_state_manual_lock_blocks_automatic_transition(db_session):
    stock = Stock(code="P7D", name="P7D Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    locked = AttentionState(
        stock_id=stock.id,
        state_level="L2",
        state_label="Active Watch",
        transition="hold",
        manual_lock=True,
        compute_profile="enhanced_monitoring",
        rule_version="attention_rules_v1",
    )
    db_session.add(locked)
    db_session.commit()

    fusion = make_fusion(
        db_session,
        stock.id,
        strength="strong",
        confidence="high",
        independence="medium",
        structure="confirmation",
    )
    attention = update_attention_state_from_fusion(db_session, stock, fusion)

    assert attention.id == locked.id
    assert attention.state_level == "L2"
    assert attention.manual_lock is True
