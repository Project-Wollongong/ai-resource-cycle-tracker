import json
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import announcements, stocks
from app.models import Announcement, Stock


def _client(db_session) -> TestClient:
    app = FastAPI()
    app.include_router(announcements.router, prefix="/api")
    app.include_router(stocks.router, prefix="/api")

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _seed_announcement(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    db_session.add(
        Announcement(
            stock_id=stock.id,
            ann_id="ann-1",
            headline="High-Grade Drill Results",
            ann_date=datetime(2026, 7, 22, 10, 30),
            url="https://example.com/ann.pdf",
            price_sensitive=True,
            ann_type="DRILL_RESULTS",
            type_score=85,
            matched_keywords=json.dumps(["drill results"]),
            raw_payload="{}",
            ai_summary="Reports 10m at 4.5g/t gold from 70m.",
            ai_metrics=json.dumps(
                {
                    "intercepts": [
                        {
                            "width_m": 10,
                            "grade": 4.5,
                            "unit": "g/t",
                            "commodity": "gold",
                            "depth_m": 70,
                        }
                    ],
                    "project": "Bankan",
                    "qualitative_context": {
                        "grade_thickness": 45,
                        "depth_category": "shallow",
                        "interval_quality_label": "strong",
                        "company_percentile": 80,
                        "project_percentile": 80,
                        "trend_vs_previous": "improving",
                        "materiality_label": "high",
                        "company_history_count": 5,
                        "project_history_count": 5,
                        "reason": "grade-thickness is 45",
                        "qualitative_assessment": (
                            "Within the stored project history, this interval ranks as strong, "
                            "with grade-thickness in the 80th percentile, shallow depth, and high materiality."
                        ),
                    },
                }
            ),
        )
    )
    db_session.commit()


def test_announcements_api_returns_ai_metrics_with_qualitative_context(db_session):
    _seed_announcement(db_session)

    response = _client(db_session).get("/api/announcements?code=TST")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    context = body[0]["ai_metrics"]["qualitative_context"]
    assert context["grade_thickness"] == 45
    assert context["depth_category"] == "shallow"
    assert context["trend_vs_previous"] == "improving"
    assert context["materiality_label"] == "high"
    assert context["company_percentile"] == 80


def test_stock_announcements_api_returns_ai_metrics_with_qualitative_context(db_session):
    _seed_announcement(db_session)

    response = _client(db_session).get("/api/stocks/TST/announcements")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["code"] == "TST"
    assert body[0]["ai_metrics"]["qualitative_context"]["project_percentile"] == 80
