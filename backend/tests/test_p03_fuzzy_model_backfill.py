import json
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import admin, p3
from app.api.security import require_admin_access
from app.models import (
    Announcement, AssetUnit, AssetUnitIdentity, EntityMapping, EntityMappingChangeLog,
    EntityMention, EvidenceDocument, P01EntityProposal, P3Event, P3Fact, P3ParseRun,
    Project, Stock, StockProject,
)
from app.services.entity_fuzzy_matcher import suggest_fuzzy_mappings
from app.services.entity_mapping_review_service import record_model_suggestion, review_entity_mapping
from app.services.entity_resolution_service import resolve_entities_for_run
from app.services.p01_proposal_approval_service import review_proposal
from app.services.p3_entity_candidate_service import aggregate_unresolved_candidates


def _backbone(db):
    stock = Stock(code="FZY", name="Fuzzy Mining", commodity="copper")
    db.add(stock); db.flush()
    project = Project(project_key="fuzzy-project", name="Project A", commodity="copper")
    db.add(project); db.flush()
    db.add(StockProject(stock_id=stock.id, project_id=project.id, relationship_type="owner"))
    north = AssetUnit(project_id=project.id, name="North Pipe", unit_type="pipe")
    south = AssetUnit(project_id=project.id, name="South Pipe", unit_type="pipe")
    db.add_all([north, south]); db.flush()
    return stock, project, north, south


def _source(db, stock, project, suffix, excerpt):
    announcement = Announcement(
        stock_id=stock.id, ann_id=f"FZY-{suffix}", headline=f"Entity update {suffix}",
        ann_date=datetime(2026, 9, min(int(suffix), 28)), url=f"https://example.test/{suffix}.pdf",
    )
    db.add(announcement); db.flush()
    evidence = EvidenceDocument(
        stock_id=stock.id, announcement_id=announcement.id, source_type="fixture",
        source_id=announcement.ann_id, title=announcement.headline, document_date=announcement.ann_date,
        url=announcement.url, source_url=announcement.url, page_count=2,
        evidence_status="text_ready", download_status="downloaded", text_status="extracted",
    )
    db.add(evidence); db.flush()
    run = P3ParseRun(
        evidence_document_id=evidence.id, announcement_id=announcement.id,
        parser_name="entity-test", parser_version="v1", input_hash=str(suffix).ljust(64, "0"), status="parsed",
    )
    db.add(run); db.flush()
    event = P3Event(
        announcement_id=announcement.id, evidence_document_id=evidence.id, parse_run_id=run.id,
        stock_id=stock.id, project_id=project.id, mapped_project_id=project.id,
        project_mapping_status="confirmed", event_type="DRILL_RESULTS", event_family="F01",
        primary_family="F01", event_title="Entity mapping", source_section="highlights",
        source_page_start=1, source_page_end=1, source_excerpt=excerpt,
    )
    db.add(event); db.flush()
    fact = P3Fact(
        announcement_id=announcement.id, evidence_document_id=evidence.id, parse_run_id=run.id,
        p3_event_id=event.id, stock_id=stock.id, project_id=project.id,
        mapped_project_id=project.id, project_mapping_status="confirmed", fact_type="target_name",
        fact_family="F01", schema_name="test", field_name="Target Name", value_raw=excerpt,
        value_json="{}", source_section="highlights", source_page_start=1, source_page_end=1,
        source_excerpt=excerpt,
    )
    db.add(fact); db.flush()
    return announcement, evidence, run, event, fact


def _unresolved(db, source, raw, normalized, proposal_id=None):
    announcement, evidence, run, event, _ = source
    mention = EntityMention(
        announcement_id=announcement.id, evidence_document_id=evidence.id, parse_run_id=run.id,
        p3_event_id=event.id, mention_type="asset_unit", mention_text_raw=raw,
        mention_text_normalized=normalized, source_section="highlights",
        source_page_start=1, source_page_end=1, source_excerpt=event.source_excerpt,
    )
    db.add(mention); db.flush()
    mapping = EntityMapping(
        entity_mention_id=mention.id, matched_entity_type="asset_unit", matched_entity_id=None,
        match_method="unresolved_candidate", match_confidence=0.55, status="review_needed",
        stock_validation_result="announcement_stock_recorded", parent_validation_result="parent_project_confirmed",
        matching_reason="unresolved test mention", candidate_parent_project_id=event.mapped_project_id,
        proposal_id=proposal_id,
    )
    db.add(mapping); db.flush()
    event.asset_unit_mapping_id = mapping.id
    event.asset_unit_mapping_status = "review_needed"
    return mention, mapping


