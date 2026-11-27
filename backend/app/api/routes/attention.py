"""P07 attention state: read it, and move it by hand.

Promotion to Decision Ready is reserved for a person by design. These are the
routes that let one take it; without them the reservation was simply a dead
end.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...models import AttentionState, Stock, TradeDecision
from ...services.attention_override import (
    AttentionOverrideError,
    clear_attention_override,
    set_attention_state,
)
from ...services.attention_state import STATE_LABELS
from ..deps import get_db
from ..security import require_admin_access

router = APIRouter(prefix="/attention", tags=["attention"])


class AttentionSetIn(BaseModel):
    level: str = Field(..., description="L0-L5")
    actor: str = Field(..., min_length=1, description="who is taking responsibility")
    note: str = ""
    lock: bool = False


def _out(state: AttentionState, decision: TradeDecision | None = None) -> dict:
    return {
        "state_level": state.state_level,
        "state_label": state.state_label,
        "previous_state_level": state.previous_state_level,
        "transition": state.transition,
        "reason": state.reason,
        "manual_override": bool(state.manual_override),
        "manual_lock": bool(state.manual_lock),
        "alert_priority": state.alert_priority,
        "effective_at": state.effective_at,
        "trade_decision": None if decision is None else {
            "decision": decision.decision,
            "action": decision.action,
            "conviction": decision.conviction,
            "reason": decision.reason,
        },
    }


def _stock(db: Session, code: str) -> Stock:
    stock = db.query(Stock).filter(Stock.code == code.upper()).one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"stock {code.upper()} not found")
    return stock


def _current(db: Session, stock_id: int) -> AttentionState | None:
    return (
        db.query(AttentionState)
        .filter_by(stock_id=stock_id, ended_at=None)
        .order_by(AttentionState.effective_at.desc(), AttentionState.id.desc())
        .first()
    )


def _latest_decision(db: Session, stock_id: int) -> TradeDecision | None:
    return (
        db.query(TradeDecision)
        .filter_by(stock_id=stock_id)
        .order_by(TradeDecision.decision_date.desc(), TradeDecision.id.desc())
        .first()
    )


@router.get("/levels")
def list_levels() -> dict:
    """The ladder, so a caller does not have to hard-code it."""
    return {"levels": [{"level": key, "label": value} for key, value in STATE_LABELS.items()]}


@router.get("/{code}")
def get_attention(code: str, db: Session = Depends(get_db)) -> dict:
    stock = _stock(db, code)
    state = _current(db, stock.id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"{stock.code} has no attention state yet")
    return _out(state, _latest_decision(db, stock.id))


@router.put("/{code}", dependencies=[Depends(require_admin_access)])
def set_attention(code: str, payload: AttentionSetIn, db: Session = Depends(get_db)) -> dict:
    """Move a stock to a level by hand and hold it there.

    The trade decision is recomputed immediately, so a promotion to Decision
    Ready produces its consequence in the same call rather than waiting for
    the next pipeline run.
    """
    stock = _stock(db, code)
    try:
        state = set_attention_state(
            db, stock, payload.level.upper(), payload.actor, payload.note, payload.lock
        )
    except AttentionOverrideError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _out(state, _latest_decision(db, stock.id))


@router.delete("/{code}", dependencies=[Depends(require_admin_access)])
def release_attention(code: str, actor: str, db: Session = Depends(get_db)) -> dict:
    """Hand the state back to the engine."""
    stock = _stock(db, code)
    try:
        state = clear_attention_override(db, stock, actor)
    except AttentionOverrideError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if state is None:
        raise HTTPException(status_code=404, detail=f"{stock.code} has no attention state yet")
    return _out(state, _latest_decision(db, stock.id))
