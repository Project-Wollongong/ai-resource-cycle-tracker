"""Cycle Score sub-scores. All pure functions returning (score, components).

The components dict is persisted verbatim into score_snapshots.components —
it is the system's explainability contract: every point must be traceable to
a rule and an observed value.

Sub-scores are stepped ladders rather than continuous curves on purpose:
"rel_vol 5.2x → 40/40 points" is auditable, a fitted curve is not.
"""

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from .indicators import IndicatorResult

LABEL_HIGH = "High Priority"
LABEL_WATCH = "Watch Closely"
LABEL_MONITOR = "Monitor"
LABEL_IGNORE = "Ignore"


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# ---------- Funding Score (0-100) ----------

def funding_score(ind: IndicatorResult, thresholds: dict) -> tuple[float, dict]:
    min_turnover = float(thresholds.get("min_dollar_turnover", 50_000))
    components: dict = {}

    # 1) relative volume, max 40 — gated by liquidity floor and price direction
    points, note = 0, None
    if ind.rel_vol is None:
        note = "insufficient_liquidity" if ind.avg_volume_20 == 0 else "insufficient_history"
    elif ind.dollar_turnover < min_turnover:
        note = "insufficient_liquidity"
    elif ind.day_change_pct is not None and ind.day_change_pct < 0:
        note = "high_volume_down_day"  # distribution is not accumulation
    elif ind.rel_vol >= 5:
        points = 40
    elif ind.rel_vol >= 3:
        points = 30
    elif ind.rel_vol >= 2:
        points = 20
    elif ind.rel_vol >= 1.5:
        points = 10
    components["rel_vol"] = {
        "points": points,
        "max": 40,
        "value": round(ind.rel_vol, 2) if ind.rel_vol is not None else None,
        "day_change_pct": round(ind.day_change_pct, 2) if ind.day_change_pct is not None else None,
        "dollar_turnover": round(ind.dollar_turnover),
        "note": note,
    }

    # 2) breakout, max 30 — highest window only
    if ind.breakout_252:
        points, window = 30, 252
    elif ind.breakout_60:
        points, window = 22, 60
    elif ind.breakout_20:
        points, window = 12, 20
    else:
        points, window = 0, None
    components["breakout"] = {"points": points, "max": 30, "window": window}

    # 3) consecutive up days, max 15
    up = ind.consecutive_up_days
    points = 15 if up >= 5 else 12 if up == 4 else 8 if up == 3 else 4 if up == 2 else 0
    components["consecutive_up"] = {"points": points, "max": 15, "days": up}

    # 4) volume trend MA5/MA20, max 15
    trend = ind.vol_trend
    points = 0
    if trend is not None:
        points = 15 if trend >= 2 else 10 if trend >= 1.5 else 5 if trend >= 1.2 else 0
    components["vol_trend"] = {
        "points": points,
        "max": 15,
        "value": round(trend, 2) if trend is not None else None,
    }

    total = float(sum(c["points"] for c in components.values()))
    return total, components


# ---------- Announcement Score (0-100) ----------

@dataclass(frozen=True)
class ScoredAnnouncement:
    headline: str
    ann_type: str
    type_score: float
    ann_date: date
    price_sensitive: bool
    ann_id: str | None = None
    url: str | None = None
    ai_summary: str | None = None
    interval_quality_label: str | None = None
    materiality_label: str | None = None
    grade_thickness: float | None = None
    qualitative_assessment: str | None = None


@dataclass(frozen=True)
class RiskAnnouncement:
    headline: str
    ann_type: str
    ann_date: date
    price_sensitive: bool = False


def _decay(age_days: int) -> float:
    if age_days <= 3:
        return 1.0
    if age_days <= 7:
        return 0.8
    if age_days <= 14:
        return 0.5
    if age_days <= 30:
        return 0.25
    return 0.0


