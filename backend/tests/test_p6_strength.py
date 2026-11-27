"""What the fusion layer counts as a strong case, and what it refuses to."""
from datetime import date

import pytest

from app.models import AnalyticalSignal, Stock
from app.services.p5_p6_adapter import _opportunity_strength

AS_OF = date(2026, 11, 27)


@pytest.fixture
def stock(db_session):
    row = Stock(code="FUS", name="Fusion Co", commodity="gold")
    db_session.add(row)
    db_session.commit()
    return row


def signals(db_session, stock, *specs):
    """specs are (engine, direction, magnitude, dependency_group)."""
    rows = [
        AnalyticalSignal(stock_id=stock.id, signal_date=AS_OF, engine=engine,
                         direction=direction, magnitude=magnitude,
                         dependency_group=group)
        for engine, direction, magnitude, group in specs
    ]
    db_session.add_all(rows)
    db_session.commit()
    return [row.id for row in rows]


def test_no_positive_reading_is_no_opportunity(db_session, stock):
    ids = signals(db_session, stock, ("technical", "negative", 0.75, "price_action:x"))

    strength, basis = _opportunity_strength(db_session, ids)

    assert strength == "none"
    assert basis["engines_negative"] == ["technical"]


def test_one_source_cannot_be_strong_however_loud(db_session, stock):
    """Seven lenses agreeing on one day of price action are one source. Counting
    the rows instead would let a single engine present itself as agreement."""
    ids = signals(
        db_session, stock,
        ("technical", "positive", 1.0, "price_action:x"),
        ("technical", "positive", 1.0, "price_action:x"),
        ("technical", "positive", 1.0, "price_action:x"),
    )

    strength, basis = _opportunity_strength(db_session, ids)

    assert strength == "weak"
    assert basis["positive_sources"] == 1


def test_two_independent_sources_with_real_magnitude_read_as_strong(db_session, stock):
    ids = signals(
        db_session, stock,
        ("technical", "positive", 0.75, "price_action:x"),
        ("catalyst", "positive", 0.5, "announcement_event:x:resource"),
    )

    assert _opportunity_strength(db_session, ids)[0] == "strong"


def test_three_independent_sources_at_high_magnitude_read_as_exceptional(db_session, stock):
    ids = signals(
        db_session, stock,
        ("technical", "positive", 0.75, "price_action:x"),
        ("catalyst", "positive", 0.75, "announcement_event:x:resource"),
        ("fundamental", "positive", 0.9, "project_progress:x"),
    )

    assert _opportunity_strength(db_session, ids)[0] == "exceptional"


def test_a_neutral_reading_contributes_nothing(db_session, stock):
    """A 252-day high is recorded neutral because the backtest measured it at
    -29.78% excess; it must not become the second source that lifts a case."""
    ids = signals(
        db_session, stock,
        ("catalyst", "positive", 0.75, "announcement_event:x:resource"),
        ("technical", "neutral", 1.0, "price_action:x"),
    )

    strength, basis = _opportunity_strength(db_session, ids)

    assert strength == "weak"
    assert basis["positive_sources"] == 1


def test_an_equally_sourced_negative_case_caps_the_strength(db_session, stock):
    """Two engines pointing opposite ways is uncertainty, not conviction."""
    ids = signals(
        db_session, stock,
        ("technical", "positive", 0.75, "price_action:x"),
        ("catalyst", "positive", 0.75, "announcement_event:x:resource"),
        ("fundamental", "negative", 0.75, "project_progress:x"),
        ("catalyst", "negative", 0.75, "announcement_event:x:funding"),
    )

    strength, basis = _opportunity_strength(db_session, ids)

    assert strength == "weak"
    assert basis["cap_applied"] == "contradicted_by_equally_sourced_negative"


def test_a_single_contradicting_reading_caps_at_moderate(db_session, stock):
    ids = signals(
        db_session, stock,
        ("technical", "positive", 0.75, "price_action:x"),
        ("catalyst", "positive", 0.75, "announcement_event:x:resource"),
        ("fundamental", "positive", 0.9, "project_progress:x"),
        ("catalyst", "negative", 0.5, "announcement_event:x:funding"),
    )

    strength, basis = _opportunity_strength(db_session, ids)

    assert strength == "moderate"
    assert basis["cap_applied"] == "contradicted_by_a_negative_reading"


def test_the_verdict_no_longer_comes_from_the_cycle_score(db_session, stock):
    """The whole point: two engines agreeing outrank a low score, and a high
    score cannot carry a case no engine supports."""
    none_at_all = _opportunity_strength(db_session, [])[0]
    two_engines = _opportunity_strength(db_session, signals(
        db_session, stock,
        ("technical", "positive", 0.75, "price_action:x"),
        ("catalyst", "positive", 0.75, "announcement_event:x:resource"),
    ))[0]

    assert none_at_all == "none"
    assert two_engines == "strong"


# --- divergence must be visible, not merely capped ---------------------------

from app.models import ScoreSnapshot  # noqa: E402
from app.services.p5_p6_adapter import _conflicts  # noqa: E402


def _snapshot(stock):
    return ScoreSnapshot(stock_id=stock.id, date=AS_OF, funding_score=50,
                         announcement_score=50, resource_score=50, commodity_score=50,
                         risk_score=50, cycle_score=40, label="Ignore")


def test_engines_pointing_opposite_ways_are_reported_as_a_conflict(db_session, stock):
    """The strength was being capped for this while the record said there was
    no conflict, so the divergence was flattened with no explanation."""
    basis = {"engines_positive": ["catalyst"], "engines_negative": ["technical"]}

    found = _conflicts(db_session, [1], _snapshot(stock), [], basis)

    assert any(item.startswith("cross_engine_divergence") for item in found)
    assert "catalyst" in found[0] and "technical" in found[0]


def test_one_engine_disagreeing_with_itself_is_named_separately(db_session, stock):
    """A trend reading and an exhaustion reading from the same engine is an
    internal divergence, which is a different finding from two engines
    disagreeing with each other."""
    basis = {"engines_positive": ["technical"], "engines_negative": ["technical"]}

    found = _conflicts(db_session, [1], _snapshot(stock), [], basis)

    assert "engine_internal_divergence:technical" in found


def test_agreement_produces_no_divergence_entry(db_session, stock):
    basis = {"engines_positive": ["catalyst", "technical"], "engines_negative": []}

    found = _conflicts(db_session, [1], _snapshot(stock), [], basis)

    assert not any("divergence" in item for item in found)
