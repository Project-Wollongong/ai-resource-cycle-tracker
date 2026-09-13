from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import trade_reviews
from app.config import settings
from app.models import Stock
from app.services.position_management import close_position, open_position_from_execution


def _client(db_session) -> TestClient:
    app = FastAPI()
    app.include_router(trade_reviews.router, prefix="/api")

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_trade_reviews_api_create_list_and_candidates(db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "secret")
    stock = Stock(code="TRA", name="Trade Review API", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    position = open_position_from_execution(
        db_session,
        stock,
        entry_price=0.10,
        quantity=10_000,
        opened_at=datetime(2026, 9, 10, 10, 0),
    )
    close_position(
        db_session,
        position,
        stock,
        exit_price=0.13,
        closed_at=datetime(2026, 10, 10, 10, 0),
        reason="Manual close.",
    )

    client = _client(db_session)
    assert client.post(f"/api/trade-reviews/positions/{position.id}").status_code == 401

    created = client.post(
        f"/api/trade-reviews/positions/{position.id}",
        headers={"X-Admin-Token": "secret"},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["code"] == "TRA"
    assert body["return_pct"] == 30.0
    assert body["metadata"]["auto_rule_change"] is False
    assert body["learning_candidates"][0]["status"] == "proposed"
    assert body["learning_candidates"][0]["applied_at"] is None

    listed = client.get("/api/trade-reviews").json()
    assert [item["id"] for item in listed] == [body["id"]]

    candidates = client.get("/api/trade-reviews/candidates/list").json()
    assert len(candidates) == 1
    assert candidates[0]["requires_human_approval"] is True


def test_trade_reviews_api_rejects_open_position(db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "secret")
    stock = Stock(code="TRO", name="Trade Review Open", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    position = open_position_from_execution(
        db_session,
        stock,
        entry_price=0.10,
        quantity=10_000,
        opened_at=datetime(2026, 9, 10, 10, 0),
    )

    response = _client(db_session).post(
        f"/api/trade-reviews/positions/{position.id}",
        headers={"X-Admin-Token": "secret"},
    )

    assert response.status_code == 422
    assert "closed position" in response.json()["detail"]
