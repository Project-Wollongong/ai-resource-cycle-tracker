import copy
import importlib.util
import json
from pathlib import Path

from app.services.p3_acceptance_baseline import compare_fixed_sample_baseline


ROOT = Path(__file__).parents[2]
BASELINE = ROOT / "docs/beta02-acceptance/p03-fixed-sample-baseline-v2.json"


def _builder_module():
    path = ROOT / "scripts/verify_p03_facts.py"
    spec = importlib.util.spec_from_file_location("verify_p03_facts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_all_fixed_samples_match_the_frozen_information_point_baseline():
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    actual = _builder_module().build_current_baseline()

    assert expected["sample_count"] == 10
    assert compare_fixed_sample_baseline(actual, expected) == []
    assert all(item["fixture_sha256_verified"] for item in actual["samples"])
    assert all(item["reconciliation"]["all_atomic_facts_grouped"] for item in actual["samples"])
    assert all(item["reconciliation"]["all_points_source_counted"] for item in actual["samples"])


def test_baseline_keeps_information_point_target_separate_from_fact_volume():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    by_id = {item["sample_id"]: item for item in baseline["samples"]}

    drilling = by_id["S05"]
    assert drilling["atomic_fact_count"] == 74
    assert drilling["information_point_count"] == 18
    assert drilling["source_insufficient"] is True
    assert baseline["counting_policy"]["target_is_not_a_quota"] is True
    assert baseline["counting_policy"]["no_padding"] is True


def test_baseline_reports_missing_fields_and_conservative_attribution():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    by_id = {item["sample_id"]: item for item in baseline["samples"]}

    assert by_id["S08"]["atomic_fact_count"] == 0  # Appendix 3Y routing-only negative sample
    assert by_id["S10"]["unfound_fields"]["required_fact_types"] == ["permit_status", "permit_type"]
    assert by_id["S10"]["attribution"]["projects"] == []
    assert by_id["S10"]["attribution"]["asset_units"] == []
    assert by_id["S01"]["attribution"]["company_level_atomic_fact_count"] == 3

    approved_assets = {"Bolt Cutter Central", "Hutt", "Chewy", "Leia", "Yin"}
    reported_assets = {
        asset["asset_unit"]
        for item in baseline["samples"]
        for asset in item["attribution"]["asset_units"]
    }
    assert reported_assets <= approved_assets


def test_baseline_comparator_exposes_count_drift():
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    actual = copy.deepcopy(expected)
    actual["samples"][0]["information_point_count"] += 1

    drift = compare_fixed_sample_baseline(actual, expected)

    assert drift == [{"sample_id": "S01", "field": "information_point_count", "expected": 5, "actual": 6}]
