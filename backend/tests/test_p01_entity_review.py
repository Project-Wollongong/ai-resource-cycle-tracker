from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import admin
from app.api.security import require_admin_access
from app.models import AssetUnit, Project, Stock


def test_entity_proposal_review_approves_only_after_manual_action(db_session):
    stock = Stock(code="REV", name="Review Co", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    app = FastAPI()
    app.include_router(admin.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin_access] = lambda: True
    client = TestClient(app)
    created = client.post("/api/admin/entity-proposals", json={
        "stock_id": stock.id,
        "target_level": "asset_unit",
        "proposed_project_name": "Review Project",
        "proposed_asset_name": "Central Zone",
        "proposed_asset_type": "deposit",
        "proposed_commodity": "gold",
        "proposed_ownership_pct": 70,
        "proposed_operator": "Operator X",
        "source_type": "asx_pdf",
        "source_ref": "ASX-REV-001",
        "source_page": 2,
        "source_excerpt": "Central Zone is operated by Operator X.",
    })
    assert created.status_code == 201, created.text
    proposal_id = created.json()["id"]
    assert db_session.query(Project).filter_by(project_key="review-project").count() == 0
    reviewed = client.post(f"/api/admin/entity-proposals/{proposal_id}/review", json={"action": "approve", "reviewer": "human-reviewer"})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "approved"
    project = db_session.query(Project).filter_by(project_key="review-project").one()
    assert db_session.query(AssetUnit).filter_by(project_id=project.id, name="Central Zone").count() == 1


def test_entity_source_search_is_read_only(db_session):
    stock = Stock(code="SRC", name="Source Co", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    app = FastAPI()
    app.include_router(admin.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin_access] = lambda: True
    client = TestClient(app)
    response = client.get("/api/admin/entity-source-search?q=nonexistent")
    assert response.status_code == 200
    assert response.json() == []


def test_online_entity_source_search_is_read_only_and_manual(monkeypatch, db_session):
    class FakeSource:
        def fetch(self, code, count=20):
            assert code == "AGY"
            assert count == 2
            return [
                type("Row", (), {"ann_id": "AGY-001", "headline": "Project Update", "url": "https://example.test/agy-001.pdf"})(),
                type("Row", (), {"ann_id": "AGY-002", "headline": "Quarterly Report", "url": "https://example.test/agy-002.pdf"})(),
            ]

    monkeypatch.setattr(admin, "AsxJsonAnnouncementSource", FakeSource)
    app = FastAPI()
    app.include_router(admin.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin_access] = lambda: True
    client = TestClient(app)

    response = client.get("/api/admin/entity-source-search/online?code=agy&q=project&count=2")
    assert response.status_code == 200, response.text
    assert response.json() == [{
        "source_type": "asx_online",
        "source_id": "AGY-001",
        "title": "Project Update",
        "url": "https://example.test/agy-001.pdf",
        "stock_id": None,
        "project_id": None,
        "source_page": None,
        "excerpt": "Online ASX result; open PDF and manually record page/excerpt before proposing.",
    }]
    assert db_session.query(Project).count() == 0
