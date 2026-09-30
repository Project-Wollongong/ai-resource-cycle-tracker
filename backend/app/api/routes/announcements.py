from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session

from ...models import Announcement, AnnouncementVersionRelation, EvidenceDocument, Stock
from ...schemas import AnnouncementOut, AnnouncementVersionRelationOut, EvidenceDocumentOut
from ..deps import get_db
from ..serializers import announcement_out
from ...services.stock_identity import find_current_or_historical, IdentityConflict
from ...services.evidence_service import ensure_evidence

router = APIRouter(prefix="/announcements", tags=["announcements"])


@router.get("/evidence", response_model=list[EvidenceDocumentOut])
def list_evidence(historical_baseline: bool | None = None, code: str | None = None, db: Session = Depends(get_db)):
    query = db.query(EvidenceDocument)
    if historical_baseline is not None: query = query.filter(EvidenceDocument.historical_baseline == historical_baseline)
    if code: query = query.join(Stock, EvidenceDocument.stock_id == Stock.id).filter(Stock.code == code.upper())
    return query.order_by(EvidenceDocument.id.desc()).limit(500).all()


@router.get("", response_model=list[AnnouncementOut])
def list_announcements(
    on_date: date | None = None,
    ann_type: str | None = None,
    code: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(Announcement, Stock).join(Stock, Announcement.stock_id == Stock.id)
    if on_date:
        q = q.filter(
            Announcement.ann_date >= datetime.combine(on_date, datetime.min.time()),
            Announcement.ann_date
            < datetime.combine(on_date + timedelta(days=1), datetime.min.time()),
        )
    if ann_type:
        q = q.filter(Announcement.ann_type == ann_type)
    if code:
        try:
            stock = find_current_or_historical(db, code)
        except IdentityConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if stock is None:
            return []
        q = q.filter(Announcement.stock_id == stock.id)
    rows = q.order_by(Announcement.ann_date.desc()).limit(min(limit, 500)).all()
    return [announcement_out(ann, stock.code) for ann, stock in rows]


@router.get("/{announcement_id}/evidence", response_model=EvidenceDocumentOut)
def announcement_evidence(announcement_id: str, db: Session = Depends(get_db)):
    evidence = db.query(EvidenceDocument).filter_by(source_type="asx_pdf", source_id=announcement_id).one_or_none()
    if evidence is None:
        raise HTTPException(status_code=404, detail="evidence document not found")
    return evidence


@router.get("/{announcement_id}/version-relations", response_model=list[AnnouncementVersionRelationOut])
def announcement_version_relations(announcement_id: str, db: Session = Depends(get_db)):
    announcement = db.query(Announcement).filter_by(ann_id=announcement_id).first()
    if announcement is None: raise HTTPException(status_code=404, detail="announcement not found")
    return db.query(AnnouncementVersionRelation).filter((AnnouncementVersionRelation.predecessor_announcement_id == announcement.id) | (AnnouncementVersionRelation.successor_announcement_id == announcement.id)).order_by(AnnouncementVersionRelation.id).all()


@router.get("/evidence/{evidence_id}/original")
def evidence_original(evidence_id: int, db: Session = Depends(get_db)):
    evidence = db.get(EvidenceDocument, evidence_id)
    if evidence is None or not evidence.local_original_path:
        raise HTTPException(status_code=404, detail="local original PDF is not available")
    path = __import__("pathlib").Path(evidence.local_original_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="local original PDF is missing")
    return FileResponse(path, media_type="application/pdf", filename="original.pdf")


@router.get("/evidence/{evidence_id}/raw-text")
def evidence_raw_text(evidence_id: int, db: Session = Depends(get_db)):
    evidence = db.get(EvidenceDocument, evidence_id)
    if evidence is None or not evidence.local_raw_text_path:
        raise HTTPException(status_code=404, detail="raw text is not available")
    path = __import__("pathlib").Path(evidence.local_raw_text_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="raw text is missing")
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@router.post("/{announcement_id}/evidence/fetch", response_model=EvidenceDocumentOut)
def fetch_announcement_evidence(announcement_id: str, db: Session = Depends(get_db)):
    row = db.query(Announcement, Stock).join(Stock, Announcement.stock_id == Stock.id).filter(Announcement.ann_id == announcement_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="announcement not found")
    evidence = ensure_evidence(db, row[0], row[1], force_download=True)
    db.commit()
    return evidence


@router.post("/evidence/{evidence_id}/retry", response_model=EvidenceDocumentOut)
def retry_evidence(evidence_id: int, db: Session = Depends(get_db)):
    evidence = db.get(EvidenceDocument, evidence_id)
    if evidence is None or evidence.announcement_id is None:
        raise HTTPException(status_code=404, detail="evidence document not found")
    row = db.query(Announcement, Stock).join(Stock, Announcement.stock_id == Stock.id).filter(Announcement.id == evidence.announcement_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="announcement not found")
    extract_only = evidence.download_status == "downloaded" and evidence.text_status == "failed"
    result = ensure_evidence(db, row[0], row[1], force_download=not extract_only, extract_only=extract_only)
    db.commit()
    return result
