"""Preview-first, administrator-scoped P02 -> P03 historical backfill."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import (
    Announcement,
    BackfillRun,
    BackfillRunItem,
    EntityMapping,
    EntityMention,
    EvidenceDocument,
    P3Event,
    P3Fact,
    P3ParseRun,
    P3VersionRelation,
    Stock,
)
from .evidence_service import ensure_evidence
from .p3_parse_service import PARSER_NAME, PARSER_VERSION, parse_evidence

PIPELINE_VERSION = "p02_p03_backfill_v1"
FAMILIES = {f"F{i:02d}" for i in range(1, 9)}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def normalize_request(payload: dict[str, Any]) -> dict[str, Any]:
    result = {
        "stock_codes": sorted({str(x).strip().upper() for x in payload.get("stock_codes", []) if str(x).strip()}),
        "announcement_ids": sorted({str(x).strip() for x in payload.get("announcement_ids", []) if str(x).strip()}),
        "date_from": str(payload["date_from"]) if payload.get("date_from") else None,
        "date_to": str(payload["date_to"]) if payload.get("date_to") else None,
        "event_families": sorted({str(x).strip().upper() for x in payload.get("event_families", []) if str(x).strip()}),
        "download_missing_pdf": bool(payload.get("download_missing_pdf", False)),
        "extract_raw_text": bool(payload.get("extract_raw_text", True)),
        "parse_document": bool(payload.get("parse_document", True)),
        "classify_events": bool(payload.get("classify_events", True)),
        "extract_facts": bool(payload.get("extract_facts", True)),
        "map_entities": bool(payload.get("map_entities", True)),
        "check_version_relations": bool(payload.get("check_version_relations", True)),
        "only_failed": bool(payload.get("only_failed", False)),
        "only_unparsed": bool(payload.get("only_unparsed", False)),
        "parser_version": str(payload.get("parser_version") or PARSER_VERSION).strip(),
    }
    if not any((result["stock_codes"], result["announcement_ids"], result["date_from"], result["date_to"])):
        raise ValueError("an explicit stock, announcement, or date scope is required; full-history backfill is disabled")
    unknown = set(result["event_families"]) - FAMILIES
    if unknown:
        raise ValueError(f"invalid event families: {', '.join(sorted(unknown))}")
    if any(result[key] for key in ("classify_events", "extract_facts", "map_entities", "check_version_relations")) and not result["parse_document"]:
        raise ValueError("P3 classification/fact/mapping/version actions require parse_document=true")
    if result["extract_facts"] and not result["classify_events"]:
        raise ValueError("extract_facts requires classify_events=true")
    if (result["map_entities"] or result["check_version_relations"]) and not result["classify_events"]:
        raise ValueError("entity mapping and version checks require classify_events=true")
    return result


def _execution_parser_version(request: dict[str, Any]) -> str:
    profile = f"c{int(request['classify_events'])}f{int(request['extract_facts'])}m{int(request['map_entities'])}v{int(request['check_version_relations'])}"
    if profile == "c1f1m1v1":
        return request["parser_version"]
    return f"{request['parser_version'][:30]}-{profile}"


def _evidence(session: Session, announcement: Announcement) -> EvidenceDocument | None:
    if announcement.evidence_document_id:
        row = session.get(EvidenceDocument, announcement.evidence_document_id)
        if row:
            return row
    return session.query(EvidenceDocument).filter_by(source_type="asx_pdf", source_id=announcement.ann_id).first()


def _has_parse(session: Session, evidence: EvidenceDocument | None, parser_version: str) -> bool:
    if evidence is None:
        return False
    input_hash = evidence.file_hash_sha256 or evidence.content_hash
    if not input_hash:
        return False
    return session.query(P3ParseRun.id).filter_by(
        evidence_document_id=evidence.id,
        parser_name=PARSER_NAME,
        parser_version=parser_version,
        input_hash=input_hash,
    ).filter(P3ParseRun.status.in_(["parsed", "partial", "review_needed"])).first() is not None


def _families(session: Session, announcement: Announcement) -> list[str]:
    values: set[str] = set()
    try:
        values.update(json.loads(announcement.event_families_json or "[]"))
    except (TypeError, ValueError):
        pass
    values.update(row[0] for row in session.query(P3Event.primary_family).filter_by(announcement_id=announcement.id).all() if row[0] != "OTHER")
    return sorted(values)


def select_announcements(session: Session, request: dict[str, Any]) -> tuple[list[Announcement], list[dict[str, Any]]]:
    query = session.query(Announcement).join(Stock)
    if request["stock_codes"]:
        query = query.filter(Stock.code.in_(request["stock_codes"]))
    if request["announcement_ids"]:
        query = query.filter(Announcement.ann_id.in_(request["announcement_ids"]))
    if request["date_from"]:
        query = query.filter(Announcement.ann_date >= datetime.fromisoformat(request["date_from"]))
    if request["date_to"]:
        end = datetime.fromisoformat(request["date_to"])
        if len(request["date_to"]) == 10:
            end = end.replace(hour=23, minute=59, second=59)
        query = query.filter(Announcement.ann_date <= end)
    selected: list[Announcement] = []
    skipped: list[dict[str, Any]] = []
    for announcement in query.order_by(Announcement.ann_date, Announcement.id).all():
        families = _families(session, announcement)
        if request["event_families"] and not set(families).intersection(request["event_families"]):
            skipped.append({"announcement_id": announcement.ann_id, "reason": "family_filter_mismatch"})
            continue
        evidence = _evidence(session, announcement)
        if request["only_failed"]:
            latest_parse = session.query(P3ParseRun).filter_by(announcement_id=announcement.id).order_by(P3ParseRun.id.desc()).first()
            evidence_failed = bool(evidence and (evidence.download_status == "failed" or evidence.text_status == "failed"))
            if not evidence_failed and not (latest_parse and latest_parse.status == "failed"):
                skipped.append({"announcement_id": announcement.ann_id, "reason": "not_failed"})
                continue
        if request["only_unparsed"] and _has_parse(session, evidence, _execution_parser_version(request)):
            skipped.append({"announcement_id": announcement.ann_id, "reason": "already_parsed_same_version_and_hash"})
            continue
        selected.append(announcement)
    return selected, skipped


def preview_backfill(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Build a stable preview without downloads, parsing, status changes or commits."""
    request = normalize_request(payload)
    announcements, skipped = select_announcements(session, request)
    by_stock: dict[str, int] = {}
    by_family: dict[str, int] = {}
    candidates: list[dict[str, Any]] = []
    totals = {key: 0 for key in ("existing_pdf", "missing_pdf", "existing_raw_text", "missing_raw_text", "parsed", "unparsed", "possible_failure")}
    for announcement in announcements:
        evidence = _evidence(session, announcement)
        has_pdf = bool(evidence and evidence.download_status == "downloaded" and (evidence.file_hash_sha256 or evidence.content_hash))
        has_text = bool(evidence and evidence.text_status == "extracted")
        parsed = _has_parse(session, evidence, _execution_parser_version(request))
        totals["existing_pdf" if has_pdf else "missing_pdf"] += 1
        totals["existing_raw_text" if has_text else "missing_raw_text"] += 1
        totals["parsed" if parsed else "unparsed"] += 1
        if not has_pdf and not announcement.url:
            totals["possible_failure"] += 1
        by_stock[announcement.stock.code] = by_stock.get(announcement.stock.code, 0) + 1
        families = _families(session, announcement)
        for family in families or ["UNCLASSIFIED"]:
            by_family[family] = by_family.get(family, 0) + 1
        candidates.append({
            "id": announcement.id, "announcement_id": announcement.ann_id,
            "stock_code": announcement.stock.code, "headline": announcement.headline,
            "ann_date": announcement.ann_date, "families": families,
            "has_pdf": has_pdf, "has_raw_text": has_text, "already_parsed": parsed,
            "reason": "selected_by_explicit_admin_scope",
        })
    candidate_ids = [row.id for row in announcements]
    token = hashlib.sha256(_json({"request": request, "candidate_ids": candidate_ids}).encode()).hexdigest()
    actions = [name for name, enabled in (
        ("download_missing_pdf", request["download_missing_pdf"]), ("extract_raw_text", request["extract_raw_text"]),
        ("parse_document", request["parse_document"]), ("classify_events", request["classify_events"]),
        ("extract_facts", request["extract_facts"]), ("map_entities", request["map_entities"]),
        ("check_version_relations", request["check_version_relations"]),
    ) if enabled]
    return {
        "preview_token": token, "filters": request, "candidate_ids": candidate_ids,
        "total_announcements": len(announcements), "skipped_count": len(skipped), "skipped": skipped,
        **totals,
        "estimated_downloads": totals["missing_pdf"] if request["download_missing_pdf"] else 0,
        "estimated_reparse": sum(not row["already_parsed"] for row in candidates) if request["parse_document"] else 0,
        "by_stock": dict(sorted(by_stock.items())), "by_family": dict(sorted(by_family.items())),
        "actions": actions, "candidates": candidates,
        "notice": "本次只处理管理员选定范围，不会自动处理全部历史公告。",
        "read_only": True,
    }


