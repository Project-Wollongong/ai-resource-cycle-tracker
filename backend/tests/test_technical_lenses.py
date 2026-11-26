"""The seven lenses, each shown a price history it should recognise."""
import ast
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.analysis.indicators import DailyBar
from app.analysis.technical_lenses import (
    INSUFFICIENT_DATA,
    LENSES,
    NO_MATERIAL_CHANGE,
    REPORTED,
    breakout,
    exhaustion,
    momentum,
    participation,
    read_all,
    structure,
    trend,
    volatility,
)

START = date(2025, 1, 1)


def bars(closes, volumes=None, ranges=None):
    """Ascending daily bars. `ranges` sets each bar's high/low spread as a fraction."""
    volumes = volumes or [100_000] * len(closes)
    ranges = ranges or [0.02] * len(closes)
    return [
        DailyBar(
            date=START + timedelta(days=index),
            open=close,
            high=close * (1 + spread),
            low=close * (1 - spread),
            close=close,
            volume=volume,
        )
        for index, (close, volume, spread) in enumerate(zip(closes, volumes, ranges))
    ]


def flat(count, value=1.0):
    return [value] * count


def rising(count, start=1.0, step=0.01):
    return [start + step * index for index in range(count)]


# --- each lens reports what it is for ---------------------------------------

def test_trend_recognises_a_stacked_advance():
    reading = trend(bars(rising(220)))

    assert reading.status == REPORTED
    assert reading.direction == "positive"
    assert reading.persistence == "long"
    assert reading.evidence["ma20"] > reading.evidence["ma50"] > reading.evidence["ma200"]


def test_trend_recognises_a_stacked_decline():
    reading = trend(bars(list(reversed(rising(220)))))

    assert reading.status == REPORTED
    assert reading.direction == "negative"


def test_trend_says_nothing_when_the_averages_disagree():
    # a long flat stretch leaves no slope to read
    assert trend(bars(flat(220))).status == NO_MATERIAL_CHANGE


def test_momentum_reports_a_decelerating_advance():
    """Up hard over sixty days, then rolling over in the last ten."""
    closes = rising(60, start=1.0, step=0.02) + [2.2 - 0.02 * i for i in range(12)]
    reading = momentum(bars(closes))

    assert reading.status == REPORTED
    assert reading.direction == "negative"
    assert reading.evidence["roc60_pct"] > 20
    assert reading.evidence["roc10_pct"] < 0


def test_momentum_reports_a_strong_recent_push():
    closes = flat(60) + [1.0 + 0.03 * index for index in range(21)]
    reading = momentum(bars(closes))

    assert reading.status == REPORTED
    assert reading.direction == "positive"
    assert reading.evidence["roc20_pct"] >= 25


def test_participation_flags_a_volume_spike():
    volumes = [100_000] * 25 + [900_000]
    reading = participation(bars(rising(26), volumes))

    assert reading.status == REPORTED
    assert reading.evidence["rel_vol"] >= 3.0
    assert reading.magnitude in {"strong", "exceptional"}


def test_participation_flags_a_rise_the_volume_is_not_supporting():
    """Price up on steadily thinning turnover: the move is losing sponsorship."""
    closes = flat(25) + [1.02, 1.04, 1.06, 1.08, 1.10]
    volumes = [100_000] * 25 + [40_000] * 5
    reading = participation(bars(closes, volumes))

    assert reading.status == REPORTED
    assert reading.direction == "negative"
    assert reading.evidence["volume_ma5_vs_ma20"] < 0.7


def test_volatility_recognises_a_contraction():
    spreads = [0.05] * 45 + [0.004] * 15
    reading = volatility(bars(flat(60), ranges=spreads))

    assert reading.status == REPORTED
    assert reading.evidence["atr_ratio"] <= 0.65
    # a squeeze says nothing about which way it resolves
    assert reading.direction == "neutral"


def test_volatility_recognises_an_expansion():
    spreads = [0.004] * 45 + [0.05] * 15
    reading = volatility(bars(flat(60), ranges=spreads))

    assert reading.status == REPORTED
    assert reading.evidence["atr_ratio"] >= 1.8


def test_structure_places_price_at_the_top_of_its_range():
    reading = structure(bars(rising(60)))

    assert reading.status == REPORTED
    assert reading.direction == "positive"
    assert reading.evidence["position_in_range"] >= 0.9


def test_structure_places_price_at_the_bottom_of_its_range():
    reading = structure(bars(list(reversed(rising(60)))))

    assert reading.status == REPORTED
    assert reading.direction == "negative"


def test_breakout_reports_a_new_sixty_day_high():
    reading = breakout(bars(flat(61) + [1.5]))

    assert reading.status == REPORTED
    assert reading.direction == "positive"
    assert "60" in reading.summary


