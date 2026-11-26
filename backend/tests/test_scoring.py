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
from app.models import Announcement, AnalyticalSignal, AttentionState, FusionRecord, PriceBar, ScoreSnapshot, Signal, Stock, TradeDecision
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


def test_announcement_score_ignores_context_quality_but_still_reports_it():
    """The quality and materiality labels belong to the resource sub-score,
    which reads them alongside trend, depth and percentile. Scoring them here
    too let one drill result move 0.40 and 0.20 of the cycle score at once."""
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

    by_headline = {item["headline"]: item for item in comps["announcements"]}
    contextual = by_headline["contextual drill result"]
    # both are type_score 70, same day, neither price-sensitive, so the
    # labelled one must no longer outscore the plain one
    assert score == 75.0
    assert contextual["effective"] == by_headline["high quality drill result"]["effective"]
    assert "qualitative_bonus" not in contextual
    # still reported, so the reader can see what the labels said
    assert contextual["interval_quality_label"] == "strong"
    assert contextual["materiality_label"] == "high"
    assert contextual["grade_thickness"] == 45.0
    assert contextual["qualitative_assessment"] == "Strong in stored project history."
    assert comps["bonus"] == 5


def test_one_announcement_moves_the_resource_score_only(db_session):
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
    assert ann_item["ann_id"] == "ann-context"
    assert ann_item["url"] == "https://example.com/ann.pdf"
    # the labels reach the resource sub-score (weight 0.20) and stop there;
    # counting them in the announcement sub-score (0.40) as well let a single
    # filing move both at once
    assert "qualitative_bonus" not in ann_item
    assert ann_item["interval_quality_label"] == "strong"
    assert ann_item["materiality_label"] == "high"
    assert ann_item["grade_thickness"] == 45.0
    assert snapshot.resource_score == 83.0
    assert components["resource"]["source"] == "qualitative_context_auto"
    assert components["resource"]["context_count"] == 1
    assert components["resource"]["items"][0]["score"] == 83.0


