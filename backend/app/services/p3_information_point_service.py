"""Group atomic P3Fact rows into source-grounded logical information points.

Information points are a counting and presentation layer.  They never invent,
drop, aggregate numerically, or replace their component facts.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict

from sqlalchemy.orm import Session

from ..models import P3Fact, P3InformationPoint, P3InformationPointFact, P3ParseRun


SUMMARY_SECTIONS = {"summary", "highlights", "key_results", "executive_summary"}
DRILL_ORDER = {"hole_id": 0, "interval_length": 1, "grade": 2, "from_depth": 3, "to_depth": 4, "true_width": 5}
RESERVE_ORDER = {"resource_or_reserve_type": 0, "classification": 1, "tonnage": 2, "grade": 3, "contained_metal": 4, "commodity": 5}
TIMELINE_ORDER = {"original_timing": 0, "dfs_completion": 1, "first_ore_timing": 1, "first_production_timing": 1, "timeline_change": 2}
TESTWORK_ORDER = {"testwork_type": 0, "recovery": 1, "product_grade": 2, "sample_count": 3, "sample_type": 4, "processing_route": 5}


def build_information_points(session: Session, run: P3ParseRun, facts: list[P3Fact] | None = None) -> list[P3InformationPoint]:
    existing = session.query(P3InformationPoint).filter_by(parse_run_id=run.id).order_by(P3InformationPoint.id).all()
    if existing:
        _sync_existing_shortcuts(existing)
        session.flush()
        return existing
    facts = facts if facts is not None else session.query(P3Fact).filter_by(parse_run_id=run.id).order_by(P3Fact.id).all()
    groups: dict[str, list[P3Fact]] = defaultdict(list)
    for fact in facts:
        if fact.review_status != "rejected":
            groups[_group_key(fact)].append(fact)
    output: list[P3InformationPoint] = []
    for group_key, members in groups.items():
        point_type = _point_type(members)
        members.sort(key=lambda fact: (_display_order(point_type, fact), fact.id))
        primary = _primary_fact(point_type, members)
        point = P3InformationPoint(
            event_id=primary.p3_event_id,
            announcement_id=run.announcement_id,
            evidence_document_id=run.evidence_document_id,
            parse_run_id=run.id,
            stock_id=primary.stock_id,
            project_id=_single_value(members, "project_id"),
            asset_unit_id=_single_value(members, "asset_unit_id"),
            family=primary.fact_family,
            point_type=point_type,
            point_title=_point_title(point_type, members),
            group_key=group_key,
            fact_count=len(members),
            status=_point_status(members),
            source_section=_source_section(members),
            source_page_start=min(page for page in (fact.source_page_start for fact in members) if page is not None),
            source_page_end=max(page for page in (fact.source_page_end or fact.source_page_start for fact in members) if page is not None),
            source_excerpt=max((fact.source_excerpt or "" for fact in members), key=len),
            review_status="review_needed" if any(fact.review_status == "review_needed" for fact in members) else "proposed",
            metadata_json=json.dumps({
                "definition": "one explicit source claim backed by one or more atomic P3Fact rows",
                "fact_ids": [fact.id for fact in members],
                "primary_fact_id": primary.id,
                "group_schema": "logical_information_point_v2",
                "no_padding": True,
                "no_truncation": True,
            }, ensure_ascii=False),
        )
        session.add(point); session.flush()
        for order, fact in enumerate(members):
            fact.information_point_group_id = point.id
            fact.information_point_type = point_type
            fact.parent_fact_id = None if fact.id == primary.id else primary.id
            fact.display_order = order
            session.add(P3InformationPointFact(
                information_point_id=point.id, p3_fact_id=fact.id,
                role="primary" if fact.id == primary.id else "component", display_order=order,
            ))
        output.append(point)
    session.flush()
    for point in output:
        previous = session.query(P3InformationPoint).filter(
            P3InformationPoint.announcement_id == point.announcement_id,
            P3InformationPoint.parse_run_id != run.id,
            P3InformationPoint.group_key == point.group_key,
            P3InformationPoint.superseded_by_id.is_(None),
        ).order_by(P3InformationPoint.id.desc()).first()
        if previous:
            previous.superseded_by_id = point.id
            previous.active_result = False
    return output


def information_point_summary(points: list[P3InformationPoint], atomic_fact_count: int) -> dict:
    count = len(points)
    summary_count = sum(point.source_section in SUMMARY_SECTIONS for point in points)
    standard_form_count = sum(point.source_section == "standard_form" for point in points)
    body_fallback_count = sum(point.source_section in {"body", "body_fallback"} for point in points)
    count_status = "source_insufficient" if count < 20 else "target_range" if count <= 50 else "high_density"
    return {
        "information_point_count": count,
        "atomic_fact_count": atomic_fact_count,
        "target_min": 20,
        "target_max": 50,
        "count_status": count_status,
        "source_insufficient": count < 20,
        "summary_point_count": summary_count,
        "standard_form_point_count": standard_form_count,
        "body_fallback_point_count": body_fallback_count,
        "review_needed_count": sum(point.review_status == "review_needed" for point in points),
        "summary_coverage_ratio": round(summary_count / count, 4) if count else 0.0,
        "policy": "20-50 is a coverage target; points are never padded or truncated",
    }


def _group_key(fact: P3Fact) -> str:
    metadata = _json_dict(fact.metadata_json)
    interval_group = metadata.get("reported_interval_group")
    source_unit = metadata.get("source_unit")
    source_identity = source_unit if source_unit and not str(source_unit).startswith(("body_fallback:", "standard_form:")) else _excerpt_identity(fact)
    if interval_group:
        semantic = f"{fact.fact_family}|drill_intersection|{interval_group}|{fact.source_page_start}"
    elif fact.fact_family == "F08" and metadata.get("period_basis"):
        semantic = f"{fact.fact_family}|{fact.fact_type}|{metadata['period_basis']}|{fact.period_start}|{fact.period_end}|{fact.source_page_start}"
    elif fact.fact_family == "F04" and fact.fact_type in TIMELINE_ORDER:
        semantic = f"{fact.fact_family}|timeline_change|{source_identity}"
    elif fact.fact_family == "F02" and metadata.get("resource_or_reserve_type"):
        semantic = f"{fact.fact_family}|resource_reserve|{metadata.get('resource_or_reserve_type')}|{metadata.get('classification')}|{source_identity}"
    elif fact.fact_family == "F03" and fact.fact_type in TESTWORK_ORDER:
        semantic = f"{fact.fact_family}|testwork|{source_identity}"
    elif source_unit and not str(source_unit).startswith(("body_fallback:", "standard_form:")):
        semantic = f"{fact.fact_family}|summary_claim|{source_unit}"
    else:
        event_type = fact.event.event_type if fact.event else ""
        semantic = f"{fact.fact_family}|{event_type}|{source_identity}"
    return hashlib.sha256(semantic.encode("utf-8")).hexdigest()


def _point_type(facts: list[P3Fact]) -> str:
    types = {fact.fact_type for fact in facts}
    if "interval_length" in types and "grade" in types:
        return "drill_intersection"
    if "timeline_change" in types or {"dfs_completion", "original_timing"}.issubset(types):
        return "timeline_change"
    if "resource_or_reserve_type" in types or "classification" in types and "tonnage" in types:
        return "resource_reserve_row"
    if any(_json_dict(fact.metadata_json).get("resource_or_reserve_type") for fact in facts):
        return "resource_reserve_summary"
    if {"recovery", "product_grade"}.issubset(types):
        return "metallurgical_test_result"
    family = facts[0].fact_family
    if family == "F04" and types.intersection({"mine_life", "annual_production", "processing_capacity", "throughput"}):
        return "development_parameters"
    if family == "F05" and types.intersection({"area", "expiry_date"}):
        return "permit_scope_and_term"
    if family == "F07" and "transaction_type" in types:
        return "earn_in_summary"
    if family == "F07" and "earn_in_percentage" in types:
        return "earn_in_phase"
    if family == "F07" and "current_ownership" in types:
        return "ownership_structure"
    if family == "F07" and "manager" in types:
        return "management_role"
    if len(types) == 1:
        return next(iter(types))
    priorities = (
        "funding_amount", "cash_balance", "operating_cash_flow", "investing_cash_flow",
        "financing_cash_flow", "reported_increase", "permit_status", "earn_in_amount",
    )
    return next((item for item in priorities if item in types), "reported_claim")


def _point_title(point_type: str, facts: list[P3Fact]) -> str:
    by_type: dict[str, P3Fact] = {}
    for fact in facts:
        by_type.setdefault(fact.fact_type, fact)
    if point_type == "drill_intersection":
        hole = _value(by_type.get("hole_id")); width = _value(by_type.get("interval_length"))
        grade = _value(by_type.get("grade")); depth = _value(by_type.get("from_depth"))
        return f"{hole or 'Drill hole'}: {width or '?'}m @ {grade or '?'}% from {depth or '?'}m"
    if point_type == "timeline_change":
        old = _value(by_type.get("original_timing")); new = _value(by_type.get("dfs_completion"))
        return f"Project schedule changed from {old or 'previous timing'} to {new or 'revised timing'}"
    if point_type == "resource_reserve_row":
        kind = _value(by_type.get("resource_or_reserve_type")) or "Resource / Reserve"
        classification = _value(by_type.get("classification"))
        values = [_display(by_type.get(name)) for name in ("tonnage", "grade", "contained_metal")]
        return " · ".join(item for item in [kind, classification, *values] if item)
    if point_type == "metallurgical_test_result":
        return " · ".join(item for item in (_display(by_type.get("recovery")), _display(by_type.get("product_grade")), _display(by_type.get("sample_count"))) if item)
    if point_type == "development_parameters":
        return " · ".join(_display(fact) for fact in facts)
    if point_type == "permit_scope_and_term":
        return "Permit scope / term · " + " · ".join(_display(fact) for fact in facts)
    if point_type == "earn_in_summary":
        return "Earn-in summary · " + " · ".join(_display(fact) for fact in facts)
    if point_type == "earn_in_phase":
        phase = _json_dict(facts[0].metadata_json).get("phase")
        return f"Earn-in Phase {phase or '?'} · " + " · ".join(_display(fact) for fact in facts)
    if point_type == "ownership_structure":
        return "Current ownership · " + " · ".join(_display(fact) for fact in facts)
    if point_type == "management_role":
        return "Management role · " + " · ".join(_display(fact) for fact in facts)
    if facts[0].fact_family == "F08":
        basis = _json_dict(facts[0].metadata_json).get("period_basis")
        suffix = "Current Quarter" if basis == "current_quarter" else "Year-to-Date" if basis == "year_to_date" else "Period End"
        return f"{_display(facts[0])} · {suffix}"
    return " · ".join(_display(fact) for fact in facts[:3])


def _display(fact: P3Fact | None) -> str:
    if fact is None:
        return ""
    unit = f" {fact.unit_raw}" if fact.unit_raw and fact.unit_raw.casefold() not in fact.value_raw.casefold() else ""
    return f"{fact.field_name}: {fact.value_raw}{unit}"


def _value(fact: P3Fact | None) -> str | None:
    return fact.value_text or fact.value_raw if fact else None


def _point_status(facts: list[P3Fact]) -> str:
    statuses = list(dict.fromkeys(fact.status for fact in facts))
    return statuses[0] if len(statuses) == 1 else "mixed"


def _source_section(facts: list[P3Fact]) -> str:
    sections = list(dict.fromkeys(fact.source_section for fact in facts))
    return sections[0] if len(sections) == 1 else "mixed"


def _single_value(facts: list[P3Fact], field: str):
    values = {getattr(fact, field) for fact in facts if getattr(fact, field) is not None}
    return next(iter(values)) if len(values) == 1 else None


def _excerpt_identity(fact: P3Fact) -> str:
    excerpt = re.sub(r"\s+", " ", (fact.source_excerpt or "").casefold()).strip()
    return f"p{fact.source_page_start}:{excerpt}"


def _display_order(point_type: str, fact: P3Fact) -> int:
    mapping = DRILL_ORDER if point_type == "drill_intersection" else RESERVE_ORDER if point_type == "resource_reserve_row" else TIMELINE_ORDER if point_type == "timeline_change" else TESTWORK_ORDER if point_type == "metallurgical_test_result" else {}
    return mapping.get(fact.fact_type, 50)


def _primary_fact(point_type: str, facts: list[P3Fact]) -> P3Fact:
    preferred = {
        "drill_intersection": "hole_id",
        "resource_reserve_row": "resource_or_reserve_type",
        "timeline_change": "timeline_change",
        "metallurgical_test_result": "testwork_type",
    }.get(point_type)
    return next((fact for fact in facts if fact.fact_type == preferred), facts[0])


def _sync_existing_shortcuts(points: list[P3InformationPoint]) -> None:
    for point in points:
        links = list(point.fact_links)
        primary_link = next((link for link in links if link.role == "primary"), links[0] if links else None)
        if primary_link is None:
            continue
        for link in links:
            link.fact.information_point_group_id = point.id
            link.fact.information_point_type = point.point_type
            link.fact.parent_fact_id = None if link.fact.id == primary_link.fact.id else primary_link.fact.id
            link.fact.display_order = link.display_order


def _json_dict(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
