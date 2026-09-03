from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import historical_analysis

from test_historical_scoring import add_price_bars, add_stock


def _client(db_session) -> TestClient:
    app = FastAPI()
    app.include_router(historical_analysis.router, prefix="/api")

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_run_historical_analysis_api_creates_snapshot(db_session):
    stock = add_stock(db_session, code="API")
    dates = add_price_bars(db_session, stock, [1.0] * 21, [100_000] * 21)

    response = _client(db_session).post(
        "/api/historical-analysis/run",
        json={"code": "api", "as_of_date": dates[-1].isoformat()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "API"
    assert body["as_of_date"] == dates[-1].isoformat()
    assert body["status"] == "success"
    assert body["input_hash"]
    assert body["input_summary"]["last_price_date"] == dates[-1].isoformat()
    assert body["components"]["weights"]
    assert [row["horizon_days"] for row in body["returns"]] == [5, 20, 60, 120]


def test_list_and_get_historical_analysis_snapshots_api(db_session):
    stock = add_stock(db_session, code="APL")
    dates = add_price_bars(db_session, stock, [1.0] * 21, [100_000] * 21)
    client = _client(db_session)
    created = client.post(
        "/api/historical-analysis/run",
        json={"code": "APL", "as_of_date": dates[-1].isoformat()},
    ).json()

    list_response = client.get("/api/historical-analysis?code=APL")
    detail_response = client.get(f"/api/historical-analysis/{created['id']}")

    assert list_response.status_code == 200
    assert [row["id"] for row in list_response.json()] == [created["id"]]
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == created["id"]
    assert [row["horizon_days"] for row in detail_response.json()["returns"]] == [5, 20, 60, 120]


def test_refresh_historical_analysis_returns_api(db_session):
    stock = add_stock(db_session, code="APR")
    dates = add_price_bars(db_session, stock, [1.0, 1.1, 1.2], [100_000] * 3)
    client = _client(db_session)
    created = client.post(
        "/api/historical-analysis/run",
        json={"code": "APR", "as_of_date": dates[0].isoformat()},
    ).json()

    response = client.post(f"/api/historical-analysis/{created['id']}/returns")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["returns"][0]["status"] == "unavailable"


def test_run_historical_analysis_api_returns_404_for_unknown_code(db_session):
    response = _client(db_session).post(
        "/api/historical-analysis/run",
        json={"code": "missing", "as_of_date": date(2026, 7, 4).isoformat()},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "stock MISSING not found"


def test_run_historical_analysis_api_returns_422_for_incomplete_input(db_session):
    add_stock(db_session, code="NOP")

    response = _client(db_session).post(
        "/api/historical-analysis/run",
        json={"code": "NOP", "as_of_date": date(2026, 7, 4).isoformat()},
    )

    assert response.status_code == 422
    assert "no_price_bars" in response.json()["detail"]
