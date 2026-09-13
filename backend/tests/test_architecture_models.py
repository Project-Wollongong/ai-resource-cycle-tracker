import json
from datetime import date, datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app import models


def test_beta02_architecture_tables_are_registered(db_session):
    inspector = inspect(db_session.bind)

    expected = {
        "projects",
        "stock_projects",
        "evidence_documents",
        "p3_facts",
        "p3_statements",
        "p4_features",
        "analytical_signals",
        "fusion_records",
        "attention_states",
        "trade_decisions",
        "positions",
        "position_events",
        "trade_reviews",
        "strategy_learning_candidates",
    }

    assert expected.issubset(set(inspector.get_table_names()))


def test_beta02_minimal_lineage_records_can_be_persisted(db_session):
    stock = models.Stock(code="OD6", name="OD6 Metals", commodity="rare_earth")
    project = models.Project(
        project_key="od6-splinter-rock",
        name="Splinter Rock",
        commodity="rare_earth",
        region="Esperance",
        jurisdiction="WA",
    )
    db_session.add_all([stock, project])
    db_session.commit()

    db_session.add(
        models.StockProject(
            stock_id=stock.id,
            project_id=project.id,
            relationship_type="owner",
            ownership_pct=100.0,
        )
    )
    evidence = models.EvidenceDocument(
        stock_id=stock.id,
        project_id=project.id,
        source_type="asx_announcement",
        source_id="OD6-2026-001",
        title="Drilling results",
        document_date=datetime(2026, 9, 10, 9, 30),
        url="https://example.test/od6.pdf",
        content_hash="sha256:example",
    )
    db_session.add(evidence)
    db_session.commit()

    fact = models.P3Fact(
        evidence_document_id=evidence.id,
        stock_id=stock.id,
        project_id=project.id,
        fact_type="drilling_intercept",
        schema_name="drilling_v1",
        field_name="grade_thickness",
        value_json=json.dumps({"width_m": 42, "grade": 2.1}),
        unit="m_pct",
        confidence=0.92,
        source_page=6,
        extractor_version="rules_fulltext_v1",
    )
    statement = models.P3Statement(
        evidence_document_id=evidence.id,
        stock_id=stock.id,
        project_id=project.id,
        statement_type="expansion_potential",
        statement_text="Mineralisation remains open at depth.",
        source_page=7,
        confidence=0.8,
        extractor_version="rules_fulltext_v1",
    )
    db_session.add_all([fact, statement])
    db_session.commit()

    feature = models.P4Feature(
        stock_id=stock.id,
        project_id=project.id,
        evidence_document_id=evidence.id,
        as_of_date=date(2026, 9, 10),
        feature_group="drilling",
        feature_name="grade_thickness",
        value_json=json.dumps(88.2),
        unit="m_pct",
        input_refs_json=json.dumps([{"p3_fact_id": fact.id}]),
        formula_version="grade_thickness_v1",
    )
    analytical_signal = models.AnalyticalSignal(
        stock_id=stock.id,
        engine="fundamental",
        signal_date=date(2026, 9, 10),
        direction="positive",
        magnitude=75.0,
        confidence=0.78,
        persistence="medium",
        source_event_id=evidence.source_id,
        dependency_group=evidence.source_id,
        evidence_ids_json=json.dumps([evidence.id, statement.id]),
        feature_ids_json=json.dumps([feature.id]),
        logic_version="fundamental_v1",
    )
    db_session.add_all([feature, analytical_signal])
    db_session.commit()

    fusion = models.FusionRecord(
        stock_id=stock.id,
        fusion_date=date(2026, 9, 10),
        opportunity_strength="moderate",
        confidence="medium",
        signal_structure="early_formation",
        evidence_independence="single_event",
        official_result="moderate",
        shadow_result="strong",
        conflict_flag=True,
        analytical_signal_ids_json=json.dumps([analytical_signal.id]),
        rule_version="fusion_rules_v1",
    )
    db_session.add(fusion)
    db_session.commit()

    attention = models.AttentionState(
        stock_id=stock.id,
        fusion_record_id=fusion.id,
        state_level="L2",
        state_label="Active Watch",
        previous_state_level="L1",
        transition="upgrade",
        reason="Moderate early formation from stored drilling evidence.",
        compute_profile="normal_extraction",
        alert_priority="dashboard",
        rule_version="attention_rules_v1",
    )
    db_session.add(attention)
    db_session.commit()

    assert attention.id is not None


def test_project_and_evidence_identity_constraints(db_session):
    project = models.Project(project_key="duplicate-key", name="Project")
    db_session.add(project)
    db_session.commit()

    db_session.add(models.Project(project_key="duplicate-key", name="Duplicate"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    stock = models.Stock(code="ABC", name="ABC Ltd", commodity="gold")
    db_session.add(stock)
    db_session.commit()

    db_session.add_all(
        [
            models.EvidenceDocument(
                stock_id=stock.id,
                source_type="asx_announcement",
                source_id="ABC-001",
            ),
            models.EvidenceDocument(
                stock_id=stock.id,
                source_type="asx_announcement",
                source_id="ABC-001",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
