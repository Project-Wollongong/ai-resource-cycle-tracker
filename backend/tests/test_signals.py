from datetime import date

from app.analysis.indicators import compute_indicators
from app.analysis.signals import (
    AnnouncementEvent,
    SignalCandidate,
    assign_event_roles,
    detect_announcement_signal,
    detect_price_signals,
    detect_score_cross,
)
from app.models import Signal, SignalReturn, Stock
from app.services.config_service import DEFAULTS
from app.services.signal_service import persist_signals

from conftest import make_bars

THRESH = DEFAULTS["signal_thresholds"]


def ind_for(closes, volumes):
    return compute_indicators(make_bars(closes, volumes))


def types_of(candidates):
    return [c.signal_type for c in candidates]


# ---------- REL_VOL_SPIKE ----------

def test_rel_vol_spike_triggers_on_up_day():
    ind = ind_for([1.0] * 20 + [1.08], [100_000] * 20 + [400_000])
    cands = detect_price_signals(ind, THRESH)
    assert "REL_VOL_SPIKE" in types_of(cands)
    spike = next(c for c in cands if c.signal_type == "REL_VOL_SPIKE")
    assert spike.evidence["rel_vol" ] == 4.0
    assert "4.0x" in spike.reason


def test_rel_vol_spike_blocked_on_down_day():
    # 6x volume, -5% day: distribution — must NOT signal
    ind = ind_for([1.0] * 20 + [0.95], [100_000] * 20 + [600_000])
    assert "REL_VOL_SPIKE" not in types_of(detect_price_signals(ind, THRESH))


def test_rel_vol_spike_blocked_on_flat_day():
    ind = ind_for([1.0] * 20 + [1.0], [100_000] * 20 + [600_000])
    assert "REL_VOL_SPIKE" not in types_of(detect_price_signals(ind, THRESH))


def test_rel_vol_spike_blocked_below_liquidity_floor():
    # 10x rel_vol but ~A$12k turnover
    ind = ind_for([0.01] * 20 + [0.012], [100_000] * 20 + [1_000_000])
    assert detect_price_signals(ind, THRESH) == []


def test_rel_vol_spike_below_threshold():
    ind = ind_for([1.0] * 20 + [1.08], [100_000] * 20 + [290_000])
    assert "REL_VOL_SPIKE" not in types_of(detect_price_signals(ind, THRESH))


# ---------- breakouts ----------

def test_breakout_60_requires_volume_confirmation():
    closes = [1.0] * 60 + [1.2]
    confirmed = detect_price_signals(ind_for(closes, [100_000] * 60 + [160_000]), THRESH)
    unconfirmed = detect_price_signals(ind_for(closes, [100_000] * 60 + [140_000]), THRESH)
    assert "BREAKOUT_60D" in types_of(confirmed)
    assert "BREAKOUT_60D" not in types_of(unconfirmed)


def test_breakout_252_suppresses_60():
    ind = ind_for([1.0] * 252 + [1.5], [100_000] * 252 + [200_000])
    types = types_of(detect_price_signals(ind, THRESH))
    assert "BREAKOUT_252D" in types
    assert "BREAKOUT_60D" not in types


# ---------- KEY_ANNOUNCEMENT ----------

def ann_event(ann_type, score, ps=False, ann_id="a1"):
    return AnnouncementEvent(
        ann_id=ann_id, headline=f"{ann_type} headline", ann_type=ann_type,
        type_score=score, price_sensitive=ps,
    )


def test_key_announcement_triggers_on_drill_results():
    cand = detect_announcement_signal([ann_event("DRILL_RESULTS", 85)], THRESH)
    assert cand is not None
    assert cand.signal_type == "KEY_ANNOUNCEMENT"
    assert cand.evidence["announcements"][0]["type"] == "DRILL_RESULTS"


def test_key_announcement_excludes_placement_and_halt_unconditionally():
    # even price-sensitive: a raise is dilution, a halt is only "something coming"
    assert detect_announcement_signal([ann_event("PLACEMENT", 50, ps=True)], THRESH) is None
    assert detect_announcement_signal([ann_event("TRADING_HALT", 55, ps=True)], THRESH) is None


def test_key_announcement_ignores_low_score_noise():
    assert detect_announcement_signal([ann_event("QUARTERLY", 40, ps=True)], THRESH) is None
    assert detect_announcement_signal([ann_event("OTHER", 20)], THRESH) is None


def test_key_announcement_bundles_same_day_hits():
    cand = detect_announcement_signal(
        [ann_event("JORC_MRE", 90, ann_id="a1"), ann_event("DRILL_RESULTS", 85, ann_id="a2")],
        THRESH,
    )
    assert len(cand.evidence["announcements"]) == 2
    assert cand.reason.startswith("JORC_MRE")  # strongest first


# ---------- SCORE_CROSS_UP ----------

