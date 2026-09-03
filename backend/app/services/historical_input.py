"""Point-in-time input assembly for historical analysis.

This module only builds the bounded input package. It does not score, call AI,
or persist snapshots.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time, timedelta
import hashlib
import json
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..analysis.indicators import DailyBar, compute_indicators
from ..models import Announcement, CommodityBar, PriceBar, Signal, Stock
from .config_service import get_all_config

ANNOUNCEMENT_HISTORY_DAYS = 365


def build_historical_analysis_input(
    session: Session,
    stock: Stock,
    as_of_date: date,
    mode: str = "approximate",
) -> dict[str, Any]:
    """Return the data package visible at a historical date.

    Current storage does not have a universal available_at column, so this first
    version uses date/ann_date approximations and marks the boundary as
    approximate unless data is missing.
    """

    if mode not in {"strict", "approximate"}:
        raise ValueError(f"invalid historical input mode: {mode}")

    as_of_cutoff = datetime.combine(as_of_date, time.max)
    warnings = [
        "Using date/ann_date as available_at approximations; universal available_at is not implemented.",
        "Using current app_config because point-in-time config reconstruction is not implemented.",
    ]

    market_data_as_of = _resolve_market_data_as_of(session, stock, as_of_date)
    if market_data_as_of is None:
        boundary_status = "incomplete"
        warnings.append("No price bars exist on or before as_of_date.")
        price_bars = []
        indicators = None
    else:
        if market_data_as_of != as_of_date:
            warnings.append(
                f"as_of_date is not a stock trading day; market data rolled back to {market_data_as_of.isoformat()}."
            )
        price_bars = _load_price_bars(session, stock, market_data_as_of)
        indicators = compute_indicators(
            [
                DailyBar(
                    date=row["date"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                )
                for row in price_bars
            ]
        )
        boundary_status = "approximate"

    config = get_all_config(session)
    instrument = (config.get("commodity_instruments") or {}).get(stock.commodity)
    commodity_bars = (
        _load_commodity_bars(session, instrument, market_data_as_of)
        if instrument and market_data_as_of is not None
        else []
    )
    if not instrument:
        warnings.append(f"No commodity instrument configured for {stock.commodity}.")

    announcements = _load_announcements(session, stock, as_of_date, as_of_cutoff)
    if any(item.get("ai_summary") or item.get("ai_metrics") for item in announcements):
        warnings.append(
            "Stored AI announcement metrics do not have separate generated_at/model_version metadata."
        )

    signals = (
        _load_live_signals(session, stock, market_data_as_of)
        if market_data_as_of is not None
        else []
    )
    latest_price = price_bars[-1] if price_bars else None

    payload: dict[str, Any] = {
        "stock": {
            "id": stock.id,
            "code": stock.code,
            "name": stock.name,
            "commodity": stock.commodity,
            "stage": stock.stage,
        },
        "as_of": {
            "as_of_date": as_of_date,
            "as_of_cutoff": as_of_cutoff,
            "market_data_as_of": market_data_as_of,
            "mode": mode,
            "boundary_status": boundary_status,
            "warnings": warnings,
        },
        "price_bars": price_bars,
        "latest_price": latest_price,
        "indicators": asdict(indicators) if indicators is not None else None,
        "announcements": announcements,
        "commodity": {
            "instrument": instrument,
            "bars": commodity_bars,
        },
        "signals": signals,
        "config": config,
    }
    payload["input_summary"] = _build_input_summary(payload)
    payload["input_hash"] = _hash_payload(payload)
    return payload


def _resolve_market_data_as_of(session: Session, stock: Stock, as_of_date: date) -> date | None:
    return (
        session.query(func.max(PriceBar.date))
        .filter(PriceBar.stock_id == stock.id, PriceBar.date <= as_of_date)
        .scalar()
    )


def _load_price_bars(session: Session, stock: Stock, market_data_as_of: date) -> list[dict[str, Any]]:
    rows = (
        session.query(PriceBar)
        .filter(PriceBar.stock_id == stock.id, PriceBar.date <= market_data_as_of)
        .order_by(PriceBar.date.asc())
        .all()
    )
    return [
        {
            "date": row.date,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
        }
        for row in rows
    ]


def _load_announcements(
    session: Session,
    stock: Stock,
    as_of_date: date,
    as_of_cutoff: datetime,
) -> list[dict[str, Any]]:
    since = datetime.combine(as_of_date - timedelta(days=ANNOUNCEMENT_HISTORY_DAYS), time.min)
    rows = (
        session.query(Announcement)
        .filter(
            Announcement.stock_id == stock.id,
            Announcement.ann_date >= since,
            Announcement.ann_date <= as_of_cutoff,
        )
        .order_by(Announcement.ann_date.desc(), Announcement.id.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "ann_id": row.ann_id,
            "headline": row.headline,
            "ann_date": row.ann_date,
            "url": row.url,
            "price_sensitive": row.price_sensitive,
            "ann_type": row.ann_type,
            "type_score": row.type_score,
            "matched_keywords": _loads_json(row.matched_keywords, []),
            "ai_summary": row.ai_summary,
            "ai_metrics": _loads_json(row.ai_metrics, None),
        }
        for row in rows
    ]


def _load_commodity_bars(
    session: Session,
    instrument: str,
    market_data_as_of: date,
) -> list[dict[str, Any]]:
    rows = (
        session.query(CommodityBar)
        .filter(CommodityBar.instrument == instrument, CommodityBar.date <= market_data_as_of)
        .order_by(CommodityBar.date.asc())
        .all()
    )
    return [{"date": row.date, "close": row.close} for row in rows]


def _load_live_signals(session: Session, stock: Stock, market_data_as_of: date) -> list[dict[str, Any]]:
    rows = (
        session.query(Signal)
        .filter(
            Signal.stock_id == stock.id,
            Signal.source == "live",
            Signal.date <= market_data_as_of,
        )
        .order_by(Signal.date.desc(), Signal.id.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "date": row.date,
            "signal_type": row.signal_type,
            "label": row.label,
            "reason": row.reason,
            "evidence": _loads_json(row.evidence, {}),
            "price_at_signal": row.price_at_signal,
            "cycle_score_at_signal": row.cycle_score_at_signal,
        }
        for row in rows
    ]


def _build_input_summary(payload: dict[str, Any]) -> dict[str, Any]:
    price_bars = payload["price_bars"]
    announcements = payload["announcements"]
    commodity_bars = payload["commodity"]["bars"]
    signals = payload["signals"]
    return {
        "price_bar_count": len(price_bars),
        "first_price_date": price_bars[0]["date"] if price_bars else None,
        "last_price_date": price_bars[-1]["date"] if price_bars else None,
        "announcement_count": len(announcements),
        "latest_announcement_at": announcements[0]["ann_date"] if announcements else None,
        "commodity_bar_count": len(commodity_bars),
        "last_commodity_date": commodity_bars[-1]["date"] if commodity_bars else None,
        "live_signal_count": len(signals),
    }


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _loads_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default
