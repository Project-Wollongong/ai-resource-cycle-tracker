"""Background startup refresh for stale local market data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from threading import Thread

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import market_tz, settings
from ..database import SessionLocal
from ..models import PriceBar
from .pipeline import run_daily_pipeline

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StartupRefreshDecision:
    should_refresh: bool
    last_price_date: date | None
    expected_price_date: date
    reason: str


def expected_latest_price_date(now: datetime | None = None) -> date:
    """Return the latest daily bar date the app should expect locally."""

    tz = market_tz()
    local_now = now.astimezone(tz) if now and now.tzinfo else (now or datetime.now(tz))
    today = local_now.date()
    cutoff = time(settings.schedule_hour, settings.schedule_minute)
    if today.weekday() < 5 and local_now.time() >= cutoff:
        return today
    return _previous_weekday(today)


def should_refresh_on_startup(session: Session, now: datetime | None = None) -> StartupRefreshDecision:
    last_price_date: date | None = session.query(func.max(PriceBar.date)).scalar()
    expected_date = expected_latest_price_date(now)
    if last_price_date is None:
        return StartupRefreshDecision(True, None, expected_date, "no_price_bars")
    if last_price_date < expected_date:
        return StartupRefreshDecision(True, last_price_date, expected_date, "stale_price_bars")
    return StartupRefreshDecision(False, last_price_date, expected_date, "fresh_price_bars")


def start_startup_refresh() -> Thread | None:
    if not settings.enable_startup_refresh:
        logger.info("startup refresh disabled")
        return None

    thread = Thread(target=_startup_refresh_task, name="startup-refresh", daemon=True)
    thread.start()
    return thread


def _startup_refresh_task() -> None:
    try:
        with SessionLocal() as session:
            decision = should_refresh_on_startup(session)
        if not decision.should_refresh:
            logger.info(
                "startup refresh skipped: latest price bar %s, expected %s",
                decision.last_price_date,
                decision.expected_price_date,
            )
            return

        logger.info(
            "startup refresh running: %s, latest price bar %s, expected %s",
            decision.reason,
            decision.last_price_date,
            decision.expected_price_date,
        )
        stats = run_daily_pipeline(trigger="startup")
        logger.info(
            "startup refresh finished: errors=%s prices_added=%s report_date=%s skipped=%s",
            stats.get("errors"),
            stats.get("prices_added"),
            stats.get("report_date"),
            stats.get("skipped"),
        )
    except Exception:
        logger.exception("startup refresh failed")


def _previous_weekday(d: date) -> date:
    d = d - timedelta(days=1)
    while d.weekday() >= 5:
        d = d - timedelta(days=1)
    return d
