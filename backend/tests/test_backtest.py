import json
from datetime import date, datetime, timedelta

import pytest

from app.models import Announcement, CommodityBar, PriceBar, Signal, SignalReturn, Stock
from app.services.backtest import backtest_summary, fill_pending_returns

from conftest import next_weekday


def add_stock(session, code="TST", commodity="gold"):
    stock = Stock(code=code, name=f"{code} Ltd", commodity=commodity)
    session.add(stock)
    session.commit()
    return stock


def add_price_bars(session, stock, closes, start=date(2026, 1, 5), volumes=None):
    dates = []
    d = start
    for i, close in enumerate(closes):
        volume = volumes[i] if volumes else 100_000
        session.add(
            PriceBar(
                stock_id=stock.id, date=d, open=close, high=close, low=close,
                close=close, volume=volume,
            )
        )
        dates.append(d)
        d = next_weekday(d)
    session.commit()
    return dates


def add_signal(session, stock, sig_date, signal_type="REL_VOL_SPIKE", source="live",
               label="Monitor", cycle_score=50.0, price=1.0, horizons=(5, 20, 60, 120)):
    signal = Signal(
        stock_id=stock.id, date=sig_date, signal_type=signal_type, source=source,
        label=label if source == "live" else None, reason="test",
        evidence=json.dumps({}), price_at_signal=price,
        cycle_score_at_signal=cycle_score if source == "live" else None,
    )
    session.add(signal)
    session.flush()
    for h in horizons:
        session.add(SignalReturn(signal_id=signal.id, horizon_days=h))
    session.commit()
    return signal


def add_announcement(
    session,
    stock,
    ann_id,
    ann_date,
    interval_quality_label,
    materiality_label,
):
    announcement = Announcement(
        stock_id=stock.id,
        ann_id=ann_id,
        headline=f"{ann_id} drilling update",
        ann_date=datetime.combine(ann_date, datetime.min.time()),
        ann_type="DRILLING",
        ai_metrics=json.dumps(
            {
                "qualitative_context": {
                    "interval_quality_label": interval_quality_label,
                    "materiality_label": materiality_label,
                    "qualitative_assessment": "test context",
                }
            }
        ),
    )
    session.add(announcement)
    session.commit()
    return announcement


def test_fill_uses_next_day_close_as_entry(db_session):
    stock = add_stock(db_session)
    closes = [1.00, 1.05, 1.02, 1.04, 1.06, 1.08, 1.155, 1.20]
    dates = add_price_bars(db_session, stock, closes)
    add_signal(db_session, stock, dates[0], price=1.00)

    stats = fill_pending_returns(db_session, today=dates[-1])
    assert stats["filled"] == 1  # only the 5d horizon has enough bars

    sr5 = (
        db_session.query(SignalReturn).filter_by(horizon_days=5, status="filled").one()
    )
    # entry = FIRST bar after signal day (1.05), NOT the signal-day close (1.00)
    assert sr5.entry_price == pytest.approx(1.05)
    # exit = 5 bars after entry -> closes[6] = 1.155 -> exactly +10%
    assert sr5.return_pct == pytest.approx(10.0)

    sr20 = db_session.query(SignalReturn).filter_by(horizon_days=20).one()
    assert sr20.status == "pending"


def test_fill_computes_benchmark_excess(db_session):
    stock = add_stock(db_session)
    closes = [1.00] + [1.00] * 7
    dates = add_price_bars(db_session, stock, closes)
    # benchmark rises 2% between entry (dates[1]) and exit (dates[6])
    db_session.add(CommodityBar(instrument="OZR.AX", date=dates[1], close=100.0))
    db_session.add(CommodityBar(instrument="OZR.AX", date=dates[6], close=102.0))
    db_session.commit()
    add_signal(db_session, stock, dates[0])

    fill_pending_returns(db_session, today=dates[-1])
    sr5 = db_session.query(SignalReturn).filter_by(horizon_days=5, status="filled").one()
    assert sr5.benchmark_return_pct == pytest.approx(2.0)


def test_unavailable_when_stock_stops_trading(db_session):
    stock = add_stock(db_session)
    start = date(2026, 1, 5)
    dates = add_price_bars(db_session, stock, [1.0, 1.0, 1.0], start=start)  # 2 bars after signal
    add_signal(db_session, stock, dates[0])

    today = start + timedelta(days=176)  # long after; last bar is stale
    fill_pending_returns(db_session, today=today)

    by_horizon = {
        sr.horizon_days: sr.status for sr in db_session.query(SignalReturn).all()
    }
    # elapsed 176 > 2*h for 5/20/60 -> unavailable; 120 needs 240 days -> still pending
    assert by_horizon[5] == "unavailable"
    assert by_horizon[20] == "unavailable"
    assert by_horizon[60] == "unavailable"
    assert by_horizon[120] == "pending"


def test_pending_while_stock_still_prints_bars(db_session):
    # suspension then resumption: few bars after signal but the stock is alive
    stock = add_stock(db_session)
    start = date(2026, 1, 5)
    sig_date = start
    add_price_bars(db_session, stock, [1.0], start=start)
    resume = start + timedelta(days=95)
    add_price_bars(db_session, stock, [1.1, 1.1, 1.1], start=resume)
    add_signal(db_session, stock, sig_date)

    today = resume + timedelta(days=3)
    fill_pending_returns(db_session, today=today)
    sr5 = db_session.query(SignalReturn).filter_by(horizon_days=5).one()
    assert sr5.status == "pending"  # elapsed >> 10 days but bars are fresh


