from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import settings
from app.models import PriceBar, Stock
from app.services import pipeline
from app.services.startup_refresh import expected_latest_price_date, should_refresh_on_startup


def test_expected_latest_price_date_rolls_weekend_back_to_friday(monkeypatch):
    monkeypatch.setattr(settings, "schedule_hour", 18)
    monkeypatch.setattr(settings, "schedule_minute", 30)
    tz = ZoneInfo("Australia/Sydney")

    result = expected_latest_price_date(datetime(2026, 9, 6, 19, 30, tzinfo=tz))

    assert result == date(2026, 9, 4)


def test_expected_latest_price_date_uses_previous_weekday_before_cutoff(monkeypatch):
    monkeypatch.setattr(settings, "schedule_hour", 18)
    monkeypatch.setattr(settings, "schedule_minute", 30)
    tz = ZoneInfo("Australia/Sydney")

    result = expected_latest_price_date(datetime(2026, 9, 7, 9, 0, tzinfo=tz))

    assert result == date(2026, 9, 4)


def test_expected_latest_price_date_uses_today_after_cutoff(monkeypatch):
    monkeypatch.setattr(settings, "schedule_hour", 18)
    monkeypatch.setattr(settings, "schedule_minute", 30)
    tz = ZoneInfo("Australia/Sydney")

    result = expected_latest_price_date(datetime(2026, 9, 7, 19, 0, tzinfo=tz))

    assert result == date(2026, 9, 7)


def test_should_refresh_on_startup_when_price_bars_are_stale(db_session, monkeypatch):
    monkeypatch.setattr(settings, "schedule_hour", 18)
    monkeypatch.setattr(settings, "schedule_minute", 30)
    stock = Stock(code="A1M", name="AIC Mines", commodity="copper")
    db_session.add(stock)
    db_session.commit()
    db_session.add(
        PriceBar(
            stock_id=stock.id,
            date=date(2026, 8, 25),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=100_000,
        )
    )
    db_session.commit()

    decision = should_refresh_on_startup(
        db_session,
        datetime(2026, 9, 6, 19, 30, tzinfo=ZoneInfo("Australia/Sydney")),
    )

    assert decision.should_refresh is True
    assert decision.last_price_date == date(2026, 8, 25)
    assert decision.expected_price_date == date(2026, 9, 4)
    assert decision.reason == "stale_price_bars"


def test_should_refresh_on_startup_skips_when_price_bars_are_fresh(db_session):
    stock = Stock(code="A1M", name="AIC Mines", commodity="copper")
    db_session.add(stock)
    db_session.commit()
    db_session.add(
        PriceBar(
            stock_id=stock.id,
            date=date(2026, 9, 4),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=100_000,
        )
    )
    db_session.commit()

    decision = should_refresh_on_startup(
        db_session,
        datetime(2026, 9, 6, 19, 30, tzinfo=ZoneInfo("Australia/Sydney")),
    )

    assert decision.should_refresh is False
    assert decision.reason == "fresh_price_bars"


def test_run_daily_pipeline_skips_when_another_run_is_active():
    assert pipeline._pipeline_lock.acquire(blocking=False)
    try:
        result = pipeline.run_daily_pipeline(trigger="test")
    finally:
        pipeline._pipeline_lock.release()

    assert result == {
        "skipped": True,
        "reason": "pipeline_already_running",
        "trigger": "test",
    }
