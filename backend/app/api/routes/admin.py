import json
import re
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from ...database import SessionLocal
from ...models import Announcement, AnnouncementVersionRelation, AssetUnit, AssetUnitIdentity, BackfillRun, BackfillRunItem, CommodityRelationship, EntityMapping, EntityMappingChangeLog, EntityMention, EvidenceDocument, P01EntityProposal, P3Event, P3EventClassificationReview, P3Fact, P3FactReview, P3VersionRelation, P3VersionRelationChangeLog, PipelineRun, PipelineRunItem, Project, ProjectIdentity, ProjectRelationship, Stock
from ...notify.telegram import TelegramNotifier
from ...schemas import AnnouncementVersionRelationCreate, AnnouncementVersionRelationOut, AnnouncementVersionRelationReview, BackfillRequest, BackfillRunRequest, EvidenceDocumentOut, HistoricalBaselineCreate, Message, P01EntityProposalCreate, P01EntityProposalOut, P01EntityProposalReview, P01ProposalCorrection, P01ProposalDecision, P01SourceSearchResult, P3ClassificationReviewOut, P3EntityMappingCorrection, P3EntityMappingReviewAction, P3EntityModelSuggestionCreate, P3EventCorrection, P3EventOut, P3EventReviewAction, P3FactCorrection, P3FactOut, P3FactReviewAction, P3FactReviewOut, P3VersionRelationCorrection, P3VersionRelationReviewAction, PipelineRunItemOut, PipelineRunOut
from .p3 import _entity_mapping_out, _event_out, _fact_out
from ...services.p3_fact_review import apply_review
from ...services.p3_database_consistency_audit import audit_database_consistency
from ...services.p01_proposal_approval_service import review_proposal
from ...services.entity_mapping_review_service import record_model_suggestion, review_entity_mapping
from ...services.p3_versioning_service import get_version_object, object_snapshot, review_version_relation as review_p3_version_relation
from ...services.stock_identity import normalize
from ...services.backfill_service import create_backfill_run, execute_backfill_run, preview_backfill, retry_failed
from ...config import BASE_DIR, settings
from ...services.config_service import get_all_config, set_config
from ...services.historical_evidence_import import import_historical_evidence, validate_historical_pdf
from ...datasources.asx_announcements import AsxJsonAnnouncementSource
from ...datasources.base import SourceBlockedError
from ..deps import get_db
from ..security import require_admin_access

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin_access)])


def _backfill_run_out(row: BackfillRun) -> dict:
    return {
        "id": row.id, "started_at": row.started_at, "finished_at": row.finished_at,
        "status": row.status, "requested_by": row.requested_by, "parser_version": row.parser_version,
        "pipeline_version": row.pipeline_version, "filters": _safe_json(row.filter_snapshot_json, {}),
        "configuration": _safe_json(row.configuration_snapshot_json, {}),
        "total_announcements": row.total_announcements, "succeeded_announcements": row.succeeded_announcements,
        "skipped_announcements": row.skipped_announcements, "partial_announcements": row.partial_announcements,
        "failed_announcements": row.failed_announcements, "downloaded_files": row.downloaded_files,
        "extracted_texts": row.extracted_texts, "parsed_documents": row.parsed_documents,
        "created_events": row.created_events, "created_facts": row.created_facts,
        "mapped_entities": row.mapped_entities, "review_needed_count": row.review_needed_count,
        "error_summary": row.error_summary, "retry_of_run_id": row.retry_of_run_id,
        "cancel_requested": row.cancel_requested, "created_at": row.created_at, "updated_at": row.updated_at,
    }


def _backfill_item_out(row: BackfillRunItem) -> dict:
    return {
        "id": row.id, "backfill_run_id": row.backfill_run_id, "announcement_id": row.announcement_id,
        "stock_id": row.stock_id, "evidence_document_id": row.evidence_document_id,
        "status": row.status, "stage": row.stage, "parser_version": row.parser_version,
        "input_hash": row.input_hash, "created_event_count": row.created_event_count,
        "created_fact_count": row.created_fact_count, "mapped_count": row.mapped_count,
        "review_needed_count": row.review_needed_count, "error_message": row.error_message,
        "started_at": row.started_at, "finished_at": row.finished_at,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }


