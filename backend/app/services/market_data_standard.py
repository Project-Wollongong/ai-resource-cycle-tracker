"""P03-neutral market-data normalization and quality flags.

This module only standardizes source rows. It deliberately does not calculate
technical indicators, returns, signals, valuation or other P04 features.
"""
from datetime import date, datetime
from typing import Any


def normalize_market_row(row: dict[str, Any], *, instrument_code: str, instrument_type: str, source: str, source_symbol: str, currency: str | None = None, timezone: str = "UTC", is_adjusted: str = "unknown") -> dict[str, Any]:
    trading_date = row.get("trading_date", row.get("date"))
    if isinstance(trading_date, datetime):
        trading_date = trading_date.date()
    if isinstance(trading_date, str):
        trading_date = date.fromisoformat(trading_date[:10])
    flags: list[str] = []
    values = {key: _number(row.get(key)) for key in ("open", "high", "low", "close", "adjusted_close", "volume")}
    if trading_date is None: flags.append("missing_date")
    if values["close"] is None: flags.append("missing_close")
    if values["volume"] is None: flags.append("missing_volume")
    if any(values[key] is not None and values[key] < 0 for key in ("open", "high", "low", "close", "adjusted_close", "volume")): flags.append("negative_value_review_needed")
    quality = "review_needed" if flags else "ok"
    return {"instrument_code": instrument_code, "instrument_type": instrument_type, "trading_date": trading_date, **values, "currency": currency, "source": source, "source_symbol": source_symbol, "timezone": timezone, "is_adjusted": is_adjusted if is_adjusted in {"true", "false", "unknown"} else "unknown", "quality_status": quality, "quality_flags": flags}


def _number(value: Any) -> float | None:
    if value is None or value == "": return None
    return float(value)
