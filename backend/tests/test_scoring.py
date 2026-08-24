from datetime import date, datetime, timedelta
import json

import pytest

from app.analysis.indicators import compute_indicators
from app.analysis.scoring import (
    LABEL_HIGH,
    LABEL_IGNORE,
    LABEL_MONITOR,
    LABEL_WATCH,
    ScoredAnnouncement,
    RiskAnnouncement,
    announcement_score,
    commodity_score,
    cycle_score,
    funding_score,
    label_for,
    risk_score,
)
from app.models import Announcement, PriceBar, ScoreSnapshot, Stock
from app.services.scoring_service import score_and_signal_stock
from app.services.config_service import DEFAULTS

from conftest import make_bars

THRESH = DEFAULTS["signal_thresholds"]
AS_OF = date(2026, 6, 30)


def ind_for(closes, volumes):
    return compute_indicators(make_bars(closes, volumes))


def ann(days_ago, type_score=85.0, ann_type="DRILL_RESULTS", ps=False, headline="x"):
    return ScoredAnnouncement(
        headline=headline,
        ann_type=ann_type,
        type_score=type_score,
        ann_date=AS_OF - timedelta(days=days_ago),
        price_sensitive=ps,
    )


# ---------- funding ----------

@pytest.mark.parametrize(
    ("todays_volume", "expected_points"),
    [(500_000, 40), (300_000, 30), (200_000, 20), (150_000, 10), (149_000, 0)],
)
def test_funding_rel_vol_ladder(todays_volume, expected_points):
    ind = ind_for([1.0] * 20 + [1.05], [100_000] * 20 + [todays_volume])
    _, comps = funding_score(ind, THRESH)
    assert comps["rel_vol"]["points"] == expected_points


def test_funding_direction_gate_blocks_down_day():
    # 6x volume on a -5% day: distribution, not accumulation -> 0 points
    ind = ind_for([1.0] * 20 + [0.95], [100_000] * 20 + [600_000])
    _, comps = funding_score(ind, THRESH)
    assert comps["rel_vol"]["points"] == 0
    assert comps["rel_vol"]["note"] == "high_volume_down_day"


def test_funding_liquidity_floor():
    # 10x rel_vol but only A$11k turnover — zombie-book noise
    ind = ind_for([0.011] * 20 + [0.011], [100_000] * 20 + [1_000_000])
    _, comps = funding_score(ind, THRESH)
    assert comps["rel_vol"]["points"] == 0
    assert comps["rel_vol"]["note"] == "insufficient_liquidity"


def test_funding_breakout_takes_highest_window_only():
    ind = ind_for([1.0] * 252 + [1.5], [100_000] * 253)
    _, comps = funding_score(ind, THRESH)
    assert comps["breakout"]["points"] == 30
    assert comps["breakout"]["window"] == 252


@pytest.mark.parametrize(("up_days", "expected"), [(5, 15), (4, 12), (3, 8), (2, 4), (1, 0)])
def test_funding_consecutive_ladder(up_days, expected):
    closes = [1.0] * 20 + [1.0 + 0.01 * i for i in range(1, up_days + 1)]
    ind = ind_for(closes, [100_000] * len(closes))
    _, comps = funding_score(ind, THRESH)
    assert comps["consecutive_up"]["points"] == expected


def test_funding_max_score_is_100():
    # 252d breakout + 12x rel_vol + 5 up days + vol trend 2.06x, all on an up day
    closes = [1.0] * 252 + [1.0 + 0.05 * i for i in range(1, 6)]
    volumes = [100_000] * 256 + [1_200_000]
    ind = ind_for(closes, volumes)
    score, comps = funding_score(ind, THRESH)
    assert comps["rel_vol"]["points"] == 40
    assert comps["breakout"]["points"] == 30
    assert comps["consecutive_up"]["points"] == 15
    assert comps["vol_trend"]["points"] == 15
    assert score == 100.0


# ---------- risk ----------

def test_risk_score_penalizes_low_liquidity_and_recent_placement():
    ind = ind_for([0.05] * 20 + [0.05], [100_000] * 20 + [100_000])
    score, comps = risk_score(
        ind,
        [
            RiskAnnouncement(
                headline="Placement to raise capital",
                ann_type="PLACEMENT",
                ann_date=AS_OF - timedelta(days=3),
                price_sensitive=False,
            )
        ],
        THRESH,
        AS_OF,
    )

    assert score == pytest.approx(12.0)
    assert comps["liquidity_adjust"] == -20.0
    assert comps["event_adjust"] == -18.0
    assert comps["label"] == "elevated_risk"


