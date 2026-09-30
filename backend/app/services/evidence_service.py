"""Lifecycle service for Announcement -> EvidenceDocument raw files and text."""
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Announcement, EvidenceDocument, Stock
from .evidence_downloader import download_file
from .evidence_storage import atomic_write_bytes, evidence_dir, sha256_file, write_metadata
from .evidence_text_extractor import extract_pdf_text


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _metadata(announcement: Announcement, stock: Stock, evidence: EvidenceDocument) -> dict:
    root = Path(settings.evidence_root)
    def relative(path):
        return str(Path(path).relative_to(root)) if path else None
    return {
        "announcement_id": announcement.ann_id,
        "ticker": stock.code,
        "title": announcement.headline,
        "asx_published_at": announcement.ann_date,
        "source_url": announcement.url,
        "local_original_path": relative(evidence.local_original_path or evidence.raw_storage_path),
        "local_raw_text_path": relative(evidence.local_raw_text_path or evidence.raw_text_path),
        "sha256": evidence.file_hash_sha256 or evidence.content_hash,
        "file_size_bytes": evidence.file_size_bytes,
        "content_type": evidence.content_type,
        "page_count": evidence.page_count,
        "fetched_at": evidence.downloaded_at,
        "text_extracted_at": evidence.text_extracted_at,
        "download_status": evidence.download_status,
        "text_status": evidence.text_status,
        "evidence_status": evidence.evidence_status,
        "error_message": evidence.error_message,
        "retry_count": evidence.retry_count,
        "tool": "evidence_service_v1",
    }


def ensure_evidence(session: Session, announcement: Announcement, stock: Stock, *, force_download: bool = False, extract_only: bool = False, download_enabled: bool = True, extract_enabled: bool = True) -> EvidenceDocument:
    evidence = session.query(EvidenceDocument).filter_by(source_type="asx_pdf", source_id=announcement.ann_id).one_or_none()
    if evidence is None:
        evidence = EvidenceDocument(stock_id=stock.id, announcement_id=announcement.id, source_type="asx_pdf", source_id=announcement.ann_id, title=announcement.headline, document_date=announcement.ann_date, url=announcement.url, source_url=announcement.url)
        session.add(evidence)
        session.flush()
    else:
        evidence.stock_id = evidence.stock_id or stock.id
        evidence.announcement_id = evidence.announcement_id or announcement.id
        evidence.title = announcement.headline
        evidence.url = announcement.url
        evidence.source_url = announcement.url

    is_retry = bool(force_download or extract_only) and evidence.id is not None
    if is_retry:
        evidence.retry_count = (evidence.retry_count or 0) + 1
        evidence.last_retry_at = _now()

    directory = evidence_dir(stock.code, announcement.ann_id)
    original = directory / "original.pdf"
    text_path = directory / "raw_text.txt"
    try:
        if download_enabled and not extract_only and not (original.exists() and evidence.file_hash_sha256 and not force_download):
            evidence.download_status = "downloading"
            downloaded = download_file(announcement.url)
            temp = directory / ".incoming.pdf"
            atomic_write_bytes(temp, downloaded.content)
            digest = sha256_file(temp)
            canonical = session.query(EvidenceDocument).filter(EvidenceDocument.file_hash_sha256 == digest, EvidenceDocument.id != evidence.id).first()
            if canonical:
                evidence.duplicate_of_id = canonical.id
            atomic_write_bytes(original, temp.read_bytes())
            temp.unlink(missing_ok=True)
            evidence.file_hash_sha256 = digest
            evidence.content_hash = digest
            evidence.file_size_bytes = original.stat().st_size
            evidence.content_type = downloaded.content_type
            evidence.local_original_path = str(original)
            evidence.raw_storage_path = str(original)
            evidence.downloaded_at = _now()
            evidence.download_status = "downloaded"
            evidence.evidence_status = "file_saved"
        elif original.exists() and evidence.file_hash_sha256:
            evidence.download_status = "downloaded"
            evidence.evidence_status = "file_saved"
        if extract_enabled and original.exists() and evidence.download_status == "downloaded" and (not text_path.exists() or evidence.text_status != "extracted"):
            evidence.text_status = "extracting"
            text, pages = extract_pdf_text(original)
            atomic_write_bytes(text_path, text.encode("utf-8"))
            evidence.page_count = pages
            evidence.local_raw_text_path = str(text_path)
            evidence.raw_text_path = str(text_path)
            evidence.text_extracted_at = _now()
            evidence.text_status = "extracted"
            evidence.evidence_status = "text_ready"
        evidence.error_message = None
    except Exception as exc:
        evidence.error_message = str(exc)[:2000]
        if evidence.download_status in {"downloading", "pending"}:
            evidence.download_status = "failed"
        elif evidence.text_status == "extracting":
            evidence.text_status = "failed"
        evidence.evidence_status = "file_saved" if evidence.download_status == "downloaded" else "failed"
        if not is_retry:
            evidence.retry_count = (evidence.retry_count or 0) + 1
            evidence.last_retry_at = _now()
    finally:
        evidence.metadata_json = json.dumps(_metadata(announcement, stock, evidence), ensure_ascii=False, default=str)
        announcement.evidence_document_id = evidence.id
        session.flush()
        write_metadata(directory, _metadata(announcement, stock, evidence))
    return evidence
