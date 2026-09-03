"""Score a point-in-time historical analysis input package."""

from __future__ import annotations

from typing import Any

from ..analysis.indicators import DailyBar, compute_indicators
from ..analysis.scoring import (
    RiskAnnouncement,
    ScoredAnnouncement,
    announcement_score,
    commodity_score,
    cycle_score,
    funding_score,
    label_for,
    risk_score,
    sentiment_score,
)
from .scoring_service import _score_resource_context


def score_historical_analysis_input(payload: dict[str, Any]) -> dict[str, Any]:
    """Return scores for a bounded historical input package without persisting.

    The caller is responsible for building the payload with
    build_historical_analysis_input(). This function deliberately does not query
    live data sources, write snapshots, or create signals.
    """

    bars = [
        DailyBar(
            date=row["date"],
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row["volume"]),
        )
        for row in payload.get("price_bars", [])
    ]
    ind = compute_indicators(bars)
    if ind is None:
        return {
            "status": "incomplete",
            "reason": "no_price_bars",
            "as_of": payload.get("as_of", {}),
            "input_hash": payload.get("input_hash"),
        }

    config = payload.get("config") or {}
    thresholds = config.get("signal_thresholds") or {}
    weights = config.get("weights") or {}
    label_thresholds = config.get("label_thresholds") or {}
    eval_date = ind.date

    funding, funding_comp = funding_score(ind, thresholds)

    scored_anns = [
        ScoredAnnouncement(
            headline=row["headline"],
            ann_type=row["ann_type"],
            type_score=float(row["type_score"]),
            ann_date=row["ann_date"].date(),
            price_sensitive=bool(row["price_sensitive"]),
            **_qualitative_context_for_score(row.get("ai_metrics")),
        )
        for row in payload.get("announcements", [])
    ]
    announcement, announcement_comp = announcement_score(scored_anns, eval_date)
    _add_source_announcement_metadata(announcement_comp, payload.get("announcements", []))

    resource, resource_comp = _resource_score_from_payload(payload, eval_date)

    risk, risk_comp = risk_score(
        ind,
        [
            RiskAnnouncement(
                headline=row["headline"],
                ann_type=row["ann_type"],
                ann_date=row["ann_date"].date(),
                price_sensitive=bool(row["price_sensitive"]),
            )
            for row in payload.get("announcements", [])
        ],
        thresholds,
        eval_date,
    )

    commodity_rows = payload.get("commodity", {}).get("bars", [])
    commodity_closes = [(row["date"], float(row["close"])) for row in commodity_rows]
    commodity, commodity_comp = commodity_score(commodity_closes, eval_date)
    commodity_comp["instrument"] = payload.get("commodity", {}).get("instrument")

    sentiment, sentiment_comp = sentiment_score()

    total = cycle_score(announcement, resource, commodity, risk, sentiment, weights)
    label = label_for(total, label_thresholds)
    components = {
        "funding": {
            **funding_comp,
            "role": "funding_confirmation",
            "included_in_cycle_score": False,
        },
        "announcement": announcement_comp,
        "resource": resource_comp,
        "commodity": commodity_comp,
        "risk": risk_comp,
        "sentiment": sentiment_comp,
        "weights": weights,
    }

    return {
        "status": "success",
        "as_of": payload.get("as_of", {}),
        "input_hash": payload.get("input_hash"),
        "input_summary": payload.get("input_summary", {}),
        "funding_score": funding,
        "announcement_score": announcement,
        "resource_score": resource,
        "commodity_score": commodity,
        "risk_score": risk,
        "sentiment_score": sentiment,
        "cycle_score": total,
        "label": label,
        "components": components,
        "reason": _build_rule_reason(
            total,
            label,
            {
                "announcement": announcement,
                "resource": resource,
                "commodity": commodity,
                "risk": risk,
                "sentiment": sentiment,
            },
        ),
    }


def _qualitative_context_for_score(metrics: dict[str, Any] | None) -> dict[str, Any]:
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


def _add_source_announcement_metadata(
    announcement_comp: dict[str, Any],
    source_rows: list[dict[str, Any]],
) -> None:
    for item in announcement_comp.get("announcements", []):
        match = next(
            (
                row
                for row in source_rows
                if row.get("headline", "").startswith(item.get("headline", ""))
                and row.get("ann_type") == item.get("type")
            ),
            None,
        )
        if match is None:
            continue
        item["ann_id"] = match.get("ann_id")
        item["url"] = match.get("url")
        item["ai_summary"] = match.get("ai_summary")


def _resource_score_from_payload(payload: dict[str, Any], eval_date) -> tuple[float, dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for announcement in payload.get("announcements", []):
        for context in _qualitative_contexts(announcement.get("ai_metrics")):
            item_score, drivers = _score_resource_context(context)
            items.append(
                {
                    "ann_id": announcement.get("ann_id"),
                    "date": announcement["ann_date"].date().isoformat(),
                    "headline": announcement["headline"][:100],
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

    ranked = sorted(items, key=lambda item: item["score"], reverse=True)[:8]
    best = ranked[0]["score"]
    avg = sum(item["score"] for item in ranked) / len(ranked)
    value = round(0.7 * best + 0.3 * avg, 1)
    return value, {
        "value": value,
        "source": "qualitative_context_auto",
        "lookback_days": 365,
        "as_of": eval_date.isoformat(),
        "context_count": len(items),
        "used_count": len(ranked),
        "best_context_score": best,
        "avg_context_score": round(avg, 1),
        "items": ranked,
    }


def _qualitative_contexts(metrics: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(metrics, dict):
        return []
    contexts = metrics.get("qualitative_contexts")
    if isinstance(contexts, list):
        return [item for item in contexts if isinstance(item, dict)]
    context = metrics.get("qualitative_context")
    return [context] if isinstance(context, dict) else []


def _build_rule_reason(total: float, label: str, sub_scores: dict[str, float]) -> str:
    main_driver = max(sub_scores, key=sub_scores.get)
    return (
        f"Historical rule score is {total:.1f} ({label}). "
        f"The strongest visible driver in the bounded input is {main_driver}."
    )
