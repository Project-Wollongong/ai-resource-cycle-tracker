"""P05 Catalyst Analysis Agent — project progress, read from P03 events alone.

The PRD gives this agent a narrow door: entity data, project events, derived
features, original evidence and its own history. Price, volume, technical
indicators and every other agent's conclusions are forbidden outright, and for
a rules engine the import graph is what enforces that. A test asserts it.

It runs every day whether or not an announcement arrived, because the absence
of news is itself worth re-reading — a milestone whose window has passed is
overdue. It is never a failure: the PRD says so explicitly, and so does the
forward lens.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Sequence

from sqlalchemy.orm import Session

from ..analysis.catalyst_lenses import (
    REPORTED,
    LensReading,
    ProjectEvent,
    current_stage,
    read_all,
)
from ..analysis.lens_reading import INSUFFICIENT_DATA
from ..models import AnalyticalSignal, ForwardCatalystMap, P3Event, P3ParseRun

LOGIC_VERSION = "catalyst_seven_lens_v1"
ENGINE = "catalyst"
LIVE_RUNS = ("parsed", "partial", "review_needed")

_MAGNITUDE = {"minor": 0.25, "moderate": 0.5, "strong": 0.75, "exceptional": 1.0}
_CONFIDENCE = {"low": 0.4, "medium": 0.65, "high": 0.85}


def load_events(session: Session, stock_id: int) -> list[ProjectEvent]:
    """Live P03 events for one stock. Superseded parse runs are excluded, so a
    figure that a corrected re-parse replaced cannot come back as progress."""
    rows = (
        session.query(P3Event)
        .join(P3ParseRun, P3ParseRun.id == P3Event.parse_run_id)
        .filter(P3Event.stock_id == stock_id, P3ParseRun.status.in_(LIVE_RUNS))
        .order_by(P3Event.occurred_on, P3Event.id)
        .all()
    )
    events = []
    for row in rows:
        try:
            tags = tuple(json.loads(row.revision_tags_json or "[]"))
        except json.JSONDecodeError:
            tags = ()
        events.append(
            ProjectEvent(
                event_type=row.event_type or "",
                event_status=row.event_status or "",
                family=row.primary_family or "",
                occurred_on=row.occurred_on,
                reported_on=row.reported_on.date() if hasattr(row.reported_on, "date")
                else row.reported_on,
                revision_tags=tags,
                event_id=row.id,
            )
        )
    return events


def analyse(session: Session, stock_id: int, as_of: date) -> list[AnalyticalSignal]:
    """Run the seven lenses, persist the signals, and refresh the forward map."""
    events = load_events(session, stock_id)
    readings = read_all(events, as_of)
    narrative = build_narrative(readings, as_of)

    written = [
        _upsert(session, stock_id, as_of, reading, narrative)
        for reading in readings
        if reading.status == REPORTED
    ]
    _refresh_forward_map(session, stock_id, as_of, events, readings)
    return written


def build_narrative(readings: Sequence[LensReading], as_of: date) -> str:
    """One pass over all seven lenses, including the ones with nothing to say."""
    lines = [f"项目催化七视角（截至 {as_of}）"]
    for reading in readings:
        if reading.status == REPORTED:
            mark = {"positive": "推进", "negative": "受阻", "neutral": "中性"}[reading.direction]
            lines.append(f"· {reading.lens}｜{mark}·{reading.magnitude}：{reading.summary}")
            for risk in reading.risks:
                lines.append(f"    留意：{risk}")
        elif reading.status == INSUFFICIENT_DATA:
            lines.append(f"· {reading.lens}｜证据不足：{reading.summary}")
        else:
            lines.append(f"· {reading.lens}｜无实质变化：{reading.summary}")

    material = [r for r in readings if r.status == REPORTED]
    if not material:
        lines.append("结论：七个视角均无实质变化，本日不产生催化信号。")
    else:
        advancing = sum(1 for r in material if r.direction == "positive")
        blocked = sum(1 for r in material if r.direction == "negative")
        if advancing and blocked:
            lines.append(
                f"结论：{len(material)} 个视角有实质读数，{advancing} 项推进、{blocked} 项受阻。"
                "项目可以一边推进一边积累约束，两者并存不矛盾。"
            )
        elif advancing:
            lines.append(f"结论：{len(material)} 个视角有实质读数，方向一致为推进。")
        else:
            lines.append(f"结论：{len(material)} 个视角有实质读数，方向一致为受阻或等待。")
    return "\n".join(lines)


def _upsert(
    session: Session, stock_id: int, as_of: date, reading: LensReading, narrative: str
) -> AnalyticalSignal:
    source_event_id = f"catalyst_lens:{reading.lens}:{as_of.isoformat()}"
    row = (
        session.query(AnalyticalSignal)
        .filter_by(
            stock_id=stock_id,
            signal_date=as_of,
            engine=ENGINE,
            source_event_id=source_event_id,
            logic_version=LOGIC_VERSION,
        )
        .one_or_none()
    )
    if row is None:
        row = AnalyticalSignal(
            stock_id=stock_id,
            signal_date=as_of,
            engine=ENGINE,
            source_event_id=source_event_id,
            logic_version=LOGIC_VERSION,
        )
        session.add(row)

    row.direction = reading.direction
    row.magnitude = _MAGNITUDE[reading.magnitude]
    row.confidence = _CONFIDENCE[reading.confidence]
    row.persistence = reading.persistence
    row.dependency_group = _dependency_group(reading, as_of)
    row.evidence_ids_json = json.dumps([])
    row.feature_ids_json = json.dumps([])
    row.key_drivers_json = json.dumps(list(reading.drivers), ensure_ascii=False)
    row.key_risks_json = json.dumps(list(reading.risks), ensure_ascii=False)
    row.narrative = narrative
    row.metadata_json = json.dumps(
        {
            "lens": reading.lens,
            "magnitude_label": reading.magnitude,
            "confidence_label": reading.confidence,
            "summary": reading.summary,
            "evidence": reading.evidence,
        },
        ensure_ascii=False,
        default=str,
    )
    session.flush()
    return row


def _dependency_group(reading: LensReading, as_of: date) -> str:
    """Which source a reading should be charged to.

    A lens set off by one family of announcement is charged to that
    announcement event, under the same key the fusion layer already uses — so a
    drill result that moves this engine and the fundamental one counts once,
    not twice. A reading drawn from the whole event history, or from several
    families at once, is its own synthesis and gets the standing-state key.
    """
    families = reading.evidence.get("trigger_families") or []
    if len(families) == 1:
        return f"announcement_event:{as_of.isoformat()}:{families[0]}"
    return f"project_progress:{as_of.isoformat()}"


def _refresh_forward_map(
    session: Session,
    stock_id: int,
    as_of: date,
    events: Sequence[ProjectEvent],
    readings: Sequence[LensReading],
) -> ForwardCatalystMap:
    by_lens = {reading.lens: reading for reading in readings}
    forward = by_lens["forward"].evidence
    bottleneck = by_lens["bottleneck"].evidence
    dependency = by_lens["dependency"].evidence
    stage = current_stage(events)

    previous = (
        session.query(ForwardCatalystMap)
        .filter(ForwardCatalystMap.stock_id == stock_id, ForwardCatalystMap.as_of_date < as_of)
        .order_by(ForwardCatalystMap.as_of_date.desc())
        .first()
    )
    if previous is None:
        change = "首次建立 Forward Catalyst Map。"
    elif previous.current_stage != stage:
        change = f"阶段由 {previous.current_stage} 变为 {stage}。"
    elif previous.next_expected_event != forward.get("next_expected_event"):
        change = "下一关键事件已更新。"
    else:
        change = "与上次相比无变化。"

    row = (
        session.query(ForwardCatalystMap)
        .filter_by(stock_id=stock_id, as_of_date=as_of, logic_version=LOGIC_VERSION)
        .one_or_none()
    )
    if row is None:
        row = ForwardCatalystMap(
            stock_id=stock_id, as_of_date=as_of, logic_version=LOGIC_VERSION
        )
        session.add(row)

    row.current_stage = stage
    row.previous_stage = by_lens["lifecycle"].evidence.get("previous_stage")
    row.next_expected_event = forward.get("next_expected_event")
    # The company has not been read as stating a window, so none is claimed.
    row.expected_window = None
    row.importance = "high" if stage in {"permitting", "development_decision"} else "medium"
    row.probability = "not_assessed"
    row.dependencies_json = json.dumps(
        dependency.get("stale_open_items", []), ensure_ascii=False, default=str
    )
    row.bottlenecks_json = json.dumps(bottleneck.get("unresolved", []), ensure_ascii=False)
    row.evidence_basis_json = json.dumps(
        [event.event_type for event in events[-10:]], ensure_ascii=False
    )
    row.change_since_previous = change
    session.flush()
    return row
