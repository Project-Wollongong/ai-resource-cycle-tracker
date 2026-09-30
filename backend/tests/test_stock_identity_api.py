from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import stocks
from app.models import Stock
from app.services import stock_identity as identity


def test_stock_identity_api_preserves_existing_stock_lookup(db_session):
    stock = Stock(code="CVV", name="Company Vision", commodity="GOLD", active=True)
    db_session.add(stock)
    db_session.flush()
    identity.ensure_current_identities(db_session, stock, source="test")

    app = FastAPI()
    app.include_router(stocks.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    response = client.post(
        "/api/stocks/CVV/identities",
        json={
            "kind": "ticker",
            "value": "OLD",
            "valid_from": "2018-01-01",
            "valid_to": "2022-01-01",
            "source": "test",
        },
    )
    assert response.status_code == 201, response.text
    assert client.get("/api/stocks/CVV").status_code == 200
    resolved = client.get(
        "/api/stocks/resolve",
        params={"identifier": "OLD", "as_of": "2020-01-01", "kind": "ticker"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["code"] == "CVV"

    history = client.get("/api/stocks/CVV/identities")
    assert history.status_code == 200
    assert any(row["value"] == "OLD" and not row["is_current"] for row in history.json())


def test_stock_identity_api_changes_current_identity_without_duplicate_stock(db_session):
    stock = Stock(code="CVV", name="Company Vision", commodity="GOLD", active=True)
    db_session.add(stock)
    db_session.flush()
    identity.ensure_current_identities(db_session, stock, source="test")

    app = FastAPI()
    app.include_router(stocks.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    response = client.put(
        "/api/stocks/CVV",
        json={"code": "NEW", "name": "New Company", "identity_effective_from": "2024-01-01"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["code"] == "NEW"
    assert client.get("/api/stocks/CVV").status_code == 200
    assert client.post("/api/stocks", json={"code": "CVV", "name": "Another", "commodity": "GOLD"}).status_code == 409