def announcement_score(
    announcements: Sequence[ScoredAnnouncement], as_of: date
) -> tuple[float, dict]:
    """max(effective) + key-announcement bonus. No announcements in 30d -> 0:
    a silent stock has no forming story, which is exactly what the radar
    should distinguish."""
    items = []
    for ann in announcements:
        age = (as_of - ann.ann_date).days
        if age < 0:
            continue  # future-dated (timezone edge) — ignore rather than leak
        decay = _decay(age)
        if decay == 0.0:
            continue
        qualitative_bonus = _qualitative_announcement_bonus(
            ann.interval_quality_label,
            ann.materiality_label,
        )
        adjusted_base = clamp(ann.type_score + qualitative_bonus)
        effective = adjusted_base * decay * (1.2 if ann.price_sensitive else 1.0)
        items.append(
            {
                "ann_id": ann.ann_id,
                "headline": ann.headline[:100],
                "type": ann.ann_type,
                "url": ann.url,
                "ai_summary": ann.ai_summary,
                "base": ann.type_score,
                "qualitative_bonus": qualitative_bonus,
                "adjusted_base": adjusted_base,
                "age_days": age,
                "decay": decay,
                "price_sensitive": ann.price_sensitive,
                "effective": round(effective, 1),
                "interval_quality_label": ann.interval_quality_label,
                "materiality_label": ann.materiality_label,
                "grade_thickness": ann.grade_thickness,
                "qualitative_assessment": ann.qualitative_assessment,
            }
        )
    if not items:
        return 0.0, {"announcements": [], "best": 0, "bonus": 0, "note": "no_announcements_30d"}

    items.sort(key=lambda x: x["effective"], reverse=True)
    best = items[0]["effective"]
    bonus = min(15, 5 * sum(1 for item in items[1:] if item["base"] >= 70))
    score = clamp(best + bonus)
    return score, {"announcements": items, "best": best, "bonus": bonus}


def _qualitative_announcement_bonus(
    interval_quality_label: str | None,
    materiality_label: str | None,
) -> float:
    """Small auditable uplift for drill-result context quality/materiality.

    The base announcement type remains the primary signal. Qualitative context
    can only add a bounded bonus when comparable history exists; insufficient
    history deliberately contributes no points.
    """

    quality_points = {
        "exceptional": 6.0,
        "strong": 4.0,
        "moderate": 2.0,
        "weak": 0.0,
        "insufficient_history": 0.0,
    }.get(interval_quality_label or "", 0.0)
    materiality_points = {
        "high": 4.0,
        "medium": 2.0,
        "low": 0.0,
        "insufficient_history": 0.0,
    }.get(materiality_label or "", 0.0)
    return min(10.0, quality_points + materiality_points)


# ---------- Commodity Score (0-100) ----------

def commodity_score(closes: Sequence[tuple[date, float]], as_of: date) -> tuple[float, dict]:
    """clamp(50 + r20*200 + r60*100). closes = ascending (date, close) for the
    stock's mapped instrument; only bars <= as_of are considered."""
    usable = [(d, c) for d, c in closes if d <= as_of and c > 0]
    if len(usable) < 61:
        return 50.0, {"note": "insufficient_data", "bars": len(usable)}
    last = usable[-1][1]
    r20 = last / usable[-21][1] - 1
    r60 = last / usable[-61][1] - 1
    score = clamp(50 + r20 * 200 + r60 * 100)
    return score, {
        "instrument_close": last,
        "r20_pct": round(r20 * 100, 2),
        "r60_pct": round(r60 * 100, 2),
    }


# ---------- Risk Score (0-100, higher is safer) ----------

