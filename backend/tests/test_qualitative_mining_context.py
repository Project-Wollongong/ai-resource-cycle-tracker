import json
from datetime import datetime, timedelta

from app.models import Announcement, Stock
from app.services.qualitative_mining_context import (
    build_qualitative_context,
    build_qualitative_contexts,
    enrich_qualitative_context,
)


def _metrics(width, grade, unit="g/t", commodity="gold", depth=80, project="Bankan"):
    return {
        "intercepts": [
            {
                "width_m": width,
                "grade": grade,
                "unit": unit,
                "commodity": commodity,
                "depth_m": depth,
                "text": f"{width}m at {grade} {unit}",
            }
        ],
        "project": project,
        "commodities": [commodity],
    }


def _metrics_with_region(width, grade, region, unit="g/t", commodity="gold", depth=80, project="Bankan"):
    metrics = _metrics(width, grade, unit=unit, commodity=commodity, depth=depth, project=project)
    metrics["region"] = region
    return metrics


def _add_history(session, stock, values, project="Bankan", unit="g/t", commodity="gold", start=None, region=None):
    start = start or datetime(2026, 1, 1)
    for i, grade_thickness in enumerate(values):
        width = 10
        grade = grade_thickness / width
        session.add(
            Announcement(
                stock_id=stock.id,
                ann_id=f"hist-{project}-{unit}-{commodity}-{i}",
                headline="Historical drill result",
                ann_date=start + timedelta(days=i),
                url="https://example.com/history.pdf",
                price_sensitive=True,
                ann_type="DRILL_RESULTS",
                type_score=85,
                matched_keywords="[]",
                raw_payload="{}",
                ai_metrics=json.dumps(
                    _metrics_with_region(width, grade, region, unit=unit, commodity=commodity, project=project)
                    if region
                    else _metrics(width, grade, unit=unit, commodity=commodity, project=project)
                ),
            )
        )
    session.commit()


def test_build_context_returns_insufficient_history_without_comparables(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    context = build_qualitative_context(db_session, "TST", _metrics(12, 3.5, depth=90))

    assert context is not None
    assert context["grade_thickness"] == 42
    assert context["depth_category"] == "shallow"
    assert context["interval_quality_label"] == "insufficient_history"
    assert context["company_percentile"] is None
    assert context["project_percentile"] is None
    assert context["trend_vs_previous"] == "insufficient_history"
    assert context["company_history_count"] == 0
    assert context["project_history_count"] == 0
    assert "insufficient company history" in context["reason"]
    assert "not enough stored comparable company or project history" in context["qualitative_assessment"]
    assert "company comparable history n=0" in context["reason"]
    assert "project comparable history n=0" in context["reason"]


def test_build_context_calculates_project_percentile(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Bankan")

    context = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4.5, depth=70, project="Bankan"),
        ann_type="DRILL_RESULTS",
        price_sensitive=True,
    )

    assert context is not None
    assert context["grade_thickness"] == 45
    assert context["company_percentile"] == 80
    assert context["project_percentile"] == 80
    assert context["company_history_count"] == 5
    assert context["project_history_count"] == 5
    assert context["extraction_quality"] == "partial"
    assert context["missing_fields"] == ["region"]
    assert "regional context unavailable because region is missing" in context["comparison_warnings"]
    assert context["interval_quality_label"] == "strong"
    assert context["materiality_label"] == "high"
    assert context["trend_vs_previous"] == "improving"
    assert "announcement type is DRILL_RESULTS" in context["reason"]
    assert "price_sensitive is true" in context["reason"]
    assert "company comparable history n=5" in context["reason"]
    assert "project comparable history n=5" in context["reason"]
    assert "comparison limited to same stock, commodity, and unit" in context["reason"]


