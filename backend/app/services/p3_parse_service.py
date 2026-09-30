"""Versioned P03 parse service reading only local EvidenceDocument files."""
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session
from pypdf import PdfReader

from ..models import Announcement, AssetUnitIdentity, EvidenceDocument, P3Event, P3Fact, P3InformationPoint, P3ParseRun, ProjectIdentity
from .p3_classification_service import classify_announcement
from .p3_fact_extractor import extract_and_persist_facts
from .p3_information_point_service import build_information_points
from .p3_section_detector import detect_sections
from .p3_revision_marker import connect_version_candidate
from .p3_summary_fact_pipeline import extract_summary_first_candidates
from .p3_entity_matching import unique_identity_match
from .entity_resolution_service import resolve_entities_for_run
from .entity_fuzzy_matcher import suggest_fuzzy_mappings
from .p3_entity_candidate_service import aggregate_unresolved_candidates, discover_entity_candidates
from .p3_versioning_service import detect_version_relation_candidates

PARSER_NAME = "deterministic_p3_parser"
PARSER_VERSION = "p3_reported_fact_v7_version_relations"


def parse_evidence(
    session: Session,
    evidence: EvidenceDocument,
    parser_version: str = PARSER_VERSION,
    *,
    classify_events: bool = True,
    extract_facts: bool = True,
    map_entities: bool = True,
    check_version_relations: bool = True,
) -> P3ParseRun:
    input_hash = evidence.file_hash_sha256 or evidence.content_hash or _path_hash(evidence.local_raw_text_path or evidence.raw_text_path)
    if not input_hash:
        return _failed_run(session, evidence, parser_version, "evidence has no local text or file hash", "no_text")
    existing = session.query(P3ParseRun).filter_by(evidence_document_id=evidence.id, parser_name=PARSER_NAME, parser_version=parser_version, input_hash=input_hash).filter(P3ParseRun.status.in_(["parsed", "partial", "review_needed"])).order_by(P3ParseRun.id.desc()).first()
    if existing:
        if not session.query(P3InformationPoint).filter_by(parse_run_id=existing.id).first():
            existing_facts = session.query(P3Fact).filter_by(parse_run_id=existing.id).order_by(P3Fact.id).all()
            if existing_facts:
                build_information_points(session, existing, existing_facts)
                session.commit()
        return existing
    previous = session.query(P3ParseRun).filter_by(evidence_document_id=evidence.id).filter(P3ParseRun.status.in_(["parsed", "partial", "review_needed"])).all()
    for run in previous: run.status = "superseded"
    run = P3ParseRun(evidence_document_id=evidence.id, announcement_id=evidence.announcement_id, parser_name=PARSER_NAME, parser_version=parser_version, input_hash=input_hash, status="running")
    session.add(run); session.flush()
    try:
        pages = _read_pages(evidence)
        if not pages:
            run.status = "failed"; run.source_scope = "no_text"; run.error_message = "no readable local PDF or Raw Text"; run.completed_at = datetime.utcnow(); session.commit(); return run
        sections = detect_sections(pages)
        announcement = session.get(Announcement, evidence.announcement_id) if evidence.announcement_id else None
        headline = announcement.headline if announcement else evidence.title
        raw_payload = announcement.raw_payload if announcement else None
        if sections:
            ranked = sorted(sections, key=lambda item: (0 if item["name"] in {"summary", "executive_summary"} else 1 if item["name"] == "highlights" else 2, item["page"]))
            first_page = ranked[0]["page"]
            selected = [item for item in ranked if item["page"] == first_page][:2]
            scope = selected[0]["name"]
            event_inputs = selected
        else:
            scope = "body_fallback"
            event_inputs = [{"text": pages[0], "name": "body_fallback", "page": 1}]

        # Standard ASX forms are a deliberate exception to Summary-only scope:
        # their stable tables are scanned for routing anchors and page lineage.
        prelim = classify_announcement(headline, raw_payload, [], reported_on=evidence.document_date)
        if sections and (prelim.document.default_family in {"F02", "F06", "F07"} or set(prelim.families) & {"F02", "F06", "F07"}):
            event_inputs.append({"text": pages[0], "name": "body_fallback", "page": 1})
        if prelim.document.standard_form in {"Appendix 5B", "Appendix 4C"}:
            for page_number, page_text in enumerate(pages, 1):
                if any(marker in page_text.casefold() for marker in ("cash and cash equivalents", "net cash from", "quarter ended", "exploration & evaluation")):
                    event_inputs.append({"text": page_text, "name": "standard_form", "page": page_number})

        run.source_scope = scope
        run.pages_examined_json = json.dumps(sorted({item["page"] for item in event_inputs if item.get("page") is not None}))
        result = classify_announcement(headline, raw_payload, event_inputs, reported_on=evidence.document_date)
        if announcement and classify_events:
            announcement.document_category = result.document.document_category
            announcement.official_header_type = result.document.official_header_type
            announcement.official_subtype = result.document.official_subtype
            announcement.standard_form = result.document.standard_form
            announcement.event_families_json = json.dumps(result.families, ensure_ascii=False)
            announcement.event_labels_json = json.dumps(result.event_tags, ensure_ascii=False)
            announcement.revision_tags_json = json.dumps(result.revision_tags, ensure_ascii=False)
            announcement.classification_source = "summary_confirmation" if sections else "body_fallback"
            connect_version_candidate(session, announcement)
        event_models: list[P3Event] = []
        for item in result.events if classify_events else []:
            project_id, asset_unit_id = _match_approved_entities(session, item["source_excerpt"])
            event = P3Event(announcement_id=evidence.announcement_id, evidence_document_id=evidence.id, parse_run_id=run.id, stock_id=evidence.stock_id, project_id=project_id, asset_unit_id=asset_unit_id, **item)
            if run.source_scope == "body_fallback" and event.classification_status != "review_needed":
                event.classification_status = "review_needed"
            session.add(event)
            event_models.append(event)
        session.flush()
        fact_candidates, extraction_audit = extract_summary_first_candidates(
            event_models, pages, sections, result.document.standard_form
        ) if extract_facts else ([], {"standard_form_pages": [], "body_fallback_pages": []})
        accessed_pages = {item["page"] for item in event_inputs if item.get("page") is not None}
        accessed_pages.update(extraction_audit["standard_form_pages"])
        accessed_pages.update(extraction_audit["body_fallback_pages"])
        accessed_pages.update(item["page"] for item in sections if item.get("page") is not None)
        run.pages_examined_json = json.dumps(sorted(accessed_pages))
        facts = extract_and_persist_facts(session, run, event_models, candidates=fact_candidates) if extract_facts else []
        entity_mentions, entity_mappings = resolve_entities_for_run(session, run, event_models, facts) if map_entities else ([], [])
        candidate_mentions, candidate_mappings, _ = discover_entity_candidates(
            session, run, event_models, facts, aggregate_proposals=False
        ) if map_entities else ([], [], [])
        fuzzy_suggestions = suggest_fuzzy_mappings(session, candidate_mentions) if map_entities else []
        update_proposals = aggregate_unresolved_candidates(
            session, announcement.stock_id, candidate_mappings
        ) if announcement and map_entities else []
        version_relations = detect_version_relation_candidates(session, announcement, event_models, facts) if announcement and check_version_relations else []
        information_points = build_information_points(session, run, facts) if facts else []
        point_types = Counter(point.point_type for point in information_points)
        run.status = "review_needed" if result.review_needed or run.source_scope == "body_fallback" else "parsed"
        if any(fact.review_status == "review_needed" for fact in facts) and run.status == "parsed":
            run.status = "review_needed"
        run.output_summary_json = json.dumps({
            "event_count": len(result.events), "fact_count": len(facts),
            "information_point_count": len(information_points), "families": result.families,
            "document_category": result.document.document_category, "neutral_only": True,
            "derived_metrics": False, "fact_extraction": extraction_audit,
            "requested_stages": {"classify_events": classify_events, "extract_facts": extract_facts, "map_entities": map_entities, "check_version_relations": check_version_relations},
            "entity_resolution": {
                "version": "p3_entity_mapping_v2_review_only_suggestions",
                "mention_count": len(entity_mentions) + len(candidate_mentions),
                "mapping_count": len(entity_mappings) + len(candidate_mappings) + len(fuzzy_suggestions),
                "confirmed_count": sum(item.status == "confirmed" for item in entity_mappings),
                "review_needed_count": sum(item.status == "review_needed" for item in entity_mappings),
                "methods": ["exact_match", "alias_match", "former_name_match", "fuzzy_match"],
                "fuzzy_matching": True,
                "fuzzy_suggestion_count": len(fuzzy_suggestions),
                "fuzzy_auto_confirmed_count": 0,
                "model_assistance": "review_only_intake",
                "model_auto_confirmed_count": 0,
                "p01_entities_created": 0,
                "unresolved_mention_count": len(candidate_mentions),
                "unresolved_mapping_count": len(candidate_mappings),
                "pending_proposal_ids": [item.id for item in update_proposals],
            },
            "version_relations": {
                "candidate_count": len(version_relations),
                "candidate_ids": [item.id for item in version_relations],
                "automatic_status_changes": 0,
                "human_confirmation_required": True,
            },
            "information_point_grouping": {
                "schema": "logical_information_point_v2",
                "information_point_count": len(information_points),
                "atomic_fact_count": len(facts),
                "grouped_fact_count": sum(point.fact_count for point in information_points),
                "all_facts_preserved": sum(point.fact_count for point in information_points) == len(facts),
                "point_types": dict(sorted(point_types.items())),
                "display_reduction": len(facts) - len(information_points),
                "no_padding": True,
                "no_truncation": True,
            },
        }, ensure_ascii=False)
    except Exception as exc:
        run.status = "failed"; run.error_message = str(exc)[:2000]
    run.completed_at = datetime.utcnow(); session.commit(); session.refresh(run); return run