def test_risk_score_rewards_stronger_liquidity_without_events():
    ind = ind_for([1.0] * 20 + [1.0], [100_000] * 20 + [1_500_000])
    score, comps = risk_score(ind, [], THRESH, AS_OF)

    assert score == 58.0
    assert comps["liquidity_adjust"] == 8.0
    assert comps["events"] == []


def test_risk_score_caps_event_penalties():
    ind = ind_for([1.0] * 20 + [1.0], [100_000] * 21)
    events = [
        RiskAnnouncement("Placement", "PLACEMENT", AS_OF, False),
        RiskAnnouncement("Trading halt", "TRADING_HALT", AS_OF, True),
        RiskAnnouncement("Voluntary suspension", "TRADING_HALT", AS_OF, True),
    ]
    score, comps = risk_score(ind, events, THRESH, AS_OF)

    assert comps["event_adjust"] == -35.0
    assert score == 15.0


# ---------- announcement ----------

def test_announcement_no_news_is_zero():
    score, comps = announcement_score([], AS_OF)
    assert score == 0.0
    assert comps["note"] == "no_announcements_30d"


@pytest.mark.parametrize(
    ("age", "expected_decay"),
    [(0, 1.0), (3, 1.0), (4, 0.8), (7, 0.8), (8, 0.5), (14, 0.5), (15, 0.25), (30, 0.25)],
)
def test_announcement_decay_boundaries(age, expected_decay):
    score, _ = announcement_score([ann(age, type_score=80.0)], AS_OF)
    assert score == pytest.approx(80.0 * expected_decay)


def test_announcement_older_than_30d_excluded():
    score, _ = announcement_score([ann(31)], AS_OF)
    assert score == 0.0


def test_announcement_price_sensitive_multiplier_clamped():
    score, _ = announcement_score([ann(0, type_score=90.0, ps=True)], AS_OF)
    assert score == 100.0  # 90*1.2=108 -> clamp


def test_announcement_bonus_counts_key_announcements_capped():
    anns = [ann(0, 85), ann(2, 85), ann(5, 90, "JORC_MRE"), ann(6, 75, "OFFTAKE")]
    score, comps = announcement_score(anns, AS_OF)
    # best = 90*0.8=72... no: JORC at age5 -> 90*0.8=72; drill age0 -> 85. best=85
    assert comps["best"] == 85.0
    assert comps["bonus"] == 15  # 3 other key announcements -> capped at 15
    assert score == 100.0

    many = [ann(i, 85) for i in range(6)]
    _, comps2 = announcement_score(many, AS_OF)
    assert comps2["bonus"] == 15  # 5 others -> still 15


def test_announcement_low_base_gets_no_bonus():
    anns = [ann(0, 85), ann(1, 50, "PLACEMENT"), ann(2, 55, "TRADING_HALT")]
    _, comps = announcement_score(anns, AS_OF)
    assert comps["bonus"] == 0


def test_announcement_qualitative_context_adds_bounded_bonus_and_components():
    score, comps = announcement_score(
        [
            ann(
                0,
                type_score=70,
                ps=False,
                headline="high quality drill result",
            ),
            ScoredAnnouncement(
                headline="contextual drill result",
                ann_type="DRILL_RESULTS",
                type_score=70,
                ann_date=AS_OF,
                price_sensitive=False,
                interval_quality_label="strong",
                materiality_label="high",
                grade_thickness=45.0,
                qualitative_assessment="Strong in stored project history.",
            ),
        ],
        AS_OF,
    )

    contextual = comps["announcements"][0]
    assert score == 83.0
    assert contextual["qualitative_bonus"] == 8.0
    assert contextual["adjusted_base"] == 78.0
    assert contextual["interval_quality_label"] == "strong"
    assert contextual["materiality_label"] == "high"
    assert contextual["grade_thickness"] == 45.0
    assert contextual["qualitative_assessment"] == "Strong in stored project history."
    assert comps["bonus"] == 5