def create_backfill_run(session: Session, payload: dict[str, Any], preview_token: str, requested_by: str = "admin", retry_of_run_id: int | None = None) -> BackfillRun:
    preview = preview_backfill(session, payload)
    if preview["preview_token"] != preview_token:
        raise ValueError("preview is stale or does not match the confirmed filters; preview again")
    run = BackfillRun(
        status="previewed", requested_by=requested_by, parser_version=_execution_parser_version(preview["filters"]),
        pipeline_version=PIPELINE_VERSION, filter_snapshot_json=_json({"filters": preview["filters"], "candidate_ids": preview["candidate_ids"]}),
        configuration_snapshot_json=_json({"actions": preview["actions"], "preview_counts": {k: preview[k] for k in ("total_announcements", "existing_pdf", "missing_pdf", "existing_raw_text", "missing_raw_text", "parsed", "unparsed", "skipped_count")}}),
        preview_token=preview_token, total_announcements=preview["total_announcements"], retry_of_run_id=retry_of_run_id,
    )
    session.add(run); session.flush()
    for announcement in session.query(Announcement).filter(Announcement.id.in_(preview["candidate_ids"])).all():
        session.add(BackfillRunItem(backfill_run_id=run.id, announcement_id=announcement.id, stock_id=announcement.stock_id, status="pending", stage="metadata", parser_version=run.parser_version))
    session.commit(); session.refresh(run)
    return run


