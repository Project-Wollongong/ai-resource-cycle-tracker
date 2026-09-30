"""Human-review boundary for fuzzy/model entity mapping suggestions."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import (
    Announcement, AssetUnit, CommodityRelationship, EntityMapping,
    EntityMappingChangeLog, EntityMention, P3Event, P3Fact, Project, Stock,
)
from .entity_exact_matcher import EntityCandidate
from .entity_validation_service import validate_candidate


def record_model_suggestion(
    session: Session,
    mention: EntityMention,
    *,
    matched_entity_type: str,
    matched_entity_id: int,
    confidence: float,
    model_name: str,
    model_version: str,
    reasoning: str,
) -> EntityMapping:
    """Persist a model recommendation without granting it any write authority."""
    if confidence < 0 or confidence > 1:
        raise ValueError("confidence must be between 0 and 1")
    if matched_entity_type != mention.mention_type:
        raise ValueError("suggested entity type must match the mention type")
    locked = session.query(EntityMapping).filter_by(
        entity_mention_id=mention.id, status="confirmed"
    ).all()
    if any(mapping_is_human_locked(row) for row in locked):
        raise ValueError("an existing human-confirmed mapping is locked")
    candidate = _candidate(session, matched_entity_type, matched_entity_id)
    announcement = session.get(Announcement, mention.announcement_id)
    if announcement is None:
        raise ValueError("mention announcement not found")
    target = _target(session, mention)
    project_ids = {
        value for value in (
            getattr(target, "mapped_project_id", None), getattr(target, "project_id", None)
        ) if value
    }
    valid, stock_result, parent_result, validation_reason = validate_candidate(
        session, announcement, candidate, [candidate], project_ids, set()
    )
    existing = session.query(EntityMapping).filter_by(
        entity_mention_id=mention.id,
        matched_entity_type=matched_entity_type,
        matched_entity_id=matched_entity_id,
        match_method="model_suggestion",
    ).filter(EntityMapping.status.in_(["review_needed", "ambiguous", "confirmed"])).first()
    if existing:
        return existing
    mapping = EntityMapping(
        entity_mention_id=mention.id,
        matched_entity_type=matched_entity_type,
        matched_entity_id=matched_entity_id,
        match_method="model_suggestion",
        match_confidence=confidence,
        status="review_needed",
        stock_validation_result=stock_result,
        parent_validation_result=parent_result,
        matching_reason=(
            f"Model suggestion only; human confirmation required. {reasoning.strip()} "
            f"Validation: {validation_reason}"
        ).strip(),
        candidate_parent_project_id=candidate.project_id,
        candidate_payload_json=json.dumps({
            "model_name": model_name,
            "model_version": model_version,
            "model_confidence": confidence,
            "model_reasoning": reasoning,
            "validation_passed": valid,
            "automatic_confirmation": False,
        }, ensure_ascii=False),
    )
    session.add(mapping)
    session.flush()
    return mapping


def review_entity_mapping(
    session: Session,
    mapping: EntityMapping,
    *,
    action: str,
    reviewer: str,
    review_note: str,
    corrected_entity_type: str | None = None,
    corrected_entity_id: int | None = None,
) -> EntityMapping:
    """Confirm/reject a suggestion while retaining every prior mapping row."""
    if mapping.status not in {"review_needed", "ambiguous"}:
        raise ValueError("only pending or ambiguous mappings can be reviewed")
    if not reviewer.strip() or not review_note.strip():
        raise ValueError("reviewer and review_note are required")
    mention = session.get(EntityMention, mapping.entity_mention_id)
    if mention is None:
        raise ValueError("entity mention not found")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    before = _snapshot(mapping)
    if action == "reject":
        mapping.status = "rejected"
        mapping.reviewed_by = reviewer.strip()
        mapping.reviewed_at = now
        mapping.review_note = review_note
        session.add(EntityMappingChangeLog(
            entity_mention_id=mention.id, old_mapping_id=mapping.id, new_mapping_id=None,
            action="reject_suggestion", before_json=json.dumps(before, ensure_ascii=False),
            after_json=json.dumps(_snapshot(mapping), ensure_ascii=False),
            reviewer=reviewer.strip(), review_note=review_note,
        ))
        session.flush()
        return mapping
    if action not in {"confirm", "correct"}:
        raise ValueError("unsupported mapping review action")

    entity_type = corrected_entity_type or mapping.matched_entity_type
    entity_id = corrected_entity_id or mapping.matched_entity_id
    if entity_id is None:
        raise ValueError("a confirmed mapping requires an approved P01 entity")
    if entity_type != mention.mention_type:
        raise ValueError("confirmed entity type must match the mention type")
    candidate = _candidate(session, entity_type, entity_id)
    announcement = session.get(Announcement, mention.announcement_id)
    if announcement is None:
        raise ValueError("mention announcement not found")
    target = _target(session, mention)
    explicit_projects = {
        value for value in (
            getattr(target, "mapped_project_id", None), getattr(target, "project_id", None),
        ) if value
    }
    valid, stock_result, parent_result, reason = validate_candidate(
        session, announcement, candidate, [candidate], explicit_projects, set()
    )
    if not valid:
        raise ValueError(f"Stock/parent validation failed: {reason}")

    existing_confirmed = session.query(EntityMapping).filter_by(
        entity_mention_id=mention.id, status="confirmed"
    ).first()
    if existing_confirmed:
        if existing_confirmed.matched_entity_type == entity_type and existing_confirmed.matched_entity_id == entity_id:
            return existing_confirmed
        if existing_confirmed.match_method in {"manual_confirmation", "p01_proposal_approved"}:
            raise ValueError("an existing human-confirmed mapping is locked")
        existing_confirmed.status = "superseded"

    open_rows = session.query(EntityMapping).filter(
        EntityMapping.entity_mention_id == mention.id,
        EntityMapping.status.in_(["review_needed", "ambiguous"]),
    ).all()
    for row in open_rows:
        row.status = "superseded"
        row.reviewed_by = reviewer.strip()
        row.reviewed_at = now
        row.review_note = review_note
    session.flush()
    confirmed = EntityMapping(
        entity_mention_id=mention.id,
        matched_entity_type=entity_type,
        matched_entity_id=entity_id,
        match_method="manual_confirmation",
        match_confidence=1.0,
        status="confirmed",
        stock_validation_result="human_confirmed_after_stock_validation",
        parent_validation_result=parent_result,
        matching_reason=f"Human confirmed after reviewing suggestion {mapping.id}. {reason}",
        candidate_parent_project_id=candidate.project_id,
        candidate_payload_json=json.dumps({
            "source_mapping_id": mapping.id,
            "source_match_method": mapping.match_method,
            "human_locked": True,
            "automatic_overwrite_allowed": False,
        }, ensure_ascii=False),
        reviewed_by=reviewer.strip(), reviewed_at=now, review_note=review_note,
    )
    session.add(confirmed)
    session.flush()
    _link_target(target, confirmed)
    session.add(EntityMappingChangeLog(
        entity_mention_id=mention.id, old_mapping_id=mapping.id, new_mapping_id=confirmed.id,
        action="manual_confirmation" if action == "confirm" else "manual_correction",
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(_snapshot(confirmed), ensure_ascii=False),
        reviewer=reviewer.strip(), review_note=review_note,
    ))
    session.flush()
    return confirmed


def mapping_is_human_locked(mapping: EntityMapping) -> bool:
    return mapping.status == "confirmed" and (
        mapping.match_method in {"manual_confirmation", "p01_proposal_approved"}
        or mapping.reviewed_by is not None
    )


def _candidate(session: Session, entity_type: str, entity_id: int) -> EntityCandidate:
    if entity_type == "stock":
        row = session.get(Stock, entity_id)
        if row: return EntityCandidate("stock", row.id, row.name, row.name, "model_suggestion", 0.0)
    elif entity_type == "project":
        row = session.get(Project, entity_id)
        if row: return EntityCandidate("project", row.id, row.name, row.name, "model_suggestion", 0.0, project_id=row.id)
    elif entity_type == "asset_unit":
        row = session.get(AssetUnit, entity_id)
        if row: return EntityCandidate("asset_unit", row.id, row.name, row.name, "model_suggestion", 0.0, project_id=row.project_id, parent_asset_unit_id=row.parent_asset_unit_id)
    elif entity_type == "commodity":
        row = session.get(CommodityRelationship, entity_id)
        if row:
            project_id = row.project_id or (row.asset_unit.project_id if row.asset_unit else None)
            return EntityCandidate("commodity", row.id, row.commodity, row.commodity, "model_suggestion", 0.0, project_id=project_id)
    raise ValueError("suggested P01 entity not found")


def _target(session: Session, mention: EntityMention):
    return session.get(P3Fact, mention.p3_fact_id) if mention.p3_fact_id else session.get(P3Event, mention.p3_event_id)


def _link_target(target, mapping: EntityMapping) -> None:
    if target is None:
        return
    if mapping.matched_entity_type == "project":
        target.project_id = mapping.matched_entity_id
        target.mapped_project_id = mapping.matched_entity_id
        target.project_mapping_id = mapping.id
        target.project_mapping_status = "confirmed"
    elif mapping.matched_entity_type == "asset_unit":
        target.asset_unit_id = mapping.matched_entity_id
        target.mapped_asset_unit_id = mapping.matched_entity_id
        target.asset_unit_mapping_id = mapping.id
        target.asset_unit_mapping_status = "confirmed"
        if isinstance(target, P3Fact):
            target.project_attribution_status = "confirmed"


def _snapshot(mapping: EntityMapping) -> dict:
    output = {field: getattr(mapping, field) for field in (
        "id", "entity_mention_id", "matched_entity_type", "matched_entity_id", "matched_alias_id",
        "match_method", "match_confidence", "status", "stock_validation_result",
        "parent_validation_result", "matching_reason", "candidate_parent_project_id",
        "proposal_id", "reviewed_by", "reviewed_at", "review_note",
    )}
    if output["reviewed_at"] is not None:
        output["reviewed_at"] = output["reviewed_at"].isoformat()
    return output
