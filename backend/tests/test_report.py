import json
from datetime import date, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import reports
from app.models import Announcement, DailyReport, PriceBar, ScoreSnapshot, Signal, Stock
from app.notify.base import PushResult
from app.services import report as report_service
from app.services.report import build_daily_report, push_daily_report, render_telegram_html


REPORT_DATE = date(2026, 7, 30)


def _client(db_session) -> TestClient:
    app = FastAPI()
    app.include_router(reports.router, prefix="/api")

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _seed_report_inputs(db_session) -> Stock:
    stock = Stock(code="TST", name="Test Gold", commodity="gold", active=True)
    db_session.add(stock)
    db_session.commit()

    db_session.add_all(
        [
            PriceBar(
                stock_id=stock.id,
                date=date(2026, 7, 29),
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=100_000,
            ),
            PriceBar(
                stock_id=stock.id,
                date=REPORT_DATE,
                open=1.1,
                high=1.1,
                low=1.1,
                close=1.1,
                volume=200_000,
            ),
            ScoreSnapshot(
                stock_id=stock.id,
                date=date(2026, 7, 29),
                funding_score=20,
                announcement_score=10,
                resource_score=50,
                commodity_score=55,
                risk_score=50,
                cycle_score=48.5,
                label="Ignore",
                components="{}",
            ),
            ScoreSnapshot(
                stock_id=stock.id,
                date=REPORT_DATE,
                funding_score=80,
                announcement_score=70,
                resource_score=50,
                commodity_score=55,
                risk_score=50,
                sentiment_score=50,
                cycle_score=68.5,
                label="Watch Closely",
                components=json.dumps(
                    {
                        "funding": {
                            "rel_vol": {
                                "value": 2.5,
                                "dollar_turnover": 220_000,
                            }
                        },
                        "announcement": {
                            "announcements": [
                                {
                                    "headline": "High-grade drill results",
                                    "type": "DRILL_RESULTS",
                                }
                            ]
                        },
                        "risk": {"events": []},
                    }
                ),
            ),
            Signal(
                stock_id=stock.id,
                date=REPORT_DATE,
                signal_type="REL_VOL_SPIKE",
                source="live",
                label="Watch Closely",
                reason="Volume spike",
                evidence="{}",
                price_at_signal=1.1,
                cycle_score_at_signal=68.5,
            ),
            Announcement(
                stock_id=stock.id,
                ann_id="ann-1",
                headline="High-grade drill results",
                ann_date=datetime(2026, 7, 30, 9, 0),
                url="https://example.test/ann-1",
                price_sensitive=True,
                ann_type="DRILL_RESULTS",
                type_score=85,
                matched_keywords="[]",
                raw_payload="{}",
                ai_metrics=json.dumps(
                    {
                        "qualitative_context": {
                            "interval_quality_label": "strong",
                            "materiality_label": "high",
                            "grade_thickness": 45.0,
                            "qualitative_assessment": "Strong relative to stored project history.",
                        }
                    }
                ),
            ),
        ]
    )
    db_session.commit()
    return stock


def test_build_daily_report_persists_expected_sections(db_session):
    _seed_report_inputs(db_session)

    report = build_daily_report(db_session, {"blocked_sources": ["BLK"]})
    content = json.loads(report.content_json)

    assert report.report_date == REPORT_DATE
    assert content["report_date"] == "2026-07-30"
    assert content["top"] == [
        {
            "code": "TST",
            "name": "Test Gold",
            "commodity": "gold",
            "cycle_score": 68.5,
            "label": "Watch Closely",
            "day_change_pct": 10.0,
        }
    ]
    assert content["signals"][0]["type"] == "REL_VOL_SPIKE"
    assert content["announcements"][0]["headline"] == "High-grade drill results"
    assert content["announcements"][0]["price_sensitive"] is True
    assert content["announcements"][0]["quality"] == "strong"
    assert content["announcements"][0]["materiality"] == "high"
    assert content["announcements"][0]["grade_thickness"] == 45.0
    assert content["announcements"][0]["assessment"] == "Strong relative to stored project history."
    assert content["source_degraded"] == ["BLK"]
    assert content["daily_review"]["new_story"][0]["code"] == "TST"
    assert content["daily_review"]["new_story"][0]["announcement_type"] == "DRILL_RESULTS"
    assert content["daily_review"]["market_confirmation"][0]["code"] == "TST"
    assert content["daily_review"]["rising_fast"][0]["score_change"] == 20.0
    assert "Research only" in content["disclaimer"]
    assert report.content_text == render_telegram_html(content)
    assert "Daily Review" in report.content_text
    assert "quality=strong" in report.content_text
    assert "materiality=high" in report.content_text
    assert "Strong relative to stored project history." in report.content_text


