from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import admin, p3, projects
from app.api.security import require_admin_access
from app.models import (
    Announcement, AssetUnit, EntityMapping, EntityMappingChangeLog, EntityMention,
    EvidenceDocument, P01EntityProposal, P01EntityProposalReview, P3Event, P3Fact,
    P3ParseRun, Project, Stock, StockProject,
)
from app.services.p3_entity_candidate_service import discover_entity_candidates


def _seed(db, code="NPP", project_name="Project A"):
    stock = Stock(code=code, name=f"{code} Mining", commodity="copper")
    db.add(stock); db.flush()
    project = Project(project_key=f"{code.casefold()}-project", name=project_name, commodity="copper")
    db.add(project); db.flush()
    db.add(StockProject(stock_id=stock.id, project_id=project.id, relationship_type="owner")); db.flush()
    return stock, project


def _candidate_announcement(db, stock, project, index, name="North Pipe"):
    ann = Announcement(
        stock_id=stock.id, ann_id=f"{stock.code}-{index}", headline=f"{name} update {index}",
        ann_date=datetime(2026, 8, 1) + timedelta(days=index), url=f"https://example.test/{stock.code}-{index}.pdf",
    )
    db.add(ann); db.flush()
    evidence = EvidenceDocument(
        stock_id=stock.id, announcement_id=ann.id, source_type="fixture", source_id=ann.ann_id,
        title=ann.headline, document_date=ann.ann_date, url=ann.url, source_url=ann.url,
        page_count=3, evidence_status="text_ready", download_status="downloaded", text_status="extracted",
    )
    db.add(evidence); db.flush()
    run = P3ParseRun(
        evidence_document_id=evidence.id, announcement_id=ann.id, parser_name="candidate-test",
        parser_version="candidate-v1", input_hash=f"{stock.code}-{index}".ljust(64, "0"), status="running",
    )
    db.add(run); db.flush()
    excerpt = f"Project A reports an independent drill programme and results at {name}."
    event = P3Event(
        announcement_id=ann.id, evidence_document_id=evidence.id, parse_run_id=run.id, stock_id=stock.id,
        project_id=project.id, mapped_project_id=project.id, project_mapping_status="confirmed",
        event_type="DRILL_RESULTS", event_family="F01", primary_family="F01", event_title=f"{name} drilling",
        source_section="highlights", source_page_start=index, source_page_end=index, source_excerpt=excerpt,
    )
    db.add(event); db.flush()
    fact = P3Fact(
        announcement_id=ann.id, evidence_document_id=evidence.id, parse_run_id=run.id, p3_event_id=event.id,
        stock_id=stock.id, project_id=project.id, mapped_project_id=project.id, project_mapping_status="confirmed",
        fact_type="drilling_status", fact_family="F01", schema_name="test", field_name="Drilling Status",
        value_raw="results reported", value_json="{}", source_section="highlights",
        source_page_start=index, source_page_end=index, source_excerpt=excerpt,
    )
    db.add(fact); db.flush()
    mentions, mappings, proposals = discover_entity_candidates(db, run, [event], [fact])
    run.status = "parsed"; db.commit()
    return ann, evidence, run, event, fact, mentions, mappings, proposals


def _client(db):
    app = FastAPI()
    app.include_router(admin.router, prefix="/api")
    app.include_router(projects.router, prefix="/api")
    app.include_router(p3.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin_access] = lambda: True
    return TestClient(app)


def test_first_unknown_name_keeps_mention_and_mapping_without_formal_asset(db_session):
    stock, project = _seed(db_session)
    _, _, _, event, fact, mentions, mappings, proposals = _candidate_announcement(db_session, stock, project, 1)
    assert len(mentions) == 2 and len(mappings) == 2  # Event and Fact contexts are both retained.
    assert all(row.status == "review_needed" and row.matched_entity_id is None for row in mappings)
    assert proposals == []
    assert db_session.query(P01EntityProposal).count() == 0
    assert db_session.query(AssetUnit).count() == 0
    assert event.asset_unit_id is None and fact.asset_unit_id is None
    assert event.asset_unit_mapping_status == fact.asset_unit_mapping_status == "review_needed"


def test_repeated_evidence_aggregates_one_pending_proposal_without_tree_visibility(db_session):
    stock, project = _seed(db_session, "NPA")
    _candidate_announcement(db_session, stock, project, 1)
    _candidate_announcement(db_session, stock, project, 2)
    _candidate_announcement(db_session, stock, project, 3)
    proposals = db_session.query(P01EntityProposal).filter_by(status="pending").all()
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.proposal_type == "new_asset_unit_candidate"
    assert proposal.supporting_announcement_count == 3
    assert proposal.supporting_evidence_count == 3
    assert proposal.supporting_event_count == 3
    assert proposal.supporting_fact_count == 3
    assert db_session.query(AssetUnit).count() == 0
    tree = _client(db_session).get(f"/api/projects/{project.project_key}").json()
    assert tree["asset_units"] == []

    detail = _client(db_session).get(f"/api/admin/entity-review/p3-update-proposals/{proposal.id}")
    assert detail.status_code == 200
    body = detail.json()
    assert len({item["announcement"]["ann_id"] for item in body["evidence"]}) == 3
    assert all(item["source_page_start"] and item["source_excerpt"] for item in body["evidence"])
    assert all(item["evidence_document"]["pdf_url"].startswith("/api/announcements/evidence/") for item in body["evidence"])