def test_one_filings_many_intercepts_count_as_one_piece_of_evidence(db_session):
    """A quarterly report lists ten intercepts. Ranking them individually let a
    single document fill all eight slots and carry the sub-score alone — BRE
    scored 96.6 that way, off one filing counted four times."""
    from app.services.scoring_service import _resource_score_from_contexts

    stock = Stock(code="DUP", name="Duplicate Co", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    eval_date = date(2026, 10, 1)
    contexts = [
        {"interval_quality_label": "exceptional", "materiality_label": "low",
         "grade_thickness": 90.0 + index, "depth_category": "shallow"}
        for index in range(10)
    ]
    db_session.add(Announcement(
        stock_id=stock.id, ann_id="one-filing", headline="Quarterly Activities Report",
        ann_date=datetime(2026, 9, 30), ann_type="QUARTERLY", type_score=40,
        matched_keywords="[]", raw_payload="{}",
        ai_metrics=json.dumps({"qualitative_contexts": contexts}),
    ))
    db_session.add(Announcement(
        stock_id=stock.id, ann_id="other-filing", headline="Drilling update",
        ann_date=datetime(2026, 9, 20), ann_type="DRILL_RESULTS", type_score=70,
        matched_keywords="[]", raw_payload="{}",
        ai_metrics=json.dumps({"qualitative_contexts": [
            {"interval_quality_label": "weak", "materiality_label": "low",
             "grade_thickness": 3.0, "depth_category": "deep"}
        ]}),
    ))
    db_session.commit()

    _, components = _resource_score_from_contexts(db_session, stock, eval_date)

    # eleven contexts, but only two filings behind them
    assert components["context_count"] == 11
    assert components["announcement_count"] == 2
    assert components["used_count"] == 2
    # the weak filing must still pull the average down; it cannot be crowded out
    assert {item["ann_id"] for item in components["items"]} == {"one-filing", "other-filing"}


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


def test_score_and_signal_stock_writes_p5_p6_compat_records_idempotently(db_session):
    stock = Stock(code="P56", name="P56 Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    bars = make_bars([1.0] * 20 + [1.08], [100_000] * 20 + [400_000])
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
            ann_id="p56-drill",
            headline="High-grade drilling results",
            ann_date=datetime.combine(eval_date, datetime.min.time()),
            url="https://example.com/p56.pdf",
            price_sensitive=True,
            ann_type="DRILL_RESULTS",
            type_score=85,
            matched_keywords="[]",
            raw_payload="{}",
            ai_metrics=json.dumps(
                {
                    "qualitative_context": {
                        "interval_quality_label": "strong",
                        "materiality_label": "high",
                        "trend_vs_previous": "improving",
                        "depth_category": "shallow",
                        "project_percentile": 80,
                        "grade_thickness": 88.0,
                    }
                }
            ),
        )
    )
    db_session.commit()

    # the same drilling, as P03 recorded it — the Catalyst Agent reads events,
    # not the announcement score, so without this it has nothing to read
    from app.models import EvidenceDocument, P3Event, P3ParseRun

    evidence = EvidenceDocument(stock_id=stock.id, source_type="asx_pdf",
                                source_id="p56-drill", title="High-grade drilling results")
    db_session.add(evidence)
    db_session.commit()
    run = P3ParseRun(evidence_document_id=evidence.id, parser_name="t", parser_version="t",
                     input_hash="t", status="parsed")
    db_session.add(run)
    db_session.commit()
    db_session.add(P3Event(
        evidence_document_id=evidence.id, parse_run_id=run.id, stock_id=stock.id,
        event_type="Drilling Completed", event_title="Drilling Completed",
        primary_family="F01", event_status="completed",
        occurred_on=eval_date, reported_on=datetime.combine(eval_date, datetime.min.time()),
        revision_tags_json="[]",
    ))
    db_session.commit()

    for _ in range(2):
        score_and_signal_stock(
            db_session,
            stock,
            thresholds=DEFAULTS["signal_thresholds"],
            weights=DEFAULTS["weights"],
            label_thresholds=DEFAULTS["label_thresholds"],
            commodity_map={},
        )

    analytical = db_session.query(AnalyticalSignal).filter_by(stock_id=stock.id).all()
    assert sorted({row.engine for row in analytical}) == ["catalyst", "fundamental", "technical"]
    # two of the three engines write their own rows now, each under its own
    # logic version; only fundamental is still reshaped by the adapter
    by_version = {row.engine: row.logic_version for row in analytical}
    assert by_version["technical"] == "technical_seven_lens_v1"
    assert by_version["catalyst"] == "catalyst_seven_lens_v1"
    assert by_version["fundamental"] == "cycle_score_adapter_v1"

    # The one drilling result reaches the fundamental engine as an announcement
    # and the catalyst engine as a P03 event. That is one source, so both must
    # land in the same dependency group — otherwise P6 reads a single drill
    # result as two independent confirmations.
    groups = {(row.engine, row.dependency_group) for row in analytical}
    event_group = f"announcement_event:{eval_date.isoformat()}:exploration"
    assert ("fundamental", event_group) in groups
    assert ("catalyst", event_group) in groups
    # the technical agent groups its lenses under one price-action key, so a day
    # of agreeing lenses is one source rather than seven
    assert ("technical", f"price_action:{eval_date.isoformat()}") in groups

    fusion = db_session.query(FusionRecord).filter_by(stock_id=stock.id, fusion_date=eval_date).one()
    assert fusion.rule_version == "fusion_adapter_v1"
    assert fusion.opportunity_strength in {"moderate", "strong", "exceptional"}
    assert fusion.signal_structure == "confirmation"
    assert json.loads(fusion.analytical_signal_ids_json) == [row.id for row in analytical]

    attention = db_session.query(AttentionState).filter_by(stock_id=stock.id, ended_at=None).one()
    assert attention.state_level == "L3"
    assert attention.state_label == "Investigation"
    assert attention.transition == "upgrade"
    assert attention.compute_profile == "deep_investigation"
    metadata = json.loads(attention.metadata_json)
    assert metadata["recommended_state"] == "L4"
    assert metadata["human_review_required"] is True

    decision = db_session.query(TradeDecision).filter_by(stock_id=stock.id, decision_date=eval_date).one()
    assert decision.decision == "wait"
    assert decision.action == "none"
    assert decision.attention_state_id == attention.id
    assert decision.fusion_record_id == fusion.id


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


def test_neutral_signals_do_not_count_toward_confirmation(db_session):
    """A watch_only rule is recorded but must not make its engine look like a
    second, independent opinion — otherwise a rule the backtest says is not
    predictive would manufacture confirmation."""
    from app.services.p5_p6_adapter import _engines

    stock = Stock(code="NEU", name="Neutral Co", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    rows = [
        AnalyticalSignal(
            stock_id=stock.id,
            signal_date=date(2026, 3, 2),
            engine="catalyst",
            direction="positive",
            magnitude=70.0,
        ),
        AnalyticalSignal(
            stock_id=stock.id,
            signal_date=date(2026, 3, 2),
            engine="technical",
            direction="neutral",
            magnitude=30.0,
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()
    ids = [row.id for row in rows]

    # the neutral technical row is stored, but only the catalyst engine counts
    assert db_session.query(AnalyticalSignal).filter(AnalyticalSignal.id.in_(ids)).count() == 2
    assert _engines(db_session, ids) == {"catalyst"}


def test_breakout_252d_still_cannot_pass_for_confirmation():
    """Window length is not strength: the longest window measured the worst.
    The adapter used to express that as a lower weight; the technical agent now
    expresses it where the reading is made, by withholding a direction."""
    from app.analysis.technical_lenses import breakout
    from tests.test_technical_lenses import bars, flat

    year_high = breakout(bars(flat(260) + [2.0]))
    sixty_day_high = breakout(bars(flat(61) + [1.5]))

    assert year_high.direction == "neutral"
    assert sixty_day_high.direction == "positive"
