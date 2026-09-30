"""Conservative P03 Event/Fact/Statement versioning with human-confirmed effects."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import (
    Announcement, AnnouncementVersionRelation, P3Event, P3Fact, P3Statement,
    P3VersionRelation, P3VersionRelationChangeLog,
)
from .p3_revision_marker import relation_type_for


OBJECT_MODELS = {"event": P3Event, "fact": P3Fact, "statement": P3Statement}
SUPERSEDING_TYPES = {"corrects", "restates", "revises", "replaces", "supersedes"}
WITHDRAWING_TYPES = {"withdraws", "retracts"}
EFFECTIVE_TYPES = SUPERSEDING_TYPES | WITHDRAWING_TYPES
ALLOWED_RELATION_TYPES = EFFECTIVE_TYPES | {"related_to"}
GENERIC_TITLES = {"update", "results", "project", "positive", "significant"}
PERIODIC_FACT_TYPES = {
    "cash_balance", "cash_receipts", "operating_cash_flow", "investing_cash_flow",
    "financing_cash_flow", "exploration_spend", "development_spend", "administration_spend",
    "production", "revenue", "cost", "reporting_period",
}


def detect_version_relation_candidates(
    session: Session,
    announcement: Announcement,
    events: list[P3Event],
    facts: list[P3Fact],
    statements: list[P3Statement] | None = None,
) -> list[P3VersionRelation]:
    """Propose source-grounded links only; never changes object validity."""
    statements = statements or []
    detection_text = " ".join(filter(None, [
        announcement.headline, announcement.official_header_type, announcement.official_subtype,
        announcement.standard_form,
        *(getattr(row, "source_excerpt", "") or "" for row in [*events, *facts, *statements]),
    ]))
    announcement_relation = session.query(AnnouncementVersionRelation).filter_by(
        successor_announcement_id=announcement.id,
    ).filter(AnnouncementVersionRelation.status.in_(["pending_review", "confirmed"])).order_by(AnnouncementVersionRelation.id.desc()).first()
    detected_type = _normalise_relation_type(
        relation_type_for(detection_text)
        or (announcement_relation.relation_type if announcement_relation else None)
    )
    if detected_type is None or announcement.headline.casefold().strip() in GENERIC_TITLES:
        return []

    predecessor_announcement_id = announcement_relation.predecessor_announcement_id if announcement_relation else None
    if predecessor_announcement_id is None:
        return []
    predecessor_announcement = session.get(Announcement, predecessor_announcement_id)
    if predecessor_announcement is None or predecessor_announcement.stock_id != announcement.stock_id:
        return []

    proposals: list[P3VersionRelation] = []
    for successor in facts:
        predecessor = _matching_fact(session, predecessor_announcement_id, successor, detected_type)
        if predecessor:
            proposals.append(_create_candidate(session, "fact", predecessor, successor, detected_type, announcement))
    for successor in events:
        predecessor = _matching_event(session, predecessor_announcement_id, successor)
        if predecessor:
            proposals.append(_create_candidate(session, "event", predecessor, successor, detected_type, announcement))
    for successor in statements:
        predecessor = _matching_statement(session, predecessor_announcement_id, successor)
        if predecessor:
            proposals.append(_create_candidate(session, "statement", predecessor, successor, detected_type, announcement))
    if detected_type in WITHDRAWING_TYPES and not any(row.predecessor_type == "fact" for row in proposals):
        source = facts[0] if facts else events[0] if events else statements[0] if statements else None
        predecessor = _withdrawal_fact_target(session, predecessor_announcement_id, announcement, events, facts, statements)
        if predecessor and source:
            proposals.append(_create_withdrawal_candidate(session, predecessor, source, detected_type, announcement))
    if not proposals and events:
        previous_events = session.query(P3Event).filter_by(announcement_id=predecessor_announcement_id).order_by(P3Event.id.desc()).all()
        if len(previous_events) == 1:
            proposals.append(_create_candidate(session, "event", previous_events[0], events[0], detected_type, announcement))
    session.flush()
    return proposals


def review_version_relation(
    session: Session,
    relation: P3VersionRelation,
    action: str,
    reviewer: str,
    review_note: str,
    changes: dict | None = None,
) -> P3VersionRelation:
    if not reviewer.strip() or not review_note.strip():
        raise ValueError("reviewer and review_note are required")
    if action not in {"confirm", "reject", "correct"}:
        raise ValueError("unsupported version-relation review action")
    before = relation_snapshot(relation)
    affected_before = _relation_object_keys(relation)

    if action == "correct":
        _apply_changes(session, relation, changes or {})
    elif action == "confirm":
        _validate_relation(session, relation)
        if relation.relation_type in EFFECTIVE_TYPES:
            conflict = session.query(P3VersionRelation).filter(
                P3VersionRelation.id != relation.id,
                P3VersionRelation.predecessor_type == relation.predecessor_type,
                P3VersionRelation.predecessor_id == relation.predecessor_id,
                P3VersionRelation.status == "confirmed",
                P3VersionRelation.relation_type.in_(EFFECTIVE_TYPES),
            ).first()
            if conflict:
                raise ValueError(f"predecessor already has confirmed effective relation {conflict.id}")
        relation.status = "confirmed"
    else:
        relation.status = "rejected"

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    relation.reviewed_by = reviewer.strip()
    relation.reviewed_at = now
    relation.review_note = review_note.strip()
    session.flush()
    affected = affected_before | _relation_object_keys(relation)
    for object_type, object_id in affected:
        recompute_validity(session, object_type, object_id)
    after = relation_snapshot(relation)
    session.add(P3VersionRelationChangeLog(
        relation_id=relation.id, action=action,
        before_json=json.dumps(before, ensure_ascii=False, default=str),
        after_json=json.dumps(after, ensure_ascii=False, default=str),
        reviewer=reviewer.strip(), review_note=review_note.strip(),
    ))
    session.flush()
    return relation


def recompute_validity(session: Session, object_type: str, object_id: int) -> None:
    target = get_version_object(session, object_type, object_id)
    if target is None:
        return
    effective_outgoing = None
    if _is_rejected(target):
        target.validity_status = "rejected"
        target.validity_reason = "The extracted object was rejected during human review."
    else:
        effective_outgoing = session.query(P3VersionRelation).filter(
            P3VersionRelation.predecessor_type == object_type,
            P3VersionRelation.predecessor_id == object_id,
            P3VersionRelation.status == "confirmed",
            P3VersionRelation.relation_type.in_(EFFECTIVE_TYPES),
        ).order_by(P3VersionRelation.id.desc()).first()
        if effective_outgoing and effective_outgoing.relation_type in WITHDRAWING_TYPES:
            target.validity_status = "withdrawn"
            target.validity_reason = effective_outgoing.withdrawal_reason or effective_outgoing.review_note or f"Relation {effective_outgoing.id} confirmed."
        elif effective_outgoing:
            target.validity_status = "superseded"
            target.validity_reason = effective_outgoing.review_note or f"Relation {effective_outgoing.id} confirmed."
        elif target.validity_status in {"superseded", "withdrawn", "correction_pending_review", "rejected"}:
            target.validity_status = "current"
            target.validity_reason = ""
    target.validity_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    incoming = session.query(P3VersionRelation).filter(
        P3VersionRelation.successor_type == object_type,
        P3VersionRelation.successor_id == object_id,
        P3VersionRelation.status == "confirmed",
        P3VersionRelation.relation_type.in_(EFFECTIVE_TYPES),
    ).first()
    if incoming and not effective_outgoing and not _is_rejected(target):
        target.validity_status = "current"
        target.validity_reason = f"Current successor in confirmed relation {incoming.id}."


def has_pending_relation(session: Session, object_type: str, object_id: int) -> bool:
    return session.query(P3VersionRelation.id).filter(
        P3VersionRelation.predecessor_type == object_type,
        P3VersionRelation.predecessor_id == object_id,
        P3VersionRelation.status == "proposed",
    ).first() is not None


def get_version_object(session: Session, object_type: str, object_id: int):
    model = OBJECT_MODELS.get(object_type)
    return session.get(model, object_id) if model else None


def relation_snapshot(relation: P3VersionRelation) -> dict:
    return {name: getattr(relation, name) for name in (
        "id", "predecessor_type", "predecessor_id", "successor_type", "successor_id",
        "relation_type", "status", "source_announcement_id", "source_evidence_document_id",
        "source_page_start", "source_page_end", "source_excerpt", "withdrawal_reason",
        "detected_by", "confidence", "reviewed_by", "reviewed_at", "review_note",
    )}


def object_snapshot(target) -> dict | None:
    if target is None:
        return None
    base = {"id": target.id, "validity_status": target.validity_status}
    if isinstance(target, P3Fact):
        base.update({"type": "fact", "fact_type": target.fact_type, "field_name": target.field_name,
                     "value_raw": target.value_raw, "family": target.fact_family,
                     "announcement_id": target.announcement_id, "project_id": target.project_id,
                     "asset_unit_id": target.asset_unit_id})
    elif isinstance(target, P3Event):
        base.update({"type": "event", "event_type": target.event_type, "title": target.event_title,
                     "family": target.primary_family, "announcement_id": target.announcement_id,
                     "project_id": target.project_id, "asset_unit_id": target.asset_unit_id})
    else:
        base.update({"type": "statement", "statement_type": target.statement_type,
                     "value_raw": target.statement_text, "announcement_id": target.announcement_id,
                     "project_id": target.project_id, "asset_unit_id": target.asset_unit_id})
    return base


def _create_candidate(session, object_type, predecessor, successor, relation_type, announcement):
    existing = session.query(P3VersionRelation).filter_by(
        predecessor_type=object_type, predecessor_id=predecessor.id,
        successor_type=object_type, successor_id=successor.id,
        relation_type=relation_type,
    ).first()
    if existing:
        return existing
    page_start = getattr(successor, "source_page_start", None) or getattr(successor, "source_page", None)
    page_end = getattr(successor, "source_page_end", None) or page_start
    excerpt = getattr(successor, "source_excerpt", "") or announcement.headline
    relation = P3VersionRelation(
        predecessor_type=object_type, predecessor_id=predecessor.id,
        successor_type=object_type, successor_id=successor.id,
        relation_type=relation_type, status="proposed",
        source_announcement_id=announcement.id,
        source_evidence_document_id=successor.evidence_document_id,
        source_page_start=page_start, source_page_end=page_end, source_excerpt=excerpt,
        detected_by="rule", confidence=0.9 if object_type == "fact" else 0.75,
    )
    relation.original_suggestion_json = json.dumps({
        "predecessor": object_snapshot(predecessor), "successor": object_snapshot(successor),
        "relation_type": relation_type, "source": "P02 announcement relation + P03 object match",
    }, ensure_ascii=False, default=str)
    session.add(relation); session.flush()
    return relation


def _create_withdrawal_candidate(session, predecessor, source, relation_type, announcement):
    existing = session.query(P3VersionRelation).filter_by(
        predecessor_type="fact", predecessor_id=predecessor.id,
        successor_type=None, successor_id=None, relation_type=relation_type,
        source_announcement_id=announcement.id,
    ).first()
    if existing:
        return existing
    page_start = getattr(source, "source_page_start", None) or getattr(source, "source_page", None)
    relation = P3VersionRelation(
        predecessor_type="fact", predecessor_id=predecessor.id,
        successor_type=None, successor_id=None, relation_type=relation_type, status="proposed",
        source_announcement_id=announcement.id,
        source_evidence_document_id=source.evidence_document_id,
        source_page_start=page_start, source_page_end=getattr(source, "source_page_end", None) or page_start,
        source_excerpt=getattr(source, "source_excerpt", "") or announcement.headline,
        detected_by="rule", confidence=0.8,
    )
    relation.original_suggestion_json = json.dumps({
        "predecessor": object_snapshot(predecessor), "successor": None,
        "relation_type": relation_type, "source": "explicit withdrawal wording",
    }, ensure_ascii=False, default=str)
    session.add(relation); session.flush()
    return relation


def _matching_fact(session, predecessor_announcement_id, successor, relation_type):
    rows = session.query(P3Fact).filter_by(
        announcement_id=predecessor_announcement_id, stock_id=successor.stock_id,
        fact_type=successor.fact_type,
    ).order_by(P3Fact.id.desc()).all()
    for row in rows:
        if not _same_entity_context(row, successor):
            continue
        if successor.fact_type in PERIODIC_FACT_TYPES:
            same_period = (row.period_start, row.period_end, row.as_of_date) == (
                successor.period_start, successor.period_end, successor.as_of_date,
            )
            if not same_period:
                continue
        return row
    return None


def _matching_event(session, predecessor_announcement_id, successor):
    rows = session.query(P3Event).filter_by(
        announcement_id=predecessor_announcement_id, stock_id=successor.stock_id,
        event_type=successor.event_type, primary_family=successor.primary_family,
    ).order_by(P3Event.id.desc()).all()
    return next((row for row in rows if _same_entity_context(row, successor)), None)


def _matching_statement(session, predecessor_announcement_id, successor):
    rows = session.query(P3Statement).filter_by(
        announcement_id=predecessor_announcement_id, stock_id=successor.stock_id,
        statement_type=successor.statement_type,
    ).order_by(P3Statement.id.desc()).all()
    return next((row for row in rows if _same_entity_context(row, successor)), None)


def _withdrawal_fact_target(session, predecessor_announcement_id, announcement, events, facts, statements):
    text = " ".join([
        announcement.headline,
        *(getattr(row, "source_excerpt", "") or "" for row in [*events, *facts, *statements]),
    ]).casefold()
    rows = session.query(P3Fact).filter_by(announcement_id=predecessor_announcement_id).order_by(P3Fact.id.desc()).all()
    matched = []
    for row in rows:
        phrases = {row.fact_type.replace("_", " ").casefold(), row.field_name.casefold()}
        if any(phrase and phrase in text for phrase in phrases):
            matched.append(row)
    return matched[0] if len(matched) == 1 else None


def _same_entity_context(old, new):
    for field in ("project_id", "asset_unit_id"):
        old_value, new_value = getattr(old, field, None), getattr(new, field, None)
        if old_value is not None and new_value is not None and old_value != new_value:
            return False
    return True


def _normalise_relation_type(value):
    if value == "amends":
        return "revises"
    return value if value in ALLOWED_RELATION_TYPES else None


def _validate_relation(session, relation):
    if relation.relation_type not in ALLOWED_RELATION_TYPES:
        raise ValueError("invalid relation_type")
    predecessor = get_version_object(session, relation.predecessor_type, relation.predecessor_id)
    if predecessor is None:
        raise ValueError("predecessor object not found")
    if relation.relation_type in WITHDRAWING_TYPES:
        if relation.successor_id is not None and get_version_object(session, relation.successor_type, relation.successor_id) is None:
            raise ValueError("successor object not found")
        return
    if relation.successor_id is None or relation.successor_type is None:
        raise ValueError("this relation type requires a successor")
    successor = get_version_object(session, relation.successor_type, relation.successor_id)
    if successor is None:
        raise ValueError("successor object not found")
    if relation.relation_type in SUPERSEDING_TYPES and relation.predecessor_type != relation.successor_type:
        raise ValueError("corrective relation must connect the same object type")
    if predecessor.id == successor.id and relation.predecessor_type == relation.successor_type:
        raise ValueError("predecessor and successor must differ")


def _apply_changes(session, relation, changes):
    allowed = {
        "predecessor_type", "predecessor_id", "successor_type", "successor_id", "relation_type",
        "source_page_start", "source_page_end", "source_excerpt", "withdrawal_reason",
    }
    for field, value in changes.items():
        if field not in allowed:
            raise ValueError(f"unsupported relation correction field: {field}")
        setattr(relation, field, value)
    _validate_relation(session, relation)


def _relation_object_keys(relation):
    keys = {(relation.predecessor_type, relation.predecessor_id)}
    if relation.successor_type and relation.successor_id:
        keys.add((relation.successor_type, relation.successor_id))
    return keys


def _is_rejected(target):
    if isinstance(target, P3Fact):
        return target.review_status == "rejected"
    if isinstance(target, P3Event):
        return target.classification_status == "rejected"
    return getattr(target, "review_status", None) == "rejected"
