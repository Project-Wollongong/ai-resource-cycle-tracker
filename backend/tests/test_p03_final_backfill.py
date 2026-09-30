from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import admin
from app.api.security import require_admin_access
from app.models import Announcement, BackfillRun, BackfillRunItem, EvidenceDocument, P3Event, P3Fact, Stock
from app.config import settings
from app.analysis.ai_stub import NoopAnalyzer
from app.datasources.base import RawAnnouncement
from app.services.announcements import sync_announcements
from app.services import announcements as announcement_service


def _client(db):
    app = FastAPI()
    app.include_router(admin.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin_access] = lambda: True
    return TestClient(app)


def _announcement(db, tmp_path, ann_id="backfill-good", with_text=True):
    stock = db.query(Stock).filter_by(code="BF1").first()
    if stock is None:
        stock = Stock(code="BF1", name="Backfill One", commodity="copper")
        db.add(stock); db.flush()
    announcement = Announcement(stock_id=stock.id, ann_id=ann_id, headline="DFS Revised Completion Timing", ann_date=datetime(2026, 9, 18), url="")
    db.add(announcement); db.flush()
    evidence = EvidenceDocument(stock_id=stock.id, announcement_id=announcement.id, source_type="asx_pdf", source_id=ann_id, title=announcement.headline, document_date=announcement.ann_date, download_status="downloaded" if with_text else "failed", text_status="extracted" if with_text else "failed", evidence_status="text_ready" if with_text else "failed", file_hash_sha256=("a" * 63 + str(len(ann_id) % 10)) if with_text else None)
    if with_text:
        path = tmp_path / f"{ann_id}.txt"
        path.write_text("HIGHLIGHTS\nDFS completion has been rescheduled to Q4 2026 from September 2026.\nFID targeted for end of 2027.", encoding="utf-8")
        evidence.local_raw_text_path = str(path)
    db.add(evidence); db.flush(); announcement.evidence_document_id = evidence.id; db.commit()
    return announcement, evidence


def _request(**overrides):
    payload = {
        "stock_codes": ["BF1"], "announcement_ids": [], "event_families": [],
        "download_missing_pdf": False, "extract_raw_text": False, "parse_document": True,
        "classify_events": True, "extract_facts": True, "map_entities": True,
        "check_version_relations": True, "only_failed": False, "only_unparsed": False,
        "parser_version": "p3-final-test-v1",
    }
    payload.update(overrides)
    return payload


def test_preview_is_read_only_scoped_and_run_is_idempotent(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "evidence_root", str(tmp_path))
    _announcement(db_session, tmp_path)
    client = _client(db_session)
    before = (db_session.query(BackfillRun).count(), db_session.query(P3Event).count(), db_session.query(P3Fact).count())
    preview = client.post("/api/admin/backfill/preview", json=_request())
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["read_only"] is True and body["total_announcements"] == 1
    assert "不会自动处理全部历史公告" in body["notice"]
    assert before == (db_session.query(BackfillRun).count(), db_session.query(P3Event).count(), db_session.query(P3Fact).count())

    executed = client.post("/api/admin/backfill/run", json={**_request(), "preview_token": body["preview_token"], "requested_by": "pytest"})
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "success", executed.json()["error_summary"]
    first_counts = (db_session.query(P3Event).count(), db_session.query(P3Fact).count())
    assert first_counts[0] > 0

    preview2 = client.post("/api/admin/backfill/preview", json=_request()).json()
    rerun = client.post("/api/admin/backfill/run", json={**_request(), "preview_token": preview2["preview_token"], "requested_by": "pytest"})
    assert rerun.status_code == 200
    assert rerun.json()["skipped_announcements"] == 1
    assert first_counts == (db_session.query(P3Event).count(), db_session.query(P3Fact).count())


def test_preview_requires_explicit_scope_and_rejects_stale_token(db_session):
    client = _client(db_session)
    no_scope = client.post("/api/admin/backfill/preview", json=_request(stock_codes=[]))
    assert no_scope.status_code == 422
    stale = client.post("/api/admin/backfill/run", json={**_request(), "preview_token": "0" * 64, "requested_by": "pytest"})
    assert stale.status_code == 409
    assert db_session.query(BackfillRun).count() == 0