def test_render_telegram_html_handles_empty_sections():
    content = {
        "report_date": "2026-07-30",
        "top": [],
        "signals": [],
        "announcements": [],
        "movers": [],
        "source_degraded": [],
        "disclaimer": "Research only.",
    }

    rendered = render_telegram_html(content)

    assert "AI Resource Cycle Tracker - 2026-07-30" in rendered
    assert "(no scores yet)" in rendered
    assert "(none today)" in rendered
    assert "<i>Research only.</i>" in rendered


def test_reports_api_lists_latest_and_date_lookup(db_session):
    _seed_report_inputs(db_session)
    build_daily_report(db_session)
    client = _client(db_session)

    list_response = client.get("/api/reports?limit=30")
    latest_response = client.get("/api/reports/latest")
    date_response = client.get("/api/reports/2026-07-30")

    assert list_response.status_code == 200
    assert latest_response.status_code == 200
    assert date_response.status_code == 200
    assert list_response.json()[0]["report_date"] == "2026-07-30"
    assert latest_response.json()["content"]["top"][0]["code"] == "TST"
    assert date_response.json()["content"]["signals"][0]["reason"] == "Volume spike"


def test_reports_api_returns_404_when_missing(db_session):
    client = _client(db_session)

    latest_response = client.get("/api/reports/latest")
    date_response = client.get("/api/reports/2026-07-30")

    assert latest_response.status_code == 404
    assert date_response.status_code == 404


def test_push_daily_report_records_sent_skipped_and_errors(db_session, monkeypatch):
    daily_report = DailyReport(
        report_date=REPORT_DATE,
        content_json="{}",
        content_text="daily report",
    )
    db_session.add(daily_report)
    db_session.commit()

    class SentNotifier:
        def send(self, text: str) -> PushResult:
            assert text == "daily report"
            return PushResult(sent=True)

    class FailedNotifier:
        def send(self, text: str) -> PushResult:
            assert text == "daily report"
            return PushResult(sent=False, error="smtp failed")

    monkeypatch.setattr(report_service, "TelegramNotifier", SentNotifier)
    monkeypatch.setattr(report_service, "EmailNotifier", FailedNotifier)

    result = push_daily_report(db_session, daily_report)

    assert result == {
        "sent": True,
        "sent_channels": ["telegram"],
        "skipped_channels": [],
        "errors": {"email": "smtp failed"},
    }
    assert daily_report.pushed is True
    assert daily_report.pushed_at is not None
    assert json.loads(daily_report.push_error) == {"email": "smtp failed"}


def test_push_daily_report_marks_unconfigured_channels_as_skipped(db_session, monkeypatch):
    daily_report = DailyReport(
        report_date=REPORT_DATE,
        content_json="{}",
        content_text="daily report",
    )
    db_session.add(daily_report)
    db_session.commit()

    class SkippedNotifier:
        def send(self, text: str) -> PushResult:
            return PushResult(sent=False, skipped=True)

    monkeypatch.setattr(report_service, "TelegramNotifier", SkippedNotifier)
    monkeypatch.setattr(report_service, "EmailNotifier", SkippedNotifier)

    result = push_daily_report(db_session, daily_report)

    assert result == {
        "sent": False,
        "sent_channels": [],
        "skipped_channels": ["telegram", "email"],
        "errors": {},
    }
    assert daily_report.pushed is False
    assert daily_report.pushed_at is None
    assert daily_report.push_error is None
