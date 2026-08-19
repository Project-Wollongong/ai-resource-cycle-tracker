"""Score one stock on its own latest bar and detect the day's signals."""

import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..analysis.indicators import DailyBar, compute_indicators
from ..analysis.scoring import (
    ScoredAnnouncement,
    announcement_score,
    commodity_score,
    cycle_score,
    funding_score,
    label_for,
)
from ..analysis.signals import (
    AnnouncementEvent,
    detect_announcement_signal,
    detect_price_signals,
    detect_score_cross,
)
from ..models import Announcement, CommodityBar, PriceBar, ScoreSnapshot, Stock
from .signal_service import persist_signals

ANNOUNCEMENT_LOOKBACK_DAYS = 30
RESOURCE_CONTEXT_LOOKBACK_DAYS = 365
RESOURCE_CONTEXT_MAX_ITEMS = 8


def load_bars(session: Session, stock: Stock) -> list[DailyBar]:
    rows = (
        session.query(PriceBar)
        .filter(PriceBar.stock_id == stock.id)
        .order_by(PriceBar.date)
        .all()
    )
    return [
        DailyBar(date=r.date, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume)
        for r in rows
    ]


def score_and_signal_stock(
    session: Session,
    stock: Stock,
    thresholds: dict,
    weights: dict,
    label_thresholds: dict,
    commodity_map: dict,
) -> dict:
    bars = load_bars(session, stock)
    ind = compute_indicators(bars)
    if ind is None:
        return {"skipped": "no_bars", "signals": 0}
    # each stock is evaluated on its OWN latest bar so one laggy ticker
    # doesn't stale-date the whole watchlist
    eval_date = ind.date

    funding, funding_comp = funding_score(ind, thresholds)

    ann_rows = (
        session.query(Announcement)
        .filter(
            Announcement.stock_id == stock.id,
            Announcement.ann_date
            >= datetime.combine(eval_date - timedelta(days=ANNOUNCEMENT_LOOKBACK_DAYS), datetime.min.time()),
        )
        .order_by(Announcement.ann_date.desc())
        .all()
    )
    scored_anns = [
        ScoredAnnouncement(
            headline=a.headline,
            ann_type=a.ann_type,
            type_score=a.type_score,
            ann_date=a.ann_date.date(),
            price_sensitive=a.price_sensitive,
            **_qualitative_context_for_score(a.ai_metrics),
        )
        for a in ann_rows
    ]
    announcement, ann_comp = announcement_score(scored_anns, eval_date)

    if stock.resource_score_override is not None:
        resource = stock.resource_score_override
        resource_comp = {
            "value": resource,
            "source": "manual_override",
        }
    else:
        resource, resource_comp = _resource_score_from_contexts(session, stock, eval_date)
    risk = stock.risk_score_override if stock.risk_score_override is not None else 50.0
    risk_comp = {
        "value": risk,
        "source": "manual_override" if stock.risk_score_override is not None else "neutral_default",
    }

    instrument = commodity_map.get(stock.commodity)
    closes = []
    if instrument:
        closes = (
            session.query(CommodityBar.date, CommodityBar.close)
            .filter(CommodityBar.instrument == instrument)
            .order_by(CommodityBar.date)
            .all()
        )
    commodity, commodity_comp = commodity_score(closes, eval_date)
    commodity_comp["instrument"] = instrument

    total = cycle_score(funding, announcement, resource, commodity, risk, weights)
    label = label_for(total, label_thresholds)

    prev_snap = (
        session.query(ScoreSnapshot)
        .filter(ScoreSnapshot.stock_id == stock.id, ScoreSnapshot.date < eval_date)
        .order_by(ScoreSnapshot.date.desc())
        .first()
    )

    components = json.dumps(
        {
            "funding": funding_comp,
            "announcement": ann_comp,
            "resource": resource_comp,
            "commodity": commodity_comp,
            "risk": risk_comp,
            "weights": weights,
        }
    )
    snapshot = (
        session.query(ScoreSnapshot)
        .filter_by(stock_id=stock.id, date=eval_date)
        .one_or_none()
    )
    if snapshot is None:
        snapshot = ScoreSnapshot(stock_id=stock.id, date=eval_date)
        session.add(snapshot)
    snapshot.funding_score = funding
    snapshot.announcement_score = announcement
    snapshot.resource_score = resource
    snapshot.commodity_score = commodity
    snapshot.risk_score = risk
    snapshot.cycle_score = total
    snapshot.label = label
    snapshot.components = components
    session.commit()

    # ---- signals for the evaluation day ----
    candidates = detect_price_signals(ind, thresholds)

    # "new" announcements: since the previous snapshot (covers weekend gaps),
    # capped by announcement_window_days; first run = evaluation day only.
    window_days = int(thresholds.get("announcement_window_days", 5))
    since = prev_snap.date if prev_snap else eval_date - timedelta(days=1)
    since = max(since, eval_date - timedelta(days=window_days))
    new_events = [
        AnnouncementEvent(
            ann_id=a.ann_id,
            headline=a.headline,
            ann_type=a.ann_type,
            type_score=a.type_score,
            price_sensitive=a.price_sensitive,
        )
        for a in ann_rows
        if since < a.ann_date.date() <= eval_date
    ]
    key_candidate = detect_announcement_signal(new_events, thresholds)
    if key_candidate:
        candidates.append(key_candidate)
    cross_candidate = detect_score_cross(
        prev_snap.cycle_score if prev_snap else None, total, thresholds
    )
    if cross_candidate:
        candidates.append(cross_candidate)

    added = persist_signals(
        session,
        stock,
        eval_date,
        candidates,
        price_at_signal=ind.close,
        source="live",
        label=label,
        cycle_score=total,
    )
    return {
        "signals": added,
        "eval_date": eval_date.isoformat(),
        "cycle_score": round(total, 1),
        "label": label,
    }


