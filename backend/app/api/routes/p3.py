import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, object_session

from ...models import Announcement, AssetUnit, AssetUnitIdentity, CommodityRelationship, EntityMapping, EntityMention, EvidenceDocument, P3Event, P3Fact, P3FactReview, P3InformationPoint, P3ParseRun, P3Statement, P3VersionRelation, Project, ProjectIdentity, Stock, StockIdentity
from ...schemas import P3EventOut, P3FactOut, P3InformationPointOut, P3ParseRunOut
from ...services.p3_family_rules import FAMILY_NAMES, FAMILY_ORDER
from ...services.p3_information_point_service import information_point_summary
from ...services.p3_parse_service import PARSER_VERSION, parse_evidence
from ...services.p3_versioning_service import get_version_object, has_pending_relation, object_snapshot
from ..deps import get_db

router = APIRouter(tags=["p3-parsing"])


def _announcement(announcement_id: str, db: Session):
    row = db.query(Announcement).filter_by(ann_id=announcement_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="announcement not found")
    return row


@router.get("/announcements/{announcement_id}/parse-status")
def parse_status(announcement_id: str, db: Session = Depends(get_db)):
    announcement = _announcement(announcement_id, db)
    evidence = db.query(EvidenceDocument).filter_by(announcement_id=announcement.id).order_by(EvidenceDocument.id.desc()).first()
    latest = db.query(P3ParseRun).filter_by(announcement_id=announcement.id).order_by(P3ParseRun.id.desc()).first()
    events = _effective_events(db, announcement.id)
    facts = _effective_facts(db, announcement.id)
    points = _effective_information_points(db, announcement.id)
    point_summary = information_point_summary(points, len(facts))
    output_summary = _json_object(latest.output_summary_json) if latest else {}
    extraction_audit = output_summary.get("fact_extraction", {})
    grouping_audit = output_summary.get("information_point_grouping", {})
    return {
        "announcement_id": announcement_id,
        "has_evidence": evidence is not None,
        "evidence_id": evidence.id if evidence else None,
        "parse_status": latest.status if latest else "unparsed",
        "latest_parse_run": P3ParseRunOut.model_validate(latest) if latest else None,
        "event_count": len(events),
        "fact_count": len(facts),
        **point_summary,
        "review_needed": any(event.review_needed for event in events) or bool(latest and latest.status == "review_needed"),
        "error_message": latest.error_message if latest else None,
        "fact_extraction": extraction_audit if isinstance(extraction_audit, dict) else {},
        "information_point_grouping": grouping_audit if isinstance(grouping_audit, dict) else {},
    }


@router.get("/announcements/{announcement_id}/events", response_model=list[P3EventOut])
def announcement_events(
    announcement_id: str, all_versions: bool = False, current_only: bool = True,
    include_historical: bool = False, include_superseded: bool = False,
    include_withdrawn: bool = False, include_rejected: bool = False,
    db: Session = Depends(get_db),
):
    announcement = _announcement(announcement_id, db)
    if all_versions:
        rows = db.query(P3Event).filter_by(announcement_id=announcement.id).order_by(P3Event.id).all()
    else:
        rows = _effective_events(db, announcement.id, current_validity_only=(
            current_only and not any((include_historical, include_superseded, include_withdrawn, include_rejected))
        ))
    if not all_versions:
        rows = [row for row in rows if _validity_visible(row, current_only, include_historical, include_superseded, include_withdrawn, include_rejected)]
    return [_event_out(row, db) for row in rows]


@router.get("/p3/events", response_model=list[P3EventOut])
def list_p3_events(
    current_only: bool = True, include_historical: bool = False, include_superseded: bool = False,
    include_withdrawn: bool = False, include_rejected: bool = False, stock_id: int | None = None,
    family: str | None = None, db: Session = Depends(get_db),
):
    query = db.query(P3Event)
    if stock_id is not None: query = query.filter(P3Event.stock_id == stock_id)
    if family: query = query.filter(P3Event.primary_family == family)
    if current_only:
        announcement_ids = [item[0] for item in query.with_entities(P3Event.announcement_id).filter(P3Event.announcement_id.is_not(None)).distinct().all()]
        include_noncurrent = any((include_historical, include_superseded, include_withdrawn, include_rejected))
        rows = [row for announcement_id in announcement_ids for row in _effective_events(db, announcement_id, current_validity_only=not include_noncurrent)]
        if stock_id is not None: rows = [row for row in rows if row.stock_id == stock_id]
        if family: rows = [row for row in rows if row.primary_family == family]
    else:
        rows = query.order_by(P3Event.id.desc()).limit(2000).all()
    rows = [row for row in rows if _validity_visible(row, current_only, include_historical, include_superseded, include_withdrawn, include_rejected)]
    return [_event_out(row, db) for row in rows]


