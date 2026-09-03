from datetime import date, datetime, time, timedelta

from app.models import Announcement, PriceBar, Stock
from app.services.historical_input import build_historical_analysis_input

from conftest import next_weekday


def add_stock(session, code="HST", commodity="gold"):
    stock = Stock(code=code, name=f"{code} Ltd", commodity=commodity)
    session.add(stock)
    session.commit()
    return stock


def add_price_bars(session, stock, closes, start=date(2026, 7, 2)):
    d = start
    for close in closes:
        session.add(
            PriceBar(
                stock_id=stock.id,
                date=d,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=100_000,
            )
        )
        d = next_weekday(d)
    session.commit()


def add_announcement(session, stock, ann_id, ann_date):
    session.add(
        Announcement(
            stock_id=stock.id,
            ann_id=ann_id,
            headline=f"{ann_id} update",
            ann_date=ann_date,
            url=f"https://example.test/{ann_id}",
            price_sensitive=False,
            ann_type="OTHER",
            type_score=20.0,
        )
    )
    session.commit()


def test_historical_input_excludes_price_bars_after_as_of_date(db_session):
    stock = add_stock(db_session)
    add_price_bars(db_session, stock, [1.0, 1.1, 1.2])

    payload = build_historical_analysis_input(db_session, stock, date(2026, 7, 4))

    assert [row["date"] for row in payload["price_bars"]] == [
        date(2026, 7, 2),
        date(2026, 7, 3),
    ]
    assert payload["latest_price"]["close"] == 1.1


def test_historical_input_excludes_announcements_after_as_of_date(db_session):
    stock = add_stock(db_session)
    add_price_bars(db_session, stock, [1.0, 1.1])
    add_announcement(db_session, stock, "before", datetime(2026, 7, 4, 10, 0))
    add_announcement(db_session, stock, "future", datetime(2026, 7, 5, 9, 0))

    payload = build_historical_analysis_input(db_session, stock, date(2026, 7, 4))

    assert [row["ann_id"] for row in payload["announcements"]] == ["before"]


def test_historical_input_rolls_weekend_back_to_latest_price_bar(db_session):
    stock = add_stock(db_session)
    add_price_bars(db_session, stock, [1.0, 1.1, 1.2])

    payload = build_historical_analysis_input(db_session, stock, date(2026, 7, 4))

    assert payload["as_of"]["as_of_date"] == date(2026, 7, 4)
    assert payload["as_of"]["market_data_as_of"] == date(2026, 7, 3)
    assert payload["input_summary"]["last_price_date"] == date(2026, 7, 3)
    assert any("rolled back to 2026-07-03" in item for item in payload["as_of"]["warnings"])


def test_historical_input_includes_end_of_day_announcement(db_session):
    stock = add_stock(db_session)
    add_price_bars(db_session, stock, [1.0, 1.1])
    add_announcement(db_session, stock, "end-of-day", datetime.combine(date(2026, 7, 4), time.max))
    add_announcement(
        db_session,
        stock,
        "next-microsecond",
        datetime.combine(date(2026, 7, 4), time.max) + timedelta(microseconds=1),
    )

    payload = build_historical_analysis_input(db_session, stock, date(2026, 7, 4))

    assert [row["ann_id"] for row in payload["announcements"]] == ["end-of-day"]
