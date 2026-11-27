"""The P06 narrative: what the engines said, assembled into something readable.

P06 asks for a trader's assessment written at trader-to-trader density, and
that is not what a rules engine can produce. This writes the honest version of
it -- an ordered account of what each engine read, where they agree, where they
pull against each other, and what would change the answer -- and labels itself
as a synthesis so nobody mistakes it for the judgement the PRD describes.

The order follows the PRD's own list, because the sequence is the argument:
conclusion first, then the evidence for it, then the evidence against, then
what to watch. A reader who stops after one line should still have the part
that matters.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Sequence

from ..models import AnalyticalSignal

STRENGTH_TEXT = {
    "none": "没有任何引擎给出正向读数",
    "weak": "机会强度弱",
    "moderate": "机会强度中等",
    "strong": "机会强度强",
    "exceptional": "机会强度极强",
}

ENGINE_TEXT = {
    "technical": "技术面",
    "catalyst": "项目催化",
    "fundamental": "基本面",
    "sentiment": "市场情绪",
}

INDEPENDENCE_TEXT = {
    "high": "三个以上互相独立的来源",
    "medium": "两个独立来源",
    "single_source": "只有一个来源",
    "none": "没有可计的来源",
}

# How this narrative was produced, stated in the text itself. A reader who
# cannot tell a rules synthesis from a model's judgement cannot weigh it.
PROVENANCE = (
    "以上为规则引擎对各分析引擎读数的结构化综述，不是交易员判断："
    "它不推断行情阶段、不给顶底结论、不提出交易建议。"
)


def _loads(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except (TypeError, ValueError):
        return fallback


def _engine_name(key: str) -> str:
    return ENGINE_TEXT.get(key, key)


def _describe_conflict(entry: str) -> str:
    if entry.startswith("cross_engine_divergence:"):
        body = entry.split(":", 1)[1]
        up, _, down = body.partition("_vs_")
        ups = "、".join(_engine_name(name) for name in up.split("+") if name)
        downs = "、".join(_engine_name(name) for name in down.split("+") if name)
        return f"{ups}看多，而{downs}看空"
    if entry.startswith("engine_internal_divergence:"):
        names = "、".join(_engine_name(name) for name in entry.split(":", 1)[1].split(","))
        return f"{names}引擎内部不同视角方向相反"
    return entry


def build_fusion_narrative(
    *,
    fusion_date: date,
    opportunity_strength: str,
    confidence: str | None,
    signal_structure: str | None,
    evidence_independence: str | None,
    conflicts: Sequence[str],
    blocking_conditions: Sequence[str],
    strength_basis: dict[str, Any] | None,
    signals: Sequence[AnalyticalSignal],
) -> str:
    basis = strength_basis or {}
    lines: list[str] = [f"综合研判（截至 {fusion_date}）"]

    # 1. the conclusion, and what it rests on
    headline = STRENGTH_TEXT.get(opportunity_strength, opportunity_strength)
    independence = INDEPENDENCE_TEXT.get(evidence_independence or "none", evidence_independence)
    lines.append(f"结论：{headline}；证据来自{independence}，置信度 {confidence or '未评'}。")

    if blocking_conditions:
        lines.append("存在阻断条件，在解除之前不构成可行动的机会：" + "；".join(blocking_conditions) + "。")

    # 2. what each engine actually said, strongest reading first
    positive = [s for s in signals if s.direction == "positive"]
    negative = [s for s in signals if s.direction == "negative"]
    neutral = [s for s in signals if s.direction == "neutral"]

    if positive:
        lines.append("支持的读数：")
        lines.extend(_bullets(positive))
    if negative:
        lines.append("反对的读数：")
        lines.extend(_bullets(negative))
    if neutral:
        names = "、".join(sorted({_lens_of(s) for s in neutral}))
        lines.append(
            f"另有 {len(neutral)} 条中性读数（{names}）不计入方向——"
            "被回测证伪的规则照常记录，但不能充当确认。"
        )

    # 3. the disagreement, which is the finding rather than an inconvenience
    if conflicts:
        lines.append("分歧：")
        lines.extend(f"  · {_describe_conflict(entry)}" for entry in conflicts)
        if basis.get("cap_applied"):
            lines.append(
                "  机会强度已因此被压低——两个引擎指向相反时，诚实的读法是不确定，不是信心。"
            )

    # 4. what would move the answer
    lines.append("要改变这个结论，需要：")
    lines.extend(_what_would_change(opportunity_strength, basis, bool(conflicts)))

    lines.append(PROVENANCE)
    return "\n".join(lines)


def _lens_of(signal: AnalyticalSignal) -> str:
    metadata = _loads(signal.metadata_json, {})
    return str(metadata.get("lens") or signal.engine)


def _bullets(signals: Sequence[AnalyticalSignal]) -> list[str]:
    ranked = sorted(signals, key=lambda s: s.magnitude or 0.0, reverse=True)
    out = []
    for signal in ranked:
        metadata = _loads(signal.metadata_json, {})
        summary = metadata.get("summary") or (_loads(signal.key_drivers_json, []) or [""])[0]
        out.append(f"  · {_engine_name(signal.engine)}·{_lens_of(signal)}：{summary}")
    return out


def _what_would_change(strength: str, basis: dict[str, Any], has_conflict: bool) -> list[str]:
    """Named conditions, not a hedge.

    "Watch for developments" is worth nothing; a reader needs to know which
    observation would actually move this from where it sits.
    """
    needs: list[str] = []
    positive_sources = int(basis.get("positive_sources") or 0)
    negative_sources = int(basis.get("negative_sources") or 0)

    if positive_sources == 0:
        needs.append("  · 任意一个引擎给出正向读数——目前一个都没有")
    elif positive_sources == 1:
        needs.append("  · 第二个独立来源的正向读数；单一来源无论多强都只能算弱")
    if has_conflict and negative_sources:
        needs.append(f"  · 当前 {negative_sources} 个负向来源中至少一个转向或失效")
    if strength in {"strong", "exceptional"}:
        needs.append("  · 人工确认后方可进入 Decision Ready——引擎按设计不会自己晋升")
    if not needs:
        needs.append("  · 下一份公告或下一个交易日的价量变化")
    return needs
