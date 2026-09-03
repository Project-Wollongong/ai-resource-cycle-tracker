from datetime import date, timedelta

import pytest

from app.models import CommodityBar, HistoricalAnalysisReturn, Stock
from app.services.historical_analysis import run_historical_analysis
from app.services.historical_returns import (
    evaluate_historical_snapshot_returns,
    evaluate_pending_historical_returns,
)

from test_historical_scoring import add_price_bars, add_stock


def test_evaluate_historical_snapshot_returns_uses_next_bar_entry(db_session):
    stock = add_stock(db_session, code="HRT")
    dates = add_price_bars(
        db_session,
        stock,
        [1.00, 1.05, 1.10, 1.00, 1.20, 1.30, 1.155],
        [100_000] * 7,
    )
    snapshot = run_historical_analysis(db_session, stock, dates[0])
    db_session.add(CommodityBar(instrument="OZR.AX", date=dates[1], close=100.0))
    db_session.add(CommodityBar(instrument="OZR.AX", date=dates[6], close=102.0))
    db_session.commit()

    returns = evaluate_historical_snapshot_returns(db_session, snapshot, horizons=(5,), today=dates[-1])

    ret = returns[0]
    assert ret.status == "filled"
    assert ret.entry_date == dates[1]
    assert ret.entry_price == pytest.approx(1.05)
    assert ret.exit_date == dates[6]
    assert ret.exit_price == pytest.approx(1.155)
    assert ret.return_pct == pytest.approx(10.0)
    assert ret.benchmark_return_pct == pytest.approx(2.0)
    assert ret.max_drawdown_pct == pytest.approx(-11.15)


def test_evaluate_historical_snapshot_returns_is_idempotent(db_session):
    stock = add_stock(db_session, code="HRI")
    dates = add_price_bars(db_session, stock, [1.0] * 8, [100_000] * 8)
    snapshot = run_historical_analysis(db_session, stock, dates[0])

    first = evaluate_historical_snapshot_returns(db_session, snapshot, horizons=(5,), today=dates[-1])
    second = evaluate_historical_snapshot_returns(db_session, snapshot, horizons=(5,), today=dates[-1])

    assert second[0].id == first[0].id
    assert db_session.query(HistoricalAnalysisReturn).count() == 4


def test_evaluate_historical_snapshot_returns_stays_pending_when_stock_has_fresh_bars(db_session):
    stock = add_stock(db_session, code="HRP")
    dates = add_price_bars(db_session, stock, [1.0, 1.1, 1.2], [100_000] * 3)
    snapshot = run_historical_analysis(db_session, stock, dates[0])

    returns = evaluate_historical_snapshot_returns(db_session, snapshot, horizons=(5,), today=dates[-1])

    assert returns[0].status == "pending"
    assert returns[0].entry_price is None


def test_evaluate_historical_snapshot_returns_marks_stale_stock_unavailable(db_session):
    stock = add_stock(db_session, code="HRU")
    dates = add_price_bars(db_session, stock, [1.0, 1.1], [100_000] * 2)
    snapshot = run_historical_analysis(db_session, stock, dates[0])

    returns = evaluate_historical_snapshot_returns(
        db_session,
        snapshot,
        horizons=(5,),
        today=dates[0] + timedelta(days=30),
    )

    assert returns[0].status == "unavailable"


def test_evaluate_pending_historical_returns_fills_existing_pending_rows(db_session):
    stock = add_stock(db_session, code="HRF")
    dates = add_price_bars(db_session, stock, [1.0, 1.0, 1.0], [100_000] * 3)
    snapshot = run_historical_analysis(db_session, stock, dates[0])
    evaluate_historical_snapshot_returns(db_session, snapshot, horizons=(5,), today=dates[-1])

    add_price_bars(db_session, stock, [1.1, 1.2, 1.3, 1.4, 1.5], start=dates[-1] + timedelta(days=1), volumes=[100_000] * 5)
    stats = evaluate_pending_historical_returns(db_session, today=date(2026, 2, 1))

    ret = db_session.query(HistoricalAnalysisReturn).filter_by(horizon_days=5).one()
    assert stats["filled"] == 1
    assert ret.status == "filled"


def test_evaluate_pending_historical_returns_no_pending_rows(db_session):
    assert evaluate_pending_historical_returns(db_session) == {
        "filled": 0,
        "unavailable": 0,
        "pending": 0,
    }
