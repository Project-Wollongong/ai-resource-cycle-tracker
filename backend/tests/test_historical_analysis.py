from datetime import date

import pytest

from app.models import HistoricalAnalysisSnapshot, Stock
from app.services.historical_analysis import (
    run_historical_analysis,
    run_historical_analysis_for_code,
)

from test_historical_scoring import add_price_bars, add_stock


def test_run_historical_analysis_builds_scores_and_saves_snapshot(db_session):
    stock = add_stock(db_session, code="HAN")
    dates = add_price_bars(db_session, stock, [1.0] * 21, [100_000] * 21)

    snapshot = run_historical_analysis(db_session, stock, dates[-1])

    assert snapshot.id is not None
    assert snapshot.stock_id == stock.id
    assert snapshot.as_of_date == dates[-1]
    assert snapshot.status == "success"
    assert snapshot.input_hash
    assert snapshot.label in {"High Priority", "Watch Closely", "Monitor", "Ignore"}
    assert db_session.query(HistoricalAnalysisSnapshot).count() == 1


def test_run_historical_analysis_for_code_is_case_insensitive(db_session):
    stock = add_stock(db_session, code="HAC")
    dates = add_price_bars(db_session, stock, [1.0] * 21, [100_000] * 21)

    snapshot = run_historical_analysis_for_code(db_session, "hac", dates[-1])

    assert snapshot.stock_id == stock.id
    assert snapshot.as_of_date == dates[-1]


def test_run_historical_analysis_is_idempotent_for_same_bounded_input(db_session):
    stock = add_stock(db_session, code="HAI")
    dates = add_price_bars(db_session, stock, [1.0] * 21, [100_000] * 21)

    first = run_historical_analysis(db_session, stock, dates[-1])
    second = run_historical_analysis(db_session, stock, dates[-1])

    assert second.id == first.id
    assert db_session.query(HistoricalAnalysisSnapshot).count() == 1


def test_run_historical_analysis_rejects_unknown_stock_code(db_session):
    with pytest.raises(ValueError, match="stock MISSING not found"):
        run_historical_analysis_for_code(db_session, "missing", date(2026, 7, 4))


def test_run_historical_analysis_rejects_incomplete_inputs_without_saving(db_session):
    stock = Stock(code="NOP", name="No Prices", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    with pytest.raises(ValueError, match="historical analysis incomplete: no_price_bars"):
        run_historical_analysis(db_session, stock, date(2026, 7, 4))

    assert db_session.query(HistoricalAnalysisSnapshot).count() == 0
