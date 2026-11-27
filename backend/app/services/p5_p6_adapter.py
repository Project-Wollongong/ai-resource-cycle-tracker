"""Compatibility adapter from the current radar model to Beta02 P5/P6 records.

This keeps ScoreSnapshot/Signal as the live product contract while writing
append-only-shaped P5 analytical signals and one P6 fusion record per stock/day.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from ..models import AnalyticalSignal, Announcement, FusionRecord, ScoreSnapshot, Signal, Stock
from .attention_state import update_attention_state_from_fusion
from .p6_narrative import build_fusion_narrative
from .trade_decision import write_trade_decision_from_state

P5_LOGIC_VERSION = "cycle_score_adapter_v1"
P6_RULE_VERSION = "fusion_adapter_v1"

TECHNICAL_SIGNAL_TYPES = {"REL_VOL_SPIKE", "BREAKOUT_60D", "BREAKOUT_252D"}


def write_p5_p6_compat_records(
    session: Session,
    stock: Stock,
    snapshot: ScoreSnapshot,
    signals: list[Signal],
    engine_signal_ids: list[int] | None = None,
) -> FusionRecord:
    """`engine_signal_ids` are rows a real P05 engine wrote for itself. The
    technical readings arrive that way now; this function no longer reshapes
    price signals into a P5 row, it only folds in what the engine produced."""
    components = _loads(snapshot.components, {})
    analytical_ids: list[int] = list(engine_signal_ids or [])

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
                dependency_group=_dependency_group_from_resource(session, resource, snapshot.date),
                evidence_ids=[],
                feature_ids=[],
                key_drivers=_resource_drivers(resource),
                key_risks=[],
                metadata={"score": snapshot.resource_score, "component": resource},
            ).id
        )

    # The catalyst engine used to be the announcement sub-score wearing a P5
    # label. An announcement score is not a reading of project progress, which
    # is what P05 asks the Catalyst Agent for, so that engine is now its own
    # and writes its own rows; nothing is projected here.

    risk = components.get("risk") if isinstance(components.get("risk"), dict) else {}
    blocking_conditions = _blocking_conditions(snapshot.risk_score, risk)
    opportunity_strength, strength_basis = _opportunity_strength(session, analytical_ids)
    conflicts = _conflicts(session, analytical_ids, snapshot, signals, strength_basis)
    official_result = "blocked" if blocking_conditions else opportunity_strength

    signal_rows = (
        session.query(AnalyticalSignal).filter(AnalyticalSignal.id.in_(analytical_ids)).all()
        if analytical_ids else []
    )
    narrative = build_fusion_narrative(
        fusion_date=snapshot.date,
        opportunity_strength=opportunity_strength,
        confidence=_fusion_confidence(session, analytical_ids, snapshot),
        signal_structure=_signal_structure(session, analytical_ids),
        evidence_independence=_evidence_independence(session, analytical_ids),
        conflicts=conflicts,
        blocking_conditions=blocking_conditions,
        strength_basis=strength_basis,
        signals=signal_rows,
    )

    fusion = _upsert_fusion_record(
        session,
        stock_id=stock.id,
        fusion_date=snapshot.date,
        opportunity_strength=opportunity_strength,
        confidence=_fusion_confidence(session, analytical_ids, snapshot),
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
        narrative=narrative,
        metadata={
            "score_snapshot_id": snapshot.id,
            "cycle_score": snapshot.cycle_score,
            "label": snapshot.label,
            # what the engines said, and what the old lookup would have said —
            # kept side by side so the change in verdict stays auditable
            "strength_basis": strength_basis,
            "cycle_score_strength": _strength_from_score(snapshot.cycle_score),
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
    narrative: str | None = None,
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
    row.narrative = narrative
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


# Beta02 8.2: one event is one piece of evidence, however many documents it
# produces. Companies routinely file several documents for a single event
# (annual report + Appendix 4G + MD&A; an acquisition + its investor
# presentation), so keying the dependency group on the document id reads one
# event as several independent confirmations. Key on (day, event family)
# instead, while source_event_id keeps the document id for traceability.
ANN_TYPE_TO_EVENT_FAMILY = {
    "DRILL_RESULTS": "exploration",
    "DRILLING_UPDATE": "exploration",
    "JORC_MRE": "resource",
    "STUDY": "development",
    "OFFTAKE": "commercial",
    "JV_FARMIN": "commercial",
    "PLACEMENT": "funding",
    "SUBSTANTIAL_HOLDER": "ownership",
    "TRADING_HALT": "administrative",
    "QUARTERLY": "financial",
    "OTHER": "other",
}


def _event_family(ann_type: Any) -> str:
    if not isinstance(ann_type, str):
        return "other"
    return ANN_TYPE_TO_EVENT_FAMILY.get(ann_type.upper(), "other")


def _event_dependency_group(ann_type: Any, signal_date: date) -> str:
    return f"announcement_event:{signal_date.isoformat()}:{_event_family(ann_type)}"


def _first_dict(container: dict[str, Any], key: str) -> dict[str, Any] | None:
    items = container.get(key)
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    return None


def _ann_type_for(session: Session, ann_id: Any, declared: Any) -> Any:
    """Prefer the type carried in the component; fall back to the stored
    announcement so snapshots written before the field existed still group with
    the catalyst signal from the same event instead of splitting off."""
    if isinstance(declared, str) and declared:
        return declared
    if not ann_id:
        return None
    return (
        session.query(Announcement.ann_type)
        .filter(Announcement.ann_id == ann_id)
        .limit(1)
        .scalar()
    )


def _dependency_group_from_resource(
    session: Session, resource: dict[str, Any], signal_date: date
) -> str:
    first = _first_dict(resource, "items")
    if first is not None and first.get("ann_id"):
        ann_type = _ann_type_for(session, first.get("ann_id"), first.get("type"))
        return _event_dependency_group(ann_type, signal_date)
    source = resource.get("source") or "resource_component"
    return f"{source}:{signal_date.isoformat()}"


def _dependency_group_from_announcement(
    session: Session, announcement: dict[str, Any], signal_date: date
) -> str:
    first = _first_dict(announcement, "announcements")
    if first is not None and first.get("ann_id"):
        ann_type = _ann_type_for(session, first.get("ann_id"), first.get("type"))
        return _event_dependency_group(ann_type, signal_date)
    return f"announcement_cluster:{signal_date.isoformat()}"


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


def _conflicts(
    session: Session, analytical_ids: list[int], snapshot: ScoreSnapshot, signals: list[Signal],
    strength_basis: dict,
) -> list[str]:
    """Disagreements worth a reader's attention, engines first.

    Engine disagreement was invisible here: the strength was being capped for
    it while the record reported no conflict, so a project advancing against a
    falling share price — the divergence the architecture names as a state in
    its own right — was flattened into a quiet "weak" with no explanation.
    """
    found: list[str] = []
    up, down = strength_basis.get("engines_positive", []), strength_basis.get("engines_negative", [])
    if up and down:
        shared = sorted(set(up) & set(down))
        if shared:
            found.append(f"engine_internal_divergence:{','.join(shared)}")
        crossing = sorted(set(up) ^ set(down))
        if crossing:
            found.append(f"cross_engine_divergence:{'+'.join(up)}_vs_{'+'.join(down)}")
    if not analytical_ids and snapshot.cycle_score >= 60:
        found.append("cycle_score_without_p5_signal_adapter_support")
    if snapshot.risk_score < 40 and any(s.signal_type in TECHNICAL_SIGNAL_TYPES for s in signals):
        found.append("technical_strength_with_elevated_risk")
    return found


def _opportunity_strength(session: Session, analytical_ids: list[int]) -> tuple[str, dict]:
    """How strong a case the engines actually made, from the engines.

    This used to be a lookup on the Cycle Score, which meant the P05 engines
    could not influence the one field that matters: they shaped the texture of
    a fusion record -- its confidence, structure and independence -- while the
    verdict came from the old chain regardless. Two engines that read their own
    data were decoration.

    Four rules, each one a thing the old lookup could not express:

    Only positive readings build strength. Strength feeds the attention state,
    which feeds a buy decision, so a well-evidenced case for decline must not
    arrive there as an opportunity. It belongs in conflicts instead.

    Neutral readings count for nothing, which is how a rule the backtest
    falsified stays unable to manufacture agreement.

    Sources are counted, not signals. Seven technical lenses agreeing on one
    day of price action are one source; the dependency group is what says so.

    Disagreement is not strength. A bull case contradicted by an equally
    well-sourced bear case is capped, because the honest reading of two
    opposing engines is uncertainty, not conviction.
    """
    rows = (
        session.query(AnalyticalSignal)
        .filter(AnalyticalSignal.id.in_(analytical_ids))
        .all()
        if analytical_ids else []
    )
    positive = [row for row in rows if row.direction == "positive"]
    negative = [row for row in rows if row.direction == "negative"]
    up_sources = {row.dependency_group for row in positive if row.dependency_group}
    down_sources = {row.dependency_group for row in negative if row.dependency_group}
    top = max((row.magnitude or 0.0) for row in positive) if positive else 0.0

    evidence = {
        "positive_sources": len(up_sources),
        "negative_sources": len(down_sources),
        "strongest_positive_magnitude": top,
        "engines_positive": sorted({row.engine for row in positive}),
        "engines_negative": sorted({row.engine for row in negative}),
    }

    if not positive:
        return "none", {**evidence, "reason": "no positive reading from any engine"}

    if len(up_sources) >= 3 and top >= 0.75:
        strength = "exceptional"
    elif len(up_sources) >= 2 and top >= 0.5:
        strength = "strong"
    elif len(up_sources) >= 2:
        strength = "moderate"
    else:
        strength = "weak"

    capped = None
    if len(down_sources) >= len(up_sources):
        capped, strength = "contradicted_by_equally_sourced_negative", _cap(strength, "weak")
    elif negative:
        capped, strength = "contradicted_by_a_negative_reading", _cap(strength, "moderate")
    return strength, {**evidence, "cap_applied": capped}


_STRENGTH_ORDER = ("none", "weak", "moderate", "strong", "exceptional")


def _cap(strength: str, ceiling: str) -> str:
    return min(strength, ceiling, key=_STRENGTH_ORDER.index)


def _strength_from_score(score: float) -> str:
    """The lookup the verdict used to come from. Retained only so a record can
    show what the old chain would have concluded."""
    for threshold, name in ((85, "exceptional"), (75, "strong"), (60, "moderate"), (45, "weak")):
        if score >= threshold:
            return name
    return "none"


def _fusion_confidence(session: Session, analytical_ids: list[int], snapshot: ScoreSnapshot) -> str:
    """Confidence counts independent sources, not rows.

    Counting rows let one engine's seven lenses, all reading the same day of
    price action, present themselves as three independent agreements.
    """
    sources = {
        row.dependency_group
        for row in session.query(AnalyticalSignal).filter(AnalyticalSignal.id.in_(analytical_ids)).all()
        if row.dependency_group
    } if analytical_ids else set()
    if len(sources) >= 3 and snapshot.risk_score >= 45:
        return "high"
    if sources and snapshot.risk_score >= 35:
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
    """Engines carrying directional evidence. Neutral signals are recorded but
    do not make their engine count toward confirmation — a rule the backtest
    says is not predictive must not manufacture a second opinion."""
    if not analytical_ids:
        return set()
    return {
        row.engine
        for row in session.query(AnalyticalSignal.engine, AnalyticalSignal.direction)
        .filter(AnalyticalSignal.id.in_(analytical_ids))
        .all()
        if row.direction != "neutral"
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