def test_breakout_reports_a_new_sixty_day_low():
    reading = breakout(bars(flat(61) + [0.5]))

    assert reading.status == REPORTED
    assert reading.direction == "negative"


def test_breakout_reports_one_that_did_not_hold():
    """A high made this week, already given back — a failure, not a breakout."""
    closes = flat(62) + [1.4] + flat(9, 0.95)
    reading = breakout(bars(closes))

    assert reading.status == REPORTED
    assert reading.direction == "negative"
    assert "跌回" in reading.summary


def test_a_year_high_is_marked_unconfirmed_rather_than_bullish_confirmation():
    """BREAKOUT_252D measured -29.78% excess past five days in this project's
    own backtest. It still gets reported, but a neutral direction keeps it from
    supplying the second opinion that would turn one reading into agreement."""
    reading = breakout(bars(flat(260) + [2.0]))

    assert reading.status == REPORTED
    assert reading.direction == "neutral"
    assert reading.confidence == "low"
    assert any("仅作关注" in risk for risk in reading.risks)


def test_exhaustion_measures_stretch_against_the_stock_s_own_habit():
    """A quiet stock that suddenly runs is stretched; a jumpy one is not."""
    calm = exhaustion(bars(flat(80) + [1.6]))

    assert calm.status == REPORTED
    assert calm.direction == "negative"
    assert calm.evidence["extension_above_ma20_pct"] > calm.evidence["typical_abs_extension_pct"]


def test_exhaustion_counts_consecutive_advances():
    closes = flat(70) + [1.0 + 0.001 * index for index in range(1, 9)]
    reading = exhaustion(bars(closes))

    assert reading.status == REPORTED
    assert reading.evidence["consecutive_up_days"] >= 7
    # a long count on its own is weak evidence and must say so
    assert reading.confidence == "low"


# --- what every lens must do ------------------------------------------------

@pytest.mark.parametrize("lens", LENSES, ids=lambda lens: lens.__name__)
def test_a_lens_with_too_little_history_says_so_rather_than_guessing(lens):
    reading = lens(bars(flat(5)))

    assert reading.status == INSUFFICIENT_DATA
    assert reading.direction == "neutral"
    assert reading.evidence["bars_available"] == 5


@pytest.mark.parametrize("lens", LENSES, ids=lambda lens: lens.__name__)
def test_every_lens_returns_the_contract_enums(lens):
    reading = lens(bars(rising(260)))

    assert reading.status in {REPORTED, NO_MATERIAL_CHANGE, INSUFFICIENT_DATA}
    assert reading.direction in {"positive", "negative", "neutral"}
    assert reading.magnitude in {"minor", "moderate", "strong", "exceptional"}
    assert reading.confidence in {"low", "medium", "high"}
    assert reading.persistence in {"short", "medium", "long", "structural"}
    assert reading.summary


def test_read_all_returns_all_seven_lenses():
    readings = read_all(bars(rising(260)))

    assert len(readings) == 7
    assert [reading.lens for reading in readings] == [
        "trend", "momentum", "participation", "volatility", "structure",
        "breakout", "exhaustion",
    ]


def test_the_technical_lenses_cannot_reach_another_engine():
    """The PRD requires analytical isolation to be enforced by what the code can
    reach, not by an instruction telling it not to look. For a rules engine the
    import graph is that enforcement, so this asserts on it."""
    imported = _imported_modules("app/analysis/technical_lenses.py")

    for forbidden in ("announcement", "fundamental", "catalyst", "sentiment",
                      "fusion", "scoring", "sqlalchemy", "models", "database"):
        offenders = [name for name in imported if forbidden in name.lower()]
        assert not offenders, f"technical lenses must not import {offenders}"
    # price in, nothing else. lens_reading is the shape every engine returns and
    # deliberately belongs to none of them — sharing it through one engine would
    # put a hole in the graph this test exists to protect.
    project = {name for name in imported if name.startswith(".")}
    assert project <= {
        ".indicators", ".indicators.DailyBar",
        ".lens_reading", ".lens_reading.LensReading",
        ".lens_reading.REPORTED", ".lens_reading.NO_MATERIAL_CHANGE",
        ".lens_reading.INSUFFICIENT_DATA",
    }


def _imported_modules(relative_path: str) -> set[str]:
    """Every module name this file pulls in, from the syntax tree rather than
    the text — a module named in a sentence of prose is not a dependency."""
    source = Path(__file__).resolve().parents[1] / relative_path
    tree = ast.parse(source.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # keep the leading dots: "..models" is a different reach than "models"
            base = "." * node.level + (node.module or "")
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
    return names