def test_partial_run_and_retry_only_failed_items(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "evidence_root", str(tmp_path))
    _announcement(db_session, tmp_path, "backfill-good-2", True)
    failed_announcement, failed_evidence = _announcement(db_session, tmp_path, "backfill-failed", False)
    client = _client(db_session)
    preview = client.post("/api/admin/backfill/preview", json=_request()).json()
    result = client.post("/api/admin/backfill/run", json={**_request(), "preview_token": preview["preview_token"], "requested_by": "pytest"})
    assert result.status_code == 200
    assert result.json()["status"] == "partial", result.json()["error_summary"]
    source_run_id = result.json()["id"]
    assert db_session.query(BackfillRunItem).filter_by(backfill_run_id=source_run_id, status="failed").count() == 1

    path = tmp_path / "recovered.txt"
    path.write_text("HIGHLIGHTS\nDFS completion targeted for Q4 2026.", encoding="utf-8")
    failed_evidence.download_status = "downloaded"; failed_evidence.text_status = "extracted"
    failed_evidence.evidence_status = "text_ready"; failed_evidence.file_hash_sha256 = "b" * 64
    failed_evidence.local_raw_text_path = str(path); db_session.commit()
    retried = client.post(f"/api/admin/backfill/runs/{source_run_id}/retry-failed?requested_by=pytest")
    assert retried.status_code == 200, retried.text
    assert retried.json()["retry_of_run_id"] == source_run_id
    retry_items = db_session.query(BackfillRunItem).filter_by(backfill_run_id=retried.json()["id"]).all()
    assert len(retry_items) == 1 and retry_items[0].announcement_id == failed_announcement.id


def test_run_and_item_queries_do_not_expose_local_paths(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "evidence_root", str(tmp_path))
    _announcement(db_session, tmp_path, "backfill-safe", True)
    client = _client(db_session)
    preview = client.post("/api/admin/backfill/preview", json=_request()).json()
    run = client.post("/api/admin/backfill/run", json={**_request(), "preview_token": preview["preview_token"], "requested_by": "pytest"}).json()
    detail = client.get(f"/api/admin/backfill/runs/{run['id']}")
    items = client.get(f"/api/admin/backfill/runs/{run['id']}/items")
    assert detail.status_code == items.status_code == 200
    assert str(tmp_path) not in detail.text and str(tmp_path) not in items.text


def test_new_announcement_automatically_continues_from_p02_to_p03(db_session, monkeypatch):
    stock = Stock(code="AUTO", name="Automatic Co", commodity="copper")
    db_session.add(stock); db_session.commit()
    raw = RawAnnouncement("auto-1", "DFS Completion Timing", datetime(2026, 9, 30, tzinfo=timezone.utc), "https://example.test/auto.pdf", True, {"announcementType": "PROGRESS REPORT"})
    source = SimpleNamespace(fetch=lambda code, count: [raw])
    parse_calls = []

    def fake_evidence(session, announcement, current_stock, **kwargs):
        row = EvidenceDocument(stock_id=current_stock.id, announcement_id=announcement.id, source_type="asx_pdf", source_id=announcement.ann_id, title=announcement.headline, download_status="downloaded", text_status="extracted", evidence_status="text_ready", file_hash_sha256="c" * 64)
        session.add(row); session.flush(); announcement.evidence_document_id = row.id
        return row

    monkeypatch.setattr(announcement_service, "ensure_evidence", fake_evidence)
    monkeypatch.setattr(announcement_service, "parse_evidence", lambda session, evidence, version: (parse_calls.append((evidence.id, version)) or SimpleNamespace(status="parsed")))
    result = sync_announcements(db_session, stock, source, NoopAnalyzer(), include_evidence_stats=True)
    assert result["new"] == 1 and result["p3_parsed"] == 1
    assert len(parse_calls) == 1
    assert db_session.query(Announcement).filter_by(ann_id="auto-1").count() == 1

    second = sync_announcements(db_session, stock, source, NoopAnalyzer(), include_evidence_stats=True)
    assert second["new"] == 0 and len(parse_calls) == 1


def test_backfill_stage_switches_and_failed_filter_are_effective(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "evidence_root", str(tmp_path))
    _announcement(db_session, tmp_path, "stage-only", True)
    _announcement(db_session, tmp_path, "failed-only", False)
    client = _client(db_session)

    failed_preview = client.post("/api/admin/backfill/preview", json=_request(only_failed=True, only_unparsed=False)).json()
    assert failed_preview["total_announcements"] == 1
    assert failed_preview["candidates"][0]["announcement_id"] == "failed-only"

    parse_only = _request(
        announcement_ids=["stage-only"], stock_codes=[], classify_events=False,
        extract_facts=False, map_entities=False, check_version_relations=False,
    )
    preview = client.post("/api/admin/backfill/preview", json=parse_only).json()
    result = client.post("/api/admin/backfill/run", json={**parse_only, "preview_token": preview["preview_token"], "requested_by": "pytest"})
    assert result.status_code == 200, result.text
    assert result.json()["parsed_documents"] == 1
    assert result.json()["created_events"] == 0 and result.json()["created_facts"] == 0
