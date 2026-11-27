"""Human control of the attention state, and what it unlocks below."""
import json
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import attention as attention_routes
from app.api.security import require_admin_access
from app.models import AttentionState, FusionRecord, PriceBar, Stock, TradeDecision
from app.services.attention_override import (
    AttentionOverrideError,
    clear_attention_override,
    set_attention_state,
)
from app.services.attention_state import update_attention_state_from_fusion

AS_OF = date(2026, 11, 27)


@pytest.fixture
def stock(db_session):
    row = Stock(code="ATT", name="Attention Co", commodity="gold")
    db_session.add(row)
    db_session.commit()
    db_session.add(PriceBar(stock_id=row.id, date=AS_OF, open=1.0, high=1.0,
                            low=1.0, close=1.0, volume=1000))
    db_session.commit()
    return row


def fusion(db_session, stock, strength="weak", **kwargs):
    row = FusionRecord(
        stock_id=stock.id, fusion_date=AS_OF, opportunity_strength=strength,
        confidence=kwargs.get("confidence", "medium"),
        signal_structure="single_signal", evidence_independence="single_source",
        official_result=strength, blocking_conditions_json="[]", conflicts_json="[]",
        overheating_risk=kwargs.get("overheating_risk"),
        analytical_signal_ids_json="[]", rule_version="fusion_adapter_v1",
    )
    db_session.add(row)
    db_session.commit()
    return row


def current(db_session, stock):
    return (db_session.query(AttentionState)
            .filter_by(stock_id=stock.id, ended_at=None)
            .order_by(AttentionState.id.desc()).first())


# --- the promotion itself ---------------------------------------------------

def test_a_person_can_take_the_step_the_engine_reserves_for_them(db_session, stock):
    """P07 never promotes to Decision Ready on its own. Until now there was no
    way for anyone else to either, so the reservation was a dead end."""
    fusion(db_session, stock)

    state = set_attention_state(db_session, stock, "L4", actor="Rachel", note="补充尽调后确认")

    assert state.state_level == "L4"
    assert state.manual_override is True
    assert "Rachel" in state.reason


def test_the_promotion_recomputes_the_trade_decision_in_the_same_call(db_session, stock):
    """A decision read from a state that has just moved is stale. Waiting for
    the next pipeline run would make the promotion look like it did nothing."""
    fusion(db_session, stock)

    set_attention_state(db_session, stock, "L4", actor="Rachel")

    decision = db_session.query(TradeDecision).filter_by(stock_id=stock.id).one()
    assert decision.decision == "act"
    assert decision.action in {"buy", "starter_buy"}


def test_overheating_still_holds_the_decision_back_at_l4(db_session, stock):
    """The human controls the attention state, not the decision rules."""
    fusion(db_session, stock, overheating_risk="high")

    set_attention_state(db_session, stock, "L4", actor="Rachel")

    decision = db_session.query(TradeDecision).filter_by(stock_id=stock.id).one()
    assert decision.decision == "wait"


def test_the_record_says_what_the_engine_had_concluded(db_session, stock):
    record = fusion(db_session, stock)
    update_attention_state_from_fusion(db_session, stock, record)
    engine_level = current(db_session, stock).state_level

    state = set_attention_state(db_session, stock, "L4", actor="Rachel")

    metadata = json.loads(state.metadata_json)
    assert metadata["engine_state_at_override"] == engine_level
    assert metadata["set_by"] == "Rachel"


def test_an_override_must_name_who_made_it(db_session, stock):
    fusion(db_session, stock)

    with pytest.raises(AttentionOverrideError, match="who made it"):
        set_attention_state(db_session, stock, "L4", actor="  ")


def test_an_unknown_level_is_refused(db_session, stock):
    fusion(db_session, stock)

    with pytest.raises(AttentionOverrideError, match="unknown attention level"):
        set_attention_state(db_session, stock, "L9", actor="Rachel")


# --- the engine must not undo it --------------------------------------------

def test_the_engine_leaves_a_held_state_where_the_person_put_it(db_session, stock):
    set_attention_state(db_session, stock, "L4", actor="Rachel")

    update_attention_state_from_fusion(db_session, stock, fusion(db_session, stock, "none"))

    assert current(db_session, stock).state_level == "L4"