@router.get("/p3/events/{event_id}", response_model=P3EventOut)
def event_detail(event_id: int, db: Session = Depends(get_db)):
    event = db.get(P3Event, event_id)
    if event is None: raise HTTPException(status_code=404, detail="P3 event not found")
    return _event_out(event, db)


@router.get("/p3/events/{event_id}/history")
def event_history(event_id: int, db: Session = Depends(get_db)):
    event = db.get(P3Event, event_id)
    if event is None: raise HTTPException(status_code=404, detail="P3 event not found")
    relations = db.query(P3VersionRelation).filter(
        ((P3VersionRelation.predecessor_type == "event") & (P3VersionRelation.predecessor_id == event.id))
        | ((P3VersionRelation.successor_type == "event") & (P3VersionRelation.successor_id == event.id))
    ).order_by(P3VersionRelation.id).all()
    ids = {event.id}
    for relation in relations:
        if relation.predecessor_type == "event": ids.add(relation.predecessor_id)
        if relation.successor_type == "event" and relation.successor_id: ids.add(relation.successor_id)
    versions = db.query(P3Event).filter(P3Event.id.in_(ids)).order_by(P3Event.id).all()
    return {"event_id": event.id, "versions": [_event_out(row, db) for row in versions],
            "version_relations": [_version_relation_public_out(db, row) for row in relations]}


@router.get("/announcements/{announcement_id}/entity-mappings")
def announcement_entity_mappings(announcement_id: str, db: Session = Depends(get_db)):
    announcement = _announcement(announcement_id, db)
    latest = db.query(P3ParseRun).filter_by(announcement_id=announcement.id).order_by(P3ParseRun.id.desc()).first()
    if latest is None:
        return []
    rows = db.query(EntityMapping).join(EntityMention).filter(
        EntityMention.announcement_id == announcement.id,
        EntityMention.parse_run_id == latest.id,
    ).order_by(EntityMention.id, EntityMapping.id).all()
    return [_entity_mapping_out(db, row, include_candidate=False) for row in rows]


@router.get("/p3/events/{event_id}/entity-mappings")
def event_entity_mappings(event_id: int, db: Session = Depends(get_db)):
    if db.get(P3Event, event_id) is None:
        raise HTTPException(status_code=404, detail="P3 event not found")
    rows = db.query(EntityMapping).join(EntityMention).filter(EntityMention.p3_event_id == event_id).order_by(EntityMention.id, EntityMapping.id).all()
    return [_entity_mapping_out(db, row, include_candidate=False) for row in rows]


@router.get("/p3/facts/{fact_id}/entity-mappings")
def fact_entity_mappings(fact_id: int, db: Session = Depends(get_db)):
    if db.get(P3Fact, fact_id) is None:
        raise HTTPException(status_code=404, detail="P3 fact not found")
    rows = db.query(EntityMapping).join(EntityMention).filter(EntityMention.p3_fact_id == fact_id).order_by(EntityMention.id, EntityMapping.id).all()
    return [_entity_mapping_out(db, row, include_candidate=False) for row in rows]


@router.get("/announcements/{announcement_id}/classification-summary")
def classification_summary(announcement_id: str, db: Session = Depends(get_db)):
    announcement = _announcement(announcement_id, db)
    latest = db.query(P3ParseRun).filter_by(announcement_id=announcement.id).order_by(P3ParseRun.id.desc()).first()
    events = _effective_events(db, announcement.id)
    revisions = list(dict.fromkeys(_json_list(announcement.revision_tags_json) + [tag for event in events for tag in _json_list(event.revision_tags_json)]))
    families = [family for family in FAMILY_ORDER if any(event.primary_family == family for event in events)]
    return {
        "document_category": announcement.document_category,
        "official_header_type": announcement.official_header_type,
        "official_subtype": announcement.official_subtype,
        "standard_form": announcement.standard_form,
        "event_families": [{"code": family, "name": FAMILY_NAMES.get(family, family)} for family in families],
        "event_tags": list(dict.fromkeys(event.event_type for event in events if event.primary_family != "OTHER")),
        "revision_tags": revisions,
        "parse_status": latest.status if latest else "unparsed",
        "review_needed": any(event.review_needed for event in events) or bool(latest and latest.status == "review_needed"),
    }


