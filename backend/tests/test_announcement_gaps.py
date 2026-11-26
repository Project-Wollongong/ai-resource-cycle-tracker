from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.analysis.ai_stub import NoopAnalyzer
from app.datasources.base import RawAnnouncement
from app.models import Announcement, Stock
from app.services import announcements as service


class RecentOnlySource:
    recent_announcement_limit = 5

    def __init__(self, rows):
        self.rows = rows

    def fetch(self, _code, _count):
        return self.rows


def _rows(start_day, count=5):
    start = datetime(2026, 10, start_day, tzinfo=timezone.utc)
    return [RawAnnouncement(f"ann-{index}", "Quarterly activities", start + timedelta(days=index), "https://example.test/a.pdf", False) for index in range(count)]


def _stock(db_session):
    row = Stock(code="GAP", name="Gap Co", commodity="gold")
    db_session.add(row); db_session.commit()
    return row


def _stub_evidence(monkeypatch):
    monkeypatch.setattr(service, "ensure_evidence", lambda *_args, **_kwargs: SimpleNamespace(download_status="skipped", text_status="pending"))


def test_detects_capped_recent_feed_gap(db_session, monkeypatch):
    stock = _stock(db_session)
    db_session.add(Announcement(stock_id=stock.id, ann_id="old", headline="Old", ann_date=datetime(2026, 10, 1)))
    db_session.commit(); _stub_evidence(monkeypatch)

    result = service.sync_announcements(db_session, stock, RecentOnlySource(_rows(28)), NoopAnalyzer(), include_evidence_stats=True, download_evidence=False, extract_evidence=False, parse_p3=False)
    assert result["announcement_gap"] == {"stock_code": "GAP", "database_latest_date": "2026-10-01", "source_oldest_date": "2026-10-28", "gap_days": 27}


def test_first_fetch_does_not_create_gap(db_session, monkeypatch):
    stock = _stock(db_session); _stub_evidence(monkeypatch)
    result = service.sync_announcements(db_session, stock, RecentOnlySource(_rows(28)), NoopAnalyzer(), include_evidence_stats=True, download_evidence=False, extract_evidence=False, parse_p3=False)
    assert result["announcement_gap"] is None


def test_uncapped_result_does_not_create_gap(db_session, monkeypatch):
    stock = _stock(db_session)
    db_session.add(Announcement(stock_id=stock.id, ann_id="old", headline="Old", ann_date=datetime(2026, 10, 1)))
    db_session.commit(); _stub_evidence(monkeypatch)
    result = service.sync_announcements(db_session, stock, RecentOnlySource(_rows(28, 4)), NoopAnalyzer(), include_evidence_stats=True, download_evidence=False, extract_evidence=False, parse_p3=False)
    assert result["announcement_gap"] is None
