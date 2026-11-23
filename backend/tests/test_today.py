"""The daily briefing: what to raise, what to file, and what not to imply."""
import json
from datetime import date, datetime

from app.models import Announcement, P4Feature, PriceBar, ScoreSnapshot, Signal, Stock
from app.services.today_service import build_today

TODAY = date(2026, 10, 1)


def _stock(db_session, code, closes=((TODAY, 1.00), (date(2026, 9, 30), 1.00))):
    stock = Stock(code=code, name=f"{code} Ltd", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    for day, close in closes:
        db_session.add(
            PriceBar(stock_id=stock.id, date=day, open=close, high=close, low=close,
                     close=close, volume=1000)
        )
    db_session.commit()
    return stock


def _runway(db_session, stock, quarters, as_of=date(2026, 6, 30)):
    db_session.add(P4Feature(
        stock_id=stock.id, as_of_date=as_of, feature_group="funding",
        feature_name="cash_runway_quarters", formula_version="funding_runway_v1",
        value_json=json.dumps({"numeric": quarters}),
        evidence_json=json.dumps({"entity_reported_quarters": quarters, "source_pages": {}}),
        metadata_json=json.dumps({"below_asx_disclosure_threshold": quarters < 2}),
    ))
    db_session.commit()


def _find(board, code):
    return next((item for item in board["items"] if item["code"] == code), None)


def test_a_quiet_stock_is_listed_as_quiet_not_omitted(db_session):
    # Saying "26 others had nothing to report" is information; silently showing
    # three rows leaves the reader unsure whether the rest were even checked.
    _stock(db_session, "QUIET")

    board = build_today(db_session)

    assert _find(board, "QUIET") is None
    assert "QUIET" in board["quiet"]
    assert board["universe"] == 1


def test_a_standing_state_keeps_the_date_it_was_measured(db_session):
    """A cash position from June is not today's news, and must not look like it."""
    stock = _stock(db_session, "RUNWAY")
    _runway(db_session, stock, 3.08)

    reason = _find(db_session and build_today(db_session), "RUNWAY")["reasons"][0]

    assert reason["kind"] == "funding"
    assert reason["as_of"] == date(2026, 6, 30)
    assert reason["as_of"] != TODAY


def test_runway_under_two_quarters_outranks_a_shorter_one(db_session):
    critical = _stock(db_session, "CRIT")
    caution = _stock(db_session, "CAUT")
    _runway(db_session, critical, 1.4)
    _runway(db_session, caution, 3.0)

    board = build_today(db_session)

    assert _find(board, "CRIT")["top_level"] == "critical"
    assert _find(board, "CAUT")["top_level"] == "caution"
    # the louder item sorts first
    assert [item["code"] for item in board["items"]][0] == "CRIT"


def test_a_comfortable_runway_is_not_raised_at_all(db_session):
    stock = _stock(db_session, "FINE")
    _runway(db_session, stock, 8.0)

    assert _find(build_today(db_session), "FINE") is None


def test_a_signal_is_titled_by_what_actually_fired(db_session):
    # A substantial-holder notice is not a price-volume anomaly; titling it that
    # way would make the briefing describe something that did not happen.
    stock = _stock(db_session, "SIG")
    db_session.add(Signal(
        stock_id=stock.id, date=TODAY, signal_type="KEY_ANNOUNCEMENT", source="live",
        reason="SUBSTANTIAL_HOLDER: Becoming a substantial holder", evidence="{}",
        price_at_signal=1.0, role="primary",
    ))
    db_session.commit()

    reason = _find(build_today(db_session), "SIG")["reasons"][0]

    assert reason["title"] == "关键公告"
    assert reason["level"] == "watch"


def test_a_secondary_signal_annotates_rather_than_adds_a_reason(db_session):
    """A breakout already requires volume, so the two are one event seen twice."""
    stock = _stock(db_session, "DUP")
    for signal_type, role in (("BREAKOUT_60D", "primary"), ("REL_VOL_SPIKE", "secondary")):
        db_session.add(Signal(
            stock_id=stock.id, date=TODAY, signal_type=signal_type, source="live",
            reason=f"{signal_type} fired", evidence="{}", price_at_signal=1.0, role=role,
        ))
    db_session.commit()

    item = _find(build_today(db_session), "DUP")

    assert len(item["reasons"]) == 1
    assert item["reasons"][0]["evidence"]["secondary"] == ["REL_VOL_SPIKE"]


def test_a_watch_only_rule_is_marked_unconfirmed(db_session):
    # BREAKOUT_252D measured -29.78% excess past +5d; it still fires, but it
    # must not read as a confirmation.
    stock = _stock(db_session, "WO")
    db_session.add(Signal(
        stock_id=stock.id, date=TODAY, signal_type="BREAKOUT_252D", source="live",
        reason="New 252-day high", evidence="{}", price_at_signal=1.0, role="primary",
    ))
    db_session.commit()

    reason = _find(build_today(db_session), "WO")["reasons"][0]

    assert reason["level"] == "unconfirmed"
    assert "仅关注" in reason["title"]


def test_routine_announcements_are_filed_not_raised(db_session):
    """121 of the pilot's 145 announcements are governance filings; raising them
    would bury the few that matter."""
    stock = _stock(db_session, "NOISE")
    for ann_type in ("OTHER", "DRILL_RESULTS"):
        db_session.add(Announcement(
            stock_id=stock.id, ann_id=f"{ann_type}-1", headline=f"{ann_type} headline",
            ann_date=datetime(2026, 10, 1), ann_type=ann_type,
        ))
    db_session.commit()

    item = _find(build_today(db_session), "NOISE")

    titles = [reason["title"] for reason in item["reasons"]]
    assert titles == ["钻探结果"]


def test_yesterdays_announcement_is_not_reported_as_today(db_session):
    stock = _stock(db_session, "OLD")
    db_session.add(Announcement(
        stock_id=stock.id, ann_id="old-1", headline="Drilling", ann_date=datetime(2026, 9, 30),
        ann_type="DRILL_RESULTS",
    ))
    db_session.commit()

    assert _find(build_today(db_session), "OLD") is None


def test_scored_count_only_counts_todays_snapshots(db_session):
    stock = _stock(db_session, "SC")
    db_session.add(ScoreSnapshot(
        stock_id=stock.id, date=date(2026, 9, 30), funding_score=0, announcement_score=0,
        resource_score=50, commodity_score=50, risk_score=50, cycle_score=40, label="Ignore",
    ))
    db_session.commit()

    # a stale snapshot does not count as "scored today"
    assert build_today(db_session)["scored"] == 0


def test_empty_universe_does_not_fabricate_a_date(db_session):
    board = build_today(db_session)

    assert board["as_of"] is None
    assert board["items"] == []
