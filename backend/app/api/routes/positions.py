import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...models import AttentionState, FusionRecord, Position, PositionEvent, Stock, TradeDecision
from ...schemas import PositionCloseIn, PositionOpenIn, PositionOut
from ...services.position_management import (
    close_position,
    open_position_from_execution,
    update_position_from_current_state,
)
from ..deps import get_db
from ..security import require_admin_access

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("", response_model=list[PositionOut])
def list_positions(
    status: str | None = "open",
    code: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(Position, Stock).join(Stock, Position.stock_id == Stock.id)
    if status:
        q = q.filter(Position.status == status)
    if code:
        q = q.filter(Stock.code == code.upper())
    rows = q.order_by(Position.opened_at.desc(), Position.id.desc()).limit(min(limit, 500)).all()
    return [_position_out(db, position, stock, include_events=False) for position, stock in rows]


@router.get("/{position_id}", response_model=PositionOut)
def get_position(position_id: int, db: Session = Depends(get_db)):
    position, stock = _position_and_stock(db, position_id)
    return _position_out(db, position, stock, include_events=True)


@router.post("", response_model=PositionOut, status_code=201, dependencies=[Depends(require_admin_access)])
def open_position(payload: PositionOpenIn, db: Session = Depends(get_db)):
    stock = db.query(Stock).filter_by(code=payload.code.upper()).one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"stock {payload.code.upper()} not found")
    trade_decision = None
    if payload.trade_decision_id is not None:
        trade_decision = db.get(TradeDecision, payload.trade_decision_id)
        if trade_decision is None or trade_decision.stock_id != stock.id:
            raise HTTPException(status_code=404, detail=f"trade decision {payload.trade_decision_id} not found")
    try:
        position = open_position_from_execution(
            db,
            stock,
            entry_price=payload.entry_price,
            quantity=payload.quantity,
            opened_at=payload.opened_at or datetime.utcnow(),
            trade_decision=trade_decision,
            strategy_profile=payload.strategy_profile,
            original_thesis=payload.original_thesis,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _position_out(db, position, stock, include_events=True)


@router.post("/{position_id}/refresh", response_model=PositionOut, dependencies=[Depends(require_admin_access)])
def refresh_position(position_id: int, db: Session = Depends(get_db)):
    position, stock = _position_and_stock(db, position_id)
    if position.status != "open":
        raise HTTPException(status_code=422, detail="only open positions can be refreshed")
    fusion = _latest_fusion(db, stock.id)
    attention = _latest_attention(db, stock.id)
    decision = _latest_trade_decision(db, stock.id)
    position = update_position_from_current_state(
        db,
        position,
        stock,
        fusion=fusion,
        attention=attention,
        trade_decision=decision,
    )
    return _position_out(db, position, stock, include_events=True)


@router.post("/{position_id}/close", response_model=PositionOut, dependencies=[Depends(require_admin_access)])
def close_position_endpoint(position_id: int, payload: PositionCloseIn, db: Session = Depends(get_db)):
    position, stock = _position_and_stock(db, position_id)
    if position.status != "open":
        raise HTTPException(status_code=422, detail="position is already closed")
    try:
        position = close_position(
            db,
            position,
            stock,
            exit_price=payload.exit_price,
            closed_at=payload.closed_at or datetime.utcnow(),
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _position_out(db, position, stock, include_events=True)


def _position_and_stock(db: Session, position_id: int) -> tuple[Position, Stock]:
    row = (
        db.query(Position, Stock)
        .join(Stock, Position.stock_id == Stock.id)
        .filter(Position.id == position_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"position {position_id} not found")
    return row


def _latest_fusion(db: Session, stock_id: int) -> FusionRecord | None:
    return (
        db.query(FusionRecord)
        .filter_by(stock_id=stock_id)
        .order_by(FusionRecord.fusion_date.desc(), FusionRecord.id.desc())
        .first()
    )


def _latest_attention(db: Session, stock_id: int) -> AttentionState | None:
    return (
        db.query(AttentionState)
        .filter_by(stock_id=stock_id, ended_at=None)
        .order_by(AttentionState.effective_at.desc(), AttentionState.id.desc())
        .first()
    )


def _latest_trade_decision(db: Session, stock_id: int) -> TradeDecision | None:
    return (
        db.query(TradeDecision)
        .filter_by(stock_id=stock_id)
        .order_by(TradeDecision.decision_date.desc(), TradeDecision.id.desc())
        .first()
    )


def _position_out(db: Session, position: Position, stock: Stock, include_events: bool) -> PositionOut:
    current_price = position.current_price
    market_value = current_price * position.quantity if current_price is not None else None
    pnl_pct = None
    if current_price is not None and position.entry_price:
        pnl_pct = round((current_price / position.entry_price - 1) * 100, 2)
    events = []
    if include_events:
        event_rows = (
            db.query(PositionEvent)
            .filter_by(position_id=position.id)
            .order_by(PositionEvent.event_time.desc(), PositionEvent.id.desc())
            .all()
        )
        events = [
            {
                "id": event.id,
                "event_time": event.event_time,
                "event_type": event.event_type,
                "action": event.action,
                "price": event.price,
                "quantity_delta": event.quantity_delta,
                "thesis_status": event.thesis_status,
                "catalyst_status": event.catalyst_status,
                "risk_status": event.risk_status,
                "reason": event.reason,
                "evidence": _loads(event.evidence_json, {}),
                "metadata": _loads(event.metadata_json, {}),
            }
            for event in event_rows
        ]
    return PositionOut(
        id=position.id,
        code=stock.code,
        stock_name=stock.name,
        commodity=stock.commodity,
        trade_decision_id=position.trade_decision_id,
        status=position.status,
        opened_at=position.opened_at,
        closed_at=position.closed_at,
        entry_price=position.entry_price,
        quantity=position.quantity,
        current_price=current_price,
        market_value=market_value,
        unrealized_pnl_pct=pnl_pct,
        thesis_status=position.thesis_status,
        catalyst_status=position.catalyst_status,
        risk_status=position.risk_status,
        suggested_action=position.suggested_action,
        price_stop=position.price_stop,
        thesis_stop=_loads(position.thesis_stop_json, []),
        target_logic=_loads(position.target_logic_json, {}),
        original_thesis=_loads(position.original_thesis_json, {}),
        thesis_delta=_loads(position.thesis_delta_json, {}),
        strategy_profile=position.strategy_profile,
        metadata=_loads(position.metadata_json, {}),
        events=events,
    )


def _loads(raw: str | None, default):
    if not raw:
        return default
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return default
    return value