def test_build_context_materiality_requires_drill_result_and_price_sensitive(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Bankan")

    not_drill = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4.5, depth=70, project="Bankan"),
        ann_type="OTHER",
        price_sensitive=True,
    )
    not_sensitive = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4.5, depth=70, project="Bankan"),
        ann_type="DRILL_RESULTS",
        price_sensitive=False,
    )
    deep = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4.5, depth=350, project="Bankan"),
        ann_type="DRILL_RESULTS",
        price_sensitive=True,
    )

    assert not_drill is not None
    assert not_sensitive is not None
    assert deep is not None
    assert not_drill["interval_quality_label"] == "strong"
    assert not_sensitive["interval_quality_label"] == "strong"
    assert deep["interval_quality_label"] == "strong"
    assert not_drill["materiality_label"] == "medium"
    assert not_sensitive["materiality_label"] == "medium"
    assert deep["materiality_label"] == "medium"


def test_build_context_materiality_is_low_for_weak_project_percentile(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [40, 50, 60, 70, 80], project="Bankan")

    context = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 3, depth=70, project="Bankan"),
        ann_type="DRILL_RESULTS",
        price_sensitive=True,
    )

    assert context is not None
    assert context["interval_quality_label"] == "weak"
    assert context["materiality_label"] == "low"


def test_build_context_qualitative_assessment_uses_neutral_template(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Bankan")

    with_history = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4.5, depth=70, project="Bankan"),
        ann_type="DRILL_RESULTS",
        price_sensitive=True,
    )
    no_history = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4.5, depth=70, project="Other"),
        ann_type="DRILL_RESULTS",
        price_sensitive=True,
    )

    assert with_history is not None
    assert no_history is not None
    assert with_history["qualitative_assessment"] == (
        "Within the stored project history, this interval ranks as strong, with grade-thickness "
        "in the 80th percentile, shallow depth, and high materiality."
    )
    assert no_history["qualitative_assessment"] == (
        "Stored project history is insufficient; within the company's comparable stored history, "
        "this interval ranks as strong, with grade-thickness in the 80th percentile, shallow depth, "
        "and high materiality."
    )
    combined = f"{with_history['qualitative_assessment']} {no_history['qualitative_assessment']}".lower()
    for forbidden in ("buy", "sell", "share price", "upside", "investment advice", "major positive"):
        assert forbidden not in combined


def test_build_context_uses_company_percentile_when_project_history_is_insufficient(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Bankan")

    context = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4.5, depth=70, project="Other"),
        ann_type="DRILL_RESULTS",
        price_sensitive=True,
    )

    assert context is not None
    assert context["company_percentile"] == 80
    assert context["project_percentile"] is None
    assert context["company_history_count"] == 5
    assert context["project_history_count"] == 0
    assert context["interval_quality_label"] == "strong"
    assert context["materiality_label"] == "high"
    assert "within the company's comparable stored history" in context["qualitative_assessment"]


def test_build_context_requires_minimum_project_history(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20], project="Bankan")

    context = build_qualitative_context(db_session, "TST", _metrics(10, 4.5, project="Bankan"))

    assert context is not None
    assert context["project_percentile"] is None
    assert "insufficient project history" in context["reason"]


