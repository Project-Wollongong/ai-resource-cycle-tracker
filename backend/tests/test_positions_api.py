from datetime import date, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import positions
from app.config import settings
from app.models import PriceBar, Stock


def _client(db_session) -> TestClient:
    app = FastAPI()
    app.include_router(positions.router, prefix="/api")

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_positions_api_open_refresh_close_flow(db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "secret")
    stock = Stock(code="POS", name="Position Test", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    db_session.add(
        PriceBar(
            stock_id=stock.id,
            date=date(2026, 9, 10),
            open=0.10,
            high=0.12,
            low=0.09,
            close=0.11,
            volume=1_000_000,
        )
    )
    db_session.commit()

    client = _client(db_session)
    assert client.post(
        "/api/positions",
        json={
            "code": "POS",
            "entry_price": 0.10,
            "quantity": 10_000,
            "opened_at": datetime(2026, 9, 10, 10, 0).isoformat(),
        },
    ).status_code == 401

    created = client.post(
        "/api/positions",
        headers={"X-Admin-Token": "secret"},
        json={
            "code": "POS",
            "entry_price": 0.10,
            "quantity": 10_000,
            "opened_at": datetime(2026, 9, 10, 10, 0).isoformat(),
            "original_thesis": {"core": "manual test"},
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["code"] == "POS"
    assert body["status"] == "open"
    assert body["market_value"] == 1000.0
    assert body["events"][0]["event_type"] == "initial_buy"
    position_id = body["id"]

    listed = client.get("/api/positions").json()
    assert [item["id"] for item in listed] == [position_id]
    assert listed[0]["events"] == []

    refreshed = client.post(f"/api/positions/{position_id}/refresh", headers={"X-Admin-Token": "secret"})
    assert refreshed.status_code == 200
    assert refreshed.json()["current_price"] == 0.11

    closed = client.post(
        f"/api/positions/{position_id}/close",
        headers={"X-Admin-Token": "secret"},
        json={"exit_price": 0.13, "reason": "manual close"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["events"][0]["event_type"] == "exit"

    assert client.get("/api/positions").json() == []
    assert client.get("/api/positions?status=closed").json()[0]["id"] == position_id