@router.post("/backfill/preview")
def preview_historical_backfill(payload: BackfillRequest, db: Session = Depends(get_db)):
    try:
        return preview_backfill(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/backfill/run")
def run_historical_backfill(payload: BackfillRunRequest, db: Session = Depends(get_db)):
    values = payload.model_dump(exclude={"preview_token", "requested_by"})
    try:
        run = create_backfill_run(db, values, payload.preview_token, payload.requested_by)
        return _backfill_run_out(execute_backfill_run(db, run))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/backfill/runs")
def list_backfill_runs(limit: int = 50, db: Session = Depends(get_db)):
    return [_backfill_run_out(row) for row in db.query(BackfillRun).order_by(BackfillRun.id.desc()).limit(min(limit, 200)).all()]


@router.get("/backfill/runs/{run_id}")
def get_backfill_run(run_id: int, db: Session = Depends(get_db)):
    row = db.get(BackfillRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="backfill run not found")
    return _backfill_run_out(row)


@router.get("/backfill/runs/{run_id}/items")
def list_backfill_run_items(run_id: int, db: Session = Depends(get_db)):
    if db.get(BackfillRun, run_id) is None:
        raise HTTPException(status_code=404, detail="backfill run not found")
    return [_backfill_item_out(row) for row in db.query(BackfillRunItem).filter_by(backfill_run_id=run_id).order_by(BackfillRunItem.id).all()]


@router.post("/backfill/runs/{run_id}/retry-failed")
def retry_failed_backfill(run_id: int, requested_by: str = "admin", db: Session = Depends(get_db)):
    row = db.get(BackfillRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="backfill run not found")
    try:
        return _backfill_run_out(retry_failed(db, row, requested_by))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/backfill/runs/{run_id}/cancel")
def cancel_backfill(run_id: int, db: Session = Depends(get_db)):
    row = db.get(BackfillRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="backfill run not found")
    if row.status in {"success", "partial", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="backfill run is already terminal")
    row.cancel_requested = True
    if row.status in {"draft", "previewed"}:
        row.status = "cancelled"; row.finished_at = datetime.utcnow()
    db.commit(); db.refresh(row)
    return _backfill_run_out(row)


@router.get("/p3/database-consistency")
def p3_database_consistency(db: Session = Depends(get_db)):
    """Read-only P01/P02/P03 integrity and entity-attribution audit."""
    return audit_database_consistency(db)


@router.get("/p3/entity-mappings/review-needed")
def entity_mappings_review_needed(
    stock_id: int | None = None,
    announcement_id: int | None = None,
    entity_type: str | None = None,
    mention_type: str | None = None,
    family: str | None = None,
    proposal_type: str | None = None,
    parent_project_id: int | None = None,
    status: str | None = None,
    min_supporting_announcements: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(EntityMapping).join(EntityMention).join(Announcement, Announcement.id == EntityMention.announcement_id).filter(
        EntityMapping.status.in_(["review_needed", "ambiguous"]) if status is None else EntityMapping.status == status
    )
    if stock_id is not None:
        query = query.filter(Announcement.stock_id == stock_id)
    if announcement_id is not None:
        query = query.filter(EntityMention.announcement_id == announcement_id)
    requested_mention_type = mention_type or entity_type
    if requested_mention_type:
        query = query.filter(EntityMention.mention_type == requested_mention_type)
    if family:
        query = query.outerjoin(P3Event, P3Event.id == EntityMention.p3_event_id).filter(P3Event.primary_family == family)
    if proposal_type or min_supporting_announcements is not None:
        query = query.outerjoin(P01EntityProposal, P01EntityProposal.id == EntityMapping.proposal_id)
    if proposal_type:
        query = query.filter(P01EntityProposal.proposal_type == proposal_type)
    if parent_project_id is not None:
        query = query.filter(EntityMapping.candidate_parent_project_id == parent_project_id)
    if min_supporting_announcements is not None:
        query = query.filter(P01EntityProposal.supporting_announcement_count >= min_supporting_announcements)
    if date_from is not None: query = query.filter(Announcement.ann_date >= date_from)
    if date_to is not None: query = query.filter(Announcement.ann_date <= date_to)
    rows = query.order_by(EntityMapping.id.desc()).limit(1000).all()
    return [_entity_mapping_out(db, row, include_candidate=True) for row in rows]


@router.post("/p3/entity-mappings/model-suggestions")
def create_entity_model_suggestion(payload: P3EntityModelSuggestionCreate, db: Session = Depends(get_db)):
    mention = db.get(EntityMention, payload.entity_mention_id)
    if mention is None:
        raise HTTPException(status_code=404, detail="entity mention not found")
    try:
        row = record_model_suggestion(db, mention, **payload.model_dump(exclude={"entity_mention_id"}))
        db.commit(); db.refresh(row)
    except ValueError as exc:
        db.rollback(); raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _entity_mapping_out(db, row, include_candidate=True)


@router.post("/p3/entity-mappings/{mapping_id}/confirm")
def confirm_entity_mapping(mapping_id: int, payload: P3EntityMappingReviewAction, db: Session = Depends(get_db)):
    return _review_entity_mapping(db, mapping_id, "confirm", payload.reviewer, payload.review_note)


@router.post("/p3/entity-mappings/{mapping_id}/reject")
def reject_entity_mapping(mapping_id: int, payload: P3EntityMappingReviewAction, db: Session = Depends(get_db)):
    return _review_entity_mapping(db, mapping_id, "reject", payload.reviewer, payload.review_note)


@router.put("/p3/entity-mappings/{mapping_id}")
def correct_entity_mapping(mapping_id: int, payload: P3EntityMappingCorrection, db: Session = Depends(get_db)):
    return _review_entity_mapping(
        db, mapping_id, "correct", payload.reviewer, payload.review_note,
        payload.matched_entity_type, payload.matched_entity_id,
    )


@router.get("/p3/entity-mappings/{mapping_id}/history")
def entity_mapping_history(mapping_id: int, db: Session = Depends(get_db)):
    mapping = db.get(EntityMapping, mapping_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail="entity mapping not found")
    rows = db.query(EntityMapping).filter_by(entity_mention_id=mapping.entity_mention_id).order_by(EntityMapping.id).all()
    logs = db.query(EntityMappingChangeLog).filter_by(entity_mention_id=mapping.entity_mention_id).order_by(EntityMappingChangeLog.id).all()
    return {
        "mention": _entity_mapping_out(db, mapping, include_candidate=True),
        "mappings": [_entity_mapping_out(db, row, include_candidate=True) for row in rows],
        "change_log": [{
            "id": row.id, "old_mapping_id": row.old_mapping_id, "new_mapping_id": row.new_mapping_id,
            "proposal_id": row.proposal_id, "action": row.action,
            "before": json.loads(row.before_json or "{}"), "after": json.loads(row.after_json or "{}"),
            "reviewer": row.reviewer, "review_note": row.review_note, "created_at": row.created_at,
        } for row in logs],
    }


def _review_entity_mapping(
    db: Session, mapping_id: int, action: str, reviewer: str, note: str,
    entity_type: str | None = None, entity_id: int | None = None,
):
    mapping = db.get(EntityMapping, mapping_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail="entity mapping not found")
    try:
        result = review_entity_mapping(
            db, mapping, action=action, reviewer=reviewer, review_note=note,
            corrected_entity_type=entity_type, corrected_entity_id=entity_id,
        )
        db.commit(); db.refresh(result)
    except ValueError as exc:
        db.rollback(); raise HTTPException(status_code=409 if "locked" in str(exc) else 422, detail=str(exc)) from exc
    return _entity_mapping_out(db, result, include_candidate=True)


@router.get("/p3/version-relations/review-needed")
def version_relations_review_needed(
    stock_id: int | None = None,
    project_id: int | None = None,
    family: str | None = None,
    fact_type: str | None = None,
    relation_type: str | None = None,
    status: str | None = "proposed",
    validity_status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 500,
    db: Session = Depends(get_db),
):
    query = db.query(P3VersionRelation)
    if status: query = query.filter(P3VersionRelation.status == status)
    if relation_type: query = query.filter(P3VersionRelation.relation_type == relation_type)
    if stock_id is not None or date_from is not None or date_to is not None:
        query = query.join(Announcement, Announcement.id == P3VersionRelation.source_announcement_id)
    if stock_id is not None: query = query.filter(Announcement.stock_id == stock_id)
    if date_from is not None: query = query.filter(Announcement.ann_date >= date_from)
    if date_to is not None: query = query.filter(Announcement.ann_date <= date_to)
    rows = query.order_by(P3VersionRelation.id.desc()).limit(min(limit, 1000)).all()
    output = [_version_relation_out(db, row, include_history=False) for row in rows]
    if project_id is not None:
        output = [row for row in output if any(item and item.get("project_id") == project_id for item in (row["predecessor"], row["successor"]))]
    if family:
        output = [row for row in output if any(item and item.get("family") == family for item in (row["predecessor"], row["successor"]))]
    if fact_type:
        output = [row for row in output if any(item and item.get("fact_type") == fact_type for item in (row["predecessor"], row["successor"]))]
    if validity_status:
        output = [row for row in output if row["predecessor"] and row["predecessor"].get("validity_status") == validity_status]
    return output


@router.get("/p3/version-relations/{relation_id}")
def get_p3_version_relation(relation_id: int, db: Session = Depends(get_db)):
    return _version_relation_out(db, _p3_version_relation(relation_id, db), include_history=True)


@router.post("/p3/version-relations/{relation_id}/confirm")
def confirm_p3_version_relation(relation_id: int, payload: P3VersionRelationReviewAction, db: Session = Depends(get_db)):
    return _review_p3_version_relation(db, _p3_version_relation(relation_id, db), "confirm", payload.reviewer, payload.review_note, {})


@router.post("/p3/version-relations/{relation_id}/reject")
def reject_p3_version_relation(relation_id: int, payload: P3VersionRelationReviewAction, db: Session = Depends(get_db)):
    return _review_p3_version_relation(db, _p3_version_relation(relation_id, db), "reject", payload.reviewer, payload.review_note, {})


@router.put("/p3/version-relations/{relation_id}")
def correct_p3_version_relation(relation_id: int, payload: P3VersionRelationCorrection, db: Session = Depends(get_db)):
    changes = payload.model_dump(exclude={"reviewer", "review_note"}, exclude_unset=True)
    return _review_p3_version_relation(db, _p3_version_relation(relation_id, db), "correct", payload.reviewer, payload.review_note, changes)


def _p3_version_relation(relation_id: int, db: Session) -> P3VersionRelation:
    relation = db.get(P3VersionRelation, relation_id)
    if relation is None:
        raise HTTPException(status_code=404, detail="P3 version relation not found")
    return relation


def _review_p3_version_relation(db, relation, action, reviewer, note, changes):
    try:
        review_p3_version_relation(db, relation, action, reviewer, note, changes)
        db.commit(); db.refresh(relation)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409 if "confirmed effective relation" in str(exc) else 422, detail=str(exc)) from exc
    return _version_relation_out(db, relation, include_history=True)


def _version_relation_out(db: Session, relation: P3VersionRelation, include_history: bool) -> dict:
    announcement = db.get(Announcement, relation.source_announcement_id)
    evidence = db.get(EvidenceDocument, relation.source_evidence_document_id)
    predecessor = object_snapshot(get_version_object(db, relation.predecessor_type, relation.predecessor_id))
    successor = object_snapshot(get_version_object(db, relation.successor_type, relation.successor_id)) if relation.successor_type and relation.successor_id else None
    output = {
        "id": relation.id, "predecessor_type": relation.predecessor_type, "predecessor_id": relation.predecessor_id,
        "successor_type": relation.successor_type, "successor_id": relation.successor_id,
        "relation_type": relation.relation_type, "status": relation.status,
        "source_announcement_id": relation.source_announcement_id,
        "source_evidence_document_id": relation.source_evidence_document_id,
        "source_page_start": relation.source_page_start, "source_page_end": relation.source_page_end,
        "source_excerpt": relation.source_excerpt, "withdrawal_reason": relation.withdrawal_reason,
        "detected_by": relation.detected_by, "confidence": relation.confidence,
        "reviewed_by": relation.reviewed_by, "reviewed_at": relation.reviewed_at,
        "review_note": relation.review_note, "created_at": relation.created_at, "updated_at": relation.updated_at,
        "predecessor": predecessor, "successor": successor,
        "stock": {"id": announcement.stock.id, "code": announcement.stock.code, "name": announcement.stock.name} if announcement and announcement.stock else None,
        "source_announcement": {"id": announcement.id, "ann_id": announcement.ann_id, "headline": announcement.headline,
                                "ann_date": announcement.ann_date, "url": announcement.url} if announcement else None,
        "evidence_document": {"id": evidence.id, "title": evidence.title, "page_count": evidence.page_count,
                              "pdf_url": f"/api/announcements/evidence/{evidence.id}/original"} if evidence else None,
    }
    if include_history:
        logs = db.query(P3VersionRelationChangeLog).filter_by(relation_id=relation.id).order_by(P3VersionRelationChangeLog.id).all()
        output["change_log"] = [{"id": row.id, "action": row.action, "before": _safe_json(row.before_json, {}),
                                  "after": _safe_json(row.after_json, {}), "reviewer": row.reviewer,
                                  "review_note": row.review_note, "created_at": row.created_at} for row in logs]
        output["original_suggestion"] = _safe_json(relation.original_suggestion_json, {})
    return output

def _pipeline_task(retry_of_run_id: int | None = None, only_failed_run_id: int | None = None):
    from ...services.pipeline import run_daily_pipeline
    run_daily_pipeline(trigger="manual", retry_of_run_id=retry_of_run_id, only_failed_run_id=only_failed_run_id)

def _replay_task(days: int):
    from ...services.replay import run_replay
    with SessionLocal() as session: run_replay(session, days=days)

@router.post("/run-pipeline", response_model=Message)
def run_pipeline(background: BackgroundTasks):
    background.add_task(_pipeline_task); return Message(detail="pipeline started in background; poll /api/admin/runs")

@router.post("/run-replay", response_model=Message)
def run_replay_endpoint(background: BackgroundTasks, days: int = 400):
    background.add_task(_replay_task, days); return Message(detail=f"replay ({days} bars) started in background")

@router.get("/runs", response_model=list[PipelineRunOut])
def list_runs(limit: int = 20, db: Session = Depends(get_db)):
    runs = db.query(PipelineRun).order_by(PipelineRun.id.desc()).limit(limit).all()
    return [_pipeline_run_out(r) for r in runs]


def _pipeline_run_out(r: PipelineRun) -> PipelineRunOut:
    return PipelineRunOut(id=r.id, run_at=r.run_at, trigger=r.trigger, status=r.status, stats=json.loads(r.stats_json or "{}"), finished_at=r.finished_at, pipeline_type=r.pipeline_type, provider=r.provider, started_at=r.started_at, total_items=r.total_items, succeeded_items=r.succeeded_items, skipped_items=r.skipped_items, failed_items=r.failed_items, retry_of_run_id=r.retry_of_run_id, configuration_snapshot=json.loads(r.configuration_snapshot_json or "{}"), error_summary=r.error_summary)


@router.get("/pipeline-runs", response_model=list[PipelineRunOut])
def list_pipeline_runs(limit: int = 50, db: Session = Depends(get_db)):
    return [_pipeline_run_out(r) for r in db.query(PipelineRun).order_by(PipelineRun.id.desc()).limit(min(limit, 200)).all()]


@router.get("/pipeline-runs/{run_id}", response_model=PipelineRunOut)
def get_pipeline_run(run_id: int, db: Session = Depends(get_db)):
    row = db.get(PipelineRun, run_id)
    if row is None: raise HTTPException(status_code=404, detail="pipeline run not found")
    return _pipeline_run_out(row)


@router.get("/pipeline-runs/{run_id}/items", response_model=list[PipelineRunItemOut])
def list_pipeline_run_items(run_id: int, db: Session = Depends(get_db)):
    if db.get(PipelineRun, run_id) is None: raise HTTPException(status_code=404, detail="pipeline run not found")
    return [PipelineRunItemOut(id=i.id, run_id=i.run_id, stock_id=i.stock_id, announcement_id=i.announcement_id, provider=i.provider, item_type=i.item_type, status=i.status, error_message=i.error_message, attempt_count=i.attempt_count, started_at=i.started_at, finished_at=i.finished_at, metadata=json.loads(i.metadata_json or "{}")) for i in db.query(PipelineRunItem).filter_by(run_id=run_id).order_by(PipelineRunItem.id).all()]


@router.post("/pipeline-runs/{run_id}/retry", response_model=Message)
def retry_pipeline_run(run_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    if db.get(PipelineRun, run_id) is None: raise HTTPException(status_code=404, detail="pipeline run not found")
    background.add_task(_pipeline_task, run_id, None)
    return Message(detail=f"pipeline retry started for run {run_id}")


@router.post("/pipeline-runs/{run_id}/retry-failed", response_model=Message)
def retry_failed_pipeline_run(run_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    if db.get(PipelineRun, run_id) is None: raise HTTPException(status_code=404, detail="pipeline run not found")
    background.add_task(_pipeline_task, run_id, run_id)
    return Message(detail=f"failed items retry started for run {run_id}")


@router.post("/stocks/{code}/announcements/retry", response_model=Message)
def retry_stock_announcements(code: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    stock = db.query(Stock).filter(Stock.code == code.upper()).first()
    if stock is None: raise HTTPException(status_code=404, detail="stock not found")
    def task():
        from ...services.pipeline import run_daily_pipeline
        run_daily_pipeline(trigger="manual_stock_retry", only_stock_id=stock.id)
    background.add_task(task)
    return Message(detail=f"announcement retry started for {stock.code}")


@router.get("/ingestion-config")
def ingestion_config(db: Session = Depends(get_db)):
    return get_all_config(db).get("ingestion", {})


@router.put("/ingestion-config")
def update_ingestion_config(payload: dict, db: Session = Depends(get_db)):
    allowed = {"prices", "announcements", "commodities"}
    cleaned = {key: value for key, value in payload.items() if key in allowed and isinstance(value, dict)}
    if not cleaned: raise HTTPException(status_code=422, detail="at least one ingestion section is required")
    current = get_all_config(db).get("ingestion", {})
    current.update(cleaned)
    set_config(db, "ingestion", current, changed_by="admin", source="ingestion_api")
    return current

@router.post("/test-telegram", response_model=Message)
def test_telegram():
    result = TelegramNotifier().send("<b>AI Resource Cycle Tracker</b>\nTelegram channel is configured correctly.")
    if result.skipped: return Message(detail="telegram not configured (set TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
    if not result.sent: return Message(detail=f"telegram push failed: {result.error}")
    return Message(detail="test message sent")

@router.get("/entity-proposals", response_model=list[P01EntityProposalOut])
def list_entity_proposals(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(P01EntityProposal).order_by(P01EntityProposal.id.desc())
    if status: query = query.filter_by(status=status)
    return query.limit(500).all()


@router.get("/entity-proposals/search", response_model=list[P01EntityProposalOut])
def search_entity_proposals(q: str, db: Session = Depends(get_db)):
    term = f"%{q.strip()}%"
    return db.query(P01EntityProposal).filter(
        (P01EntityProposal.proposed_project_name.ilike(term))
        | (P01EntityProposal.proposed_asset_name.ilike(term))
        | (P01EntityProposal.source_ref.ilike(term))
    ).order_by(P01EntityProposal.id.desc()).limit(500).all()


@router.get("/entity-source-search", response_model=list[P01SourceSearchResult])
def search_entity_sources(q: str, stock_id: int | None = None, db: Session = Depends(get_db)):
    term = q.strip()
    if len(term) < 2:
        raise HTTPException(status_code=422, detail="q must contain at least 2 characters")
    like = f"%{term}%"
    results: list[P01SourceSearchResult] = []
    evidence_query = db.query(EvidenceDocument).filter(
        (EvidenceDocument.title.ilike(like)) | (EvidenceDocument.source_id.ilike(like)) | (EvidenceDocument.url.ilike(like))
    )
    if stock_id is not None:
        evidence_query = evidence_query.filter(EvidenceDocument.stock_id == stock_id)
    for row in evidence_query.limit(100).all():
        results.append(P01SourceSearchResult(source_type=row.source_type, source_id=row.source_id, title=row.title, url=row.url, stock_id=row.stock_id, project_id=row.project_id, excerpt="Official source document; open PDF and record page/excerpt before proposing."))
    announcement_query = db.query(Announcement).filter((Announcement.headline.ilike(like)) | (Announcement.ann_id.ilike(like)) | (Announcement.url.ilike(like)))
    if stock_id is not None:
        announcement_query = announcement_query.filter(Announcement.stock_id == stock_id)
    for row in announcement_query.limit(100).all():
        results.append(P01SourceSearchResult(source_type="asx_announcement", source_id=row.ann_id, title=row.headline, url=row.url, stock_id=row.stock_id, excerpt="Announcement source; PDF page and exact excerpt must be entered manually."))
    return results[:200]


@router.get("/entity-source-search/online", response_model=list[P01SourceSearchResult])
def search_entity_sources_online(code: str, q: str | None = None, count: int = 20):
    """Read-only ASX search; results must be manually turned into proposals."""
    try:
        rows = AsxJsonAnnouncementSource().fetch(code.strip().upper(), count=min(max(count, 1), 50))
    except SourceBlockedError as exc:
        raise HTTPException(status_code=503, detail=f"ASX source unavailable: {exc}") from exc
    term = q.casefold().strip() if q else None
    return [
        P01SourceSearchResult(source_type="asx_online", source_id=row.ann_id, title=row.headline, url=row.url, excerpt="Online ASX result; open PDF and manually record page/excerpt before proposing.")
        for row in rows if not term or term in row.headline.casefold()
    ]

@router.post("/entity-proposals", response_model=P01EntityProposalOut, status_code=201)
def create_entity_proposal(payload: P01EntityProposalCreate, db: Session = Depends(get_db)):
    if db.get(Stock, payload.stock_id) is None: raise HTTPException(status_code=404, detail="stock not found")
    proposal = P01EntityProposal(**payload.model_dump()); db.add(proposal); db.commit(); db.refresh(proposal); return proposal

@router.post("/entity-proposals/{proposal_id}/review", response_model=P01EntityProposalOut)
def review_entity_proposal(proposal_id: int, payload: P01EntityProposalReview, db: Session = Depends(get_db)):
    proposal = db.get(P01EntityProposal, proposal_id)
    if proposal is None: raise HTTPException(status_code=404, detail="entity proposal not found")
    try:
        review_proposal(db, proposal, payload.action, payload.reviewer, payload.review_note, payload.correction)
    except ValueError as exc:
        raise HTTPException(status_code=409 if "finalized" in str(exc) else 422, detail=str(exc)) from exc
    db.commit(); db.refresh(proposal); return proposal


@router.get("/entity-review/p3-update-proposals")
def list_p3_update_proposals(
    status: str | None = None, stock_id: int | None = None, proposal_type: str | None = None,
    parent_project_id: int | None = None, min_supporting_announcements: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(P01EntityProposal).filter(P01EntityProposal.source_type == "p3_entity_candidate")
    if status: query = query.filter(P01EntityProposal.status == status)
    if stock_id is not None: query = query.filter(P01EntityProposal.stock_id == stock_id)
    if proposal_type: query = query.filter(P01EntityProposal.proposal_type == proposal_type)
    if parent_project_id is not None: query = query.filter(P01EntityProposal.proposed_parent_project_id == parent_project_id)
    if min_supporting_announcements is not None: query = query.filter(P01EntityProposal.supporting_announcement_count >= min_supporting_announcements)
    return [_p3_proposal_out(db, row) for row in query.order_by(P01EntityProposal.id.desc()).limit(1000).all()]


@router.get("/entity-review/p3-update-proposals/{proposal_id}")
def get_p3_update_proposal(proposal_id: int, db: Session = Depends(get_db)):
    return _p3_proposal_out(db, _p3_proposal(proposal_id, db), include_reviews=True)


@router.get("/entity-review/p3-update-proposals/{proposal_id}/evidence")
def get_p3_update_proposal_evidence(proposal_id: int, db: Session = Depends(get_db)):
    proposal = _p3_proposal(proposal_id, db)
    return _proposal_evidence(db, proposal)


@router.post("/entity-review/p3-update-proposals/{proposal_id}/approve")
def approve_p3_update_proposal(proposal_id: int, payload: P01ProposalDecision, db: Session = Depends(get_db)):
    return _review_p3_proposal(db, _p3_proposal(proposal_id, db), "approve", payload.reviewer, payload.review_note, {})


@router.post("/entity-review/p3-update-proposals/{proposal_id}/reject")
def reject_p3_update_proposal(proposal_id: int, payload: P01ProposalDecision, db: Session = Depends(get_db)):
    return _review_p3_proposal(db, _p3_proposal(proposal_id, db), "reject", payload.reviewer, payload.review_note, {})


@router.put("/entity-review/p3-update-proposals/{proposal_id}")
def correct_p3_update_proposal(proposal_id: int, payload: P01ProposalCorrection, db: Session = Depends(get_db)):
    return _review_p3_proposal(db, _p3_proposal(proposal_id, db), "correct", payload.reviewer, payload.review_note, payload.correction)


def _p3_proposal(proposal_id: int, db: Session) -> P01EntityProposal:
    row = db.get(P01EntityProposal, proposal_id)
    if row is None or row.source_type != "p3_entity_candidate":
        raise HTTPException(status_code=404, detail="P3 entity update proposal not found")
    return row


def _review_p3_proposal(db, proposal, action, reviewer, note, correction):
    try:
        review_proposal(db, proposal, action, reviewer, note, correction)
        db.commit(); db.refresh(proposal)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409 if "finalized" in str(exc) else 422, detail=str(exc)) from exc
    return _p3_proposal_out(db, proposal, include_reviews=True)


def _p3_proposal_out(db: Session, proposal: P01EntityProposal, include_reviews: bool = False) -> dict:
    stock = db.get(Stock, proposal.stock_id)
    parent = db.get(Project, proposal.proposed_parent_project_id) if proposal.proposed_parent_project_id else None
    result = None
    if proposal.resulting_entity_type == "asset_unit" and proposal.resulting_entity_id:
        row = db.get(AssetUnit, proposal.resulting_entity_id)
        result = {"type": "asset_unit", "id": row.id, "name": row.name, "project_id": row.project_id} if row else None
    elif proposal.resulting_entity_type == "project" and proposal.resulting_entity_id:
        row = db.get(Project, proposal.resulting_entity_id)
        result = {"type": "project", "id": row.id, "name": row.name, "project_key": row.project_key} if row else None
    output = {
        "id": proposal.id, "proposal_type": proposal.proposal_type, "status": proposal.status,
        "stock": {"id": stock.id, "code": stock.code, "name": stock.name} if stock else None,
        "stock_id": proposal.stock_id, "proposed_name": proposal.proposed_name or proposal.proposed_asset_name or proposal.proposed_project_name,
        "proposed_name_normalized": proposal.proposed_name_normalized, "proposed_entity_type": proposal.proposed_entity_type,
        "proposed_project_name": proposal.proposed_project_name, "proposed_asset_name": proposal.proposed_asset_name,
        "proposed_asset_type": proposal.proposed_asset_type, "proposed_commodity": proposal.proposed_commodity,
        "candidate_parent_project": {"id": parent.id, "name": parent.name, "project_key": parent.project_key} if parent else None,
        "proposed_parent_project_id": proposal.proposed_parent_project_id,
        "proposed_payload": _safe_json(proposal.proposed_payload_json, {}),
        "supporting_announcement_count": proposal.supporting_announcement_count,
        "supporting_evidence_count": proposal.supporting_evidence_count,
        "supporting_event_count": proposal.supporting_event_count,
        "supporting_fact_count": proposal.supporting_fact_count,
        "supporting_mentions": _safe_json(proposal.supporting_mentions_json, []),
        "source_pages": _safe_json(proposal.source_pages_json, []),
        "source_excerpts": _safe_json(proposal.source_excerpts_json, []),
        "confidence": proposal.confidence, "created_by": proposal.created_by,
        "reviewed_by": proposal.reviewed_by or proposal.reviewer, "reviewed_at": proposal.reviewed_at,
        "review_note": proposal.review_note, "correction_history": _safe_json(proposal.correction_json, {}),
        "resulting_entity": result, "created_at": proposal.created_at, "updated_at": proposal.updated_at,
        "evidence": _proposal_evidence(db, proposal),
    }
    if include_reviews:
        output["reviews"] = [{
            "id": row.id, "action": row.action, "before": _safe_json(row.before_json, {}),
            "after": _safe_json(row.after_json, {}), "reviewer": row.reviewer,
            "review_note": row.review_note, "created_at": row.created_at,
        } for row in proposal.reviews]
    return output


def _proposal_evidence(db: Session, proposal: P01EntityProposal) -> list[dict]:
    items = []
    for support in _safe_json(proposal.supporting_mentions_json, []):
        if not isinstance(support, dict):
            continue
        announcement = db.get(Announcement, support.get("announcement_id"))
        evidence = db.get(EvidenceDocument, support.get("evidence_document_id"))
        items.append({
            **support,
            "announcement": {"id": announcement.id, "ann_id": announcement.ann_id, "headline": announcement.headline,
                             "ann_date": announcement.ann_date, "url": announcement.url} if announcement else None,
            "evidence_document": {"id": evidence.id, "title": evidence.title, "page_count": evidence.page_count,
                                  "pdf_url": f"/api/announcements/evidence/{evidence.id}/original"} if evidence else None,
        })
    return items


def _safe_json(raw, default):
    try:
        value = json.loads(raw or json.dumps(default))
    except (json.JSONDecodeError, TypeError):
        return default
    return value if isinstance(value, type(default)) else default


@router.post("/announcement-version-relations", response_model=AnnouncementVersionRelationOut, status_code=201)
def create_version_relation(payload: AnnouncementVersionRelationCreate, db: Session = Depends(get_db)):
    if payload.predecessor_announcement_id == payload.successor_announcement_id:
        raise HTTPException(status_code=422, detail="predecessor and successor must differ")
    if db.get(Announcement, payload.predecessor_announcement_id) is None or db.get(Announcement, payload.successor_announcement_id) is None:
        raise HTTPException(status_code=404, detail="announcement not found")
    relation = db.query(AnnouncementVersionRelation).filter_by(predecessor_announcement_id=payload.predecessor_announcement_id, successor_announcement_id=payload.successor_announcement_id).one_or_none()
    if relation is None:
        relation = AnnouncementVersionRelation(**payload.model_dump())
        db.add(relation)
    db.commit(); db.refresh(relation)
    return relation


@router.put("/announcement-version-relations/{relation_id}/review", response_model=AnnouncementVersionRelationOut)
def review_version_relation(relation_id: int, payload: AnnouncementVersionRelationReview, db: Session = Depends(get_db)):
    relation = db.get(AnnouncementVersionRelation, relation_id)
    if relation is None: raise HTTPException(status_code=404, detail="version relation not found")
    if payload.status not in {"pending_review", "confirmed", "rejected"}: raise HTTPException(status_code=422, detail="invalid relation status")
    relation.status = payload.status; relation.reviewed_by = payload.reviewed_by; relation.review_note = payload.review_note; relation.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit(); db.refresh(relation); return relation


@router.get("/p3/classification-review", response_model=list[P3EventOut])
def list_p3_classification_review(status: str = "review_needed", include_inactive: bool = False, limit: int = 500, db: Session = Depends(get_db)):
    query = db.query(P3Event)
    if status:
        query = query.filter(P3Event.classification_status == status)
    if not include_inactive:
        query = query.filter(P3Event.active_result.is_(True))
    return [_event_out(event) for event in query.order_by(P3Event.id.desc()).limit(min(limit, 1000)).all()]


@router.get("/p3/events/{event_id}/reviews", response_model=list[P3ClassificationReviewOut])
def list_p3_event_reviews(event_id: int, db: Session = Depends(get_db)):
    _p3_event(event_id, db)
    return db.query(P3EventClassificationReview).filter_by(p3_event_id=event_id).order_by(P3EventClassificationReview.id).all()


@router.post("/p3/events/{event_id}/confirm", response_model=P3EventOut)
def confirm_p3_event(event_id: int, payload: P3EventReviewAction, db: Session = Depends(get_db)):
    event = _p3_event(event_id, db)
    before = _classification_snapshot(event)
    event.classification_status = "confirmed"
    event.active_result = True
    event.validity_status = "current"
    event.validity_reason = ""
    _finish_event_review(event, payload.reviewer, payload.review_note, before)
    _record_event_review(db, event, "confirm", before)
    db.commit(); db.refresh(event)
    return _event_out(event)


@router.post("/p3/events/{event_id}/reject", response_model=P3EventOut)
def reject_p3_event(event_id: int, payload: P3EventReviewAction, db: Session = Depends(get_db)):
    event = _p3_event(event_id, db)
    before = _classification_snapshot(event)
    event.classification_status = "rejected"
    event.active_result = False
    event.validity_status = "rejected"
    event.validity_reason = payload.review_note
    _finish_event_review(event, payload.reviewer, payload.review_note, before)
    _record_event_review(db, event, "reject", before)
    db.commit(); db.refresh(event)
    return _event_out(event)


@router.put("/p3/events/{event_id}", response_model=P3EventOut)
def correct_p3_event(event_id: int, payload: P3EventCorrection, db: Session = Depends(get_db)):
    event = _p3_event(event_id, db)
    before = _classification_snapshot(event)
    changes = payload.model_dump(exclude={"reviewer", "review_note"}, exclude_unset=True)
    if "primary_family" in changes:
        family = changes.pop("primary_family")
        if family not in {"F01", "F02", "F03", "F04", "F05", "F06", "F07", "F08", "OTHER"}:
            raise HTTPException(status_code=422, detail="invalid primary_family")
        event.primary_family = family
        event.event_family = family
    if "secondary_families" in changes:
        event.secondary_families_json = json.dumps(changes.pop("secondary_families") or [], ensure_ascii=False)
    for field, value in changes.items():
        setattr(event, field, value)
    event.classification_status = "corrected"
    event.classification_source = "human_review"
    event.active_result = True
    event.validity_status = "current"
    event.validity_reason = ""
    _finish_event_review(event, payload.reviewer, payload.review_note, before)
    _record_event_review(db, event, "correct", before)
    db.commit(); db.refresh(event)
    return _event_out(event)


def _p3_event(event_id: int, db: Session) -> P3Event:
    event = db.get(P3Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="P3 event not found")
    return event


def _classification_snapshot(event: P3Event) -> dict:
    return {
        "primary_family": event.primary_family,
        "secondary_families": json.loads(event.secondary_families_json or "[]"),
        "event_type": event.event_type,
        "event_title": event.event_title,
        "event_status": event.event_status,
        "classification_status": event.classification_status,
        "classification_source": event.classification_source,
        "classification_confidence": event.classification_confidence,
        "project_id": event.project_id,
        "asset_unit_id": event.asset_unit_id,
        "active_result": event.active_result,
    }


def _finish_event_review(event: P3Event, reviewer: str, note: str, original: dict) -> None:
    if not event.original_classification_json or event.original_classification_json == "{}":
        event.original_classification_json = json.dumps(original, ensure_ascii=False)
    event.reviewed_by = reviewer
    event.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    event.review_note = note


def _record_event_review(db: Session, event: P3Event, action: str, before: dict) -> None:
    db.add(P3EventClassificationReview(
        p3_event_id=event.id,
        action=action,
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(_classification_snapshot(event), ensure_ascii=False),
        reviewer=event.reviewed_by or "unknown",
        review_note=event.review_note,
    ))


@router.get("/p3/facts/review-needed", response_model=list[P3FactOut])
def list_p3_fact_review_needed(
    stock_id: int | None = None,
    announcement_id: int | None = None,
    family: str | None = None,
    field_name: str | None = None,
    status: str | None = None,
    limit: int = 500,
    db: Session = Depends(get_db),
):
    query = db.query(P3Fact).filter(P3Fact.review_status == "review_needed", P3Fact.active_result.is_(True))
    if stock_id is not None: query = query.filter(P3Fact.stock_id == stock_id)
    if announcement_id is not None: query = query.filter(P3Fact.announcement_id == announcement_id)
    if family: query = query.filter(P3Fact.fact_family == family)
    if field_name: query = query.filter(P3Fact.field_name == field_name)
    if status: query = query.filter(P3Fact.status == status)
    return [_fact_out(db, fact) for fact in query.order_by(P3Fact.id.desc()).limit(min(limit, 1000)).all()]


@router.get("/p3/facts/{fact_id}/reviews", response_model=list[P3FactReviewOut])
def list_p3_fact_reviews(fact_id: int, db: Session = Depends(get_db)):
    _p3_fact(fact_id, db)
    return db.query(P3FactReview).filter_by(p3_fact_id=fact_id).order_by(P3FactReview.id).all()


@router.post("/p3/facts/{fact_id}/confirm", response_model=P3FactOut)
def confirm_p3_fact(fact_id: int, payload: P3FactReviewAction, db: Session = Depends(get_db)):
    fact = apply_review(db, _p3_fact(fact_id, db), "confirm", payload.reviewer, payload.review_note)
    db.commit(); db.refresh(fact)
    return _fact_out(db, fact)


@router.post("/p3/facts/{fact_id}/reject", response_model=P3FactOut)
def reject_p3_fact(fact_id: int, payload: P3FactReviewAction, db: Session = Depends(get_db)):
    fact = apply_review(db, _p3_fact(fact_id, db), "reject", payload.reviewer, payload.review_note)
    db.commit(); db.refresh(fact)
    return _fact_out(db, fact)


@router.put("/p3/facts/{fact_id}", response_model=P3FactOut)
def correct_p3_fact(fact_id: int, payload: P3FactCorrection, db: Session = Depends(get_db)):
    changes = payload.model_dump(exclude={"reviewer", "review_note"}, exclude_unset=True)
    fact = apply_review(db, _p3_fact(fact_id, db), "correct", payload.reviewer, payload.review_note, changes)
    # Keep compatibility fields synchronized while retaining the original extraction JSON.
    fact.unit = fact.unit_raw
    fact.source_page = fact.source_page_start
    fact.value_json = json.dumps({"raw": fact.value_raw, "numeric": fact.value_numeric, "text": fact.value_text}, ensure_ascii=False)
    db.commit(); db.refresh(fact)
    return _fact_out(db, fact)


def _p3_fact(fact_id: int, db: Session) -> P3Fact:
    fact = db.get(P3Fact, fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail="P3 fact not found")
    return fact


@router.post("/evidence/historical-baseline", response_model=EvidenceDocumentOut, status_code=201)
def import_historical_baseline(payload: HistoricalBaselineCreate, db: Session = Depends(get_db)):
    stock = db.get(Stock, payload.stock_id)
    if stock is None: raise HTTPException(status_code=404, detail="stock not found")
    try:
        source = validate_historical_pdf(Path(payload.local_pdf_path))
        evidence, _ = import_historical_evidence(
            db, stock=stock, local_pdf_path=source, title=payload.title,
            source_date=payload.source_date, source_url=payload.source_url,
            project_id=payload.project_id, review_status=payload.review_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit(); db.refresh(evidence); return evidence