def _counts(session: Session, announcement_id: int) -> dict[str, int]:
    mapping_count = session.query(EntityMapping.id).join(EntityMention).filter(EntityMention.announcement_id == announcement_id).count()
    return {
        "events": session.query(P3Event.id).filter_by(announcement_id=announcement_id).count(),
        "facts": session.query(P3Fact.id).filter_by(announcement_id=announcement_id).count(),
        "mappings": mapping_count,
        "relations": session.query(P3VersionRelation.id).filter_by(source_announcement_id=announcement_id).count(),
    }


def execute_backfill_run(session: Session, run: BackfillRun) -> BackfillRun:
    if run.status not in {"previewed", "draft"}:
        return run
    snapshot = json.loads(run.filter_snapshot_json)
    request = snapshot["filters"]
    run.status = "running"; run.started_at = datetime.utcnow(); session.commit()
    errors: list[str] = []
    items = session.query(BackfillRunItem).filter_by(backfill_run_id=run.id).order_by(BackfillRunItem.id).all()
    for item in items:
        session.refresh(run)
        if run.cancel_requested:
            run.status = "cancelled"; break
        announcement = session.get(Announcement, item.announcement_id)
        stock = session.get(Stock, item.stock_id)
        item.status = "running"; item.started_at = datetime.utcnow(); session.commit()
        before = _counts(session, announcement.id)
        made_progress = False
        try:
            parse_created = False
            evidence = _evidence(session, announcement)
            before_downloaded = bool(evidence and evidence.download_status == "downloaded")
            before_text = bool(evidence and evidence.text_status == "extracted")
            needs_evidence = request["download_missing_pdf"] or request["extract_raw_text"] or request["parse_document"]
            if needs_evidence:
                item.stage = "pdf_download" if request["download_missing_pdf"] else "text_extract"
                evidence = ensure_evidence(
                    session, announcement, stock,
                    extract_only=not request["download_missing_pdf"],
                    download_enabled=request["download_missing_pdf"], extract_enabled=request["extract_raw_text"],
                )
                session.commit()
            item.evidence_document_id = evidence.id if evidence else None
            if evidence and evidence.download_status == "downloaded" and not before_downloaded: run.downloaded_files += 1
            if evidence and evidence.text_status == "extracted" and not before_text: run.extracted_texts += 1
            made_progress = bool(
                evidence and ((evidence.download_status == "downloaded" and not before_downloaded) or (evidence.text_status == "extracted" and not before_text))
            )
            if request["parse_document"]:
                if evidence is None or evidence.text_status != "extracted":
                    item.stage = "text_extract"
                    raise RuntimeError(evidence.error_message if evidence and evidence.error_message else "raw text is not available")
                item.stage = "parse"; item.input_hash = evidence.file_hash_sha256 or evidence.content_hash
                existed = _has_parse(session, evidence, run.parser_version)
                parse_run = parse_evidence(
                    session, evidence, run.parser_version,
                    classify_events=request["classify_events"], extract_facts=request["extract_facts"],
                    map_entities=request["map_entities"], check_version_relations=request["check_version_relations"],
                )
                if parse_run.status == "failed":
                    raise RuntimeError(parse_run.error_message or "P3 parse failed")
                if not existed:
                    run.parsed_documents += 1
                    parse_created = True
            after = _counts(session, announcement.id)
            item.created_event_count = after["events"] - before["events"]
            item.created_fact_count = after["facts"] - before["facts"]
            item.mapped_count = after["mappings"] - before["mappings"]
            item.review_needed_count = session.query(P3Fact.id).filter_by(announcement_id=announcement.id, review_status="review_needed").count() + session.query(P3Event.id).filter_by(announcement_id=announcement.id, classification_status="review_needed").count()
            item.stage = "version_relation" if request["check_version_relations"] else "entity_map" if request["map_entities"] else "fact_extract" if request["extract_facts"] else "classify" if request["classify_events"] else "parse"
            changed = parse_created or (not before_downloaded and bool(evidence and evidence.download_status == "downloaded")) or (not before_text and bool(evidence and evidence.text_status == "extracted")) or any(after[key] > before[key] for key in after)
            item.status = "success" if changed else "skipped"
        except Exception as exc:
            session.rollback()
            item = session.get(BackfillRunItem, item.id)
            run = session.get(BackfillRun, run.id)
            item.status = "partial" if made_progress else "failed"; item.error_message = str(exc)[:2000]
            errors.append(f"{announcement.ann_id}: {exc}")
        item.finished_at = datetime.utcnow(); session.commit()
    session.refresh(run)
    counts = {status: session.query(BackfillRunItem).filter_by(backfill_run_id=run.id, status=status).count() for status in ("success", "skipped", "partial", "failed")}
    run.succeeded_announcements = counts["success"]
    run.skipped_announcements = counts["skipped"]
    run.partial_announcements = counts["partial"]
    run.failed_announcements = counts["failed"]
    run.created_events = sum(row[0] or 0 for row in session.query(BackfillRunItem.created_event_count).filter_by(backfill_run_id=run.id))
    run.created_facts = sum(row[0] or 0 for row in session.query(BackfillRunItem.created_fact_count).filter_by(backfill_run_id=run.id))
    run.mapped_entities = sum(row[0] or 0 for row in session.query(BackfillRunItem.mapped_count).filter_by(backfill_run_id=run.id))
    run.review_needed_count = sum(row[0] or 0 for row in session.query(BackfillRunItem.review_needed_count).filter_by(backfill_run_id=run.id))
    run.error_summary = "; ".join(errors[:10]) or None
    if run.cancel_requested:
        run.status = "cancelled"
    elif counts["failed"] == run.total_announcements and run.total_announcements:
        run.status = "failed"
    elif counts["failed"] or counts["partial"]:
        run.status = "partial"
    else:
        run.status = "success"
    run.finished_at = datetime.utcnow(); session.commit(); session.refresh(run)
    return run


def retry_failed(session: Session, source_run: BackfillRun, requested_by: str) -> BackfillRun:
    failed_ids = [row.announcement_id for row in session.query(BackfillRunItem).filter(BackfillRunItem.backfill_run_id == source_run.id, BackfillRunItem.status.in_(["failed", "partial"])).all()]
    if not failed_ids:
        raise ValueError("run has no failed or partial items")
    announcements = session.query(Announcement).filter(Announcement.id.in_(failed_ids)).all()
    request = json.loads(source_run.filter_snapshot_json)["filters"]
    request["announcement_ids"] = [row.ann_id for row in announcements]
    request["stock_codes"] = []
    request["date_from"] = None; request["date_to"] = None; request["event_families"] = []
    preview = preview_backfill(session, request)
    run = create_backfill_run(session, request, preview["preview_token"], requested_by, source_run.id)
    return execute_backfill_run(session, run)
