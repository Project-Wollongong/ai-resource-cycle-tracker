"""The P06 narrative: an honest synthesis, and honest about being one."""
from datetime import date

from app.models import AnalyticalSignal
from app.services.p6_narrative import PROVENANCE, build_fusion_narrative

AS_OF = date(2026, 11, 27)


def signal(engine, direction, lens, summary, magnitude=0.75):
    return AnalyticalSignal(
        stock_id=1, signal_date=AS_OF, engine=engine, direction=direction,
        magnitude=magnitude, metadata_json=f'{{"lens": "{lens}", "summary": "{summary}"}}',
        key_drivers_json="[]",
    )


def build(**overrides):
    kwargs = dict(
        fusion_date=AS_OF, opportunity_strength="weak", confidence="high",
        signal_structure="confirmation", evidence_independence="high",
        conflicts=[], blocking_conditions=[],
        strength_basis={"positive_sources": 1, "negative_sources": 2},
        signals=[],
    )
    kwargs.update(overrides)
    return build_fusion_narrative(**kwargs)


def test_it_leads_with_the_conclusion():
    """A reader who stops after one line should still have the part that
    matters."""
    lines = build().split("\n")

    assert lines[1].startswith("结论：")
    assert "机会强度弱" in lines[1]


def test_it_names_what_the_engines_actually_read():
    text = build(signals=[
        signal("catalyst", "positive", "milestone", "完成 2 项里程碑"),
        signal("technical", "negative", "trend", "均线完全空头排列"),
    ])

    assert "支持的读数" in text and "完成 2 项里程碑" in text
    assert "反对的读数" in text and "均线完全空头排列" in text


def test_a_neutral_reading_is_counted_out_with_its_reason():
    """A rule the backtest falsified is still recorded, and must not pass for
    confirmation."""
    text = build(signals=[signal("technical", "neutral", "breakout", "252 日新高（仅作关注）")])

    assert "不计入方向" in text
    assert "被回测证伪" in text


def test_divergence_is_written_out_rather_than_left_as_a_key():
    text = build(conflicts=["cross_engine_divergence:fundamental_vs_catalyst+technical"])

    assert "基本面看多，而项目催化、技术面看空" in text


def test_an_internal_divergence_reads_as_a_different_finding():
    text = build(conflicts=["engine_internal_divergence:technical"])

    assert "技术面引擎内部不同视角方向相反" in text


def test_it_says_why_the_strength_was_capped():
    text = build(
        conflicts=["engine_internal_divergence:technical"],
        strength_basis={"positive_sources": 1, "negative_sources": 2,
                        "cap_applied": "contradicted_by_equally_sourced_negative"},
    )

    assert "诚实的读法是不确定" in text


def test_a_blocking_condition_is_stated_before_anything_else():
    text = build(blocking_conditions=["risk_score_below_floor"])

    assert "在解除之前不构成可行动的机会" in text


def test_it_names_what_would_change_the_answer():
    """"Watch for developments" is worth nothing; a reader needs the specific
    observation that would move this."""
    text = build(strength_basis={"positive_sources": 1, "negative_sources": 2})

    assert "第二个独立来源的正向读数" in text


def test_with_no_positive_reading_it_says_so_plainly():
    text = build(opportunity_strength="none",
                 strength_basis={"positive_sources": 0, "negative_sources": 3})

    assert "没有任何引擎给出正向读数" in text
    assert "目前一个都没有" in text


def test_a_strong_case_still_says_a_person_has_to_confirm():
    text = build(opportunity_strength="strong",
                 strength_basis={"positive_sources": 2, "negative_sources": 0})

    assert "引擎按设计不会自己晋升" in text


def test_it_says_what_wrote_it():
    """A reader who cannot tell a rules synthesis from a model's judgement
    cannot weigh it."""
    text = build()

    assert text.endswith(PROVENANCE)
    assert "不是交易员判断" in text
