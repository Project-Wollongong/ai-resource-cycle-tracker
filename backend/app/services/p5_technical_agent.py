"""P05 Technical Analysis Agent — the first engine that does its own analysis.

Everything else writing P5 rows today is `p5_p6_adapter`, which reshapes the
Cycle Score into P5-shaped records. This reads the price history itself,
through the seven lenses the PRD names, and owes nothing to the other engines:
it never sees an announcement, a score or another agent's conclusion. That
isolation is what makes a later agreement between engines worth anything —
two readings of the same input are one opinion stated twice.

The agent emits 0-N signals. A lens with nothing material to say produces no
signal, as the PRD requires, but still appears in the narrative, so "we looked
and saw nothing" stays distinguishable from "we did not look".
"""

from __future__ import annotations

import json
from datetime import date
from typing import Sequence

from sqlalchemy.orm import Session

from ..analysis.indicators import DailyBar
from ..analysis.technical_lenses import (
    INSUFFICIENT_DATA,
    REPORTED,
    LensReading,
    read_all,
)
from ..models import AnalyticalSignal

LOGIC_VERSION = "technical_seven_lens_v1"
ENGINE = "technical"

# The PRD states magnitude and confidence as words. The column is a float, so
# the word is kept in metadata and these are what the number means.
_MAGNITUDE = {"minor": 0.25, "moderate": 0.5, "strong": 0.75, "exceptional": 1.0}
_CONFIDENCE = {"low": 0.4, "medium": 0.65, "high": 0.85}


def analyse(session: Session, stock_id: int, bars: Sequence[DailyBar]) -> list[AnalyticalSignal]:
    """Run the seven lenses for the latest bar and persist what they found."""
    if not bars:
        return []
    as_of = bars[-1].date
    readings = read_all(bars)
    narrative = build_narrative(readings, as_of)

    written: list[AnalyticalSignal] = []
    for reading in readings:
        if reading.status != REPORTED:
            continue
        written.append(_upsert(session, stock_id, as_of, reading, narrative))
    return written


def build_narrative(readings: Sequence[LensReading], as_of: date) -> str:
    """One plain-language pass over all seven lenses, including the silent ones.

    Not a trader's prose — a rules engine has no business pretending to that —
    but an honest record of what each lens saw, so a reading can be argued with.
    """
    lines = [f"技术面七视角（截至 {as_of}）"]
    for reading in readings:
        if reading.status == REPORTED:
            mark = {"positive": "偏多", "negative": "偏空", "neutral": "中性"}[reading.direction]
            lines.append(f"· {reading.lens}｜{mark}·{reading.magnitude}：{reading.summary}")
            for risk in reading.risks:
                lines.append(f"    留意：{risk}")
        elif reading.status == INSUFFICIENT_DATA:
            lines.append(f"· {reading.lens}｜证据不足：{reading.summary}")
        else:
            lines.append(f"· {reading.lens}｜无实质变化：{reading.summary}")

    material = [r for r in readings if r.status == REPORTED]
    if not material:
        lines.append("结论：七个视角均无实质变化，本日不产生技术信号。")
    else:
        longs = sum(1 for r in material if r.direction == "positive")
        shorts = sum(1 for r in material if r.direction == "negative")
        if longs and shorts:
            lines.append(
                f"结论：{len(material)} 个视角有实质读数，其中 {longs} 项偏多、{shorts} 项偏空，"
                "内部存在分歧，不宜当作单一方向的确认。"
            )
        else:
            side = "偏多" if longs else "偏空"
            lines.append(f"结论：{len(material)} 个视角有实质读数，方向一致{side}。")
    return "\n".join(lines)


def _upsert(
    session: Session,
    stock_id: int,
    as_of: date,
    reading: LensReading,
    narrative: str,
) -> AnalyticalSignal:
    # the lens is the event: one reading per lens per day, re-runnable
    source_event_id = f"technical_lens:{reading.lens}:{as_of.isoformat()}"
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
    # Every lens reads the same price series, so the seven of them are one
    # source, not seven. Sharing a dependency group keeps a day of agreeing
    # lenses from being counted downstream as independent confirmation.
    row.dependency_group = f"price_action:{as_of.isoformat()}"
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