def test_score_snapshot_announcement_components_include_qualitative_context(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    bars = make_bars([1.0] * 61, [100_000] * 61)
    for bar in bars:
        db_session.add(
            PriceBar(
                stock_id=stock.id,
                date=bar.date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
        )
    eval_date = bars[-1].date
    db_session.add(
        Announcement(
            stock_id=stock.id,
            ann_id="ann-context",
            headline="High-grade drilling at project",
            ann_date=datetime.combine(eval_date, datetime.min.time()),
            url="https://example.com/ann.pdf",
            price_sensitive=True,
            ann_type="DRILL_RESULTS",
            type_score=70,
            matched_keywords="[]",
            raw_payload="{}",
            ai_metrics=json.dumps(
                {
                    "qualitative_context": {
                        "interval_quality_label": "strong",
                        "materiality_label": "high",
                        "grade_thickness": 45.0,
                        "qualitative_assessment": "Strong in stored project history.",
                    }
                }
            ),
        )
    )
    db_session.commit()

    score_and_signal_stock(
        db_session,
        stock,
        thresholds=DEFAULTS["signal_thresholds"],
        weights=DEFAULTS["weights"],
        label_thresholds=DEFAULTS["label_thresholds"],
        commodity_map={},
    )

    snapshot = db_session.query(ScoreSnapshot).filter_by(stock_id=stock.id, date=eval_date).one()
    components = json.loads(snapshot.components)
    ann_item = components["announcement"]["announcements"][0]
    assert ann_item["qualitative_bonus"] == 8.0
    assert ann_item["interval_quality_label"] == "strong"
    assert ann_item["materiality_label"] == "high"
    assert ann_item["grade_thickness"] == 45.0
    assert snapshot.resource_score == 83.0
    assert components["resource"]["source"] == "qualitative_context_auto"
    assert components["resource"]["context_count"] == 1
    assert components["resource"]["items"][0]["score"] == 83.0


def test_manual_resource_override_still_wins_over_qualitative_context(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold", resource_score_override=62.0)
    db_session.add(stock)
    db_session.commit()

    bars = make_bars([1.0] * 61, [100_000] * 61)
    for bar in bars:
        db_session.add(
            PriceBar(
                stock_id=stock.id,
                date=bar.date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
        )
    eval_date = bars[-1].date
    db_session.add(
        Announcement(
            stock_id=stock.id,
            ann_id="ann-context",
            headline="Exceptional drilling at project",
            ann_date=datetime.combine(eval_date, datetime.min.time()),
            url="https://example.com/ann.pdf",
            price_sensitive=True,
            ann_type="DRILL_RESULTS",
            type_score=85,
            matched_keywords="[]",
            raw_payload="{}",
            ai_metrics=json.dumps(
                {
                    "qualitative_context": {
                        "interval_quality_label": "exceptional",
                        "materiality_label": "high",
                        "trend_vs_previous": "improving",
                        "depth_category": "shallow",
                        "project_percentile": 95,
                        "grade_thickness": 120.0,
                    }
                }
            ),
        )
    )
    db_session.commit()

    score_and_signal_stock(
        db_session,
        stock,
        thresholds=DEFAULTS["signal_thresholds"],
        weights=DEFAULTS["weights"],
        label_thresholds=DEFAULTS["label_thresholds"],
        commodity_map={},
    )

    snapshot = db_session.query(ScoreSnapshot).filter_by(stock_id=stock.id, date=eval_date).one()
    components = json.loads(snapshot.components)
    assert snapshot.resource_score == 62.0
    assert components["resource"] == {"value": 62.0, "source": "manual_override"}


# ---------- commodity ----------

def test_commodity_score_exact():
    closes = [(AS_OF - timedelta(days=100 - i), 100.0) for i in range(100)]
    closes[-1] = (closes[-1][0], 105.0)  # +5% vs both 20d and 60d ago
    score, comps = commodity_score(closes, AS_OF)
    assert comps["r20_pct"] == pytest.approx(5.0)
    assert comps["r60_pct"] == pytest.approx(5.0)
    assert score == pytest.approx(50 + 0.05 * 200 + 0.05 * 100)  # 65


def test_commodity_score_insufficient_data_neutral():
    closes = [(AS_OF - timedelta(days=i), 100.0) for i in range(10)]
    score, comps = commodity_score(closes, AS_OF)
    assert score == 50.0
    assert comps["note"] == "insufficient_data"


def test_commodity_score_clamped():
    closes = [(AS_OF - timedelta(days=100 - i), 100.0) for i in range(100)]
    closes[-1] = (closes[-1][0], 200.0)  # +100%
    score, _ = commodity_score(closes, AS_OF)
    assert score == 100.0


# ---------- composition ----------

def test_default_weights_sum_to_one():
    assert sum(DEFAULTS["weights"].values()) == pytest.approx(1.0)


def test_cycle_score_weighted_sum():
    score = cycle_score(100, 100, 50, 100, 50, DEFAULTS["weights"])
    assert score == pytest.approx(85.0)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (75.0, LABEL_HIGH),
        (74.9, LABEL_WATCH),
        (60.0, LABEL_WATCH),
        (59.9, LABEL_MONITOR),
        (45.0, LABEL_MONITOR),
        (44.9, LABEL_IGNORE),
        (0, LABEL_IGNORE),
    ],
)
def test_label_thresholds(score, expected):
    assert label_for(score, DEFAULTS["label_thresholds"]) == expected
