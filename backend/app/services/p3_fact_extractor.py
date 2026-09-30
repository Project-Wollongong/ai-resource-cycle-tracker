"""Persist versioned P03 reported facts beneath classified events."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ..models import AssetUnit, AssetUnitIdentity, P3Event, P3Fact, P3ParseRun, ProjectIdentity
from .p3_fact_rules import extract_fact_candidates
from .p3_fact_validation import validate_candidate
from .p3_entity_matching import unique_identity_match
from .stock_identity import normalize


_HOLE_ASSET_NAMES = {
    "BCRC": "Bolt Cutter Central", "BCDD": "Bolt Cutter Central",
    "TAMT038": "Hutt", "TAMT040": "Hutt", "TAMT036": "Chewy", "TARC435": "Leia",
}


def extract_and_persist_facts(
    session: Session, run: P3ParseRun, events: list[P3Event], pages: list[str] | None = None,
    sections: list[dict] | None = None, *, candidates: list[dict] | None = None,
) -> list[P3Fact]:
    """Create facts only for this parse run; older facts are never updated or deleted."""
    candidates = candidates if candidates is not None else extract_fact_candidates(events, pages or [], sections or [])
    existing = {
        (row.fact_family, row.fact_type, row.field_name, row.value_raw, row.source_page_start, row.source_excerpt, row.period_start, row.period_end, row.p3_event_id)
        for row in session.query(P3Fact).filter_by(parse_run_id=run.id).all()
    }
    output: list[P3Fact] = []
    for candidate in candidates:
        event = _select_event(events, candidate["fact_family"], candidate.pop("event_type_hint", None))
        if event is None:
            continue
        project_id, asset_unit_id, attribution = _resolve_entities(session, candidate["source_excerpt"], candidate.get("metadata", {}), event)
        errors = validate_candidate(candidate)
        candidate_review_status = candidate.pop("review_status")
        review_status = "review_needed" if errors else candidate_review_status
        metadata = candidate.pop("metadata", {})
        if errors:
            metadata["validation_errors"] = errors
        key = (candidate["fact_family"], candidate["fact_type"], candidate["field_name"], candidate["value_raw"], candidate["source_page_start"], candidate["source_excerpt"], candidate.get("period_start"), candidate.get("period_end"), event.id)
        if key in existing:
            continue
        value_json = json.dumps(
            {"raw": candidate["value_raw"], "numeric": candidate.get("value_numeric"), "text": candidate.get("value_text")},
            ensure_ascii=False,
        )
        fact = P3Fact(
            announcement_id=run.announcement_id,
            evidence_document_id=run.evidence_document_id,
            p3_event_id=event.id,
            parse_run_id=run.id,
            stock_id=event.stock_id,
            project_id=project_id,
            asset_unit_id=asset_unit_id,
            project_attribution_status=attribution,
            schema_name=f"{candidate['fact_family'].casefold()}_reported_fact_v1",
            value_json=value_json,
            unit=candidate.get("unit_raw"),
            confidence=candidate.get("extraction_confidence"),
            source_page=candidate.get("source_page_start"),
            metadata_json=json.dumps(metadata, ensure_ascii=False),
            review_status=review_status,
            validity_status="historical" if candidate.get("status") == "historical_reference" else "current",
            validity_reason="Source explicitly identifies a historical reference." if candidate.get("status") == "historical_reference" else "",
            original_extraction_json=json.dumps({**candidate, "metadata": metadata}, default=str, ensure_ascii=False),
            **candidate,
        )
        session.add(fact)
        output.append(fact)
        existing.add(key)
    session.flush()
    for fact in output:
        previous = session.query(P3Fact).filter(
            P3Fact.announcement_id == fact.announcement_id,
            P3Fact.parse_run_id != run.id,
            P3Fact.fact_family == fact.fact_family,
            P3Fact.fact_type == fact.fact_type,
            P3Fact.field_name == fact.field_name,
            P3Fact.value_raw == fact.value_raw,
            P3Fact.source_page_start == fact.source_page_start,
            P3Fact.source_excerpt == fact.source_excerpt,
            P3Fact.period_start == fact.period_start,
            P3Fact.period_end == fact.period_end,
        ).order_by(P3Fact.id.desc()).first()
        if previous and previous.review_status not in {"confirmed", "rejected"} and previous.superseded_by_id is None:
            previous.superseded_by_id = fact.id
            previous.active_result = False
    return output


def _select_event(events: list[P3Event], family: str, hint: str | None) -> P3Event | None:
    family_events = [event for event in events if event.primary_family == family and event.active_result]
    if not family_events:
        return None
    if hint:
        exact = next((event for event in family_events if event.event_type == hint), None)
        if exact:
            return exact
        hint_words = {word for word in normalize(hint).split() if len(word) > 3}
        ranked = sorted(
            family_events,
            key=lambda event: len(hint_words & set(normalize(event.event_type + " " + event.event_title).split())),
            reverse=True,
        )
        if ranked:
            return ranked[0]
    return family_events[0]


def _resolve_entities(session: Session, excerpt: str, metadata: dict, event: P3Event) -> tuple[int | None, int | None, str]:
    asset_name = None
    hole = str(metadata.get("hole_id") or "").upper()
    if hole:
        asset_name = _HOLE_ASSET_NAMES.get(hole) or next((name for prefix, name in _HOLE_ASSET_NAMES.items() if len(prefix) == 4 and hole.startswith(prefix)), None)
    asset_rows = session.query(AssetUnitIdentity).filter(AssetUnitIdentity.is_current.is_(True)).all()
    asset_identity = next((row for row in asset_rows if asset_name and normalize(row.value) == normalize(asset_name)), None)
    if asset_identity is None:
        asset_identity = unique_identity_match(excerpt, asset_rows, "asset_unit_id")
    if asset_identity:
        asset = session.get(AssetUnit, asset_identity.asset_unit_id)
        if asset and event.project_id and event.project_id != asset.project_id:
            return None, None, "unknown"
        return (asset.project_id if asset else None, asset_identity.asset_unit_id, "confirmed")
    project_identity = unique_identity_match(
        excerpt,
        session.query(ProjectIdentity).filter(ProjectIdentity.is_current.is_(True)).all(),
        "project_id",
    )
    if project_identity:
        return project_identity.project_id, None, "confirmed"
    return None, None, "unknown"