def test_backtest_summary_aggregation(db_session):
    stock = add_stock(db_session)
    d = date(2026, 3, 2)

    def filled_signal(sig_type, ret, bench, label="Monitor", score=50.0, source="live", offset=0):
        sig = add_signal(
            db_session, stock, d + timedelta(days=offset), signal_type=sig_type,
            label=label, cycle_score=score, source=source, horizons=(5,),
        )
        sr = db_session.query(SignalReturn).filter_by(signal_id=sig.id).one()
        sr.status = "filled"
        sr.entry_price = 1.0
        sr.return_pct = ret
        sr.benchmark_return_pct = bench
        db_session.commit()
        return sig

    filled_signal("REL_VOL_SPIKE", 10.0, 2.0)
    filled_signal("REL_VOL_SPIKE", -5.0, 1.0, offset=1)
    filled_signal("BREAKOUT_60D", 20.0, None, offset=2)
    # one unavailable signal
    sig = add_signal(db_session, stock, d + timedelta(days=3), signal_type="BREAKOUT_60D", horizons=(5,))
    sr = db_session.query(SignalReturn).filter_by(signal_id=sig.id).one()
    sr.status = "unavailable"
    db_session.commit()

    summary = backtest_summary(db_session, group_by="signal_type")
    assert summary["total_signals"] == 3
    groups = {g["group"]: g for g in summary["groups"]}

    spike_h5 = groups["REL_VOL_SPIKE"]["cells"][0]
    assert spike_h5["n"] == 2
    assert spike_h5["win_rate"] == pytest.approx(0.5)
    assert spike_h5["avg"] == pytest.approx(2.5)
    assert spike_h5["median"] == pytest.approx(2.5)
    assert spike_h5["avg_excess"] == pytest.approx(1.0)  # ((10-2)+(-5-1))/2
    assert spike_h5["low_sample"] is True

    breakout_h5 = groups["BREAKOUT_60D"]["cells"][0]
    assert breakout_h5["n"] == 1
    assert breakout_h5["avg_excess"] is None  # no benchmark data
    assert groups["BREAKOUT_60D"]["unavailable"] == 1


def test_label_grouping_excludes_replay(db_session):
    stock = add_stock(db_session)
    d = date(2026, 3, 2)
    sig = add_signal(db_session, stock, d, source="replay", horizons=(5,))
    sr = db_session.query(SignalReturn).filter_by(signal_id=sig.id).one()
    sr.status = "filled"
    sr.return_pct = 50.0
    db_session.commit()

    summary = backtest_summary(db_session, group_by="label", source="all")
    assert summary["source"] == "live"  # forced
    assert summary["total_signals"] == 0


def test_qualitative_grouping_uses_announcement_context(db_session):
    stock = add_stock(db_session)
    d = date(2026, 3, 2)
    add_announcement(db_session, stock, "A1", d, "strong", "high")
    add_announcement(db_session, stock, "A2", d + timedelta(days=1), "weak", "low")

    sig1 = add_signal(db_session, stock, d, signal_type="KEY_ANNOUNCEMENT", horizons=(5,))
    sig1.evidence = json.dumps({"announcements": [{"ann_id": "A1"}]})
    sig2 = add_signal(
        db_session,
        stock,
        d + timedelta(days=1),
        signal_type="KEY_ANNOUNCEMENT",
        horizons=(5,),
    )
    sig2.evidence = json.dumps({"announcements": [{"ann_id": "A2"}]})
    db_session.commit()

    for signal, ret in ((sig1, 12.0), (sig2, -4.0)):
        sr = db_session.query(SignalReturn).filter_by(signal_id=signal.id).one()
        sr.status = "filled"
        sr.return_pct = ret
        sr.benchmark_return_pct = 1.0
    db_session.commit()

    quality_summary = backtest_summary(db_session, group_by="interval_quality", source="all")
    assert quality_summary["source"] == "live"
    quality_groups = {g["group"]: g for g in quality_summary["groups"]}
    assert quality_groups["strong"]["cells"][0]["avg"] == pytest.approx(12.0)
    assert quality_groups["weak"]["cells"][0]["avg_excess"] == pytest.approx(-5.0)

    materiality_summary = backtest_summary(db_session, group_by="materiality", source="live")
    materiality_groups = {g["group"]: g for g in materiality_summary["groups"]}
    assert materiality_groups["high"]["cells"][0]["n"] == 1
    assert materiality_groups["low"]["cells"][0]["avg"] == pytest.approx(-4.0)


def test_qualitative_grouping_falls_back_to_same_day_and_no_context(db_session):
    stock = add_stock(db_session)
    d = date(2026, 3, 2)
    add_announcement(db_session, stock, "A1", d, "moderate", "medium")

    same_day_sig = add_signal(db_session, stock, d, signal_type="KEY_ANNOUNCEMENT", horizons=(5,))
    no_context_sig = add_signal(
        db_session,
        stock,
        d + timedelta(days=2),
        signal_type="KEY_ANNOUNCEMENT",
        horizons=(5,),
    )
    for signal in (same_day_sig, no_context_sig):
        sr = db_session.query(SignalReturn).filter_by(signal_id=signal.id).one()
        sr.status = "filled"
        sr.return_pct = 3.0
    db_session.commit()

    summary = backtest_summary(db_session, group_by="interval_quality", source="live")
    groups = {g["group"]: g for g in summary["groups"]}
    assert groups["moderate"]["cells"][0]["n"] == 1
    assert groups["no_context"]["cells"][0]["n"] == 1
