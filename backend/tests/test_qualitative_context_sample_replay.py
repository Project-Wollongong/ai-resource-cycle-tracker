import json
from datetime import datetime

from app.analysis.ai_stub import RuleBasedFullTextAnalyzer, insight_metrics_with_document
from app.models import Announcement, Stock
from app.services.qualitative_mining_context import enrich_qualitative_context


def _historical_metrics(grade_thickness: float):
    return {
        "intercepts": [
            {
                "width_m": 10,
                "grade": grade_thickness / 10,
                "unit": "g/t",
                "commodity": "gold",
                "depth_m": 80,
            }
        ],
        "project": "Bankan",
        "region": "Guinea",
    }


def test_rule_based_sample_replay_produces_quality_context(db_session):
    stock = Stock(code="TST", name="Test Resources", commodity="gold")
    db_session.add(stock)
    db_session.commit()
    for index, grade_thickness in enumerate([10, 20, 30, 40, 50]):
        db_session.add(
            Announcement(
                stock_id=stock.id,
                ann_id=f"hist-{index}",
                headline="Historical drill result",
                ann_date=datetime(2026, 1, index + 1),
                url="https://example.com/history.pdf",
                price_sensitive=True,
                ann_type="DRILL_RESULTS",
                type_score=85,
                matched_keywords="[]",
                raw_payload="{}",
                ai_metrics=json.dumps(_historical_metrics(grade_thickness)),
            )
        )
    db_session.commit()

    body = "Drilling at the Bankan Project returned 10m at 4.5 g/t Au from 70m."
    insight = RuleBasedFullTextAnalyzer().analyze(
        "High-Grade Drill Results",
        "DRILL_RESULTS",
        body_text=body,
    )

    assert insight is not None
    metrics = enrich_qualitative_context(
        db_session,
        stock.code,
        insight_metrics_with_document(insight, document=None),
        ann_type="DRILL_RESULTS",
        price_sensitive=True,
    )
    context = metrics["qualitative_context"]

    assert context["grade_thickness"] == 45
    assert context["project_percentile"] == 80
    assert context["extraction_quality"] == "partial"
    assert context["missing_fields"] == ["region"]
    assert "regional context unavailable because region is missing" in context["comparison_warnings"]