def _client(db):
    app = FastAPI()
    app.include_router(admin.router, prefix="/api")
    app.include_router(p3.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin_access] = lambda: True
    return TestClient(app)


def test_fuzzy_matching_is_last_step_and_never_auto_confirms(db_session):
    stock, project, north, _ = _backbone(db_session)
    source = _source(db_session, stock, project, "1", "Project A drilling at Nort Pipe.")
    mention, unresolved = _unresolved(db_session, source, "Nort Pipe", "nort pipe")

    suggestions = suggest_fuzzy_mappings(db_session, [mention])

    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion.matched_entity_id == north.id
    assert suggestion.match_method == "fuzzy_match"
    assert suggestion.status == "review_needed"
    assert suggestion.match_confidence >= 0.84
    assert source[3].mapped_asset_unit_id is None
    assert json.loads(suggestion.candidate_payload_json)["automatic_confirmation"] is False
    assert unresolved.status == "review_needed"


def test_fuzzy_known_entity_suggestion_does_not_create_duplicate_p01_candidate(db_session):
    stock, project, _, _ = _backbone(db_session)
    mappings = []
    for index in (7, 8):
        source = _source(db_session, stock, project, str(index), "Project A drilling at Nort Pipe.")
        mention, unresolved = _unresolved(db_session, source, "Nort Pipe", "nort pipe")
        mappings.append(unresolved)
        assert suggest_fuzzy_mappings(db_session, [mention])
    proposals = aggregate_unresolved_candidates(db_session, stock.id, mappings)
    assert proposals == []
    assert db_session.query(P01EntityProposal).count() == 0


def test_model_suggestion_requires_human_confirmation_and_manual_result_is_locked(db_session):
    stock, project, north, _ = _backbone(db_session)
    source = _source(db_session, stock, project, "2", "Project A drilling at North Pipe.")
    mention, _ = _unresolved(db_session, source, "North Pipe", "north pipe")

    suggestion = record_model_suggestion(
        db_session, mention, matched_entity_type="asset_unit", matched_entity_id=north.id,
        confidence=0.93, model_name="fixture-model", model_version="1",
        reasoning="Name and parent project agree.",
    )
    assert suggestion.status == "review_needed" and source[3].mapped_asset_unit_id is None

    confirmed = review_entity_mapping(
        db_session, suggestion, action="confirm", reviewer="p01-owner",
        review_note="Checked the PDF and approved P01 parent.",
    )
    assert confirmed.match_method == "manual_confirmation" and confirmed.status == "confirmed"
    assert source[3].mapped_asset_unit_id == north.id
    assert json.loads(confirmed.candidate_payload_json)["human_locked"] is True

    # Re-running deterministic resolution on the same Event may resolve the
    # Project, but it cannot replace the human-confirmed Asset Unit mapping.
    resolve_entities_for_run(db_session, source[2], [source[3]], [])
    db_session.flush()
    asset_rows = db_session.query(EntityMapping).filter_by(
        entity_mention_id=mention.id, matched_entity_type="asset_unit"
    ).all()
    assert [row.id for row in asset_rows if row.status == "confirmed"] == [confirmed.id]
    assert source[3].asset_unit_mapping_id == confirmed.id


