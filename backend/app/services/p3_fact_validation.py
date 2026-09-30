"""Boundary validation for deterministic P03 facts."""
from __future__ import annotations


RESOURCE_CLASSES = {"Measured", "Indicated", "Inferred"}
RESERVE_CLASSES = {"Proved", "Probable"}
VALID_STATUSES = {
    "reported", "planned", "targeted", "estimated", "forecast", "completed", "pending",
    "applied", "granted", "committed", "received", "withdrawn", "amended",
    "historical_reference", "conditional", "technical_support", "effective", "unknown",
}


def validate_candidate(candidate: dict) -> list[str]:
    errors: list[str] = []
    if not candidate.get("source_page_start"):
        errors.append("missing_source_page")
    if not candidate.get("source_excerpt"):
        errors.append("missing_source_excerpt")
    if not candidate.get("value_raw"):
        errors.append("missing_value_raw")
    if candidate.get("status") not in VALID_STATUSES:
        errors.append("invalid_status")
    classification = candidate.get("metadata", {}).get("classification")
    kind = candidate.get("metadata", {}).get("resource_or_reserve_type")
    if candidate.get("metadata", {}).get("conflicts_with_title") or candidate.get("metadata", {}).get("conflicts_with_summary") or candidate.get("metadata", {}).get("source_value_conflict"):
        errors.append("source_value_conflict")
    if kind == "Mineral Resource" and classification in RESERVE_CLASSES:
        errors.append("reserve_class_on_resource")
    if kind == "Ore Reserve" and classification in RESOURCE_CLASSES:
        errors.append("resource_class_on_reserve")
    if candidate.get("fact_type") == "cash_runway":
        errors.append("derived_p04_metric")
    return errors