def _qualitative_context_for_score(raw_metrics: str | None) -> dict:
    if not raw_metrics:
        return {}
    try:
        metrics = json.loads(raw_metrics)
    except json.JSONDecodeError:
        return {}
    if not isinstance(metrics, dict):
        return {}
    context = metrics.get("qualitative_context")
    if not isinstance(context, dict):
        return {}
    return {
        "interval_quality_label": context.get("interval_quality_label"),
        "materiality_label": context.get("materiality_label"),
        "grade_thickness": context.get("grade_thickness"),
        "qualitative_assessment": context.get("qualitative_assessment"),
    }


def _resource_score_from_contexts(session: Session, stock: Stock, eval_date) -> tuple[float, dict]:
    since = datetime.combine(eval_date - timedelta(days=RESOURCE_CONTEXT_LOOKBACK_DAYS), datetime.min.time())
    until = datetime.combine(eval_date + timedelta(days=1), datetime.min.time())
    rows = (
        session.query(Announcement)
        .filter(
            Announcement.stock_id == stock.id,
            Announcement.ann_date >= since,
            Announcement.ann_date < until,
            Announcement.ai_metrics.isnot(None),
        )
        .order_by(Announcement.ann_date.desc(), Announcement.id.desc())
        .all()
    )
    items = []
    for announcement in rows:
        for context in _qualitative_contexts_from_metrics(announcement.ai_metrics):
            item_score, drivers = _score_resource_context(context)
            items.append(
                {
                    "ann_id": announcement.ann_id,
                    "date": announcement.ann_date.date().isoformat(),
                    "headline": announcement.headline[:100],
                    "score": item_score,
                    **drivers,
                }
            )

    if not items:
        return 50.0, {
            "value": 50.0,
            "source": "neutral_default",
            "note": "no_qualitative_context",
        }

    ranked = sorted(items, key=lambda item: item["score"], reverse=True)[:RESOURCE_CONTEXT_MAX_ITEMS]
    best = ranked[0]["score"]
    avg = sum(item["score"] for item in ranked) / len(ranked)
    value = round(0.7 * best + 0.3 * avg, 1)
    return value, {
        "value": value,
        "source": "qualitative_context_auto",
        "lookback_days": RESOURCE_CONTEXT_LOOKBACK_DAYS,
        "context_count": len(items),
        "used_count": len(ranked),
        "best_context_score": best,
        "avg_context_score": round(avg, 1),
        "items": ranked,
    }


def _qualitative_contexts_from_metrics(raw_metrics: str | None) -> list[dict]:
    if not raw_metrics:
        return []
    try:
        metrics = json.loads(raw_metrics)
    except json.JSONDecodeError:
        return []
    if not isinstance(metrics, dict):
        return []
    contexts = metrics.get("qualitative_contexts")
    if isinstance(contexts, list):
        return [item for item in contexts if isinstance(item, dict)]
    context = metrics.get("qualitative_context")
    return [context] if isinstance(context, dict) else []


def _score_resource_context(context: dict) -> tuple[float, dict]:
    quality = context.get("interval_quality_label")
    materiality = context.get("materiality_label")
    trend = context.get("trend_vs_previous")
    depth = context.get("depth_category")
    percentile = _best_percentile(context)

    quality_score = {
        "exceptional": 90.0,
        "strong": 75.0,
        "moderate": 60.0,
        "weak": 40.0,
        "insufficient_history": 50.0,
    }.get(quality, 50.0)
    materiality_adjust = {
        "high": 8.0,
        "medium": 4.0,
        "low": -4.0,
        "insufficient_history": 0.0,
    }.get(materiality, 0.0)
    trend_adjust = {
        "improving": 5.0,
        "flat": 0.0,
        "deteriorating": -5.0,
        "insufficient_history": 0.0,
    }.get(trend, 0.0)
    depth_adjust = {
        "shallow": 3.0,
        "medium": 0.0,
        "deep": -3.0,
        "unknown": 0.0,
    }.get(depth, 0.0)
    percentile_adjust = 0.0 if percentile is None else max(-8.0, min(8.0, (float(percentile) - 50.0) * 0.16))

    score = max(0.0, min(100.0, quality_score + materiality_adjust + trend_adjust + depth_adjust + percentile_adjust))
    return round(score, 1), {
        "interval_quality_label": quality,
        "materiality_label": materiality,
        "trend_vs_previous": trend,
        "depth_category": depth,
        "grade_thickness": context.get("grade_thickness"),
        "percentile": percentile,
        "quality_score": quality_score,
        "materiality_adjust": materiality_adjust,
        "trend_adjust": trend_adjust,
        "depth_adjust": depth_adjust,
        "percentile_adjust": round(percentile_adjust, 1),
        "assessment": context.get("qualitative_assessment"),
    }


def _best_percentile(context: dict) -> float | None:
    for key in ("project_percentile", "company_percentile", "regional_percentile"):
        value = context.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None