def test_build_context_project_percentile_and_trend_require_same_project(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Other")

    context = build_qualitative_context(db_session, "TST", _metrics(10, 4.5, project="Bankan"))

    assert context is not None
    assert context["project_percentile"] is None
    assert context["trend_vs_previous"] == "improving"
    assert context["trend_basis"] == "company"
    assert "trend uses company history because project history is insufficient" in context["comparison_warnings"]
    assert "insufficient project history" in context["reason"]


def test_build_context_project_percentile_requires_same_stock_code(db_session):
    current = Stock(code="TST", name="Test Resources", commodity="gold")
    other = Stock(code="OTH", name="Other Resources", commodity="gold")
    db_session.add_all([current, other])
    db_session.commit()
    _add_history(db_session, other, [10, 20, 30, 40, 50], project="Bankan")

    context = build_qualitative_context(db_session, "TST", _metrics(10, 4.5, project="Bankan"))

    assert context is not None
    assert context["project_percentile"] is None
    assert "insufficient project history" in context["reason"]


def test_build_context_classifies_depth_boundaries(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    cases = [
        (None, "unknown"),
        (100, "shallow"),
        (101, "medium"),
        (300, "medium"),
        (301, "deep"),
    ]

    for depth, expected in cases:
        context = build_qualitative_context(db_session, "TST", _metrics(10, 4.5, depth=depth))

        assert context is not None
        assert context["depth_category"] == expected


def test_build_context_does_not_label_quality_when_history_is_missing(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    exceptional = build_qualitative_context(db_session, "TST", _metrics(20, 6, depth=90))
    strong_deep = build_qualitative_context(db_session, "TST", _metrics(10, 6, depth=350))
    moderate_unknown = build_qualitative_context(db_session, "TST", _metrics(10, 3, depth=None))
    weak = build_qualitative_context(db_session, "TST", _metrics(10, 1, depth=80))

    assert exceptional is not None
    assert strong_deep is not None
    assert moderate_unknown is not None
    assert weak is not None
    assert exceptional["interval_quality_label"] == "insufficient_history"
    assert strong_deep["interval_quality_label"] == "insufficient_history"
    assert moderate_unknown["interval_quality_label"] == "insufficient_history"
    assert weak["interval_quality_label"] == "insufficient_history"
    assert exceptional["materiality_label"] == "insufficient_history"
    assert "insufficient company history" in exceptional["reason"]


def test_build_context_keeps_units_and_commodities_comparable(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Bankan", unit="%", commodity="copper")

    context = build_qualitative_context(db_session, "TST", _metrics(10, 4.5, unit="ppm", commodity="gold"))

    assert context is not None
    assert context["project_percentile"] is None
    assert context["company_percentile"] is None
    assert context["interval_quality_label"] == "insufficient_history"


def test_build_context_normalizes_gold_ppm_to_gt(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Bankan", unit="ppm", commodity="gold")

    context = build_qualitative_context(db_session, "TST", _metrics(10, 4.5, unit="ppm", commodity="gold"))

    assert context is not None
    assert context["project_percentile"] == 80
    assert context["company_percentile"] == 80
    assert context["normalized_unit"] == "g/t"
    assert "unit normalized from ppm to g/t" in context["comparison_warnings"]
    assert context["interval_quality_label"] == "strong"


def test_build_context_does_not_compare_same_unit_different_commodity(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="lithium")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Bankan", unit="%", commodity="copper")

    context = build_qualitative_context(db_session, "TST", _metrics(10, 4.5, unit="%", commodity="lithium"))

    assert context is not None
    assert context["project_percentile"] is None
    assert context["company_percentile"] is None
    assert context["interval_quality_label"] == "insufficient_history"


def test_build_context_normalizes_ppm_to_percent_for_base_metals(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="copper")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [0.1, 0.2, 0.3, 0.4, 0.5], project="Bankan", unit="%", commodity="copper")

    context = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4500, unit="ppm", commodity="copper", project="Bankan"),
    )

    assert context is not None
    assert context["grade_thickness"] == 4.5
    assert context["normalized_unit"] == "%"
    assert context["project_percentile"] == 100


def test_build_context_uses_regional_history_when_company_history_is_insufficient(db_session):
    current = Stock(code="TST", name="Test Resources", commodity="gold")
    peer = Stock(code="OTH", name="Other Resources", commodity="gold")
    db_session.add_all([current, peer])
    db_session.commit()
    _add_history(db_session, peer, [10, 20, 30, 40, 50], project="Other", region="Pilbara")

    context = build_qualitative_context(
        db_session,
        "TST",
        _metrics_with_region(10, 4.5, region="Pilbara", project="Bankan"),
        ann_type="DRILL_RESULTS",
        price_sensitive=True,
    )

    assert context is not None
    assert context["company_percentile"] is None
    assert context["project_percentile"] is None
    assert context["regional_percentile"] == 80
    assert context["regional_history_count"] == 5
    assert context["extraction_quality"] == "complete"
    assert context["missing_fields"] == []
    assert context["interval_quality_label"] == "strong"
    assert "comparable stored regional history" in context["qualitative_assessment"]


def test_build_context_marks_missing_project_region_and_depth(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    context = build_qualitative_context(
        db_session,
        "TST",
        _metrics(10, 4.5, depth=None, project=None),
    )

    assert context is not None
    assert context["extraction_quality"] == "partial"
    assert context["missing_fields"] == ["project", "region", "depth_m"]
    assert "project history insufficient" in context["comparison_warnings"]
    assert "company history insufficient" in context["comparison_warnings"]
    assert "trend history insufficient" in context["comparison_warnings"]


def test_build_context_detects_flat_and_deteriorating_trends(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [40, 42, 44, 46, 48], project="Bankan")

    flat = build_qualitative_context(db_session, "TST", _metrics(10, 4.4, project="Bankan"))
    weak = build_qualitative_context(db_session, "TST", _metrics(10, 3.0, project="Bankan"))

    assert flat is not None
    assert weak is not None
    assert flat["trend_vs_previous"] == "flat"
    assert weak["trend_vs_previous"] == "deteriorating"


def test_build_context_trend_uses_recent_project_history_only(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [5, 5, 5, 5, 5], project="Other")
    _add_history(db_session, stock, [10, 20, 100, 110, 120, 130], project="Bankan", start=datetime(2026, 2, 1))

    context = build_qualitative_context(db_session, "TST", _metrics(10, 11.5, project="Bankan"))

    assert context is not None
    assert context["trend_vs_previous"] == "flat"


def test_enrich_qualitative_context_adds_new_metrics_key(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    enriched = enrich_qualitative_context(db_session, "TST", _metrics(9, 5, depth=350))

    assert "qualitative_context" in enriched
    assert enriched["qualitative_context"]["grade_thickness"] == 45
    assert enriched["qualitative_context"]["depth_category"] == "deep"


def test_build_contexts_returns_context_for_each_valid_intercept(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    _add_history(db_session, stock, [10, 20, 30, 40, 50], project="Bankan")
    metrics = _metrics(10, 4.5, project="Bankan")
    metrics["intercepts"].append(
        {
            "width_m": 20,
            "grade": 1.5,
            "unit": "g/t",
            "commodity": "gold",
            "depth_m": 180,
            "text": "20m at 1.5 g/t",
        }
    )
    metrics["intercepts"].append({"width_m": 0, "grade": 99, "unit": "g/t", "commodity": "gold"})

    contexts = build_qualitative_contexts(
        db_session,
        "TST",
        metrics,
        ann_type="DRILL_RESULTS",
        price_sensitive=True,
    )

    assert len(contexts) == 2
    assert contexts[0]["intercept_index"] == 0
    assert contexts[0]["grade_thickness"] == 45
    assert contexts[0]["depth_category"] == "shallow"
    assert contexts[1]["intercept_index"] == 1
    assert contexts[1]["grade_thickness"] == 30
    assert contexts[1]["depth_category"] == "medium"
    assert contexts[1]["width_m"] == 20
    assert contexts[1]["grade"] == 1.5


def test_enrich_keeps_primary_context_and_adds_context_list(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    metrics = _metrics(10, 4.5)
    metrics["intercepts"].append(
        {
            "width_m": 5,
            "grade": 8,
            "unit": "g/t",
            "commodity": "gold",
            "depth_m": 60,
            "text": "5m at 8 g/t",
        }
    )

    enriched = enrich_qualitative_context(db_session, "TST", metrics)

    assert enriched["qualitative_context"]["intercept_index"] == 0
    assert len(enriched["qualitative_contexts"]) == 2
    assert enriched["qualitative_contexts"][0] == enriched["qualitative_context"]
