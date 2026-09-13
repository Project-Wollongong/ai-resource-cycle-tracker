"""Compatibility adapter from the current radar model to Beta02 P5/P6 records.

This keeps ScoreSnapshot/Signal as the live product contract while writing
append-only-shaped P5 analytical signals and one P6 fusion record per stock/day.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from ..models import AnalyticalSignal, FusionRecord, ScoreSnapshot, Signal, Stock
from .attention_state import update_attention_state_from_fusion
from .trade_decision import write_trade_decision_from_state

P5_LOGIC_VERSION = "cycle_score_adapter_v1"
P6_RULE_VERSION = "fusion_adapter_v1"

TECHNICAL_SIGNAL_TYPES = {"REL_VOL_SPIKE", "BREAKOUT_60D", "BREAKOUT_252D"}


def write_p5_p6_compat_records(
    session: Session,
    stock: Stock,
    snapshot: ScoreSnapshot,
    signals: list[Signal],
) -> FusionRecord:
    components = _loads(snapshot.components, {})
    analytical_ids: list[int] = []

    resource = components.get("resource") if isinstance(components.get("resource"), dict) else {}
    if snapshot.resource_score != 50.0 or resource.get("source") not in {None, "neutral_default"}:
        analytical_ids.append(
            _upsert_analytical_signal(
                session,
                stock_id=stock.id,
                signal_date=snapshot.date,
                engine="fundamental",
                direction=_direction_from_score(snapshot.resource_score),
                magnitude=_magnitude_from_score(snapshot.resource_score),
                confidence=_confidence_for_source(resource.get("source")),
                persistence="medium",
                source_event_id=_source_event_from_resource(resource, snapshot.date),
                dependency_group=_source_event_from_resource(resource, snapshot.date),
                evidence_ids=[],
                feature_ids=[],
                key_drivers=_resource_drivers(resource),
                key_risks=[],
                metadata={"score": snapshot.resource_score, "component": resource},
            ).id
        )

    announcement = components.get("announcement") if isinstance(components.get("announcement"), dict) else {}
    if snapshot.announcement_score > 0:
        source_event_id = _source_event_from_announcement(announcement, snapshot.date)
        analytical_ids.append(
            _upsert_analytical_signal(
                session,
                stock_id=stock.id,
                signal_date=snapshot.date,
                engine="catalyst",
                direction="positive",
                magnitude=snapshot.announcement_score,
                confidence=0.7,
                persistence="short",
                source_event_id=source_event_id,
                dependency_group=source_event_id,
                evidence_ids=_announcement_evidence_ids(announcement),
                feature_ids=[],
                key_drivers=_announcement_drivers(announcement),
                key_risks=[],
                metadata={"score": snapshot.announcement_score, "component": announcement},
            ).id
        )

    for signal in signals:
        if signal.signal_type not in TECHNICAL_SIGNAL_TYPES:
            continue
        analytical_ids.append(
            _upsert_analytical_signal(
                session,
                stock_id=stock.id,
                signal_date=snapshot.date,
                engine="technical",
                direction="positive",
                magnitude=_technical_magnitude(signal),
                confidence=0.75,
                persistence="short",
                source_event_id=f"signal:{signal.id}",
                dependency_group=f"market:{snapshot.date.isoformat()}",
                evidence_ids=[],
                feature_ids=[],
                key_drivers=[signal.reason],
                key_risks=[],
                metadata={
                    "signal_id": signal.id,
                    "signal_type": signal.signal_type,
                    "evidence": _loads(signal.evidence, {}),
                },
            ).id
        )

    risk = components.get("risk") if isinstance(components.get("risk"), dict) else {}
    blocking_conditions = _blocking_conditions(snapshot.risk_score, risk)
    conflicts = _conflicts(analytical_ids, snapshot, signals)
    opportunity_strength = _opportunity_strength(snapshot.cycle_score)
    official_result = "blocked" if blocking_conditions else opportunity_strength

    fusion = _upsert_fusion_record(
        session,
        stock_id=stock.id,
        fusion_date=snapshot.date,
        opportunity_strength=opportunity_strength,
        confidence=_fusion_confidence(analytical_ids, snapshot),
        signal_structure=_signal_structure(session, analytical_ids),
        evidence_independence=_evidence_independence(session, analytical_ids),
        dominant_drivers=_dominant_drivers(components, signals),
        conflicts=conflicts,
        blocking_conditions=blocking_conditions,
        overheating_risk=_overheating_risk(snapshot, signals),
        official_result=official_result,
        shadow_result=None,
        conflict_flag=bool(conflicts),
        human_review_required=bool(blocking_conditions and snapshot.cycle_score >= 60),
        analytical_signal_ids=analytical_ids,
        metadata={
            "score_snapshot_id": snapshot.id,
            "cycle_score": snapshot.cycle_score,
            "label": snapshot.label,
        },
    )
    attention = update_attention_state_from_fusion(session, stock, fusion)
    write_trade_decision_from_state(session, stock, fusion, attention)
    session.commit()
    return fusion


def _upsert_analytical_signal(
    session: Session,
    *,
    stock_id: int,
    signal_date: date,
    engine: str,
    direction: str,
    magnitude: float | None,
    confidence: float | None,
    persistence: str | None,
    source_event_id: str,
    dependency_group: str,
    evidence_ids: list[Any],
    feature_ids: list[Any],
    key_drivers: list[str],
    key_risks: list[str],
    metadata: dict[str, Any],
) -> AnalyticalSignal:
    row = (
        session.query(AnalyticalSignal)
        .filter_by(
            stock_id=stock_id,
            signal_date=signal_date,
            engine=engine,
            source_event_id=source_event_id,
            logic_version=P5_LOGIC_VERSION,
        )
        .one_or_none()
    )
    if row is None:
        row = AnalyticalSignal(
            stock_id=stock_id,
            signal_date=signal_date,
            engine=engine,
            source_event_id=source_event_id,
            logic_version=P5_LOGIC_VERSION,
        )
        session.add(row)
    row.direction = direction
    row.magnitude = magnitude
    row.confidence = confidence
    row.persistence = persistence
    row.dependency_group = dependency_group
    row.evidence_ids_json = json.dumps(evidence_ids)
    row.feature_ids_json = json.dumps(feature_ids)
    row.key_drivers_json = json.dumps(key_drivers)
    row.key_risks_json = json.dumps(key_risks)
    row.metadata_json = json.dumps(metadata, default=str)
    session.flush()
    return row


def _upsert_fusion_record(
    session: Session,
    *,
    stock_id: int,
    fusion_date: date,
    opportunity_strength: str,
    confidence: str,
    signal_structure: str,
    evidence_independence: str,
    dominant_drivers: list[str],
    conflicts: list[str],
    blocking_conditions: list[str],
    overheating_risk: str,
    official_result: str,
    shadow_result: str | None,
    conflict_flag: bool,
    human_review_required: bool,
    analytical_signal_ids: list[int],
    metadata: dict[str, Any],
) -> FusionRecord:
    row = (
        session.query(FusionRecord)
        .filter_by(stock_id=stock_id, fusion_date=fusion_date, rule_version=P6_RULE_VERSION)
        .one_or_none()
    )
    if row is None:
        row = FusionRecord(stock_id=stock_id, fusion_date=fusion_date, rule_version=P6_RULE_VERSION)
        session.add(row)
    row.opportunity_strength = opportunity_strength
    row.confidence = confidence
    row.signal_structure = signal_structure
    row.evidence_independence = evidence_independence
    row.dominant_drivers_json = json.dumps(dominant_drivers)
    row.conflicts_json = json.dumps(conflicts)
    row.blocking_conditions_json = json.dumps(blocking_conditions)
    row.overheating_risk = overheating_risk
    row.official_result = official_result
    row.shadow_result = shadow_result
    row.conflict_flag = conflict_flag
    row.human_review_required = human_review_required
    row.analytical_signal_ids_json = json.dumps(analytical_signal_ids)
    row.metadata_json = json.dumps(metadata, default=str)
    session.flush()
    return row


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _direction_from_score(score: float) -> str:
    if score >= 60:
        return "positive"
    if score <= 40:
        return "negative"
    return "neutral"


def _magnitude_from_score(score: float) -> float:
    return round(abs(score - 50.0) * 2, 1)


def _confidence_for_source(source: Any) -> float:
    if source == "manual_override":
        return 0.8
    if source == "qualitative_context_auto":
        return 0.65
    return 0.5


def _source_event_from_resource(resource: dict[str, Any], signal_date: date) -> str:
    items = resource.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        ann_id = items[0].get("ann_id")
        if ann_id:
            return f"announcement:{ann_id}"
    source = resource.get("source") or "resource_component"
    return f"{source}:{signal_date.isoformat()}"


def _resource_drivers(resource: dict[str, Any]) -> list[str]:
    items = resource.get("items")
    if isinstance(items, list) and items:
        drivers = []
        for item in items[:3]:
            if isinstance(item, dict):
                label = item.get("interval_quality_label") or item.get("materiality_label")
                headline = item.get("headline")
                if label or headline:
                    drivers.append(" / ".join(str(v) for v in (label, headline) if v))
        return drivers
    source = resource.get("source")
    return [str(source)] if source else []


def _source_event_from_announcement(announcement: dict[str, Any], signal_date: date) -> str:
    anns = announcement.get("announcements")
    if isinstance(anns, list) and anns and isinstance(anns[0], dict):
        ann_id = anns[0].get("ann_id")
        if ann_id:
            return f"announcement:{ann_id}"
    return f"announcement_cluster:{signal_date.isoformat()}"


def _announcement_evidence_ids(announcement: dict[str, Any]) -> list[str]:
    anns = announcement.get("announcements")
    if not isinstance(anns, list):
        return []
    return [str(a["ann_id"]) for a in anns if isinstance(a, dict) and a.get("ann_id")]


def _announcement_drivers(announcement: dict[str, Any]) -> list[str]:
    anns = announcement.get("announcements")
    if not isinstance(anns, list):
        return []
    drivers = []
    for item in anns[:3]:
        if isinstance(item, dict):
            typ = item.get("type")
            headline = item.get("headline")
            if typ or headline:
                drivers.append(": ".join(str(v) for v in (typ, headline) if v))
    return drivers


def _technical_magnitude(signal: Signal) -> float:
    if signal.signal_type == "BREAKOUT_252D":
        return 85.0
    if signal.signal_type == "BREAKOUT_60D":
        return 70.0
    evidence = _loads(signal.evidence, {})
    rel_vol = evidence.get("rel_vol") if isinstance(evidence, dict) else None
    try:
        return min(90.0, 50.0 + float(rel_vol) * 8.0)
    except (TypeError, ValueError):
        return 60.0


def _blocking_conditions(risk_score: float, risk: dict[str, Any]) -> list[str]:
    conditions = []
    if risk_score < 30:
        conditions.append("risk_score_below_30")
    events = risk.get("events")
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict) and event.get("adjustment", 0) <= -16:
                reason = event.get("reason")
                conditions.append(str(reason or "material_risk_event"))
    return conditions[:5]


def _conflicts(analytical_ids: list[int], snapshot: ScoreSnapshot, signals: list[Signal]) -> list[str]:
    if not analytical_ids and snapshot.cycle_score >= 60:
        return ["cycle_score_without_p5_signal_adapter_support"]
    if snapshot.risk_score < 40 and any(s.signal_type in TECHNICAL_SIGNAL_TYPES for s in signals):
        return ["technical_strength_with_elevated_risk"]
    return []


def _opportunity_strength(score: float) -> str:
    if score >= 85:
        return "exceptional"
    if score >= 75:
        return "strong"
    if score >= 60:
        return "moderate"
    if score >= 45:
        return "weak"
    return "none"


def _fusion_confidence(analytical_ids: list[int], snapshot: ScoreSnapshot) -> str:
    if len(analytical_ids) >= 3 and snapshot.risk_score >= 45:
        return "high"
    if analytical_ids and snapshot.risk_score >= 35:
        return "medium"
    return "low"


def _signal_structure(session: Session, analytical_ids: list[int]) -> str:
    engines = _engines(session, analytical_ids)
    if "technical" in engines and len(engines) == 1:
        return "technical_led_early_formation"
    if {"fundamental", "catalyst"}.issubset(engines) and "technical" not in engines:
        return "fundamental_led_early_formation"
    if len(engines) >= 2:
        return "confirmation"
    if engines:
        return "single_signal"
    return "no_signal"


def _evidence_independence(session: Session, analytical_ids: list[int]) -> str:
    groups = {
        row.dependency_group
        for row in session.query(AnalyticalSignal).filter(AnalyticalSignal.id.in_(analytical_ids)).all()
        if row.dependency_group
    }
    if len(groups) >= 3:
        return "high"
    if len(groups) == 2:
        return "medium"
    if len(groups) == 1:
        return "single_source"
    return "none"


def _engines(session: Session, analytical_ids: list[int]) -> set[str]:
    if not analytical_ids:
        return set()
    return {
        row.engine
        for row in session.query(AnalyticalSignal.engine).filter(AnalyticalSignal.id.in_(analytical_ids)).all()
    }


def _dominant_drivers(components: dict[str, Any], signals: list[Signal]) -> list[str]:
    drivers = []
    for key in ("announcement", "resource", "commodity", "risk"):
        comp = components.get(key)
        if isinstance(comp, dict):
            value = comp.get("value") or comp.get("best") or comp.get("instrument")
            if value is not None:
                drivers.append(f"{key}: {value}")
    drivers.extend(signal.reason for signal in signals[:3])
    return drivers[:6]


def _overheating_risk(snapshot: ScoreSnapshot, signals: list[Signal]) -> str:
    has_technical = any(signal.signal_type in TECHNICAL_SIGNAL_TYPES for signal in signals)
    if has_technical and snapshot.announcement_score < 20 and snapshot.resource_score <= 50:
        return "high"
    if has_technical and snapshot.risk_score < 45:
        return "medium"
    return "low"
