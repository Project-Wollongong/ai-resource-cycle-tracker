from datetime import date, datetime

import pytest

from app.models import Announcement, PriceBar, ScoreSnapshot, Stock
from app.services.historical_input import build_historical_analysis_input
from app.services.historical_scoring import score_historical_analysis_input

from conftest import next_weekday


def add_stock(session, code="HSC", commodity="gold"):
    stock = Stock(code=code, name=f"{code} Ltd", commodity=commodity)
    session.add(stock)
    session.commit()
    return stock


def add_price_bars(session, stock, closes, volumes, start=date(2026, 6, 1)):
    dates = []
    d = start
    for close, volume in zip(closes, volumes):
        session.add(
            PriceBar(
                stock_id=stock.id,
                date=d,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=volume,
            )
        )
        dates.append(d)
        d = next_weekday(d)
    session.commit()
    return dates


def add_announcement(session, stock, ann_id, ann_date, type_score, ann_type="OTHER"):
    session.add(
        Announcement(
            stock_id=stock.id,
            ann_id=ann_id,
            headline=f"{ann_id} update",
            ann_date=ann_date,
            url=f"https://example.test/{ann_id}",
            price_sensitive=False,
            ann_type=ann_type,
            type_score=type_score,
        )
    )
    session.commit()


def test_historical_scoring_uses_bounded_price_input(db_session):
    stock = add_stock(db_session)
    closes = [1.0] * 21 + [2.0]
    volumes = [100_000] * 21 + [1_000_000]
    dates = add_price_bars(db_session, stock, closes, volumes)

    payload = build_historical_analysis_input(db_session, stock, dates[20])
    result = score_historical_analysis_input(payload)

    assert result["status"] == "success"
    assert result["as_of"]["market_data_as_of"] == dates[20]
    assert result["input_summary"]["last_price_date"] == dates[20]
    assert result["components"]["funding"]["rel_vol"]["points"] == 0
    assert result["funding_score"] < 40


def test_historical_scoring_uses_bounded_announcement_input(db_session):
    stock = add_stock(db_session)
    dates = add_price_bars(db_session, stock, [1.0] * 21, [100_000] * 21)
    as_of = dates[-1]
    add_announcement(db_session, stock, "visible-low", datetime.combine(as_of, datetime.min.time()), 20)
    add_announcement(
        db_session,
        stock,
        "future-high",
        datetime.combine(next_weekday(as_of), datetime.min.time()),
        90,
        ann_type="DRILL_RESULTS",
    )

    payload = build_historical_analysis_input(db_session, stock, as_of)
    result = score_historical_analysis_input(payload)

    assert [row["ann_id"] for row in payload["announcements"]] == ["visible-low"]
    assert result["announcement_score"] == pytest.approx(20.0)
    assert result["components"]["announcement"]["announcements"][0]["ann_id"] == "visible-low"


def test_historical_scoring_does_not_persist_score_snapshot(db_session):
    stock = add_stock(db_session)
    dates = add_price_bars(db_session, stock, [1.0] * 21, [100_000] * 21)

    payload = build_historical_analysis_input(db_session, stock, dates[-1])
    score_historical_analysis_input(payload)

    assert db_session.query(ScoreSnapshot).count() == 0