def test_a_held_state_keeps_the_person_s_reason(db_session, stock):
    """Re-running the engine's text over it erased why the state was set,
    leaving a level nobody could account for."""
    set_attention_state(db_session, stock, "L4", actor="Rachel", note="尽调已完成")

    update_attention_state_from_fusion(db_session, stock, fusion(db_session, stock, "none"))

    assert "Rachel" in current(db_session, stock).reason
    assert "尽调已完成" in current(db_session, stock).reason


def test_a_held_state_records_what_the_engine_would_now_say(db_session, stock):
    """"You pinned L4; it now reads L1" is the comparison worth having."""
    set_attention_state(db_session, stock, "L4", actor="Rachel")

    update_attention_state_from_fusion(db_session, stock, fusion(db_session, stock, "none"))

    metadata = json.loads(current(db_session, stock).metadata_json)
    assert metadata["engine_would_be"] == "L1"


# --- releasing it -----------------------------------------------------------

def test_releasing_hands_the_state_back_without_inventing_a_transition(db_session, stock):
    set_attention_state(db_session, stock, "L4", actor="Rachel")

    released = clear_attention_override(db_session, stock, actor="Rachel")

    assert released.manual_override is False
    assert released.state_level == "L4"  # the engine moves it on the next fusion, not now
    assert "released by Rachel" in released.reason


def test_the_engine_resumes_once_the_override_is_released(db_session, stock):
    """It resumes, but it steps down rather than collapsing: hysteresis takes
    a released L4 to L3 first, so one weak day cannot undo a promotion."""
    set_attention_state(db_session, stock, "L4", actor="Rachel")
    clear_attention_override(db_session, stock, actor="Rachel")

    update_attention_state_from_fusion(db_session, stock, fusion(db_session, stock, "none"))
    assert current(db_session, stock).state_level == "L3"

    update_attention_state_from_fusion(db_session, stock, fusion(db_session, stock, "none"))
    assert current(db_session, stock).state_level == "L2"


def test_releasing_a_state_nobody_held_is_refused(db_session, stock):
    update_attention_state_from_fusion(db_session, stock, fusion(db_session, stock))

    with pytest.raises(AttentionOverrideError, match="not under a manual override"):
        clear_attention_override(db_session, stock, actor="Rachel")


# --- the route --------------------------------------------------------------

def _client(db_session, admin=True):
    app = FastAPI()
    app.include_router(attention_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    if admin:
        app.dependency_overrides[require_admin_access] = lambda: True
    return TestClient(app, raise_server_exceptions=False)


def test_the_route_promotes_and_returns_the_resulting_decision(db_session, stock):
    fusion(db_session, stock)
    client = _client(db_session)

    response = client.put("/api/attention/ATT",
                          json={"level": "L4", "actor": "Rachel", "note": "ok"})

    assert response.status_code == 200
    body = response.json()
    assert body["state_level"] == "L4"
    assert body["manual_override"] is True
    assert body["trade_decision"]["decision"] == "act"


def test_the_route_refuses_an_unknown_level_with_a_readable_message(db_session, stock):
    fusion(db_session, stock)

    response = _client(db_session).put("/api/attention/ATT",
                                       json={"level": "L9", "actor": "Rachel"})

    assert response.status_code == 422
    assert "unknown attention level" in response.json()["detail"]


def test_an_unknown_code_is_a_404_not_a_crash(db_session):
    response = _client(db_session).get("/api/attention/NOPE")

    assert response.status_code == 404


def test_moving_the_state_requires_admin_access(db_session, stock):
    fusion(db_session, stock)

    response = _client(db_session, admin=False).put(
        "/api/attention/ATT", json={"level": "L4", "actor": "Rachel"}
    )

    assert response.status_code in {401, 403}


def test_reading_the_state_does_not_require_admin_access(db_session, stock):
    update_attention_state_from_fusion(db_session, stock, fusion(db_session, stock))

    response = _client(db_session, admin=False).get("/api/attention/ATT")

    assert response.status_code == 200
    assert response.json()["state_level"] in {"L1", "L2"}


def test_the_levels_route_publishes_the_ladder(db_session):
    body = _client(db_session).get("/api/attention/levels").json()

    assert [item["level"] for item in body["levels"]] == ["L0", "L1", "L2", "L3", "L4", "L5"]
