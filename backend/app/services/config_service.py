"""Runtime-tunable config stored in the app_config table.

Weights and thresholds live here (not in .env) so they can be edited from the
Settings page and every change is persisted with the data it influenced.
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from ..models import AppConfig, AppConfigHistory

DEFAULTS: dict[str, Any] = {
    "weights": {
        "announcement": 0.40,
        "resource": 0.20,
        "commodity": 0.20,
        "risk": 0.10,
        "sentiment": 0.10,
    },
    "label_thresholds": {  # score >= threshold, checked from high to low
        "high_priority": 75,
        "watch_closely": 60,
        "monitor": 45,
    },
    "signal_thresholds": {
        "rel_vol_spike": 3.0,
        "breakout_rel_vol": 1.5,
        "min_dollar_turnover": 50000,  # A$, liquidity floor for volume-based scoring/signals
        "score_cross": 75,  # aligned with high_priority label threshold
        "key_announcement_score": 70,
        "key_announcement_ps_score": 60,  # price-sensitive announcements
        "announcement_window_days": 5,  # max lookback for "new announcement" signals
    },
    "commodity_instruments": {
        # lithium/uranium/rare_earth have no reliable continuous futures on yfinance,
        # so equity-ETF proxies are used (known limitation, 10% weight).
        "gold": "GC=F",
        "copper": "HG=F",
        "lithium": "LIT",
        "uranium": "URA",
        "rare_earth": "REMX",
    },
    "benchmark_instrument": "OZR.AX",  # ASX resources ETF, backtest baseline
}

DESCRIPTIONS = {
    "weights": "Cycle Score sub-score weights (must sum to 1.0)",
    "label_thresholds": "Cycle Score -> label mapping thresholds",
    "signal_thresholds": "Signal trigger thresholds",
    "commodity_instruments": "commodity -> yfinance instrument mapping",
    "benchmark_instrument": "Benchmark instrument for backtest excess returns",
}


def ensure_defaults(session: Session) -> None:
    for key, value in DEFAULTS.items():
        row = session.get(AppConfig, key)
        if row is None:
            session.add(
                AppConfig(key=key, value=json.dumps(value), description=DESCRIPTIONS.get(key, ""))
            )
        elif key == "weights" and set(json.loads(row.value)) != set(DEFAULTS["weights"]):
            old_value = row.value
            row.value = json.dumps(value)
            session.add(
                AppConfigHistory(
                    key=key,
                    old_value=old_value,
                    new_value=row.value,
                    changed_by="system",
                    source="startup:migrate_weights_v2",
                )
            )
    session.commit()


def get_config(session: Session, key: str) -> Any:
    row = session.get(AppConfig, key)
    if row is None:
        return DEFAULTS.get(key)
    return json.loads(row.value)


def get_all_config(session: Session) -> dict[str, Any]:
    merged = {k: v for k, v in DEFAULTS.items()}
    for row in session.query(AppConfig).all():
        merged[row.key] = json.loads(row.value)
    return merged


def set_config(
    session: Session,
    key: str,
    value: Any,
    changed_by: str = "system",
    source: str = "api",
) -> bool:
    row = session.get(AppConfig, key)
    old_serialized = row.value if row is not None else None
    new_serialized = json.dumps(value)
    if old_serialized == new_serialized:
        return False
    if row is None:
        row = AppConfig(key=key, value=new_serialized, description=DESCRIPTIONS.get(key, ""))
        session.add(row)
    else:
        row.value = new_serialized
    session.add(
        AppConfigHistory(
            key=key,
            old_value=old_serialized,
            new_value=new_serialized,
            changed_by=changed_by,
            source=source,
        )
    )
    session.commit()
    return True


def list_config_history(session: Session, limit: int = 50) -> list[AppConfigHistory]:
    return (
        session.query(AppConfigHistory)
        .order_by(AppConfigHistory.changed_at.desc(), AppConfigHistory.id.desc())
        .limit(min(limit, 200))
        .all()
    )