def test_same_name_is_not_merged_across_stock_or_parent_project(db_session):
    stock_a, project_a = _seed(db_session, "NSA", "Project A")
    stock_b, project_b = _seed(db_session, "NSB", "Project B")
    other_parent = Project(project_key="nsa-other", name="Other Parent", commodity="copper")
    db_session.add(other_parent); db_session.flush()
    db_session.add(StockProject(stock_id=stock_a.id, project_id=other_parent.id)); db_session.flush()
    for index in (1, 2):
        _candidate_announcement(db_session, stock_a, project_a, index)
        _candidate_announcement(db_session, stock_b, project_b, index)
        _candidate_announcement(db_session, stock_a, other_parent, index + 10)
    rows = db_session.query(P01EntityProposal).filter_by(status="pending", proposed_name_normalized="north pipe").all()
    assert len(rows) == 3
    assert len({row.dedupe_key for row in rows}) == 3


def test_reject_and_correct_preserve_sources_and_review_history(db_session):
    stock, project = _seed(db_session, "NPR")
    first = _candidate_announcement(db_session, stock, project, 1)
    _candidate_announcement(db_session, stock, project, 2)
    proposal = db_session.query(P01EntityProposal).one()
    client = _client(db_session)

    corrected = client.put(f"/api/admin/entity-review/p3-update-proposals/{proposal.id}", json={
        "reviewer": "reviewer-a", "review_note": "standardise candidate label",
        "correction": {"proposed_asset_type": "pipe"},
    })
    assert corrected.status_code == 200 and corrected.json()["status"] == "pending"
    rejected = client.post(f"/api/admin/entity-review/p3-update-proposals/{proposal.id}/reject", json={
        "reviewer": "reviewer-b", "review_note": "insufficient independent materiality",
    })
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert db_session.query(P01EntityProposalReview).filter_by(proposal_id=proposal.id).count() == 2
    assert db_session.query(EntityMention).count() == 4
    assert db_session.query(EntityMapping).count() == 4
    assert db_session.query(P3Event).count() == 2 and db_session.query(P3Fact).count() == 2
    assert db_session.query(EvidenceDocument).count() == 2
    assert db_session.query(AssetUnit).count() == 0
    event_payload = client.get(f"/api/announcements/{first[0].ann_id}/events").json()[0]
    assert event_payload["asset_unit"] is None and event_payload["asset_unit_id"] is None


def test_approve_creates_asset_through_p01_and_backfills_only_scoped_history(db_session):
    stock, project = _seed(db_session, "NPO")
    north = [_candidate_announcement(db_session, stock, project, index) for index in (1, 2, 3)]
    # An unrelated candidate remains pending and must not be batch-linked.
    _candidate_announcement(db_session, stock, project, 20, name="South Pipe")
    proposal = db_session.query(P01EntityProposal).filter_by(proposed_name_normalized="north pipe").one()
    client = _client(db_session)
    approved = client.post(f"/api/admin/entity-review/p3-update-proposals/{proposal.id}/approve", json={
        "reviewer": "p01-owner", "review_note": "three independent announcements establish persistent analytical value",
    })
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "approved" and body["resulting_entity"]["name"] == "North Pipe"
    asset = db_session.query(AssetUnit).filter_by(project_id=project.id, name="North Pipe").one()
    assert db_session.query(AssetUnit).filter_by(name="South Pipe").count() == 0
    tree = client.get(f"/api/projects/{project.project_key}").json()
    assert [row["name"] for row in tree["asset_units"]] == ["North Pipe"]

    north_mention_ids = {row.id for row in db_session.query(EntityMention).filter_by(mention_text_normalized="north pipe").all()}
    old_rows = db_session.query(EntityMapping).filter(EntityMapping.entity_mention_id.in_(north_mention_ids), EntityMapping.match_method == "unresolved_candidate").all()
    new_rows = db_session.query(EntityMapping).filter(EntityMapping.entity_mention_id.in_(north_mention_ids), EntityMapping.match_method == "p01_proposal_approved").all()
    assert old_rows and all(row.status == "superseded" for row in old_rows)
    assert len(new_rows) == len(old_rows) and all(row.status == "confirmed" and row.matched_entity_id == asset.id for row in new_rows)
    assert db_session.query(EntityMappingChangeLog).filter_by(proposal_id=proposal.id).count() == len(new_rows)
    for item in north:
        db_session.refresh(item[3]); db_session.refresh(item[4])
        assert item[3].mapped_asset_unit_id == asset.id and item[4].mapped_asset_unit_id == asset.id
    south = db_session.query(EntityMention).filter_by(mention_text_normalized="south pipe").all()
    assert south and all(row.mappings[-1].status == "review_needed" for row in south)