@router.get("/announcements/{announcement_id}/facts", response_model=list[P3FactOut])
def announcement_facts(
    announcement_id: str,
    family: str | None = None,
    event_id: int | None = None,
    project_id: int | None = None,
    asset_unit_id: int | None = None,
    fact_type: str | None = None,
    information_point_group_id: int | None = None,
    information_point_type: str | None = None,
    review_status: str | None = None,
    latest_parse_run_only: bool = True,
    current_only: bool = True,
    include_historical: bool = False,
    include_superseded: bool = False,
    include_withdrawn: bool = False,
    include_rejected: bool = False,
    db: Session = Depends(get_db),
):
    announcement = _announcement(announcement_id, db)
    query = db.query(P3Fact).filter(P3Fact.announcement_id == announcement.id)
    if family: query = query.filter(P3Fact.fact_family == family)
    if event_id is not None: query = query.filter(P3Fact.p3_event_id == event_id)
    if project_id is not None: query = query.filter(P3Fact.project_id == project_id)
    if asset_unit_id is not None: query = query.filter(P3Fact.asset_unit_id == asset_unit_id)
    if fact_type: query = query.filter(P3Fact.fact_type == fact_type)
    if information_point_group_id is not None: query = query.filter(P3Fact.information_point_group_id == information_point_group_id)
    if information_point_type: query = query.filter(P3Fact.information_point_type == information_point_type)
    if review_status: query = query.filter(P3Fact.review_status == review_status)
    rows = query.order_by(P3Fact.id).all()
    if latest_parse_run_only:
        rows = _effective_facts(db, announcement.id, rows, current_validity_only=(
            current_only and not any((include_historical, include_superseded, include_withdrawn, include_rejected))
        ))
    rows = [row for row in rows if _validity_visible(
        row, current_only, include_historical, include_superseded, include_withdrawn, include_rejected
    )]
    if information_point_group_id is not None:
        rows.sort(key=lambda row: (row.display_order if row.display_order is not None else 999, row.id))
    return [_fact_out(db, row) for row in rows]


@router.get("/p3/facts", response_model=list[P3FactOut])
def list_p3_facts(
    current_only: bool = True, include_historical: bool = False, include_superseded: bool = False,
    include_withdrawn: bool = False, include_rejected: bool = False, stock_id: int | None = None,
    family: str | None = None, fact_type: str | None = None, db: Session = Depends(get_db),
):
    query = db.query(P3Fact)
    if stock_id is not None: query = query.filter(P3Fact.stock_id == stock_id)
    if family: query = query.filter(P3Fact.fact_family == family)
    if fact_type: query = query.filter(P3Fact.fact_type == fact_type)
    if current_only:
        announcement_ids = [item[0] for item in query.with_entities(P3Fact.announcement_id).filter(P3Fact.announcement_id.is_not(None)).distinct().all()]
        include_noncurrent = any((include_historical, include_superseded, include_withdrawn, include_rejected))
        rows = [row for announcement_id in announcement_ids for row in _effective_facts(db, announcement_id, current_validity_only=not include_noncurrent)]
        if stock_id is not None: rows = [row for row in rows if row.stock_id == stock_id]
        if family: rows = [row for row in rows if row.fact_family == family]
        if fact_type: rows = [row for row in rows if row.fact_type == fact_type]
    else:
        rows = query.order_by(P3Fact.id.desc()).limit(5000).all()
    rows = [row for row in rows if _validity_visible(row, current_only, include_historical, include_superseded, include_withdrawn, include_rejected)]
    return [_fact_out(db, row) for row in rows]


