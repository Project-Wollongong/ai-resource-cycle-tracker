from datetime import datetime

from app.services.market_data_standard import normalize_market_row


def test_market_data_normalization_is_explicit_and_non_predictive():
    row = normalize_market_row({"date": datetime(2026, 9, 1, 16, 0), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}, instrument_code="CVV", instrument_type="stock", source="yahoo", source_symbol="CVV.AX", currency="AUD", timezone="Australia/Perth", is_adjusted="false")
    assert row["trading_date"].isoformat() == "2026-09-01"
    assert row["is_adjusted"] == "false"
    assert row["quality_status"] == "ok"
    assert "ma" not in row and "rsi" not in row and "return" not in row


def test_market_data_quality_flags_missing_and_negative_values():
    row = normalize_market_row({"date": "2026-09-01", "close": -1}, instrument_code="X", instrument_type="index", source="mock", source_symbol="X")
    assert row["quality_status"] == "review_needed"
    assert "missing_volume" in row["quality_flags"]
    assert "negative_value_review_needed" in row["quality_flags"]
