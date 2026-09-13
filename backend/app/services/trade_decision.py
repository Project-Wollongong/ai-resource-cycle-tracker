"""P8 Trade Decision Engine.

P8 turns P6/P7 state into a decision package. It does not execute trades and
every actionable package is marked as requiring user confirmation.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from ..models import AttentionState, FusionRecord, PriceBar, Stock, TradeDecision

P8_RULE_VERSION = "trade_decision_rules_v1"
DEFAULT_STRATEGY_PROFILE = "balanced"


def write_trade_decision_from_state(
    session: Session,
    stock: Stock,
    fusion: FusionRecord,
    attention: AttentionState,
    strategy_profile: str = DEFAULT_STRATEGY_PROFILE,
) -> TradeDecision:
    decision_date = fusion.fusion_date
    current_price = _latest_close(session, stock.id, decision_date)
    blockers = _json_list(fusion.blocking_conditions_json)
    conflicts = _json_list(fusion.conflicts_json)
    attention_meta = _json_object(attention.metadata_json)
    recommended_state = attention_meta.get("recommended_state")

    decision, action, conviction, reason = _decision_core(
        fusion=fusion,
        attention=attention,
        blockers=blockers,
        recommended_state=str(recommended_state) if recommended_state else None,
    )

    row = (
        session.query(TradeDecision)
        .filter_by(
            stock_id=stock.id,
            decision_date=decision_date,
            rule_version=P8_RULE_VERSION,
        )
        .one_or_none()
    )
    if row is None:
        row = TradeDecision(
            stock_id=stock.id,
            decision_date=decision_date,
            rule_version=P8_RULE_VERSION,
        )
        session.add(row)

    row.fusion_record_id = fusion.id
    row.attention_state_id = attention.id
    row.decision = decision
    row.action = action
    row.conviction = conviction
    row.reason = reason
    row.entry_logic = _entry_logic(decision, action, fusion, attention, current_price)
    row.entry_range_json = json.dumps(_entry_range(current_price, action))
    row.position_size_json = json.dumps(_position_size(action, strategy_profile))
    row.add_trigger_json = json.dumps(_add_triggers(action, fusion))
    row.invalidation_json = json.dumps(_invalidation_conditions(fusion, blockers))
    row.target_logic_json = json.dumps(_target_logic(decision, fusion))
    row.key_risks_json = json.dumps(_key_risks(fusion, blockers, conflicts))
    row.review_trigger_json = json.dumps(_review_triggers(decision, attention, fusion))
    row.strategy_profile = strategy_profile
    row.metadata_json = json.dumps(
        {
            "fusion_record_id": fusion.id,
            "attention_state_id": attention.id,
            "attention_state": attention.state_level,
            "recommended_state": recommended_state,
            "requires_user_confirmation": action != "none",
            "current_price": current_price,
            "opportunity_strength": fusion.opportunity_strength,
            "signal_structure": fusion.signal_structure,
            "evidence_independence": fusion.evidence_independence,
            "overheating_risk": fusion.overheating_risk,
        },
        default=str,
    )
    session.commit()
    return row


def _decision_core(
    *,
    fusion: FusionRecord,
    attention: AttentionState,
    blockers: list[str],
    recommended_state: str | None,
) -> tuple[str, str, str, str]:
    if attention.state_level == "L5":
        return (
            "pass",
            "none",
            "low",
            "P9 position management owns post-entry decisions for L5.",
        )
    if blockers or fusion.official_result == "blocked":
        return (
            "pass",
            "none",
            "low",
            "Blocking conditions prevent a trade decision package from becoming actionable.",
        )
    if attention.state_level in {"L0", "L1"}:
        return (
            "pass",
            "none",
            "low",
            "Attention state is below the threshold for a trade decision workflow.",
        )
    if attention.state_level == "L2":
        return (
            "wait",
            "none",
            "low",
            "Active Watch requires more evidence before entry planning.",
        )
    if attention.state_level == "L3":
        suffix = " L4 is recommended for human confirmation." if recommended_state == "L4" else ""
        return (
            "wait",
            "none",
            "medium" if recommended_state == "L4" else "low",
            f"Investigation state is not yet a trading decision.{suffix}",
        )

    if attention.state_level == "L4":
        if fusion.overheating_risk in {"medium", "high"}:
            return (
                "wait",
                "none",
                "medium",
                "Decision Ready, but overheating risk requires better entry conditions.",
            )
        if fusion.opportunity_strength == "exceptional" and fusion.confidence == "high":
            return (
                "act",
                "buy",
                "high",
                "Decision Ready with exceptional opportunity and high confidence.",
            )
        return (
            "act",
            "starter_buy",
            "medium",
            "Decision Ready, but staged entry is preferred until confirmation improves.",
        )

    return ("pass", "none", "low", "Unknown attention state.")


def _latest_close(session: Session, stock_id: int, as_of: date) -> float | None:
    row = (
        session.query(PriceBar)
        .filter(PriceBar.stock_id == stock_id, PriceBar.date <= as_of)
        .order_by(PriceBar.date.desc())
        .first()
    )
    return row.close if row is not None else None


def _entry_logic(
    decision: str,
    action: str,
    fusion: FusionRecord,
    attention: AttentionState,
    current_price: float | None,
) -> str:
    if decision == "pass":
        return "No entry plan while decision is pass."
    if action == "none":
        if attention.state_level == "L3":
            return "Complete human review before any entry package is promoted to actionable."
        return "Wait for stronger independent evidence or cleaner entry conditions."
    if current_price is None:
        return "Action requires user confirmation and a fresh market price check."
    if fusion.overheating_risk == "low":
        return "Action requires user confirmation; prefer current price or shallow pullback with thesis intact."
    return "Action requires user confirmation; avoid chasing until overheating risk clears."


def _entry_range(current_price: float | None, action: str) -> dict[str, Any]:
    if current_price is None or action == "none":
        return {}
    pullback_low = round(current_price * 0.92, 4)
    pullback_high = round(current_price * 0.97, 4)
    return {
        "reference_price": current_price,
        "acceptable_now": action == "buy",
        "pullback_range": {"low": pullback_low, "high": pullback_high},
    }


def _position_size(action: str, strategy_profile: str) -> dict[str, Any]:
    if action == "none":
        return {}
    starter = {"conservative": 0.15, "balanced": 0.25, "aggressive": 0.35}.get(strategy_profile, 0.25)
    full = {"conservative": 0.35, "balanced": 0.50, "aggressive": 0.65}.get(strategy_profile, 0.50)
    return {
        "sizing_basis": "target_position_fraction",
        "target_fraction": starter if action == "starter_buy" else full,
        "requires_user_confirmation": True,
    }


def _add_triggers(action: str, fusion: FusionRecord) -> list[str]:
    if action == "none":
        return []
    triggers = ["fresh independent confirmation", "thesis remains intact after next material announcement"]
    if fusion.signal_structure != "confirmation":
        triggers.append("signal structure improves to confirmation")
    return triggers


def _invalidation_conditions(fusion: FusionRecord, blockers: list[str]) -> list[str]:
    conditions = [
        "thesis-breaking announcement",
        "funding deterioration materially worsens risk score",
        "failed breakout or loss of key price structure",
        "expected catalyst delayed beyond reviewed window",
    ]
    conditions.extend(f"existing blocker: {item}" for item in blockers)
    if fusion.overheating_risk in {"medium", "high"}:
        conditions.append("speculative move continues without fundamental or catalyst confirmation")
    return conditions


def _target_logic(decision: str, fusion: FusionRecord) -> dict[str, Any]:
    if decision == "pass":
        return {}
    return {
        "basis": "catalyst_and_thesis_review",
        "opportunity_strength": fusion.opportunity_strength,
        "avoid_false_precision": True,
    }


def _key_risks(fusion: FusionRecord, blockers: list[str], conflicts: list[str]) -> list[str]:
    risks = list(blockers)
    risks.extend(conflicts)
    if fusion.overheating_risk and fusion.overheating_risk != "low":
        risks.append(f"overheating_risk:{fusion.overheating_risk}")
    if fusion.evidence_independence in {None, "none", "single_source"}:
        risks.append("limited independent evidence")
    return risks


def _review_triggers(decision: str, attention: AttentionState, fusion: FusionRecord) -> list[str]:
    triggers = ["new material ASX announcement", "P6 conflict or blocking condition changes"]
    if decision == "wait" and attention.state_level == "L3":
        triggers.append("human review of L4 recommendation")
    if fusion.overheating_risk in {"medium", "high"}:
        triggers.append("overheating risk normalises")
    return triggers


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


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