def test_score_cross_up():
    assert detect_score_cross(74.9, 75.0, THRESH) is not None
    assert detect_score_cross(74.9, 74.9, THRESH) is None
    assert detect_score_cross(76.0, 80.0, THRESH) is None  # already above
    assert detect_score_cross(None, 90.0, THRESH) is None  # first snapshot


# ---------- persistence ----------

def test_persist_signals_idempotent_and_creates_pending_returns(db_session):
    stock = Stock(code="TST", name="Test", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    ind = ind_for([1.0] * 20 + [1.08], [100_000] * 20 + [400_000])
    cands = detect_price_signals(ind, THRESH)
    sig_date = date(2026, 6, 30)

    added = persist_signals(
        db_session, stock, sig_date, cands, price_at_signal=1.08,
        source="live", label="Watch Closely", cycle_score=65.0,
    )
    assert added == len(cands) == 1
    added_again = persist_signals(
        db_session, stock, sig_date, cands, price_at_signal=1.08,
        source="live", label="Watch Closely", cycle_score=65.0,
    )
    assert added_again == 0  # rerun is a no-op

    signal = db_session.query(Signal).one()
    assert signal.label == "Watch Closely"
    returns = db_session.query(SignalReturn).filter_by(signal_id=signal.id).all()
    assert sorted(r.horizon_days for r in returns) == [5, 20, 60, 120]
    assert all(r.status == "pending" for r in returns)


def test_persist_replay_signals_carry_no_label_or_score(db_session):
    stock = Stock(code="RPL", name="Replay", commodity="copper")
    db_session.add(stock)
    db_session.commit()

    ind = ind_for([1.0] * 20 + [1.08], [100_000] * 20 + [400_000])
    cands = detect_price_signals(ind, THRESH)
    persist_signals(
        db_session, stock, date(2025, 3, 4), cands, price_at_signal=1.08,
        source="replay", label="High Priority", cycle_score=90.0,  # must be discarded
    )
    signal = db_session.query(Signal).one()
    assert signal.source == "replay"
    assert signal.label is None
    assert signal.cycle_score_at_signal is None


def test_assign_event_roles_marks_one_primary_per_mechanism():
    """A breakout already requires 1.5x volume, so a breakout plus a volume
    spike on one day is one price-action event, not two confirmations."""
    breakout = SignalCandidate("BREAKOUT_60D", reason="", evidence={})
    volume = SignalCandidate("REL_VOL_SPIKE", reason="", evidence={})
    announcement = SignalCandidate("KEY_ANNOUNCEMENT", reason="", evidence={})

    roles = {
        cand.signal_type: (mechanism, role)
        for cand, mechanism, role in assign_event_roles([volume, breakout, announcement])
    }

    assert roles["BREAKOUT_60D"] == ("price_action", "primary")
    assert roles["REL_VOL_SPIKE"] == ("price_action", "secondary")
    # a different causal mechanism is its own event and stays primary
    assert roles["KEY_ANNOUNCEMENT"] == ("announcement", "primary")


def test_assign_event_roles_prefers_the_longer_breakout_window():
    roles = {
        cand.signal_type: role
        for cand, _, role in assign_event_roles([
            SignalCandidate("REL_VOL_SPIKE", reason="", evidence={}),
            SignalCandidate("BREAKOUT_252D", reason="", evidence={}),
        ])
    }
    assert roles["BREAKOUT_252D"] == "primary"
    assert roles["REL_VOL_SPIKE"] == "secondary"


def test_breakout_252d_is_graded_watch_only():
    """The backtest measured it negative past +5d, so it must not count as
    confirmation. It still fires — it is an attention flag, not an entry."""
    from app.analysis.signals import SIGNAL_EVIDENCE_NOTE, is_confirming, signal_grade

    assert signal_grade("BREAKOUT_252D") == "watch_only"
    assert is_confirming("BREAKOUT_252D") is False
    assert "BREAKOUT_252D" in SIGNAL_EVIDENCE_NOTE

    # everything else keeps its default grade
    for signal_type in ("BREAKOUT_60D", "REL_VOL_SPIKE", "KEY_ANNOUNCEMENT"):
        assert is_confirming(signal_type) is True, signal_type


def test_watch_only_signal_is_still_detected_and_persisted(db_session):
    """Downgrading must not delete evidence: the rule keeps firing."""
    stock = Stock(code="WO1", name="Watch Only", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    candidates = [SignalCandidate("BREAKOUT_252D", reason="new 252d high", evidence={})]
    added = persist_signals(
        db_session, stock, date(2026, 3, 2), candidates, price_at_signal=1.0
    )

    assert added == 1
    row = db_session.query(Signal).filter_by(stock_id=stock.id).one()
    assert row.signal_type == "BREAKOUT_252D"
    assert row.role == "primary"
