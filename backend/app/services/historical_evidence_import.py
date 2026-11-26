"""Import manually obtained historical ASX PDFs into the evidence store."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import BASE_DIR, settings
from ..models import EvidenceDocument, Stock
from .evidence_storage import atomic_write_bytes, evidence_dir, sha256_file, write_metadata
from .evidence_text_extractor import extract_pdf_text


MAX_PDF_BYTES = 50 * 1024 * 1024


def validate_historical_pdf(path: Path) -> Path:
    """Keep command-line and API imports inside the project data directory."""
    source = path.expanduser().resolve()
    if source.suffix.lower() != ".pdf" or not source.is_file():
        raise ValueError("expected an existing PDF file")
    if source.stat().st_size > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds the 50 MB import limit")
    allowed_roots = (BASE_DIR / "data", BASE_DIR / "docs")
    if not any(_is_within(source, root) for root in allowed_roots):
        raise ValueError("PDF must be stored under the project data or docs directory")
    return source


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root.resolve())
        return True
    except ValueError:
        return False


def import_historical_evidence(
    session: Session,
    *,
    stock: Stock,
    local_pdf_path: Path,
    title: str,
    source_date: datetime | None,
    source_url: str = "",
    project_id: int | None = None,
    review_status: str = "pending_review",
) -> tuple[EvidenceDocument, bool]:
    """Store one PDF once, extract deterministic text, and return (row, created).

    The content hash is deliberately global rather than ticker-specific: the
    same PDF copied twice must never create two competing pieces of evidence.
    """
    source = validate_historical_pdf(local_pdf_path)
    digest = sha256_file(source)
    existing = (
        session.query(EvidenceDocument)
        .filter(EvidenceDocument.file_hash_sha256 == digest)
        .order_by(EvidenceDocument.id.asc())
        .first()
    )
    if existing is not None:
        return existing, False

    source_id = f"historical-{digest[:32]}"
    directory = evidence_dir(stock.code, source_id)
    original = directory / "original.pdf"
    atomic_write_bytes(original, source.read_bytes())
    text_path = directory / "raw_text.txt"

    try:
        text, pages = extract_pdf_text(original)
        atomic_write_bytes(text_path, text.encode("utf-8"))
        text_status, evidence_status, error = "extracted", "text_ready", None
    except Exception as exc:
        pages = None
        text_status, evidence_status, error = "failed", "file_saved", str(exc)[:2000]

    evidence = EvidenceDocument(
        stock_id=stock.id,
        project_id=project_id,
        source_type="historical_baseline",
        source_id=source_id,
        title=title,
        document_date=source_date,
        url=source_url,
        source_url=source_url,
        local_original_path=str(original),
        raw_storage_path=str(original),
        local_raw_text_path=str(text_path) if text_status == "extracted" else None,
        raw_text_path=str(text_path) if text_status == "extracted" else None,
        file_hash_sha256=digest,
        content_hash=digest,
        file_size_bytes=original.stat().st_size,
        content_type="application/pdf",
        downloaded_at=datetime.utcnow(),
        text_extracted_at=datetime.utcnow() if text_status == "extracted" else None,
        evidence_status=evidence_status,
        download_status="downloaded",
        text_status=text_status,
        error_message=error,
        historical_baseline=True,
        review_status=review_status,
        imported_at=datetime.utcnow(),
        metadata_json="{}",
    )
    session.add(evidence)
    session.flush()

    metadata = {
        "source_type": "historical_baseline",
        "announcement_id": None,
        "ticker": stock.code,
        "title": title,
        "source_url": source_url,
        "source_date": source_date,
        "local_original_path": str(original.relative_to(Path(settings.evidence_root))),
        "local_raw_text_path": str(text_path.relative_to(Path(settings.evidence_root))) if text_status == "extracted" else None,
        "sha256": digest,
        "page_count": pages,
        "historical_baseline": True,
        "review_status": review_status,
    }
    evidence.metadata_json = json.dumps(metadata, ensure_ascii=False, default=str)
    write_metadata(directory, metadata)
    return evidence, True
