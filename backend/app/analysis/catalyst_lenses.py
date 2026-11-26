"""The seven lenses the P05 Catalyst Agent reads a project's progress through.

Pure functions over P03 events. Nothing here opens a database, and nothing
here may reach price, volume, a technical indicator or another agent's
conclusion -- the PRD forbids the Catalyst Agent all four, and for a rules
engine the import graph is what enforces that. A test asserts it.

Two rules shape most of what follows. A positive announcement is not
automatically a positive catalyst: only a change to project progress,
development risk, schedule or dependency earns a signal. And silence is not
failure -- a milestone whose window has passed without news is overdue and
worth saying so, never "failed".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from .lens_reading import (
    INSUFFICIENT_DATA,
    NO_MATERIAL_CHANGE,
    REPORTED,
    LensReading,
)


@dataclass(frozen=True)
class ProjectEvent:
    """One P03 event, reduced to what progress analysis needs."""

    event_type: str
    event_status: str
    family: str
    occurred_on: date | None
    reported_on: date | None
    revision_tags: tuple[str, ...] = ()
    event_id: int | None = None

    @property
    def dated(self) -> date | None:
        return self.occurred_on or self.reported_on


# Stages are an ordering of evidence, not a track a project must run along.
# Miners routinely run drilling, metallurgy and permitting side by side, so
# "stage" here means the furthest point with evidence behind it.
STAGE_ORDER = (
    "exploration",
    "resource_definition",
    "study",
    "permitting",
    "development_decision",
    "construction",
    "production",
)

_FAMILY_STAGE = {"F01": "exploration", "F02": "resource_definition", "F03": "study",
                 "F04": "study", "F05": "permitting"}

_EVENT_STAGE = {
    "FID Target": "development_decision",
    "Final Investment Decision": "development_decision",
    "First Ore Timing": "construction",
    "Construction Commencement": "construction",
    "Commissioning": "construction",
    "First Production": "production",
    "Ramp-up": "production",
}

# The event that normally follows each stage, used to name what to watch for.
_NEXT_EVENT = {
    "exploration": "首次资源量估算（Maiden MRE）",
    "resource_definition": "初步经济评估或预可研（Scoping / PFS）",
    "study": "最终可行性研究完成与采矿权审批",
    "permitting": "最终投资决定（FID）",
    "development_decision": "建设开工",
    "construction": "投料试车与首次产出",
    "production": "产能爬坡与稳定运营",
}

# P03 families, named the way the fusion layer already names announcement
# events. A drill result driving both this engine and the fundamental one has
# to land in the same dependency group, or P06 reads one announcement as two
# independent confirmations.
P3_FAMILY_TO_EVENT_FAMILY = {
    "F01": "exploration", "F02": "resource", "F03": "development",
    "F04": "development", "F05": "development", "F06": "funding",
    "F07": "commercial", "F08": "financial",
}


def trigger_families(events: Sequence[ProjectEvent]) -> list[str]:
    """Which announcement families a reading was triggered by."""
    return sorted({P3_FAMILY_TO_EVENT_FAMILY.get(e.family, "other") for e in events})


_DERISKING_POSITIVE = {"Environmental Approval Status", "Groundwater Licence Status",
                       "Land Access / Native Title", "Joint Venture", "Offtake Agreement",
                       "Strategic Investment", "Transaction Completion"}
_FUNDING_FAMILY = "F06"
_RECENT_DAYS = 120


def _recent(events: Sequence[ProjectEvent], as_of: date, days: int = _RECENT_DAYS):
    return [e for e in events if e.dated and 0 <= (as_of - e.dated).days <= days]


def _none(lens: str, note: str) -> LensReading:
    return LensReading(lens=lens, status=INSUFFICIENT_DATA, summary=note,
                       evidence={"events_available": 0})


def _stage_of(event: ProjectEvent) -> str | None:
    return _EVENT_STAGE.get(event.event_type) or _FAMILY_STAGE.get(event.family)


def current_stage(events: Sequence[ProjectEvent]) -> str | None:
    reached = [_stage_of(e) for e in events]
    known = [s for s in reached if s in STAGE_ORDER]
    return max(known, key=STAGE_ORDER.index) if known else None


def lifecycle(events: Sequence[ProjectEvent], as_of: date) -> LensReading:
    """Furthest stage with evidence, and whether it moved."""
    if not events:
        return _none("lifecycle", "没有项目事件，无法判断生命周期阶段。")
    stage = current_stage(events)
    if stage is None:
        return LensReading("lifecycle", NO_MATERIAL_CHANGE, summary="事件未指向任何生命周期阶段。",
                           evidence={"stage": None})
    older = [e for e in events if e.dated and (as_of - e.dated).days > _RECENT_DAYS]
    previous = current_stage(older)
    advancing = [e for e in _recent(events, as_of) if _stage_of(e) == stage]
    evidence = {"stage": stage, "previous_stage": previous,
                "stage_index": STAGE_ORDER.index(stage),
                "trigger_families": trigger_families(advancing)}

    if previous and STAGE_ORDER.index(stage) > STAGE_ORDER.index(previous):
        return LensReading("lifecycle", REPORTED, "positive", "strong", "medium", "structural",
                           f"生命周期阶段由 {previous} 推进至 {stage}。",
                           (f"出现 {stage} 阶段的证据",),
                           ("阶段推进不等于价值兑现，后续仍可能倒退或停滞",), evidence)
    return LensReading("lifecycle", NO_MATERIAL_CHANGE, "neutral", "minor", "medium", "structural",
                       f"当前阶段 {stage}，近 {_RECENT_DAYS} 天内未见阶段推进。", evidence=evidence)


def milestone(events: Sequence[ProjectEvent], as_of: date) -> LensReading:
    """Milestones completed, and commitments withdrawn."""
    if not events:
        return _none("milestone", "没有项目事件，无法判断里程碑。")
    recent = _recent(events, as_of)
    done = [e for e in recent if e.event_status == "completed"]
    withdrawn = [e for e in recent if "Withdrawal" in e.revision_tags]
    evidence = {"completed": [e.event_type for e in done],
                "withdrawn": [e.event_type for e in withdrawn],
                "trigger_families": trigger_families(done + withdrawn),
                "window_days": _RECENT_DAYS}

    if withdrawn:
        return LensReading("milestone", REPORTED, "negative", "strong", "high", "medium",
                           f"{len(withdrawn)} 项已披露安排被撤回：{'、'.join(e.event_type for e in withdrawn)}。",
                           ("公司撤回了此前的承诺",),
                           ("撤回原因可能是替换方案，未必是项目失败",), evidence)
    if done:
        return LensReading("milestone", REPORTED, "positive",
                           "strong" if len(done) > 1 else "moderate", "high", "medium",
                           f"近 {_RECENT_DAYS} 天完成 {len(done)} 项里程碑："
                           f"{'、'.join(e.event_type for e in done)}。",
                           tuple(f"{e.event_type} 已完成" for e in done),
                           ("里程碑完成是事实，其经济意义由基本面另行判断",), evidence)
    return LensReading("milestone", NO_MATERIAL_CHANGE, "neutral", "minor", "medium", "medium",
                       f"近 {_RECENT_DAYS} 天没有里程碑完成或被撤回的记录。", evidence=evidence)


def derisking(events: Sequence[ProjectEvent], as_of: date) -> LensReading:
    """Approvals, partners and money in: the things that take risk off a project."""
    if not events:
        return _none("derisking", "没有项目事件，无法判断去风险进展。")
    recent = _recent(events, as_of)
    approvals = [e for e in recent if e.event_type in _DERISKING_POSITIVE]
    funds_in = [e for e in recent
                if e.family == _FUNDING_FAMILY and e.event_status in {"funds_received", "completed"}]
    proposed_only = [e for e in recent
                     if e.family == _FUNDING_FAMILY and e.event_status in {"proposed", "planned"}]
    evidence = {"approvals": [e.event_type for e in approvals],
                "funding_received": [e.event_type for e in funds_in],
                "funding_proposed_only": [e.event_type for e in proposed_only],
                "trigger_families": trigger_families(approvals + funds_in + proposed_only)}

    if approvals or funds_in:
        count = len(approvals) + len(funds_in)
        return LensReading("derisking", REPORTED, "positive",
                           "strong" if count > 1 else "moderate", "high", "long",
                           f"近 {_RECENT_DAYS} 天有 {count} 项去风险进展："
                           f"{'、'.join(e.event_type for e in approvals + funds_in)}。",
                           tuple(e.event_type for e in approvals + funds_in),
                           ("单项审批或融资到位不解除全部开发风险",), evidence)
    if proposed_only:
        # a proposal is an intention; the PRD requires the two be kept apart
        return LensReading("derisking", REPORTED, "neutral", "minor", "medium", "short",
                           f"有 {len(proposed_only)} 项融资仍处于计划或提议状态，尚未到账。",
                           ("已披露融资计划",),
                           ("计划不等于完成，到账前不构成去风险",), evidence)
    return LensReading("derisking", NO_MATERIAL_CHANGE, "neutral", "minor", "medium", "long",
                       f"近 {_RECENT_DAYS} 天未见审批、合作或资金到位的去风险事件。", evidence=evidence)


def bottleneck(events: Sequence[ProjectEvent], as_of: date) -> LensReading:
    """What the project has reached, and what it still has not."""
    if not events:
        return _none("bottleneck", "没有项目事件，无法判断开发瓶颈。")
    stage = current_stage(events)
    if stage is None:
        return LensReading("bottleneck", NO_MATERIAL_CHANGE, summary="阶段未知，瓶颈无法定位。",
                           evidence={"stage": None})
    seen = {e.event_type for e in events}
    families = {e.family for e in events}
    missing: list[str] = []
    if STAGE_ORDER.index(stage) >= STAGE_ORDER.index("study"):
        if "F05" not in families:
            missing.append("尚无审批类事件（采矿权 / 环评）")
        if not any("FID" in t for t in seen):
            missing.append("尚未出现最终投资决定（FID）")
    if STAGE_ORDER.index(stage) >= STAGE_ORDER.index("permitting") and _FUNDING_FAMILY not in families:
        missing.append("尚无融资类事件")
    evidence = {"stage": stage, "unresolved": missing}

    if missing:
        return LensReading("bottleneck", REPORTED, "negative",
                           "moderate" if len(missing) == 1 else "strong", "medium", "long",
                           f"处于 {stage} 阶段，但仍有 {len(missing)} 项前置条件未见证据："
                           f"{'；'.join(missing)}。",
                           tuple(missing),
                           ("未见证据不等于不存在——可能只是公告未被采集",), evidence)
    return LensReading("bottleneck", NO_MATERIAL_CHANGE, "neutral", "minor", "medium", "long",
                       f"处于 {stage} 阶段，已知前置条件均有证据。", evidence=evidence)


def timeline(events: Sequence[ProjectEvent], as_of: date) -> LensReading:
    """Schedules the company has changed since it first stated them."""
    if not events:
        return _none("timeline", "没有项目事件，无法判断时间进程。")
    recent = _recent(events, as_of)
    revised = [e for e in recent if {"Revised", "Amended"} & set(e.revision_tags)]
    evidence = {"revised": [e.event_type for e in revised],
                "trigger_families": trigger_families(revised),
                "window_days": _RECENT_DAYS}

    if revised:
        return LensReading("timeline", REPORTED, "negative",
                           "strong" if len(revised) > 1 else "moderate", "medium", "medium",
                           f"近 {_RECENT_DAYS} 天有 {len(revised)} 项安排被修订："
                           f"{'、'.join(e.event_type for e in revised)}。",
                           ("公司修订了此前披露的计划",),
                           ("修订方向可能是提前，也可能是推迟，需看原文",), evidence)
    return LensReading("timeline", NO_MATERIAL_CHANGE, "neutral", "minor", "medium", "medium",
                       f"近 {_RECENT_DAYS} 天未见时间安排修订。", evidence=evidence)


def forward(events: Sequence[ProjectEvent], as_of: date) -> LensReading:
    """The next thing worth waiting for, and how long the wait has been."""
    if not events:
        return _none("forward", "没有项目事件，无法给出未来催化。")
    stage = current_stage(events)
    if stage is None:
        return LensReading("forward", NO_MATERIAL_CHANGE, summary="阶段未知，无法指出下一事件。",
                           evidence={"stage": None})
    expected = _NEXT_EVENT[stage]
    dated = [e.dated for e in events if e.dated]
    quiet_days = (as_of - max(dated)).days if dated else None
    evidence = {"stage": stage, "next_expected_event": expected,
                "days_since_last_event": quiet_days,
                # the PRD forbids inventing a probability where evidence is absent
                "probability": "not_assessed"}

    if quiet_days is not None and quiet_days > 90:
        return LensReading("forward", REPORTED, "neutral", "moderate", "low", "medium",
                           f"下一关键事件应为「{expected}」，但已有 {quiet_days} 天无项目进展公告。",
                           (f"等待中：{expected}",),
                           ("长期无公告只说明进展未披露，不能据此判定里程碑失败",), evidence)
    return LensReading("forward", NO_MATERIAL_CHANGE, "neutral", "minor", "medium", "medium",
                       f"下一关键事件应为「{expected}」，项目披露节奏正常"
                       f"（距上次事件 {quiet_days} 天）。" if quiet_days is not None
                       else f"下一关键事件应为「{expected}」。", evidence=evidence)


def dependency(events: Sequence[ProjectEvent], as_of: date) -> LensReading:
    """Commitments made but not yet discharged."""
    if not events:
        return _none("dependency", "没有项目事件，无法判断依赖关系。")
    open_items = [e for e in events
                  if e.event_status in {"proposed", "planned", "pending", "application", "submitted"}
                  and e.dated and (as_of - e.dated).days > 180]
    evidence = {"stale_open_items": [
        {"event": e.event_type, "status": e.event_status,
         "days_open": (as_of - e.dated).days} for e in open_items]}

    if open_items:
        oldest = max(open_items, key=lambda e: (as_of - e.dated).days)
        return LensReading("dependency", REPORTED, "negative", "moderate", "low", "medium",
                           f"{len(open_items)} 项事项披露后超过 180 天仍未见结论，"
                           f"最久的是 {oldest.event_type}（{(as_of - oldest.dated).days} 天）。",
                           ("存在长期未结的前置事项",),
                           ("未见结论可能是公告未采集，也可能确实停滞；不等于已失败",), evidence)
    return LensReading("dependency", NO_MATERIAL_CHANGE, "neutral", "minor", "medium", "medium",
                       "未见超过 180 天仍未结的前置事项。", evidence=evidence)


LENSES = (lifecycle, milestone, derisking, bottleneck, timeline, forward, dependency)


def read_all(events: Sequence[ProjectEvent], as_of: date) -> list[LensReading]:
    """Every lens, in the order the PRD lists them."""
    return [lens(events, as_of) for lens in LENSES]