def test_model_suggestion_review_api_exposes_complete_mapping_history(db_session):
    stock, project, north, _ = _backbone(db_session)
    source = _source(db_session, stock, project, "6", "Project A work at North Pipe.")
    mention, unresolved = _unresolved(db_session, source, "North Pipe", "north pipe")
    client = _client(db_session)

    suggested = client.post("/api/admin/p3/entity-mappings/model-suggestions", json={
        "entity_mention_id": mention.id, "matched_entity_type": "asset_unit",
        "matched_entity_id": north.id, "confidence": 0.91,
        "model_name": "fixture-model", "model_version": "1",
        "reasoning": "Name, Stock and parent context agree.",
    })
    assert suggested.status_code == 200, suggested.text
    body = suggested.json()
    assert body["status"] == "review_needed" and body["matched_entity_id"] is None
    assert body["candidate_entity"]["id"] == north.id

    confirmed = client.post(f"/api/admin/p3/entity-mappings/{body['id']}/confirm", json={
        "reviewer": "p01-owner", "review_note": "Checked source page and parent Project.",
    })
    assert confirmed.status_code == 200, confirmed.text
    confirmed_id = confirmed.json()["id"]
    assert confirmed.json()["human_locked"] is True
    history = client.get(f"/api/admin/p3/entity-mappings/{confirmed_id}/history")
    assert history.status_code == 200
    history_body = history.json()
    assert {row["id"] for row in history_body["mappings"]} >= {unresolved.id, body["id"], confirmed_id}
    assert history_body["change_log"][-1]["action"] == "manual_confirmation"


def test_p01_alias_approval_backfills_all_safe_history_and_preserves_manual_conflict(db_session):
    stock, project, north, south = _backbone(db_session)
    sources = [_source(db_session, stock, project, str(index), "Project A drilling at Northern Pipe.") for index in (3, 4, 5)]
    unresolved = [_unresolved(db_session, source, "Northern Pipe", "northern pipe") for source in sources]

    # A prior manual decision on one historical mention is immutable, even if
    # the later P01 alias approval points somewhere else.
    conflict = unresolved[2][1]
    conflict.matched_entity_id = south.id
    conflict.match_method = "manual_confirmation"
    conflict.match_confidence = 1.0
    conflict.status = "confirmed"
    conflict.reviewed_by = "earlier-reviewer"
    sources[2][3].asset_unit_id = south.id
    sources[2][3].mapped_asset_unit_id = south.id
    sources[2][3].asset_unit_mapping_id = conflict.id
    sources[2][3].asset_unit_mapping_status = "confirmed"

    proposal = P01EntityProposal(
        stock_id=stock.id, target_level="asset_unit", proposed_project_name=project.name,
        proposed_asset_name="Northern Pipe", proposed_name="Northern Pipe",
        proposed_name_normalized="northern pipe", proposed_entity_type="asset_unit",
        proposed_parent_project_id=project.id, proposal_type="asset_unit_alias_candidate",
        source_type="p3_entity_candidate", source_ref="historical alias evidence",
        source_excerpt="Northern Pipe", status="pending", created_by="rule",
        proposed_payload_json=json.dumps({"target_asset_unit_id": north.id}),
    )
    db_session.add(proposal); db_session.flush()

    review_proposal(
        db_session, proposal, "approve", "p01-owner",
        "Approved alias and historical backfill after evidence review.",
    )
    db_session.flush()

    identity = db_session.query(AssetUnitIdentity).filter_by(
        asset_unit_id=north.id, normalized_value="northern pipe"
    ).one()
    assert identity.kind == "alias"
    for source in sources[:2]:
        db_session.refresh(source[3])
        assert source[3].mapped_asset_unit_id == north.id
        assert source[3].asset_unit_mapping_status == "confirmed"
    db_session.refresh(sources[2][3])
    assert sources[2][3].mapped_asset_unit_id == south.id
    assert conflict.status == "confirmed"
    backfilled = db_session.query(EntityMapping).filter_by(
        proposal_id=proposal.id, match_method="p01_proposal_approved"
    ).all()
    assert len(backfilled) == 2
    assert db_session.query(EntityMappingChangeLog).filter_by(
        proposal_id=proposal.id, action="p01_proposal_approved_historical_backfill"
    ).count() == 2
    audit = json.loads(proposal.proposed_payload_json)["historical_backfill"]
    assert audit["created_count"] == 2
    assert audit["skipped_existing_confirmation_count"] == 1
    assert audit["automatic_overwrite_count"] == 0