def _read_pages(evidence: EvidenceDocument) -> list[str]:
    if evidence.text_status != "extracted":
        return []
    if evidence.local_original_path and Path(evidence.local_original_path).is_file():
        return [page.extract_text() or "" for page in PdfReader(evidence.local_original_path).pages]
    path = evidence.local_raw_text_path or evidence.raw_text_path
    if path and Path(path).is_file():
        return [Path(path).read_text(encoding="utf-8")]
    return []


def _path_hash(path: str | None) -> str | None:
    if not path or not Path(path).is_file(): return None
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _failed_run(session, evidence, version, error, scope):
    run = P3ParseRun(evidence_document_id=evidence.id, announcement_id=evidence.announcement_id, parser_name=PARSER_NAME, parser_version=version, input_hash=evidence.file_hash_sha256 or "", status="failed", source_scope=scope, error_message=error, completed_at=datetime.utcnow())
    session.add(run); session.commit(); session.refresh(run); return run


def _match_approved_entities(session: Session, excerpt: str):
    project_match = unique_identity_match(
        excerpt,
        session.query(ProjectIdentity).filter(ProjectIdentity.is_current.is_(True)).all(),
        "project_id",
    )
    asset_match = unique_identity_match(
        excerpt,
        session.query(AssetUnitIdentity).filter(AssetUnitIdentity.is_current.is_(True)).all(),
        "asset_unit_id",
    )
    if asset_match:
        asset = session.get(AssetUnitIdentity, asset_match.id).asset_unit
        if project_match and asset.project_id != project_match.project_id:
            return project_match.project_id, None
        return asset.project_id, asset_match.asset_unit_id
    return (project_match.project_id if project_match else None, None)