@router.get("/p3/statements")
def list_p3_statements(
    current_only: bool = True, include_historical: bool = False, include_superseded: bool = False,
    include_withdrawn: bool = False, include_rejected: bool = False, stock_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(P3Statement)
    if stock_id is not None: query = query.filter(P3Statement.stock_id == stock_id)
    rows = [row for row in query.order_by(P3Statement.id.desc()).limit(5000).all()
            if _validity_visible(row, current_only, include_historical, include_superseded, include_withdrawn, include_rejected)]
    return [_statement_out(db, row) for row in rows]


@router.get("/p3/facts/{fact_id}", response_model=P3FactOut)
def fact_detail(fact_id: int, db: Session = Depends(get_db)):
    fact = db.get(P3Fact, fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail="P3 fact not found")
    return _fact_out(db, fact)


@router.get("/p3/facts/{fact_id}/history")
def fact_history(fact_id: int, db: Session = Depends(get_db)):
    fact = db.get(P3Fact, fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail="P3 fact not found")
    versions = db.query(P3Fact).filter(
        P3Fact.announcement_id == fact.announcement_id,
        P3Fact.fact_family == fact.fact_family,
        P3Fact.fact_type == fact.fact_type,
        P3Fact.field_name == fact.field_name,
    ).order_by(P3Fact.id).all()
    reviews = db.query(P3FactReview).filter(P3FactReview.p3_fact_id.in_([row.id for row in versions])).order_by(P3FactReview.id).all() if versions else []
    relations = db.query(P3VersionRelation).filter(
        ((P3VersionRelation.predecessor_type == "fact") & (P3VersionRelation.predecessor_id == fact.id))
        | ((P3VersionRelation.successor_type == "fact") & (P3VersionRelation.successor_id == fact.id))
    ).order_by(P3VersionRelation.id).all()
    related_ids = {fact.id}
    for relation in relations:
        if relation.predecessor_type == "fact": related_ids.add(relation.predecessor_id)
        if relation.successor_type == "fact" and relation.successor_id: related_ids.add(relation.successor_id)
    related_versions = db.query(P3Fact).filter(P3Fact.id.in_(related_ids)).order_by(P3Fact.id).all()
    return {
        "fact_id": fact.id,
        "versions": [_fact_out(db, row) for row in sorted({row.id: row for row in [*versions, *related_versions]}.values(), key=lambda row: row.id)],
        "version_relations": [_version_relation_public_out(db, row) for row in relations],
        "reviews": [{"id": row.id, "p3_fact_id": row.p3_fact_id, "action": row.action, "before_json": row.before_json, "after_json": row.after_json, "reviewer": row.reviewer, "review_note": row.review_note, "created_at": row.created_at} for row in reviews],
        "superseded_by_id": fact.superseded_by_id,
    }


@router.get("/announcements/{announcement_id}/information-points", response_model=list[P3InformationPointOut])
def announcement_information_points(
    announcement_id: str,
    family: str | None = None,
    information_point_type: str | None = None,
    source_section: str | None = None,
    review_status: str | None = None,
    latest_parse_run_only: bool = True,
    db: Session = Depends(get_db),
):
    announcement = _announcement(announcement_id, db)
    query = db.query(P3InformationPoint).filter(P3InformationPoint.announcement_id == announcement.id)
    if family: query = query.filter(P3InformationPoint.family == family)
    if information_point_type: query = query.filter(P3InformationPoint.point_type == information_point_type)
    if source_section: query = query.filter(P3InformationPoint.source_section == source_section)
    if review_status: query = query.filter(P3InformationPoint.review_status == review_status)
    rows = query.order_by(P3InformationPoint.id).all()
    if latest_parse_run_only:
        effective_ids = {point.id for point in _effective_information_points(db, announcement.id)}
        rows = [point for point in rows if point.id in effective_ids]
    return [_information_point_out(point) for point in rows]


@router.get("/announcements/{announcement_id}/information-point-summary")
def announcement_information_point_summary(announcement_id: str, db: Session = Depends(get_db)):
    announcement = _announcement(announcement_id, db)
    points = _effective_information_points(db, announcement.id)
    facts = _effective_facts(db, announcement.id)
    return information_point_summary(points, len(facts))


@router.post("/evidence/{evidence_id}/parse", response_model=P3ParseRunOut)
def parse_evidence_endpoint(evidence_id: int, parser_version: str | None = None, db: Session = Depends(get_db)):
    evidence = db.get(EvidenceDocument, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="evidence document not found")
    return parse_evidence(db, evidence, parser_version or PARSER_VERSION)


@router.get("/evidence/{evidence_id}/parse-runs", response_model=list[P3ParseRunOut])
def parse_runs(evidence_id: int, db: Session = Depends(get_db)):
    if db.get(EvidenceDocument, evidence_id) is None:
        raise HTTPException(status_code=404, detail="evidence document not found")
    return db.query(P3ParseRun).filter_by(evidence_document_id=evidence_id).order_by(P3ParseRun.id.desc()).all()


def _effective_events(db: Session, announcement_pk: int, current_validity_only: bool = True) -> list[P3Event]:
    runs = db.query(P3ParseRun).filter_by(announcement_id=announcement_pk).order_by(P3ParseRun.id.desc()).all()
    latest = next((run for run in runs if run.status in {"parsed", "partial", "review_needed"}), None)
    reviewed = db.query(P3Event).filter(
        P3Event.announcement_id == announcement_pk,
        P3Event.classification_status.in_(["confirmed", "corrected", "rejected"]),
    ).order_by(P3Event.id.desc()).all()
    reviewed_by_key = {}
    for event in reviewed:
        reviewed_by_key.setdefault(_event_key(event), event)
    output = [event for event in reviewed_by_key.values() if event.active_result and event.classification_status != "rejected"]
    if latest:
        for event in db.query(P3Event).filter_by(parse_run_id=latest.id, active_result=True).order_by(P3Event.id).all():
            if event.classification_status != "rejected" and _event_key(event) not in reviewed_by_key:
                output.append(event)
    if current_validity_only:
        output = [event for event in output if event.validity_status in {"current", "correction_pending_review"}]
    return sorted(output, key=lambda event: event.id)


def _event_key(event: P3Event):
    return event.primary_family, event.event_type, event.project_id, event.asset_unit_id


def _event_out(event: P3Event, db: Session | None = None) -> dict:
    db = db or object_session(event)
    pending = bool(db and has_pending_relation(db, "event", event.id))
    visible_project = event.mapped_project if event.project_mapping_status == "confirmed" else (event.project if event.project_mapping_status == "unknown" else None)
    visible_asset = event.mapped_asset_unit if event.asset_unit_mapping_status == "confirmed" else (event.asset_unit if event.asset_unit_mapping_status == "unknown" else None)
    return {
        "id": event.id,
        "event_id": event.id,
        "announcement_id": event.announcement_id,
        "evidence_document_id": event.evidence_document_id,
        "parse_run_id": event.parse_run_id,
        "stock_id": event.stock_id,
        "project_id": visible_project.id if visible_project else None,
        "asset_unit_id": visible_asset.id if visible_asset else None,
        "mapped_project_id": event.mapped_project_id,
        "mapped_asset_unit_id": event.mapped_asset_unit_id,
        "project_mapping_id": event.project_mapping_id,
        "asset_unit_mapping_id": event.asset_unit_mapping_id,
        "project_mapping_status": event.project_mapping_status,
        "asset_unit_mapping_status": event.asset_unit_mapping_status,
        "event_type": event.event_type,
        "event_family": event.event_family,
        "primary_family": event.primary_family,
        "secondary_families": _json_list(event.secondary_families_json),
        "event_title": event.event_title,
        "event_status": event.event_status,
        "classification_status": event.classification_status,
        "classification_source": event.classification_source,
        "classification_confidence": event.classification_confidence,
        "revision_tags": _json_list(event.revision_tags_json),
        "classification_reason": event.classification_reason,
        "active_result": event.active_result,
        "validity_status": event.validity_status,
        "display_validity_status": "correction_pending_review" if pending and event.validity_status == "current" else event.validity_status,
        "validity_reason": event.validity_reason,
        "has_pending_version_relation": pending,
        "source_section": event.source_section,
        "source_page_start": event.source_page_start,
        "source_page_end": event.source_page_end,
        "source_page": event.source_page_start,
        "source_excerpt": event.source_excerpt,
        "confidence": event.confidence,
        "occurred_on": event.occurred_on,
        "reported_on": event.reported_on,
        "created_at": event.created_at,
        "project": {"id": visible_project.id, "name": visible_project.name, "project_key": visible_project.project_key} if visible_project else None,
        "asset_unit": {"id": visible_asset.id, "name": visible_asset.name} if visible_asset else None,
        "review_needed": event.review_needed,
    }


def _effective_facts(
    db: Session, announcement_pk: int, rows: list[P3Fact] | None = None,
    current_validity_only: bool = True,
) -> list[P3Fact]:
    rows = rows if rows is not None else db.query(P3Fact).filter_by(announcement_id=announcement_pk).order_by(P3Fact.id).all()
    latest = db.query(P3ParseRun).filter(
        P3ParseRun.announcement_id == announcement_pk,
        P3ParseRun.status.in_(["parsed", "partial", "review_needed"]),
    ).order_by(P3ParseRun.id.desc()).first()
    reviewed = [row for row in rows if row.review_status in {"confirmed", "rejected"}]
    reviewed_by_key: dict[tuple, P3Fact] = {}
    for row in sorted(reviewed, key=lambda item: item.id, reverse=True):
        reviewed_by_key.setdefault(_fact_key(row), row)
    output = [row for row in reviewed_by_key.values() if row.active_result and row.review_status != "rejected"]
    if latest:
        for row in rows:
            if row.parse_run_id == latest.id and row.active_result and row.review_status != "rejected" and _fact_key(row) not in reviewed_by_key:
                output.append(row)
    if current_validity_only:
        output = [item for item in output if item.validity_status in {"current", "correction_pending_review"}]
    return sorted(output, key=lambda item: item.id)


def _fact_key(fact: P3Fact) -> tuple:
    return (fact.fact_family, fact.fact_type, fact.field_name, fact.project_id, fact.asset_unit_id, fact.value_raw, fact.source_page_start)


def _fact_out(db: Session, fact: P3Fact) -> dict:
    event = fact.event or (db.get(P3Event, fact.p3_event_id) if fact.p3_event_id else None)
    stock = db.get(Stock, fact.stock_id) if fact.stock_id else None
    evidence = db.get(EvidenceDocument, fact.evidence_document_id)
    visible_project = fact.mapped_project if fact.project_mapping_status == "confirmed" else (fact.project if fact.project_mapping_status == "unknown" else None)
    visible_asset = fact.mapped_asset_unit if fact.asset_unit_mapping_status == "confirmed" else (fact.asset_unit if fact.asset_unit_mapping_status == "unknown" else None)
    pending = has_pending_relation(db, "fact", fact.id)
    return {
        "id": fact.id, "event_id": fact.p3_event_id, "announcement_id": fact.announcement_id,
        "evidence_document_id": fact.evidence_document_id, "parse_run_id": fact.parse_run_id,
        "stock_id": fact.stock_id,
        "project_id": visible_project.id if visible_project else None,
        "asset_unit_id": visible_asset.id if visible_asset else None,
        "mapped_project_id": fact.mapped_project_id, "mapped_asset_unit_id": fact.mapped_asset_unit_id,
        "project_mapping_id": fact.project_mapping_id, "asset_unit_mapping_id": fact.asset_unit_mapping_id,
        "project_mapping_status": fact.project_mapping_status, "asset_unit_mapping_status": fact.asset_unit_mapping_status,
        "family": fact.fact_family, "fact_type": fact.fact_type, "field_name": fact.field_name,
        "value_raw": fact.value_raw or "", "value_numeric": fact.value_numeric, "value_text": fact.value_text,
        "unit_raw": fact.unit_raw, "unit_normalized": fact.unit_normalized,
        "currency_raw": fact.currency_raw, "currency_normalized": fact.currency_normalized,
        "quantity_type": fact.quantity_type, "period_start": fact.period_start, "period_end": fact.period_end,
        "as_of_date": fact.as_of_date, "effective_date": fact.effective_date, "status": fact.status,
        "project_attribution_status": fact.project_attribution_status, "source_section": fact.source_section,
        "source_page_start": fact.source_page_start, "source_page_end": fact.source_page_end,
        "source_page": fact.source_page_start or fact.source_page, "source_excerpt": fact.source_excerpt or "",
        "extractor_name": fact.extractor_name, "extractor_version": fact.extractor_version,
        "extraction_confidence": fact.extraction_confidence, "review_status": fact.review_status,
        "validity_status": fact.validity_status,
        "display_validity_status": "correction_pending_review" if pending and fact.validity_status == "current" else fact.validity_status,
        "validity_reason": fact.validity_reason,
        "has_pending_version_relation": pending,
        "active_result": fact.active_result, "superseded_by_id": fact.superseded_by_id,
        "information_point_group_id": fact.information_point_group_id,
        "information_point_type": fact.information_point_type,
        "parent_fact_id": fact.parent_fact_id, "display_order": fact.display_order,
        "event": {"id": event.id, "event_type": event.event_type, "event_title": event.event_title, "family": event.primary_family} if event else None,
        "stock": {"id": stock.id, "code": stock.code, "name": stock.name} if stock else None,
        "project": {"id": visible_project.id, "name": visible_project.name, "project_key": visible_project.project_key} if visible_project else None,
        "asset_unit": {"id": visible_asset.id, "name": visible_asset.name} if visible_asset else None,
        "evidence_document": {"id": evidence.id, "title": evidence.title, "source_url": evidence.source_url or evidence.url, "page_count": evidence.page_count} if evidence else None,
        "created_at": fact.created_at, "updated_at": fact.updated_at,
    }


def _statement_out(db: Session, statement: P3Statement) -> dict:
    pending = has_pending_relation(db, "statement", statement.id)
    return {
        "id": statement.id, "announcement_id": statement.announcement_id,
        "evidence_document_id": statement.evidence_document_id, "event_id": statement.p3_event_id,
        "parse_run_id": statement.parse_run_id, "stock_id": statement.stock_id,
        "project_id": statement.project_id, "asset_unit_id": statement.asset_unit_id,
        "statement_type": statement.statement_type, "statement_text": statement.statement_text,
        "source_page": statement.source_page, "source_excerpt": statement.source_excerpt,
        "confidence": statement.confidence, "extractor_version": statement.extractor_version,
        "review_status": statement.review_status, "validity_status": statement.validity_status,
        "display_validity_status": "correction_pending_review" if pending and statement.validity_status == "current" else statement.validity_status,
        "validity_reason": statement.validity_reason, "has_pending_version_relation": pending,
        "created_at": statement.created_at,
    }


def _validity_visible(row, current_only, include_historical, include_superseded, include_withdrawn, include_rejected):
    status = getattr(row, "validity_status", "current") or "current"
    intrinsically_rejected = getattr(row, "review_status", None) == "rejected" or getattr(row, "classification_status", None) == "rejected"
    if intrinsically_rejected or status == "rejected":
        return include_rejected
    if not current_only:
        return True
    if status == "current" or status == "correction_pending_review":
        return True
    return (
        (status == "historical" and include_historical)
        or (status == "superseded" and include_superseded)
        or (status == "withdrawn" and include_withdrawn)
    )


def _version_relation_public_out(db: Session, relation: P3VersionRelation) -> dict:
    announcement = db.get(Announcement, relation.source_announcement_id)
    return {
        "id": relation.id, "predecessor_type": relation.predecessor_type,
        "predecessor_id": relation.predecessor_id, "successor_type": relation.successor_type,
        "successor_id": relation.successor_id, "relation_type": relation.relation_type,
        "status": relation.status, "source_announcement_id": relation.source_announcement_id,
        "source_evidence_document_id": relation.source_evidence_document_id,
        "source_page_start": relation.source_page_start, "source_page_end": relation.source_page_end,
        "source_excerpt": relation.source_excerpt, "withdrawal_reason": relation.withdrawal_reason,
        "detected_by": relation.detected_by, "confidence": relation.confidence,
        "reviewed_by": relation.reviewed_by, "reviewed_at": relation.reviewed_at,
        "review_note": relation.review_note,
        "predecessor": object_snapshot(get_version_object(db, relation.predecessor_type, relation.predecessor_id)),
        "successor": object_snapshot(get_version_object(db, relation.successor_type, relation.successor_id)) if relation.successor_type and relation.successor_id else None,
        "source_announcement": {"ann_id": announcement.ann_id, "headline": announcement.headline,
                                "url": announcement.url} if announcement else None,
    }


def _effective_information_points(db: Session, announcement_pk: int) -> list[P3InformationPoint]:
    latest = db.query(P3ParseRun).filter(
        P3ParseRun.announcement_id == announcement_pk,
        P3ParseRun.status.in_(["parsed", "partial", "review_needed"]),
    ).order_by(P3ParseRun.id.desc()).first()
    if latest is None:
        return []
    points = db.query(P3InformationPoint).filter_by(parse_run_id=latest.id, active_result=True).order_by(P3InformationPoint.id).all()
    return [point for point in points if any(
        link.fact.validity_status in {"current", "correction_pending_review"}
        and link.fact.review_status != "rejected"
        for link in point.fact_links
    )]


def _information_point_out(point: P3InformationPoint) -> dict:
    visible_links = [link for link in point.fact_links if
                     link.fact.validity_status in {"current", "correction_pending_review"}
                     and link.fact.review_status != "rejected"]
    primary_link = next((link for link in visible_links if link.role == "primary"), None)
    return {
        "id": point.id, "event_id": point.event_id, "announcement_id": point.announcement_id,
        "evidence_document_id": point.evidence_document_id, "parse_run_id": point.parse_run_id,
        "stock_id": point.stock_id, "project_id": point.project_id, "asset_unit_id": point.asset_unit_id,
        "family": point.family, "point_type": point.point_type, "point_title": point.point_title,
        "information_point_group_id": point.id, "information_point_type": point.point_type,
        "primary_fact_id": primary_link.p3_fact_id if primary_link else None,
        "fact_count": len(visible_links), "status": point.status, "source_section": point.source_section,
        "source_page_start": point.source_page_start, "source_page_end": point.source_page_end,
        "source_excerpt": point.source_excerpt, "review_status": point.review_status,
        "active_result": point.active_result, "superseded_by_id": point.superseded_by_id,
        "facts": [{
            "id": link.fact.id, "fact_type": link.fact.fact_type, "field_name": link.fact.field_name,
            "value_raw": link.fact.value_raw, "unit_raw": link.fact.unit_raw, "status": link.fact.status,
            "role": link.role, "display_order": link.display_order,
            "information_point_group_id": link.fact.information_point_group_id,
            "information_point_type": link.fact.information_point_type,
            "parent_fact_id": link.fact.parent_fact_id,
        } for link in visible_links],
        "project": {"id": point.project.id, "name": point.project.name, "project_key": point.project.project_key} if point.project else None,
        "asset_unit": {"id": point.asset_unit.id, "name": point.asset_unit.name} if point.asset_unit else None,
        "created_at": point.created_at,
    }


def _json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def _json_object(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _entity_mapping_out(db: Session, mapping: EntityMapping, include_candidate: bool = False) -> dict:
    mention = mapping.mention or db.get(EntityMention, mapping.entity_mention_id)
    entity = _mapped_entity(db, mapping)
    alias = _mapped_alias(db, mapping)
    visible = entity if mapping.status == "confirmed" else None
    output = {
        "id": mapping.id,
        "entity_mention_id": mapping.entity_mention_id,
        "announcement_id": mention.announcement_id,
        "evidence_document_id": mention.evidence_document_id,
        "parse_run_id": mention.parse_run_id,
        "p3_event_id": mention.p3_event_id,
        "p3_fact_id": mention.p3_fact_id,
        "mention_type": mention.mention_type,
        "mention_text_raw": mention.mention_text_raw,
        "mention_text_normalized": mention.mention_text_normalized,
        "source_section": mention.source_section,
        "source_page_start": mention.source_page_start,
        "source_page_end": mention.source_page_end,
        "source_page": mention.source_page_start,
        "source_excerpt": mention.source_excerpt,
        "matched_entity_type": mapping.matched_entity_type,
        "matched_entity_id": mapping.matched_entity_id if mapping.status == "confirmed" else None,
        "matched_entity": visible,
        "matched_alias": alias,
        "match_method": mapping.match_method,
        "match_confidence": mapping.match_confidence,
        "status": mapping.status,
        "stock_validation_result": mapping.stock_validation_result,
        "parent_validation_result": mapping.parent_validation_result,
        "matching_reason": mapping.matching_reason,
        "candidate_parent_project_id": mapping.candidate_parent_project_id,
        "proposal_id": mapping.proposal_id,
        "candidate_payload": _json_object(mapping.candidate_payload_json),
        "review_needed": mapping.status in {"review_needed", "ambiguous"},
        "reviewed_by": mapping.reviewed_by,
        "reviewed_at": mapping.reviewed_at,
        "review_note": mapping.review_note,
        "human_locked": mapping.status == "confirmed" and (
            mapping.match_method in {"manual_confirmation", "p01_proposal_approved"}
            or mapping.reviewed_by is not None
        ),
        "created_at": mapping.created_at,
        "updated_at": mapping.updated_at,
    }
    if include_candidate:
        output["candidate_entity"] = entity
        output["candidate_entity_id"] = mapping.matched_entity_id
    return output


def _mapped_entity(db: Session, mapping: EntityMapping) -> dict | None:
    if mapping.matched_entity_id is None:
        return None
    if mapping.matched_entity_type == "stock":
        row = db.get(Stock, mapping.matched_entity_id)
        return {"id": row.id, "type": "stock", "name": row.name, "code": row.code} if row else None
    if mapping.matched_entity_type == "project":
        row = db.get(Project, mapping.matched_entity_id)
        return {"id": row.id, "type": "project", "name": row.name, "project_key": row.project_key} if row else None
    if mapping.matched_entity_type == "asset_unit":
        row = db.get(AssetUnit, mapping.matched_entity_id)
        return {"id": row.id, "type": "asset_unit", "name": row.name, "project_id": row.project_id} if row else None
    row = db.get(CommodityRelationship, mapping.matched_entity_id)
    return {"id": row.id, "type": "commodity", "name": row.commodity, "project_id": row.project_id, "asset_unit_id": row.asset_unit_id} if row else None


def _mapped_alias(db: Session, mapping: EntityMapping) -> dict | None:
    if mapping.matched_alias_id is None:
        return None
    model = {"stock": StockIdentity, "project": ProjectIdentity, "asset_unit": AssetUnitIdentity}.get(mapping.matched_entity_type)
    row = db.get(model, mapping.matched_alias_id) if model else None
    return {"id": row.id, "value": row.value, "kind": row.kind, "is_current": row.is_current} if row else None
