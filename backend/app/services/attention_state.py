"""P7 Attention State Engine.

The first implementation is deliberately conservative: it consumes P6 fusion
records, manages the current L0-L5 interval, and never auto-promotes to L4/L5.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import AttentionState, FusionRecord, Stock

P7_RULE_VERSION = "attention_rules_v1"

STATE_LABELS = {
    "L0": "Universe",
    "L1": "Watch",
    "L2": "Active Watch",
    "L3": "Investigation",
    "L4": "Decision Ready",
    "L5": "Position",
}
STATE_RANK = {level: rank for rank, level in enumerate(STATE_LABELS)}


def update_attention_state_from_fusion(
    session: Session,
    stock: Stock,
    fusion: FusionRecord,
) -> AttentionState:
    existing_for_fusion = (
        session.query(AttentionState)
        .filter_by(stock_id=stock.id, fusion_record_id=fusion.id, rule_version=P7_RULE_VERSION)
        .one_or_none()
    )
    if existing_for_fusion is not None:
        return existing_for_fusion

    current = _current_state(session, stock.id)
    current_level = current.state_level if current is not None else "L1"

    if current is not None and (current.manual_lock or current.manual_override):
        _apply_evaluation(current, fusion, current.state_level, "hold")
        session.commit()
        return current

    raw_target, recommended_state, human_review_required = _raw_target_state(fusion)
    target = _apply_hysteresis(current_level, raw_target, fusion)
    transition = _transition(current_level, target)

    if current is not None and target == current.state_level:
        _apply_evaluation(
            current,
            fusion,
            target,
            "hold",
            recommended_state=recommended_state,
            human_review_required=human_review_required,
        )
        session.commit()
        return current

    if current is not None:
        current.ended_at = datetime.utcnow()

    attention = AttentionState(
        stock_id=stock.id,
        fusion_record_id=fusion.id,
        state_level=target,
        state_label=STATE_LABELS[target],
        previous_state_level=current_level,
        transition=transition,
        reason=_reason(fusion, target, recommended_state),
        compute_profile=_compute_profile(target),
        alert_priority=_alert_priority(target, human_review_required),
        rule_version=P7_RULE_VERSION,
        metadata_json=json.dumps(
            _metadata(fusion, recommended_state, human_review_required),
            default=str,
        ),
    )
    session.add(attention)
    session.commit()
    return attention


def _current_state(session: Session, stock_id: int) -> AttentionState | None:
    return (
        session.query(AttentionState)
        .filter_by(stock_id=stock_id, ended_at=None)
        .order_by(AttentionState.effective_at.desc(), AttentionState.id.desc())
        .first()
    )


def _raw_target_state(fusion: FusionRecord) -> tuple[str, str | None, bool]:
    if fusion.official_result == "blocked" or _json_list(fusion.blocking_conditions_json):
        return "L2", None, True

    strength = fusion.opportunity_strength
    confidence = fusion.confidence or "low"
    independence = fusion.evidence_independence or "none"
    structure = fusion.signal_structure or "no_signal"

    if strength in {"none", "weak"}:
        return "L1", None, False
    if strength == "moderate":
        if structure in {"confirmation", "technical_led_early_formation", "fundamental_led_early_formation"}:
            return "L2", None, False
        return "L1", None, False
    if strength == "strong":
        if confidence in {"medium", "high"}:
            recommended = "L4" if independence in {"medium", "high"} else None
            return "L3", recommended, recommended == "L4"
        return "L2", None, False
    if strength == "exceptional":
        recommended = "L4" if confidence in {"medium", "high"} and independence in {"medium", "high"} else None
        return "L3", recommended, recommended == "L4"
    return "L1", None, False


def _apply_hysteresis(current_level: str, raw_target: str, fusion: FusionRecord) -> str:
    current_rank = STATE_RANK.get(current_level, 1)
    target_rank = STATE_RANK.get(raw_target, 1)

    if current_level == "L5":
        return "L5"
    if current_level == "L4" and target_rank < STATE_RANK["L3"]:
        return "L3"
    if current_level == "L3" and raw_target == "L2":
        return "L3"
    if current_level == "L3" and raw_target == "L1":
        return "L2"
    if current_level == "L2" and raw_target == "L1" and fusion.opportunity_strength != "none":
        return "L2"
    return raw_target


def _transition(previous: str, target: str) -> str:
    prev_rank = STATE_RANK.get(previous, 1)
    target_rank = STATE_RANK.get(target, 1)
    if target_rank > prev_rank:
        return "upgrade"
    if target_rank < prev_rank:
        return "downgrade"
    return "hold"


def _apply_evaluation(
    state: AttentionState,
    fusion: FusionRecord,
    target: str,
    transition: str,
    recommended_state: str | None = None,
    human_review_required: bool = False,
) -> None:
    state.fusion_record_id = fusion.id
    state.state_level = target
    state.state_label = STATE_LABELS[target]
    state.transition = transition
    state.reason = _reason(fusion, target, recommended_state)
    state.compute_profile = _compute_profile(target)
    state.alert_priority = _alert_priority(target, human_review_required)
    state.metadata_json = json.dumps(
        _metadata(fusion, recommended_state, human_review_required),
        default=str,
    )


def _reason(fusion: FusionRecord, target: str, recommended_state: str | None) -> str:
    parts = [
        f"P6 official result is {fusion.official_result}",
        f"opportunity strength is {fusion.opportunity_strength}",
        f"confidence is {fusion.confidence or 'unknown'}",
        f"evidence independence is {fusion.evidence_independence or 'unknown'}",
        f"P7 state is {target}",
    ]
    if recommended_state:
        parts.append(f"{recommended_state} requires human confirmation")
    blockers = _json_list(fusion.blocking_conditions_json)
    if blockers:
        parts.append(f"blocking conditions: {', '.join(blockers)}")
    return "; ".join(parts)


def _compute_profile(level: str) -> str:
    return {
        "L0": "minimal",
        "L1": "standard",
        "L2": "enhanced_monitoring",
        "L3": "deep_investigation",
        "L4": "decision_ready_review",
        "L5": "position_critical",
    }.get(level, "standard")


def _alert_priority(level: str, human_review_required: bool) -> str:
    if human_review_required:
        return "human_review"
    if level in {"L4", "L5"}:
        return "high_priority"
    if level == "L3":
        return "push"
    return "dashboard"


def _metadata(
    fusion: FusionRecord,
    recommended_state: str | None,
    human_review_required: bool,
) -> dict[str, Any]:
    return {
        "fusion_record_id": fusion.id,
        "fusion_rule_version": fusion.rule_version,
        "recommended_state": recommended_state,
        "human_review_required": human_review_required,
        "signal_structure": fusion.signal_structure,
        "overheating_risk": fusion.overheating_risk,
        "blocking_conditions": _json_list(fusion.blocking_conditions_json),
        "conflicts": _json_list(fusion.conflicts_json),
    }


def _json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