def risk_score(
    ind: IndicatorResult,
    announcements: Sequence[RiskAnnouncement],
    thresholds: dict,
    as_of: date,
) -> tuple[float, dict]:
    """Observable first-pass risk score.

    This is deliberately conservative: it uses only data already stored by the
    system. It does not infer cash runway, debt, or dilution terms unless those
    fields are explicitly extracted in a later module.
    """

    base = 50.0
    liquidity_adjust, liquidity_comp = _liquidity_risk_adjustment(ind, thresholds)
    event_items = []
    event_adjust = 0.0

    for ann in announcements:
        age = (as_of - ann.ann_date).days
        if age < 0 or age > 90:
            continue
        adjustment, reason = _risk_event_adjustment(ann, age)
        if adjustment == 0:
            continue
        event_adjust += adjustment
        event_items.append(
            {
                "headline": ann.headline[:100],
                "type": ann.ann_type,
                "age_days": age,
                "price_sensitive": ann.price_sensitive,
                "adjustment": adjustment,
                "reason": reason,
            }
        )

    # Event penalties are capped so one noisy announcement cluster does not
    # dominate the whole Cycle Score before proper cash/dilution parsing exists.
    event_adjust = max(-35.0, min(5.0, event_adjust))
    score = clamp(base + liquidity_adjust + event_adjust)
    label = "elevated_risk" if score < 40 else "watch_risk" if score < 50 else "neutral"

    return round(score, 1), {
        "value": round(score, 1),
        "source": "rules_v1",
        "label": label,
        "base": base,
        "liquidity_adjust": liquidity_adjust,
        "event_adjust": event_adjust,
        "liquidity": liquidity_comp,
        "events": event_items,
        "note": "cash runway and dilution terms are not parsed yet",
    }


def _liquidity_risk_adjustment(ind: IndicatorResult, thresholds: dict) -> tuple[float, dict]:
    min_turnover = float(thresholds.get("min_dollar_turnover", 50_000))
    turnover = ind.dollar_turnover
    if turnover < min_turnover * 0.2:
        adjustment, label = -20.0, "very_low_liquidity"
    elif turnover < min_turnover:
        adjustment, label = -12.0, "low_liquidity"
    elif turnover >= min_turnover * 20:
        adjustment, label = 8.0, "strong_liquidity"
    elif turnover >= min_turnover * 5:
        adjustment, label = 4.0, "adequate_liquidity"
    else:
        adjustment, label = 0.0, "minimum_liquidity_met"
    return adjustment, {
        "dollar_turnover": round(turnover),
        "min_dollar_turnover": min_turnover,
        "label": label,
    }


def _risk_event_adjustment(ann: RiskAnnouncement, age_days: int) -> tuple[float, str]:
    ann_type = (ann.ann_type or "").upper()
    headline = (ann.headline or "").lower()
    recency = 1.0 if age_days <= 14 else 0.65 if age_days <= 45 else 0.35

    if ann_type == "PLACEMENT":
        return round(-18.0 * recency, 1), "recent capital raising / dilution risk"
    if ann_type == "TRADING_HALT":
        penalty = -16.0 if "suspension" in headline else -10.0
        return round(penalty * recency, 1), "trading halt or suspension uncertainty"
    if ann_type == "SUBSTANTIAL_HOLDER" and "ceasing" in headline:
        return round(-8.0 * recency, 1), "substantial holder ceasing notice"
    if ann_type == "QUARTERLY" and ("appendix 5b" in headline or "cash" in headline):
        return 0.0, "quarterly cash report requires cash-runway extraction"
    return 0.0, ""


# ---------- Sentiment Score (0-100) ----------

def sentiment_score() -> tuple[float, dict]:
    """Neutral placeholder until forum/social data collection is wired.

    Missing sentiment data is not bearish. It simply means the system has no
    evidence yet, so the score stays neutral and the components say why.
    """

    return 50.0, {
        "value": 50.0,
        "source": "neutral_default",
        "label": "insufficient_data",
        "note": "forum/social sentiment ingestion is not enabled yet",
    }


# ---------- composition ----------

def cycle_score(
    announcement: float, resource: float, commodity: float, risk: float, sentiment: float,
    weights: dict,
) -> float:
    return (
        weights["announcement"] * announcement
        + weights["resource"] * resource
        + weights["commodity"] * commodity
        + weights["risk"] * risk
        + weights["sentiment"] * sentiment
    )


def label_for(score: float, label_thresholds: dict) -> str:
    """Compliance-fixed enum — never buy/sell wording."""
    if score >= label_thresholds["high_priority"]:
        return LABEL_HIGH
    if score >= label_thresholds["watch_closely"]:
        return LABEL_WATCH
    if score >= label_thresholds["monitor"]:
        return LABEL_MONITOR
    return LABEL_IGNORE
