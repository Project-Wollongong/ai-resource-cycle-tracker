import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...models import HistoricalAnalysisReturn, HistoricalAnalysisSnapshot, Stock
from ...schemas import HistoricalAnalysisRunIn, HistoricalAnalysisSnapshotOut
from ...services.historical_analysis import run_historical_analysis_for_code
from ...services.historical_returns import evaluate_historical_snapshot_returns
from ..deps import get_db

router = APIRouter(prefix="/historical-analysis", tags=["historical-analysis"])


@router.post("/run", response_model=HistoricalAnalysisSnapshotOut)
def run_snapshot(payload: HistoricalAnalysisRunIn, db: Session = Depends(get_db)):
    if payload.mode not in {"strict", "approximate"}:
        raise HTTPException(status_code=422, detail="mode must be strict/approximate")
    try:
        snapshot = run_historical_analysis_for_code(
            db,
            payload.code,
            payload.as_of_date,
            mode=payload.mode,
        )
    except ValueError as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=422, detail=message)
    return _snapshot_out(db, snapshot)


@router.get("", response_model=list[HistoricalAnalysisSnapshotOut])
def list_snapshots(
    code: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(HistoricalAnalysisSnapshot, Stock).join(
        Stock,
        HistoricalAnalysisSnapshot.stock_id == Stock.id,
    )
    if code:
        q = q.filter(Stock.code == code.upper())
    if date_from:
        q = q.filter(HistoricalAnalysisSnapshot.as_of_date >= date_from)
    if date_to:
        q = q.filter(HistoricalAnalysisSnapshot.as_of_date <= date_to)
    rows = (
        q.order_by(
            HistoricalAnalysisSnapshot.as_of_date.desc(),
            HistoricalAnalysisSnapshot.run_at.desc(),
            HistoricalAnalysisSnapshot.id.desc(),
        )
        .limit(min(limit, 500))
        .all()
    )
    return [_snapshot_out_from_join(db, snapshot, stock) for snapshot, stock in rows]


@router.get("/{snapshot_id}", response_model=HistoricalAnalysisSnapshotOut)
def get_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(HistoricalAnalysisSnapshot, Stock)
        .join(Stock, HistoricalAnalysisSnapshot.stock_id == Stock.id)
        .filter(HistoricalAnalysisSnapshot.id == snapshot_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"historical snapshot {snapshot_id} not found")
    snapshot, stock = row
    return _snapshot_out_from_join(db, snapshot, stock)


@router.post("/{snapshot_id}/returns", response_model=HistoricalAnalysisSnapshotOut)
def refresh_snapshot_returns(snapshot_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(HistoricalAnalysisSnapshot, Stock)
        .join(Stock, HistoricalAnalysisSnapshot.stock_id == Stock.id)
        .filter(HistoricalAnalysisSnapshot.id == snapshot_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"historical snapshot {snapshot_id} not found")
    snapshot, stock = row
    evaluate_historical_snapshot_returns(db, snapshot)
    return _snapshot_out_from_join(db, snapshot, stock)


def _snapshot_out(db: Session, snapshot: HistoricalAnalysisSnapshot) -> HistoricalAnalysisSnapshotOut:
    stock = db.get(Stock, snapshot.stock_id)
    if stock is None:
        raise HTTPException(status_code=500, detail="snapshot stock is missing")
    return _snapshot_out_from_join(db, snapshot, stock)


def _snapshot_out_from_join(
    db: Session,
    snapshot: HistoricalAnalysisSnapshot,
    stock: Stock,
) -> HistoricalAnalysisSnapshotOut:
    returns = (
        db.query(HistoricalAnalysisReturn)
        .filter_by(snapshot_id=snapshot.id)
        .order_by(HistoricalAnalysisReturn.horizon_days.asc())
        .all()
    )
    return HistoricalAnalysisSnapshotOut(
        id=snapshot.id,
        code=stock.code,
        stock_name=stock.name,
        as_of_date=snapshot.as_of_date,
        as_of_cutoff=snapshot.as_of_cutoff,
        market_data_as_of=snapshot.market_data_as_of,
        run_at=snapshot.run_at,
        mode=snapshot.mode,
        status=snapshot.status,
        boundary_status=snapshot.boundary_status,
        data_warnings=_loads(snapshot.data_warnings, []),
        input_hash=snapshot.input_hash,
        input_summary=_loads(snapshot.input_summary, {}),
        funding_score=snapshot.funding_score,
        announcement_score=snapshot.announcement_score,
        resource_score=snapshot.resource_score,
        commodity_score=snapshot.commodity_score,
        risk_score=snapshot.risk_score,
        sentiment_score=snapshot.sentiment_score,
        cycle_score=snapshot.cycle_score,
        label=snapshot.label,
        components=_loads(snapshot.components, {}),
        ai_reason=snapshot.ai_reason,
        config_snapshot=_loads(snapshot.config_snapshot, {}),
        returns=[
            {
                "horizon_days": row.horizon_days,
                "entry_date": row.entry_date,
                "entry_price": row.entry_price,
                "exit_date": row.exit_date,
                "exit_price": row.exit_price,
                "return_pct": row.return_pct,
                "benchmark_return_pct": row.benchmark_return_pct,
                "max_drawdown_pct": row.max_drawdown_pct,
                "status": row.status,
            }
            for row in returns
        ],
        created_at=snapshot.created_at,
    )


def _loads(raw: str | None, default):
    if not raw:
        return default
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return default
    return value
