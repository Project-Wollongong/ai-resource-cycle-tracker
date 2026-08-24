import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from ...models import Announcement, PriceBar, ScoreSnapshot, Signal, Stock
from ...schemas import (
    AnnouncementOut,
    Message,
    PriceBarOut,
    ScoreBrief,
    SignalOut,
    StockCreate,
    StockUpdate,
    StockWithScore,
)
from ...services.watchlist import build_stock_view
from ..deps import get_db
from ..serializers import announcement_out, signal_out

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _get_stock_or_404(db: Session, code: str) -> Stock:
    stock = db.query(Stock).filter_by(code=code.upper()).one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"stock {code.upper()} not found")
    return stock


@router.get("", response_model=list[StockWithScore])
def list_stocks(active: bool | None = True, db: Session = Depends(get_db)):
    q = db.query(Stock)
    if active is not None:
        q = q.filter_by(active=active)
    stocks = q.order_by(Stock.code).all()
    views = [build_stock_view(db, s) for s in stocks]
    views.sort(key=lambda v: v.latest_score.cycle_score if v.latest_score else -1, reverse=True)
    return views


@router.post("", response_model=StockWithScore, status_code=201)
def create_stock(payload: StockCreate, db: Session = Depends(get_db)):
    code = payload.code.strip().upper()
    existing = db.query(Stock).filter_by(code=code).one_or_none()
    if existing is not None:
        if not existing.active:  # re-activate a soft-deleted stock
            existing.active = True
            existing.name = payload.name
            existing.commodity = payload.commodity
            existing.stage = payload.stage
            db.commit()
            return build_stock_view(db, existing)
        raise HTTPException(status_code=409, detail=f"stock {code} already exists")
    stock = Stock(
        code=code,
        name=payload.name.strip(),
        commodity=payload.commodity.strip(),
        stage=payload.stage.strip(),
        notes=payload.notes.strip(),
    )
    db.add(stock)
    db.commit()
    return build_stock_view(db, stock)


@router.get("/{code}", response_model=StockWithScore)
def get_stock(code: str, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    return build_stock_view(db, stock, include_components=True)


@router.put("/{code}", response_model=StockWithScore)
def update_stock(code: str, payload: StockUpdate, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    for field in ("name", "commodity", "stage", "notes", "active"):
        value = getattr(payload, field)
        if value is not None:
            setattr(stock, field, value)
    if payload.resource_score_override is not None:
        stock.resource_score_override = payload.resource_score_override
    if payload.risk_score_override is not None:
        stock.risk_score_override = payload.risk_score_override
    if payload.clear_resource_override:
        stock.resource_score_override = None
    if payload.clear_risk_override:
        stock.risk_score_override = None
    db.commit()
    return build_stock_view(db, stock, include_components=True)


@router.delete("/{code}", response_model=Message)
def deactivate_stock(code: str, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    stock.active = False
    db.commit()
    return Message(detail=f"stock {stock.code} deactivated")


@router.get("/{code}/prices", response_model=list[PriceBarOut])
def stock_prices(code: str, days: int = 250, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    rows = (
        db.query(PriceBar)
        .filter_by(stock_id=stock.id)
        .order_by(PriceBar.date.desc())
        .limit(min(days, 600))
        .all()
    )
    return [PriceBarOut.model_validate(r) for r in reversed(rows)]


@router.get("/{code}/scores", response_model=list[ScoreBrief])
def stock_scores(code: str, days: int = 90, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    rows = (
        db.query(ScoreSnapshot)
        .filter_by(stock_id=stock.id)
        .order_by(ScoreSnapshot.date.desc())
        .limit(min(days, 400))
        .all()
    )
    return [
        ScoreBrief(
            date=r.date,
            funding_score=r.funding_score,
            announcement_score=r.announcement_score,
            resource_score=r.resource_score,
            commodity_score=r.commodity_score,
            risk_score=r.risk_score,
            sentiment_score=r.sentiment_score,
            cycle_score=r.cycle_score,
            label=r.label,
            components=json.loads(r.components or "{}"),
        )
        for r in reversed(rows)
    ]


@router.get("/{code}/announcements", response_model=list[AnnouncementOut])
def stock_announcements(code: str, limit: int = 50, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    rows = (
        db.query(Announcement)
        .filter_by(stock_id=stock.id)
        .order_by(Announcement.ann_date.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [announcement_out(a, stock.code) for a in rows]


@router.get("/{code}/signals", response_model=list[SignalOut])
def stock_signals(code: str, limit: int = 100, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    rows = (
        db.query(Signal)
        .filter_by(stock_id=stock.id)
        .options(joinedload(Signal.returns))
        .order_by(Signal.date.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [signal_out(s, stock) for s in rows]
