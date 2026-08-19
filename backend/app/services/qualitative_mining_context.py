"""Historical context for structured mining announcement intercepts.

This module enriches deterministic extraction output with derived mining
context. It only uses stored announcement metrics; when there is not enough
comparable history, percentile/trend fields explicitly report insufficient
history rather than inventing a conclusion.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from statistics import median
from typing import Any, Iterable

from sqlalchemy.orm import Session

from ..models import Announcement, Stock

QUALITATIVE_CONTEXT_KEY = "qualitative_context"
QUALITATIVE_CONTEXTS_KEY = "qualitative_contexts"
MIN_PROJECT_HISTORY = 3
MIN_TREND_HISTORY = 3
MAX_TREND_HISTORY = 5
SHALLOW_DEPTH_MAX_M = 100.0
MEDIUM_DEPTH_MAX_M = 300.0


@dataclass(frozen=True)
class ComparableIntercept:
    grade_thickness: float
    project: str | None
    region: str | None
    stock_code: str
    commodity: str
    unit: str
    announcement_id: int


def enrich_qualitative_context(
    session: Session,
    stock_code: str,
    metrics: dict[str, Any],
    ann_type: str | None = None,
    price_sensitive: bool | None = None,
) -> dict[str, Any]:
    """Return metrics with a qualitative_context object added when possible."""

    enriched = dict(metrics)
    contexts = build_qualitative_contexts(
        session,
        stock_code,
        metrics,
        ann_type=ann_type,
        price_sensitive=price_sensitive,
    )
    if contexts:
        enriched[QUALITATIVE_CONTEXT_KEY] = contexts[0]
        enriched[QUALITATIVE_CONTEXTS_KEY] = contexts
    return enriched


def build_qualitative_contexts(
    session: Session,
    stock_code: str,
    metrics: dict[str, Any],
    ann_type: str | None = None,
    price_sensitive: bool | None = None,
) -> list[dict[str, Any]]:
    """Build qualitative context for every valid extracted intercept."""

    return [
        _build_context_for_intercept(
            session=session,
            stock_code=stock_code,
            metrics=metrics,
            intercept=intercept,
            intercept_index=index,
            ann_type=ann_type,
            price_sensitive=price_sensitive,
        )
        for index, intercept in _valid_intercepts(metrics)
    ]


def build_qualitative_context(
    session: Session,
    stock_code: str,
    metrics: dict[str, Any],
    ann_type: str | None = None,
    price_sensitive: bool | None = None,
) -> dict[str, Any] | None:
    """Build qualitative context for the primary extracted intercept.

    The primary intercept is the first item in metrics["intercepts"], matching
    the analyzer's sorted "best intercept first" contract.
    """

    contexts = build_qualitative_contexts(
        session,
        stock_code,
        metrics,
        ann_type=ann_type,
        price_sensitive=price_sensitive,
    )
    return contexts[0] if contexts else None


def _build_context_for_intercept(
    session: Session,
    stock_code: str,
    metrics: dict[str, Any],
    intercept: dict[str, Any],
    intercept_index: int,
    ann_type: str | None = None,
    price_sensitive: bool | None = None,
) -> dict[str, Any]:
    grade_thickness = _grade_thickness(intercept)
    depth_category = _depth_category(intercept.get("depth_m"))
    project = _clean_project(metrics.get("project"))
    commodity = _clean_text(intercept.get("commodity"))
    region = _clean_region(metrics)
    grade, unit = _canonical_grade_and_unit(intercept, commodity)
    width_m = float(intercept["width_m"])
    source_unit = _normal_unit(intercept.get("unit"))
    missing_fields = _missing_fields(intercept, project, region)

    reason_parts = [
        f"intercept index is {intercept_index}",
        f"grade-thickness is {grade_thickness:g}",
        f"depth category is {depth_category}",
        f"normalized unit is {unit}",
    ]
    if ann_type:
        reason_parts.append(f"announcement type is {ann_type}")
    if price_sensitive is not None:
        reason_parts.append(f"price_sensitive is {str(price_sensitive).lower()}")

    comparable = _historical_intercepts(
        session=session,
        stock_code=stock_code,
        commodity=commodity,
        unit=unit,
    )
    company_values = [item.grade_thickness for item in comparable]
    company_percentile = _percentile(grade_thickness, company_values, MIN_PROJECT_HISTORY)
    reason_parts.append(f"company comparable history n={len(company_values)}")
    if company_percentile is None:
        reason_parts.append("insufficient company history")

    project_values = [
        item.grade_thickness
        for item in comparable
        if project is not None and _same_project(item.project, project)
    ]
    project_percentile = _percentile(grade_thickness, project_values, MIN_PROJECT_HISTORY)
    reason_parts.append(f"project comparable history n={len(project_values)}")
    if project is None:
        reason_parts.append("project unavailable")
    elif project_percentile is None:
        reason_parts.append("insufficient project history")
    reason_parts.append("comparison limited to same stock, commodity, and unit")

    regional_values: list[float] = []
    regional_percentile = None
    if region is None:
        reason_parts.append("region unavailable")
    else:
        regional_comparable = _historical_intercepts(
            session=session,
            stock_code=None,
            commodity=commodity,
            unit=unit,
        )
        regional_values = [
            item.grade_thickness
            for item in regional_comparable
            if _same_region(item.region, region)
        ]
        regional_percentile = _percentile(grade_thickness, regional_values, MIN_PROJECT_HISTORY)
        reason_parts.append(f"regional comparable history n={len(regional_values)}")
        if regional_percentile is None:
            reason_parts.append("insufficient regional history")
        reason_parts.append("regional comparison limited to same region, commodity, and normalized unit")

    trend_values, trend_basis = _trend_history(company_values, project_values)
    trend = _trend_vs_previous(grade_thickness, trend_values)
    if trend == "insufficient_history":
        reason_parts.append("insufficient prior comparable results for trend")
    else:
        reason_parts.append(f"trend basis is {trend_basis}")

    quality = _interval_quality_label(
        project_percentile,
        company_percentile,
        regional_percentile,
        grade_thickness,
        depth_category,
    )
    materiality = _materiality_label(
        quality,
        depth_category,
        project_percentile,
        company_percentile,
        regional_percentile,
        ann_type=ann_type,
        price_sensitive=price_sensitive,
    )
    assessment = _qualitative_assessment(
        quality,
        materiality,
        project_percentile,
        company_percentile,
        regional_percentile,
        depth_category,
    )
    comparison_warnings = _comparison_warnings(
        source_unit=source_unit,
        normalized_unit=unit,
        company_percentile=company_percentile,
        project_percentile=project_percentile,
        regional_percentile=regional_percentile,
        trend=trend,
        trend_basis=trend_basis,
        missing_fields=missing_fields,
    )

    return {
        "intercept_index": intercept_index,
        "width_m": width_m,
        "grade": grade,
        "unit": source_unit,
        "normalized_unit": unit,
        "commodity": commodity,
        "project": project,
        "region": region,
        "extraction_quality": "complete" if not missing_fields else "partial",
        "missing_fields": missing_fields,
        "comparison_warnings": comparison_warnings,
        "grade_thickness": grade_thickness,
        "depth_category": depth_category,
        "interval_quality_label": quality,
        "company_percentile": company_percentile,
        "project_percentile": project_percentile,
        "regional_percentile": regional_percentile,
        "trend_vs_previous": trend,
        "trend_basis": trend_basis,
        "materiality_label": materiality,
        "company_history_count": len(company_values),
        "project_history_count": len(project_values),
        "regional_history_count": len(regional_values),
        "reason": "; ".join(reason_parts),
        "qualitative_assessment": assessment,
    }


def _valid_intercepts(metrics: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    intercepts = metrics.get("intercepts")
    if not isinstance(intercepts, list) or not intercepts:
        return []
    out: list[tuple[int, dict[str, Any]]] = []
    for index, item in enumerate(intercepts):
        if not isinstance(item, dict):
            continue
        try:
            width = float(item["width_m"])
            grade = float(item["grade"])
        except (KeyError, TypeError, ValueError):
            continue
        commodity = _clean_text(item.get("commodity"))
        try:
            _canonical_grade_and_unit(item, commodity)
        except (KeyError, TypeError, ValueError):
            continue
        if width <= 0 or grade <= 0 or not commodity:
            continue
        out.append((index, item))
    return out


def _grade_thickness(intercept: dict[str, Any]) -> float:
    commodity = _clean_text(intercept.get("commodity"))
    grade, _unit = _canonical_grade_and_unit(intercept, commodity)
    return round(float(intercept["width_m"]) * grade, 4)


def _depth_category(depth_m: Any) -> str:
    try:
        depth = float(depth_m)
    except (TypeError, ValueError):
        return "unknown"
    if depth <= SHALLOW_DEPTH_MAX_M:
        return "shallow"
    if depth <= MEDIUM_DEPTH_MAX_M:
        return "medium"
    return "deep"


def _historical_intercepts(
    session: Session,
    stock_code: str | None,
    commodity: str,
    unit: str,
) -> list[ComparableIntercept]:
    q = (
        session.query(Announcement, Stock)
        .join(Stock, Announcement.stock_id == Stock.id)
        .filter(Announcement.ai_metrics.isnot(None))
    )
    if stock_code is not None:
        q = q.filter(Stock.code == stock_code)
    rows = q.order_by(Announcement.ann_date.asc(), Announcement.id.asc()).all()

    comparable: list[ComparableIntercept] = []
    for row, stock in rows:
        data = _loads_metrics(row.ai_metrics)
        if not data:
            continue
        project = _clean_project(data.get("project"))
        region = _clean_region(data)
        for item in _iter_intercepts(data):
            if _clean_text(item.get("commodity")) != commodity:
                continue
            try:
                _grade, canonical_unit = _canonical_grade_and_unit(item, commodity)
                if canonical_unit != unit:
                    continue
                grade_thickness = _grade_thickness(item)
            except (KeyError, TypeError, ValueError):
                continue
            comparable.append(
                ComparableIntercept(
                    grade_thickness=grade_thickness,
                    project=project,
                    region=region,
                    stock_code=stock.code,
                    commodity=commodity,
                    unit=unit,
                    announcement_id=row.id,
                )
            )
    return comparable


def _loads_metrics(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _iter_intercepts(metrics: dict[str, Any]) -> Iterable[dict[str, Any]]:
    intercepts = metrics.get("intercepts")
    if not isinstance(intercepts, list):
        return []
    return [item for item in intercepts if isinstance(item, dict)]


def _percentile(value: float, history: list[float], min_samples: int) -> float | None:
    if len(history) < min_samples:
        return None
    count = sum(1 for item in history if item <= value)
    return round(100 * count / len(history), 1)


def _trend_vs_previous(value: float, history: list[float]) -> str:
    if len(history) < MIN_TREND_HISTORY:
        return "insufficient_history"
    baseline = median(history[-MAX_TREND_HISTORY:])
    if baseline <= 0:
        return "insufficient_history"
    ratio = value / baseline
    if ratio >= 1.15:
        return "improving"
    if ratio <= 0.85:
        return "deteriorating"
    return "flat"


def _trend_history(company_values: list[float], project_values: list[float]) -> tuple[list[float], str]:
    if len(project_values) >= MIN_TREND_HISTORY:
        return project_values, "project"
    if len(company_values) >= MIN_TREND_HISTORY:
        return company_values, "company"
    return [], "insufficient_history"


def _interval_quality_label(
    project_percentile: float | None,
    company_percentile: float | None,
    regional_percentile: float | None,
    grade_thickness: float,
    depth_category: str,
) -> str:
    if project_percentile is not None:
        if project_percentile >= 90:
            return "exceptional"
        if project_percentile >= 70:
            return "strong"
        if project_percentile >= 40:
            return "moderate"
        return "weak"

    if company_percentile is not None:
        if company_percentile >= 90:
            return "exceptional"
        if company_percentile >= 70:
            return "strong"
        if company_percentile >= 40:
            return "moderate"
        return "weak"

    if regional_percentile is not None:
        if regional_percentile >= 90:
            return "exceptional"
        if regional_percentile >= 70:
            return "strong"
        if regional_percentile >= 40:
            return "moderate"
        return "weak"

    return "insufficient_history"

def _materiality_label(
    quality: str,
    depth_category: str,
    project_percentile: float | None,
    company_percentile: float | None,
    regional_percentile: float | None,
    ann_type: str | None = None,
    price_sensitive: bool | None = None,
) -> str:
    if quality == "insufficient_history":
        return "insufficient_history"
    is_drill_result = (ann_type or "").upper() == "DRILL_RESULTS"
    reference_percentile = (
        project_percentile
        if project_percentile is not None
        else company_percentile
        if company_percentile is not None
        else regional_percentile
    )
    if (
        quality in {"exceptional", "strong"}
        and reference_percentile is not None
        and reference_percentile >= 75
        and depth_category != "deep"
        and is_drill_result
        and price_sensitive is True
    ):
        return "high"
    if quality in {"strong", "moderate", "insufficient_history"}:
        return "medium"
    return "low"


def _qualitative_assessment(
    quality: str,
    materiality: str,
    project_percentile: float | None,
    company_percentile: float | None,
    regional_percentile: float | None,
    depth_category: str,
) -> str:
    if quality == "insufficient_history":
        return (
            "There is not enough stored comparable company or project history to assess "
            "whether this interval ranks strongly or weakly in context."
        )
    if project_percentile is None:
        if company_percentile is None:
            return (
                "Stored company and project history are insufficient; within the comparable stored regional history, "
                f"this interval ranks as {quality}, with grade-thickness in the {regional_percentile:g}th "
                f"percentile, {depth_category} depth, and {materiality} materiality."
            )
        return (
            "Stored project history is insufficient; within the company's comparable stored history, "
            f"this interval ranks as {quality}, with grade-thickness in the {company_percentile:g}th "
            f"percentile, {depth_category} depth, and {materiality} materiality."
        )
    return (
        f"Within the stored project history, this interval ranks as {quality}, with grade-thickness "
        f"in the {project_percentile:g}th percentile, {depth_category} depth, and {materiality} materiality."
    )


def _same_project(left: str | None, right: str | None) -> bool:
    return bool(left and right and left.casefold() == right.casefold())


def _same_region(left: str | None, right: str | None) -> bool:
    return bool(left and right and left.casefold() == right.casefold())


def _clean_project(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _clean_region(metrics: dict[str, Any]) -> str | None:
    for key in ("region", "district", "area"):
        text = str(metrics.get(key) or "").strip()
        if text:
            return text
    return None


def _clean_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normal_unit(value: Any) -> str:
    return str(value or "").strip().lower()


def _missing_fields(intercept: dict[str, Any], project: str | None, region: str | None) -> list[str]:
    missing = []
    if project is None:
        missing.append("project")
    if region is None:
        missing.append("region")
    if intercept.get("depth_m") is None:
        missing.append("depth_m")
    return missing


def _comparison_warnings(
    source_unit: str,
    normalized_unit: str,
    company_percentile: float | None,
    project_percentile: float | None,
    regional_percentile: float | None,
    trend: str,
    trend_basis: str,
    missing_fields: list[str],
) -> list[str]:
    warnings = []
    if source_unit and source_unit != normalized_unit:
        warnings.append(f"unit normalized from {source_unit} to {normalized_unit}")
    if "region" in missing_fields:
        warnings.append("regional context unavailable because region is missing")
    elif regional_percentile is None:
        warnings.append("regional history insufficient")
    if project_percentile is None:
        warnings.append("project history insufficient")
    if company_percentile is None:
        warnings.append("company history insufficient")
    if trend == "insufficient_history":
        warnings.append("trend history insufficient")
    elif trend_basis != "project":
        warnings.append(f"trend uses {trend_basis} history because project history is insufficient")
    return warnings


def _canonical_grade_and_unit(intercept: dict[str, Any], commodity: str) -> tuple[float, str]:
    grade = float(intercept["grade"])
    unit = _normal_unit(intercept.get("unit"))
    unit = unit.replace(" ", "")
    if unit in {"%", "percent", "pct"}:
        return grade, "%"
    if unit == "ppm":
        if commodity in {"gold", "silver"}:
            return grade, "g/t"
        return grade / 10_000, "%"
    if unit == "ppb":
        return grade / 1_000, "g/t"
    if unit in {"g/t", "gpt", "gt"}:
        return grade, "g/t"
    return grade, unit
