from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import admin, p3
from app.api.security import require_admin_access
from app.models import Announcement, EvidenceDocument, P3Event, P3EventClassificationReview, P3ParseRun, Stock
from app.services.p3_parse_service import PARSER_VERSION, parse_evidence


FIXTURE = Path(__file__).parents[2] / "docs" / "beta02-acceptance" / "pdfs" / "S01.pdf"


def test_parse_run_is_versioned_and_idempotent(db_session, tmp_path):
    stock = Stock(code="P3T", name="P3 Test", commodity="copper")
    db_session.add(stock); db_session.flush()
    ann = Announcement(stock_id=stock.id, ann_id="p3-1", headline="Highlights", ann_date=datetime(2026, 1, 1), url="https://example.test/a.pdf")
    db_session.add(ann); db_session.flush()
    evidence = EvidenceDocument(stock_id=stock.id, announcement_id=ann.id, source_type="asx_pdf", source_id=ann.ann_id, title=ann.headline, local_original_path=str(FIXTURE), file_hash_sha256="fixture-hash", download_status="downloaded", text_status="extracted", evidence_status="text_ready")
    db_session.add(evidence); db_session.commit()
    first = parse_evidence(db_session, evidence)
    second = parse_evidence(db_session, evidence)
    assert first.id == second.id
    assert first.status in {"parsed", "review_needed"}
    assert db_session.query(P3Event).filter_by(parse_run_id=first.id).count() >= 1
    newer = parse_evidence(db_session, evidence, parser_version="p3_v2")
    assert newer.id != first.id
    assert db_session.get(P3ParseRun, first.id).status == "superseded"


def test_no_local_text_does_not_fake_success(db_session):
    stock = Stock(code="P3F", name="P3 Failure", commodity="gold")
    db_session.add(stock); db_session.flush()
    evidence = EvidenceDocument(stock_id=stock.id, source_type="asx_pdf", source_id="p3-fail", title="No file", file_hash_sha256="x")
    db_session.add(evidence); db_session.commit()
    run = parse_evidence(db_session, evidence)
    assert run.status == "failed"
    assert run.source_scope == "no_text"


def test_p3_api_exposes_status_events_and_history(db_session):
    stock = Stock(code="P3A", name="P3 API", commodity="gold")
    db_session.add(stock); db_session.flush()
    ann = Announcement(stock_id=stock.id, ann_id="p3-api", headline="Test", ann_date=datetime(2026, 1, 1), url="")
    db_session.add(ann); db_session.flush()
    evidence = EvidenceDocument(stock_id=stock.id, announcement_id=ann.id, source_type="asx_pdf", source_id=ann.ann_id, title="Test", local_original_path=str(FIXTURE), file_hash_sha256="api-hash", download_status="downloaded", text_status="extracted", evidence_status="text_ready")
    db_session.add(evidence); db_session.commit(); parse_evidence(db_session, evidence)
    app = FastAPI(); app.include_router(p3.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    status = client.get("/api/announcements/p3-api/parse-status")
    assert status.status_code == 200 and status.json()["event_count"] >= 1
    assert status.json()["fact_count"] >= 1
    assert status.json()["information_point_count"] >= 1
    assert status.json()["count_status"] in {"source_insufficient", "target_range", "high_density"}
    events = client.get("/api/announcements/p3-api/events")
    assert events.status_code == 200 and len(events.json()) >= 1
    assert {"primary_family", "secondary_families", "classification_source", "source_page", "source_excerpt", "parse_run_id", "review_needed"}.issubset(events.json()[0])
    summary = client.get("/api/announcements/p3-api/classification-summary")
    assert summary.status_code == 200
    assert {"document_category", "official_header_type", "event_families", "event_tags", "revision_tags", "parse_status", "review_needed"}.issubset(summary.json())
    runs = client.get(f"/api/evidence/{evidence.id}/parse-runs")
    assert runs.status_code == 200 and len(runs.json()) == 1


def test_manual_review_keeps_original_and_survives_parser_rerun(db_session):
    stock = Stock(code="P3R", name="P3 Review", commodity="copper")
    db_session.add(stock); db_session.flush()
    ann = Announcement(stock_id=stock.id, ann_id="p3-review", headline="DFS Revised Completion Timing", ann_date=datetime(2026, 1, 1), url="")
    db_session.add(ann); db_session.flush()
    evidence = EvidenceDocument(stock_id=stock.id, announcement_id=ann.id, source_type="asx_pdf", source_id=ann.ann_id, title=ann.headline, local_original_path=str(FIXTURE), file_hash_sha256="review-hash", download_status="downloaded", text_status="extracted", evidence_status="text_ready")
    db_session.add(evidence); db_session.commit()
    first = parse_evidence(db_session, evidence)
    event = db_session.query(P3Event).filter_by(parse_run_id=first.id, event_type="Project Delay").one()
    original = event.original_classification_json

    app = FastAPI(); app.include_router(admin.router, prefix="/api"); app.include_router(p3.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin_access] = lambda: True
    client = TestClient(app)
    corrected = client.put(f"/api/admin/p3/events/{event.id}", json={"reviewer": "tester", "review_note": "confirmed neutral wording", "event_title": "DFS schedule delay"})
    assert corrected.status_code == 200
    assert corrected.json()["classification_status"] == "corrected"
    assert db_session.get(P3Event, event.id).original_classification_json == original
    assert db_session.query(P3EventClassificationReview).filter_by(p3_event_id=event.id, action="correct").count() == 1

    newer = parse_evidence(db_session, evidence, parser_version="p3_family_v3")
    assert newer.id != first.id
    effective = client.get("/api/announcements/p3-review/events").json()
    delay = next(item for item in effective if item["event_type"] == "Project Delay")
    assert delay["event_id"] == event.id
    assert delay["event_title"] == "DFS schedule delay"
    history = client.get(f"/api/admin/p3/events/{event.id}/reviews")
    assert history.status_code == 200 and history.json()[0]["action"] == "correct"
