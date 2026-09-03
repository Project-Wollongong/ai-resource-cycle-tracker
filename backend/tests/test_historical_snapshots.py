from datetime import date
import json

from app.models import HistoricalAnalysisSnapshot
from app.services.historical_input import build_historical_analysis_input
from app.services.historical_scoring import score_historical_analysis_input
from app.services.historical_snapshots import save_historical_analysis_snapshot

from test_historical_scoring import add_price_bars, add_stock


def test_save_historical_analysis_snapshot_persists_score_result(db_session):
    stock = add_stock(db_session, code="HSV")
    dates = add_price_bars(db_session, stock, [1.0] * 21, [100_000] * 21)
    payload = build_historical_analysis_input(db_session, stock, dates[-1])
    score = score_historical_analysis_input(payload)

    snapshot = save_historical_analysis_snapshot(db_session, stock, payload, score)

    assert snapshot.id is not None
    assert snapshot.stock_id == stock.id
    assert snapshot.as_of_date == dates[-1]
    assert snapshot.market_data_as_of == dates[-1]
    assert snapshot.input_hash == payload["input_hash"]
    assert snapshot.cycle_score == score["cycle_score"]
    assert snapshot.label == score["label"]
    assert json.loads(snapshot.input_summary)["last_price_date"] == dates[-1].isoformat()
    assert json.loads(snapshot.components)["weights"] == payload["config"]["weights"]
    assert json.loads(snapshot.config_snapshot)["label_thresholds"] == payload["config"]["label_thresholds"]


def test_save_historical_analysis_snapshot_is_idempotent_for_same_input_hash(db_session):
    stock = add_stock(db_session, code="HID")
    dates = add_price_bars(db_session, stock, [1.0] * 21, [100_000] * 21)
    payload = build_historical_analysis_input(db_session, stock, dates[-1])
    score = score_historical_analysis_input(payload)

    first = save_historical_analysis_snapshot(db_session, stock, payload, score)
    second = save_historical_analysis_snapshot(db_session, stock, payload, score)

    assert second.id == first.id
    assert db_session.query(HistoricalAnalysisSnapshot).count() == 1


def test_save_historical_analysis_snapshot_allows_new_version_for_changed_input_hash(db_session):
    stock = add_stock(db_session, code="HVR")
    dates = add_price_bars(db_session, stock, [1.0] * 21, [100_000] * 21)
    payload = build_historical_analysis_input(db_session, stock, dates[-1])
    score = score_historical_analysis_input(payload)
    first = save_historical_analysis_snapshot(db_session, stock, payload, score)

    changed_payload = {**payload, "input_hash": "b" * 64}
    changed_score = {**score, "input_hash": "b" * 64}
    second = save_historical_analysis_snapshot(db_session, stock, changed_payload, changed_score)

    assert second.id != first.id
    assert db_session.query(HistoricalAnalysisSnapshot).count() == 2
    assert {row.input_hash for row in db_session.query(HistoricalAnalysisSnapshot).all()} == {
        payload["input_hash"],
        "b" * 64,
    }


def test_save_historical_analysis_snapshot_rejects_incomplete_score(db_session):
    stock = add_stock(db_session, code="HRJ")
    payload = {
        "as_of": {
            "as_of_date": date(2026, 7, 4),
            "as_of_cutoff": date(2026, 7, 4),
        },
        "input_hash": "a" * 64,
    }

    try:
        save_historical_analysis_snapshot(
            db_session,
            stock,
            payload,
            {"status": "incomplete", "input_hash": "a" * 64},
        )
    except ValueError as exc:
        assert "successful" in str(exc)
    else:
        raise AssertionError("expected ValueError")
