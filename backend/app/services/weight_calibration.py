"""Data-backed weight calibration suggestions from filled live signal returns.

This does not auto-optimize a trading strategy. It produces a conservative,
auditable recommendation by comparing same-day sub-scores with later returns.
Replay signals are excluded because they do not carry honest historical
announcement/resource/risk scores.
"""

import math
import statistics
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import ScoreSnapshot, Signal, SignalReturn
from .config_service import DEFAULTS, get_config

SUBSCORES = (
    ("announcement", "announcement_score"),
    ("resource", "resource_score"),
    ("commodity", "commodity_score"),
    ("risk", "risk_score"),
    ("sentiment", "sentiment_score"),
)
MIN_SAMPLE = 10
MIN_WEIGHT = 0.03


@dataclass(frozen=True)
class CalibrationRow:
    values: dict[str, float]
    target: float


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    dx = [x - mean_x for x in xs]
    dy = [y - mean_y for y in ys]
    denom = math.sqrt(sum(x * x for x in dx) * sum(y * y for y in dy))
    if denom == 0:
        return None
    return sum(x * y for x, y in zip(dx, dy)) / denom


def _spread(values: list[float], targets: list[float]) -> float | None:
    if len(values) < 4:
        return None
    pairs = sorted(zip(values, targets), key=lambda p: p[0])
    group_size = max(1, len(pairs) // 3)
    low = [target for _, target in pairs[:group_size]]
    high = [target for _, target in pairs[-group_size:]]
    if not low or not high:
        return None
    return statistics.mean(high) - statistics.mean(low)


def _normalize(raw: dict[str, float], current_weights: dict[str, float]) -> dict[str, float]:
    if not raw or sum(raw.values()) <= 0:
        return {k: round(float(v), 4) for k, v in current_weights.items()}
    adjusted = {k: max(MIN_WEIGHT, v) for k, v in raw.items()}
    total = sum(adjusted.values())
    normalized = {k: v / total for k, v in adjusted.items()}

    # Round while preserving exact 1.0 sum at 4 decimals.
    rounded = {k: round(v, 4) for k, v in normalized.items()}
    drift = round(1.0 - sum(rounded.values()), 4)
    if drift:
        largest = max(rounded, key=rounded.get)
        rounded[largest] = round(rounded[largest] + drift, 4)
    return rounded


def _load_rows(session: Session, horizon_days: int, target: str) -> list[CalibrationRow]:
    rows = (
        session.query(SignalReturn, Signal, ScoreSnapshot)
        .join(Signal, SignalReturn.signal_id == Signal.id)
        .join(
            ScoreSnapshot,
            (ScoreSnapshot.stock_id == Signal.stock_id) & (ScoreSnapshot.date == Signal.date),
        )
        .filter(
            Signal.source == "live",
            SignalReturn.status == "filled",
            SignalReturn.horizon_days == horizon_days,
        )
        .all()
    )
    out: list[CalibrationRow] = []
    for sr, _sig, snap in rows:
        if sr.return_pct is None:
            continue
        if target == "excess":
            if sr.benchmark_return_pct is None:
                continue
            y = sr.return_pct - sr.benchmark_return_pct
        elif target == "return":
            y = sr.return_pct
        else:
            raise ValueError(f"invalid target: {target}")
        out.append(
            CalibrationRow(
                values={name: float(getattr(snap, attr)) for name, attr in SUBSCORES},
                target=float(y),
            )
        )
    return out


def calibrate_weights(
    session: Session,
    horizon_days: int = 20,
    target: str = "excess",
    min_sample: int = MIN_SAMPLE,
) -> dict:
    if horizon_days not in (5, 20, 60, 120):
        raise ValueError("horizon_days must be one of 5/20/60/120")
    if target not in ("excess", "return"):
        raise ValueError("target must be excess or return")
    rows = _load_rows(session, horizon_days=horizon_days, target=target)
    current_weights = get_config(session, "weights") or DEFAULTS["weights"]

    diagnostics = []
    raw_weights: dict[str, float] = {}
    targets = [r.target for r in rows]
    low_sample = len(rows) < min_sample

    for name, _attr in SUBSCORES:
        xs = [r.values[name] for r in rows]
        corr = _pearson(xs, targets)
        spread = _spread(xs, targets)
        corr_signal = max(0.0, corr or 0.0)
        spread_signal = max(0.0, spread or 0.0)
        # Correlation captures monotonicity; spread captures practical return separation.
        raw = corr_signal * 0.7 + min(spread_signal / 20.0, 1.0) * 0.3
        raw_weights[name] = raw
        diagnostics.append(
            {
                "subscore": name,
                "correlation": round(corr, 4) if corr is not None else None,
                "top_bottom_spread": round(spread, 2) if spread is not None else None,
                "raw_signal": round(raw, 4),
            }
        )

    recommended = (
        {k: round(float(v), 4) for k, v in current_weights.items()}
        if low_sample
        else _normalize(raw_weights, current_weights)
    )

    return {
        "horizon_days": horizon_days,
        "target": target,
        "sample_size": len(rows),
        "low_sample": low_sample,
        "current_weights": {k: round(float(v), 4) for k, v in current_weights.items()},
        "recommended_weights": recommended,
        "diagnostics": diagnostics,
        "method": (
            "Uses filled live signals only. Joins each signal to the same-day score snapshot, "
            "then estimates each sub-score's positive correlation and top-vs-bottom return spread. "
            "Low samples keep current weights."
        ),
    }
