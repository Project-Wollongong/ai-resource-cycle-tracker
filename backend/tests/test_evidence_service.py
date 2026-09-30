import json
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import announcements
from app.config import settings
from app.models import Announcement, EvidenceDocument, Stock
from app.services import evidence_service
from app.services.evidence_downloader import DownloadedFile


FIXTURE = Path(__file__).parents[2] / "docs" / "beta02-acceptance" / "pdfs" / "S01.pdf"


def test_evidence_saved_idempotently_and_extracts_text(monkeypatch, db_session, tmp_path):
    monkeypatch.setattr(settings, "evidence_root", str(tmp_path))
    stock = Stock(code="CVV", name="CVC Limited", commodity="gold")
    db_session.add(stock)
    db_session.flush()
    ann = Announcement(stock_id=stock.id, ann_id="2924-test", headline="Test PDF", ann_date=datetime(2026, 9, 1), url="https://example.test/test.pdf")
    db_session.add(ann)
    db_session.flush()
    payload = FIXTURE.read_bytes()
    calls = []
    monkeypatch.setattr(evidence_service, "download_file", lambda url: (calls.append(url) or DownloadedFile(payload, "application/pdf")))

    first = evidence_service.ensure_evidence(db_session, ann, stock)
    db_session.commit()
    second = evidence_service.ensure_evidence(db_session, ann, stock)
    db_session.commit()

    assert first.id == second.id
    assert len(calls) == 1
    assert first.download_status == "downloaded"
    assert first.text_status == "extracted"
    assert first.file_hash_sha256
    assert first.page_count and first.page_count > 0
    assert Path(first.local_original_path).is_file()
    assert Path(first.local_raw_text_path).read_text(encoding="utf-8")
    metadata = json.loads((Path(first.local_original_path).parent / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["announcement_id"] == "2924-test"
    assert ann.evidence_document_id == first.id


def test_download_failure_keeps_announcement_and_can_retry(monkeypatch, db_session, tmp_path):
    monkeypatch.setattr(settings, "evidence_root", str(tmp_path))
    stock = Stock(code="FAIL", name="Failure Co", commodity="gold")
    db_session.add(stock)
    db_session.flush()
    ann = Announcement(stock_id=stock.id, ann_id="fail-1", headline="Unavailable", ann_date=datetime(2026, 9, 1), url="https://example.test/fail.pdf")
    db_session.add(ann)
    db_session.flush()
    monkeypatch.setattr(evidence_service, "download_file", lambda url: (_ for _ in ()).throw(ValueError("upstream HTML error")))
    evidence = evidence_service.ensure_evidence(db_session, ann, stock)
    db_session.commit()
    assert db_session.get(Announcement, ann.id) is not None
    assert evidence.download_status == "failed"
    assert evidence.evidence_status == "failed"
    assert "HTML" in evidence.error_message
    assert not list(tmp_path.rglob("original.pdf"))


def test_local_evidence_endpoints_do_not_expose_arbitrary_paths(monkeypatch, db_session, tmp_path):
    monkeypatch.setattr(settings, "evidence_root", str(tmp_path))
    evidence = EvidenceDocument(source_type="asx_pdf", source_id="safe-1", title="Safe", local_original_path=str(tmp_path / "missing.pdf"), local_raw_text_path=str(tmp_path / "missing.txt"), download_status="downloaded", evidence_status="file_saved")
    db_session.add(evidence)
    db_session.commit()
    app = FastAPI()
    app.include_router(announcements.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    assert client.get(f"/api/announcements/evidence/{evidence.id}/original").status_code == 404
    assert client.get(f"/api/announcements/evidence/{evidence.id}/raw-text").status_code == 404
