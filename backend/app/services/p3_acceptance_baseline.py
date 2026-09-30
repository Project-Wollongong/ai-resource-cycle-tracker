"""Deterministic measurements for the fixed P03 acceptance sample set.

The baseline counts persisted parser output.  It never pads a document to the
20-50 coverage target and never treats atomic components as separate logical
claims when they belong to the same Information Point.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from ..models import P3Fact, P3InformationPoint, P3ParseRun
from .p3_information_point_service import SUMMARY_SECTIONS, information_point_summary


BASELINE_SCHEMA_VERSION = "p03-fixed-sample-baseline-v2"

# These are the deterministic extraction-floor fields used by the P03 tests.
# They are intentionally fact types, not the broader editorial fields in the
# Stage 0 review sheet.  Missing values are reported, never synthesized.
REQUIRED_FACT_TYPES: dict[str, set[str]] = {
    "S01": {"study_type", "dfs_completion", "original_timing", "timeline_change", "fid_timing", "capex_review"},
    "S02": {"reporting_period", "cash_balance", "operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "development_spend"},
    "S03": {"funding_amount", "funding_method", "issue_price", "new_securities_issued", "spp_limit", "use_of_funds"},
    "S04": {"reported_increase", "tonnage", "grade", "contained_metal", "classification", "mine_life", "first_ore_timing"},
    "S05": {"hole_id", "interval_length", "grade", "from_depth", "true_width", "resource_estimate_target", "cash_balance"},
    "S06": {"permit_type", "permit_status", "permit_identifier", "area", "expiry_date", "authority"},
    "S07": {"transaction_type", "earn_in_amount", "earn_in_percentage", "maximum_ownership", "current_ownership", "manager"},
    "S08": set(),
    "S09": {"testwork_type", "recovery", "product_grade", "processing_route", "sample_count", "drilling_status"},
    "S10": {"permit_type", "permit_status"},
}


def measure_fixed_sample(session: Session, sample: dict[str, Any], run: P3ParseRun) -> dict[str, Any]:
    """Measure one persisted parse run at Fact and Information Point grain."""
    facts = session.query(P3Fact).filter_by(parse_run_id=run.id).order_by(P3Fact.id).all()
    points = session.query(P3InformationPoint).filter_by(parse_run_id=run.id).order_by(P3InformationPoint.id).all()
    summary = information_point_summary(points, len(facts))
    output_summary = _json_dict(run.output_summary_json)
    extraction = output_summary.get("fact_extraction", {}) if isinstance(output_summary, dict) else {}

    source_counts = Counter(_source_bucket(point.source_section) for point in points)
    fact_types = {fact.fact_type for fact in facts}
    required = REQUIRED_FACT_TYPES.get(sample["sample_id"], set())
    rule_missing = sorted(extraction.get("remaining_missing_fields", []))
    required_missing = sorted(required - fact_types)

    project_counts = Counter(fact.project.name for fact in facts if fact.project is not None)
    asset_counts: Counter[tuple[str, str]] = Counter(
        (fact.asset_unit.name, fact.asset_unit.project.name)
        for fact in facts if fact.asset_unit is not None
    )
    company_facts = [fact for fact in facts if fact.project_id is None and fact.asset_unit_id is None]
    attribution_status_counts = Counter(fact.project_attribution_status for fact in facts)

    measured = {
        "sample_id": sample["sample_id"],
        "ticker": sample["ticker"],
        "headline": sample["headline"],
        "announcement_id": sample["asx_announcement_id"],
        "parse_status": run.status,
        "atomic_fact_count": len(facts),
        "information_point_count": len(points),
        "summary_information_point_count": source_counts["summary"],
        "table_information_point_count": source_counts["table"],
        "body_fallback_information_point_count": source_counts["body_fallback"],
        "other_information_point_count": source_counts["other"],
        "review_needed_count": sum(point.review_status == "review_needed" for point in points),
        "review_needed_atomic_fact_count": sum(fact.review_status == "review_needed" for fact in facts),
        "count_status": summary["count_status"],
        "source_insufficient": summary["source_insufficient"],
        "summary_coverage_ratio": summary["summary_coverage_ratio"],
        "unfound_fields": {
            "family_rule_slots": rule_missing,
            "required_fact_types": required_missing,
        },
        "required_fact_types": sorted(required),
        "extracted_fact_types": sorted(fact_types),
        "attribution": {
            "projects": [
                {"project": name, "atomic_fact_count": count}
                for name, count in sorted(project_counts.items())
            ],
            "asset_units": [
                {"asset_unit": name, "project": project, "atomic_fact_count": count}
                for (name, project), count in sorted(asset_counts.items())
            ],
            "company_level_atomic_fact_count": len(company_facts),
            "status_counts": dict(sorted(attribution_status_counts.items())),
        },
        "reconciliation": {
            "grouped_atomic_fact_count": sum(point.fact_count for point in points),
            "all_atomic_facts_grouped": sum(point.fact_count for point in points) == len(facts),
            "source_point_count": sum(source_counts.values()),
            "all_points_source_counted": sum(source_counts.values()) == len(points),
        },
    }
    return measured


def build_fixed_sample_baseline(
    measurements: list[dict[str, Any]], *, parser_version: str, extractor_version: str
) -> dict[str, Any]:
    """Build the stable, serializable baseline contract."""
    ordered = sorted(measurements, key=lambda item: int(item["sample_id"][1:]))
    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "status": "automated_baseline_pending_human_signoff",
        "parser_version": parser_version,
        "extractor_version": extractor_version,
        "counting_policy": {
            "atomic_fact": "one persisted P3Fact row",
            "information_point": "one source-grounded logical claim composed of one or more atomic Facts",
            "review_needed": "logical Information Points whose review_status is review_needed",
            "summary": sorted(SUMMARY_SECTIONS),
            "table": ["standard_form"],
            "body_fallback": ["body", "body_fallback"],
            "target_range": [20, 50],
            "target_is_not_a_quota": True,
            "no_padding": True,
            "no_truncation": True,
        },
        "sample_count": len(ordered),
        "samples": ordered,
    }


def compare_fixed_sample_baseline(actual: dict[str, Any], expected: dict[str, Any]) -> list[dict[str, Any]]:
    """Return field-level drift without hiding additions or missing samples."""
    comparable_fields = (
        "parse_status",
        "atomic_fact_count", "information_point_count", "summary_information_point_count",
        "table_information_point_count", "body_fallback_information_point_count",
        "other_information_point_count", "review_needed_count", "review_needed_atomic_fact_count",
        "count_status", "source_insufficient", "summary_coverage_ratio", "unfound_fields",
        "required_fact_types", "extracted_fact_types", "attribution", "reconciliation",
        "fixture_sha256_verified",
    )
    actual_by_id = {item["sample_id"]: item for item in actual.get("samples", [])}
    expected_by_id = {item["sample_id"]: item for item in expected.get("samples", [])}
    drift: list[dict[str, Any]] = []
    for sample_id in sorted(set(actual_by_id) | set(expected_by_id), key=lambda item: int(item[1:])):
        if sample_id not in actual_by_id or sample_id not in expected_by_id:
            drift.append({"sample_id": sample_id, "field": "sample", "expected": expected_by_id.get(sample_id), "actual": actual_by_id.get(sample_id)})
            continue
        for field in comparable_fields:
            if actual_by_id[sample_id].get(field) != expected_by_id[sample_id].get(field):
                drift.append({
                    "sample_id": sample_id,
                    "field": field,
                    "expected": expected_by_id[sample_id].get(field),
                    "actual": actual_by_id[sample_id].get(field),
                })
    return drift


def _source_bucket(source_section: str | None) -> str:
    if source_section in SUMMARY_SECTIONS:
        return "summary"
    if source_section == "standard_form":
        return "table"
    if source_section in {"body", "body_fallback"}:
        return "body_fallback"
    return "other"


def _json_dict(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
