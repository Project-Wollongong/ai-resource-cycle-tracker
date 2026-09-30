from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import admin, announcements
from app.api.security import require_admin_access
from app.config import settings
from app.models import Announcement, EvidenceDocument, Stock


def _admin_client(db_session):
    app = FastAPI()
    app.include_router(admin.router, prefix="/api")
    app.include_router(announcements.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin_access] = lambda: True
    return TestClient(app)


def test_ingestion_config_is_mask_free_and_mutable(db_session):
    client = _admin_client(db_session)
    response = client.get("/api/admin/ingestion-config")
    assert response.status_code == 200
    assert response.json()["announcements"]["max_items"] == 20
    updated = client.put("/api/admin/ingestion-config", json={"announcements": {"max_items": 7, "timeout_seconds": 12}})
    assert updated.status_code == 200
    assert updated.json()["announcements"]["max_items"] == 7


def test_version_relation_is_manual_and_queryable(db_session):
    stock = Stock(code="VER", name="Version Co", commodity="gold")
    db_session.add(stock); db_session.flush()
    first = Announcement(stock_id=stock.id, ann_id="ver-1", headline="DFS Timing", ann_date=datetime(2026, 1, 1), url="https://example.test/1.pdf")
    second = Announcement(stock_id=stock.id, ann_id="ver-2", headline="DFS Revised Completion Timing", ann_date=datetime(2026, 1, 2), url="https://example.test/2.pdf")
    db_session.add_all([first, second]); db_session.commit()
    client = _admin_client(db_session)
    created = client.post("/api/admin/announcement-version-relations", json={"predecessor_announcement_id": first.id, "successor_announcement_id": second.id, "relation_type": "revises", "confidence": 0.8})
    assert created.status_code == 201
    assert created.json()["status"] == "pending_review"
    listed = client.get("/api/announcements/ver-2/version-relations")
    assert listed.status_code == 200 and len(listed.json()) == 1
    reviewed = client.put(f"/api/admin/announcement-version-relations/{created.json()['id']}/review", json={"status": "confirmed", "reviewed_by": "human"})
    assert reviewed.status_code == 200 and reviewed.json()["status"] == "confirmed"


def test_historical_baseline_uses_same_evidence_shape(db_session, monkeypatch, tmp_path):
    stock = Stock(code="HIS", name="Historical Co", commodity="gold")
    db_session.add(stock); db_session.commit()
    source = Path(__file__).parents[2] / "docs" / "beta02-acceptance" / "pdfs" / "S01.pdf"
    monkeypatch.setattr(settings, "evidence_root", str(tmp_path))
    client = _admin_client(db_session)
    response = client.post("/api/admin/evidence/historical-baseline", json={"stock_id": stock.id, "title": "Historical baseline", "local_pdf_path": str(source)})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["historical_baseline"] is True
    assert body["download_status"] == "downloaded"
    assert body["file_hash_sha256"]
    listed = client.get("/api/announcements/evidence?historical_baseline=true")
    assert listed.status_code == 200 and len(listed.json()) == 1
