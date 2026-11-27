"""Human control over the attention state.

P07 never promotes a stock to Decision Ready or Position on its own: the
architecture reserves that step for a person, and the engine only recommends.
The mechanism for holding a state against the engine already existed -- the
engine checks `manual_override` before it moves anything -- but there was no
way to set it, so the reserved step could not be taken and everything below it
(P08's decision, P09's position, P10's review) had never run.

Setting a state is recorded as an event rather than an edit: the engine's
interval is closed and a new one opened, so the history says who moved it,
when, and what the engine thought at the time.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import AttentionState, FusionRecord, Stock
from .attention_state import P7_RULE_VERSION, STATE_LABELS, STATE_RANK, _current_state
from .trade_decision import write_trade_decision_from_state


class AttentionOverrideError(ValueError):
    """The requested change cannot be made."""


def set_attention_state(
    session: Session,
    stock: Stock,
    level: str,
    actor: str,
    note: str = "",
    lock: bool = False,
) -> AttentionState:
    """Put a stock into `level` by hand and hold it there.

    `lock` is the stronger form: an override holds until someone clears it,
    while a lock additionally signals that the holder does not want the engine
    consulted at all. Both stop the engine from moving the state.
    """
    if level not in STATE_LABELS:
        raise AttentionOverrideError(
            f"unknown attention level {level!r}; expected one of {sorted(STATE_LABELS)}"
        )
    if not actor.strip():
        raise AttentionOverrideError("an override must record who made it")

    current = _current_state(session, stock.id)
    fusion = _latest_fusion(session, stock.id)
    engine_level = current.state_level if current is not None else None
    if current is not None:
        current.ended_at = datetime.utcnow()

    state = AttentionState(
        stock_id=stock.id,
        fusion_record_id=fusion.id if fusion is not None else None,
        state_level=level,
        state_label=STATE_LABELS[level],
        previous_state_level=engine_level,
        transition=_transition(engine_level, level),
        reason=_reason(actor, note, engine_level),
        manual_override=True,
        manual_lock=lock,
        compute_profile="manual",
        alert_priority="high" if STATE_RANK[level] >= STATE_RANK["L4"] else "normal",
        rule_version=P7_RULE_VERSION,
        metadata_json=json.dumps(
            {
                "set_by": actor,
                "note": note,
                "set_at": datetime.utcnow(),
                # what the engine had concluded when the person overrode it;
                # without this the record cannot say what was overridden
                "engine_state_at_override": engine_level,
                "fusion_record_id": fusion.id if fusion is not None else None,
            },
            default=str,
        ),
    )
    session.add(state)
    session.flush()

    # P08 reads the attention state, so the decision is stale the moment the
    # state moves. Refreshing here is what makes the promotion take effect
    # rather than wait for the next pipeline run.
    if fusion is not None:
        write_trade_decision_from_state(session, stock, fusion, state)
    session.commit()
    return state


def clear_attention_override(session: Session, stock: Stock, actor: str) -> AttentionState | None:
    """Hand the state back to the engine.

    The interval is left open and only the flags are cleared, so the next
    fusion record moves it normally. Ending the interval here would invent a
    transition that nobody made.
    """
    current = _current_state(session, stock.id)
    if current is None:
        return None
    if not (current.manual_override or current.manual_lock):
        raise AttentionOverrideError(f"{stock.code} is not under a manual override")

    current.manual_override = False
    current.manual_lock = False
    current.reason = f"{current.reason} | override released by {actor}"
    metadata = _loads(current.metadata_json)
    metadata["override_released_by"] = actor
    metadata["override_released_at"] = datetime.utcnow()
    current.metadata_json = json.dumps(metadata, default=str)
    session.commit()
    return current


def _latest_fusion(session: Session, stock_id: int) -> FusionRecord | None:
    return (
        session.query(FusionRecord)
        .filter_by(stock_id=stock_id)
        .order_by(FusionRecord.fusion_date.desc(), FusionRecord.id.desc())
        .first()
    )


def _transition(previous: str | None, level: str) -> str:
    if previous is None or previous == level:
        return "hold"
    return "promote" if STATE_RANK[level] > STATE_RANK[previous] else "demote"


def _reason(actor: str, note: str, engine_level: str | None) -> str:
    base = f"Set manually by {actor}"
    if engine_level:
        base += f"; engine had {engine_level}"
    return f"{base}. {note}".strip()


def _loads(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
