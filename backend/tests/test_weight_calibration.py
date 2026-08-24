from datetime import date, timedelta

import pytest

from app.models import ScoreSnapshot, SignalReturn
from app.services.config_service import DEFAULTS, set_config
from app.services.weight_calibration import calibrate_weights

from test_backtest import add_signal, add_stock


def add_snapshot(
    session,
    stock,
    d,
    funding=50,
    announcement=50,
    resource=50,
    commodity=50,
    risk=50,
    sentiment=50,
):
    weights = DEFAULTS["weights"]
    session.add(
        ScoreSnapshot(
            stock_id=stock.id,
            date=d,
            funding_score=funding,
            announcement_score=announcement,
            resource_score=resource,
            commodity_score=commodity,
            risk_score=risk,
            sentiment_score=sentiment,
            cycle_score=(
                weights["announcement"] * announcement
                + weights["resource"] * resource
                + weights["commodity"] * commodity
                + weights["risk"] * risk
                + weights["sentiment"] * sentiment
            ),
            label="Monitor",
            components="{}",
        )
    )
    session.commit()


def fill_signal_return(session, signal, ret, bench=0.0, horizon=20):
    sr = session.query(SignalReturn).filter_by(signal_id=signal.id, horizon_days=horizon).one()
    sr.status = "filled"
    sr.entry_price = 1.0
    sr.return_pct = ret
    sr.benchmark_return_pct = bench
    session.commit()


def test_weight_calibration_recommends_predictive_subscore(db_session):
    stock = add_stock(db_session)
    start = date(2026, 1, 5)

    for i in range(12):
        d = start + timedelta(days=i)
        sentiment = 10 + i * 7
        announcement = 80 - i * 3
        add_snapshot(db_session, stock, d, sentiment=sentiment, announcement=announcement)
        sig = add_signal(
            db_session,
            stock,
            d,
            label="Monitor",
            cycle_score=50,
            horizons=(20,),
        )
        # Sentiment intentionally predicts the target; announcement moves the other way.
        fill_signal_return(db_session, sig, ret=i * 2.0, bench=0.0)

    result = calibrate_weights(db_session, horizon_days=20, target="excess", min_sample=10)

    assert result["sample_size"] == 12
    assert result["low_sample"] is False
    assert result["recommended_weights"]["sentiment"] > result["current_weights"]["sentiment"]
    assert result["recommended_weights"]["announcement"] < result["current_weights"]["announcement"]
    assert sum(result["recommended_weights"].values()) == pytest.approx(1.0)
    sentiment_diag = next(d for d in result["diagnostics"] if d["subscore"] == "sentiment")
    assert sentiment_diag["correlation"] > 0.99


def test_weight_calibration_keeps_current_weights_on_low_sample(db_session):
    stock = add_stock(db_session)
    current_weights = {
        "announcement": 0.35,
        "resource": 0.2,
        "commodity": 0.2,
        "risk": 0.1,
        "sentiment": 0.15,
    }
    set_config(db_session, "weights", current_weights)
    d = date(2026, 1, 5)
    add_snapshot(db_session, stock, d, sentiment=90, announcement=20)
    sig = add_signal(db_session, stock, d, horizons=(20,))
    fill_signal_return(db_session, sig, ret=10, bench=1)

    result = calibrate_weights(db_session, horizon_days=20, target="excess", min_sample=10)

    assert result["sample_size"] == 1
    assert result["low_sample"] is True
    assert result["recommended_weights"] == result["current_weights"]


def test_weight_calibration_rejects_invalid_target(db_session):
    with pytest.raises(ValueError):
        calibrate_weights(db_session, target="alpha")
