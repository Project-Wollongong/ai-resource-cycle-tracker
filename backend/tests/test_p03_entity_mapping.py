from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import admin, p3
from app.api.security import require_admin_access
from app.models import (
    Announcement,
    AssetUnit,
    AssetUnitIdentity,
    EntityMapping,
    EntityMention,
    EvidenceDocument,
    P01EntityProposal,
    P3Event,
    P3Fact,
    P3ParseRun,
    Project,
    ProjectIdentity,
    Stock,
    StockProject,
)
from app.services.entity_resolution_service import resolve_entities_for_run
from app.services.entity_exact_matcher import normalize_entity_name


def _base(db, code="AAA"):
    stock = Stock(code=code, name=f"{code} Resources", commodity="copper")
    db.add(stock); db.flush()
    ann = Announcement(stock_id=stock.id, ann_id=f"ANN-{code}", headline="Entity update", ann_date=datetime(2026, 9, 1))
    db.add(ann); db.flush()
    evidence = EvidenceDocument(
        stock_id=stock.id, announcement_id=ann.id, source_type="fixture", source_id=f"DOC-{code}",
        title=ann.headline, document_date=ann.ann_date, text_status="extracted",
    )
    db.add(evidence); db.flush()
    run = P3ParseRun(
        evidence_document_id=evidence.id, announcement_id=ann.id, parser_name="test",
        parser_version="entity-v1", input_hash=code * 10, status="running",
    )
    db.add(run); db.flush()
    return stock, ann, evidence, run


def _project(db, stock, key, name):
    project = Project(project_key=key, name=name, commodity="copper")
    db.add(project); db.flush()
    db.add(StockProject(stock_id=stock.id, project_id=project.id, relationship_type="owner"))
    db.flush()
    return project


def _event(db, ann, evidence, run, text, page=1):
    event = P3Event(
        announcement_id=ann.id, evidence_document_id=evidence.id, parse_run_id=run.id,
        stock_id=ann.stock_id, event_type="PROJECT_UPDATE", event_family="F04", primary_family="F04",
        event_title="Project update", source_section="highlights", source_page_start=page,
        source_page_end=page, source_excerpt=text,
    )
    db.add(event); db.flush()
    return event


def _fact(db, ann, evidence, run, event, text):
    fact = P3Fact(
        announcement_id=ann.id, evidence_document_id=evidence.id, parse_run_id=run.id,
        p3_event_id=event.id, stock_id=ann.stock_id, fact_type="project_name", fact_family="F04",
        schema_name="test", field_name="Project", value_raw="Project Alpha", value_json="{}",
        source_section="highlights", source_page_start=1, source_page_end=1, source_excerpt=text,
    )
    db.add(fact); db.flush()
    return fact


def _client(db):
    app = FastAPI(); app.include_router(admin.router, prefix="/api"); app.include_router(p3.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin_access] = lambda: True
    return TestClient(app)


def test_exact_name_normalization_is_limited_and_deterministic():
    assert normalize_entity_name("  Alpha—Copper   Project. ") == "alpha copper project"
    assert normalize_entity_name("Project Alpha") != normalize_entity_name("Alpha Copper Project")


def test_project_alpha_alias_maps_to_current_project_and_links_event_and_fact(db_session):
    stock, ann, evidence, run = _base(db_session)
    project = _project(db_session, stock, "alpha-copper", "Alpha Copper Project")
    alias = ProjectIdentity(
        project_id=project.id, kind="alias", value="Project Alpha", normalized_value="project alpha",
        is_current=False, source="approved_fixture",
    )
    db_session.add(alias); db_session.flush()
    text = "Highlights: Project Alpha remains on schedule."
    event = _event(db_session, ann, evidence, run, text)
    fact = _fact(db_session, ann, evidence, run, event, text)

    mentions, mappings = resolve_entities_for_run(db_session, run, [event], [fact])
    db_session.commit()

    assert len(mentions) == 2  # same name in Event and Fact keeps both contexts
    assert all(item.source_page_start == 1 and item.source_excerpt == text for item in mentions)
    assert all(item.match_method == "alias_match" and item.matched_alias_id == alias.id for item in mappings)
    assert all(item.status == "confirmed" for item in mappings)
    db_session.refresh(event); db_session.refresh(fact)
    assert event.mapped_project_id == project.id and event.project_mapping_status == "confirmed"
    assert fact.mapped_project_id == project.id and fact.project_mapping_status == "confirmed"

    payload = _client(db_session).get(f"/api/announcements/{ann.ann_id}/entity-mappings").json()
    assert payload[0]["mention_text_raw"] == "Project Alpha"
    assert payload[0]["matched_entity"]["name"] == "Alpha Copper Project"
    assert payload[0]["matched_alias"]["value"] == "Project Alpha"


def test_current_project_and_asset_names_exact_match_with_parent_validation(db_session):
    stock, ann, evidence, run = _base(db_session, "AAB")
    project = _project(db_session, stock, "tabba", "Tabba Tabba")
    asset = AssetUnit(project_id=project.id, name="Bolt Cutter Central", unit_type="deposit")
    db_session.add(asset); db_session.flush()
    text = "Tabba Tabba drilling at Bolt Cutter Central is complete."
    event = _event(db_session, ann, evidence, run, text)

    _, mappings = resolve_entities_for_run(db_session, run, [event], [])
    db_session.commit()
    confirmed = [item for item in mappings if item.status == "confirmed"]
    assert {(item.matched_entity_type, item.matched_entity_id) for item in confirmed} == {
        ("project", project.id), ("asset_unit", asset.id)
    }
    asset_mapping = next(item for item in confirmed if item.matched_entity_type == "asset_unit")
    assert asset_mapping.match_method == "exact_match"
    assert asset_mapping.parent_validation_result == "parent_project_confirmed"
    assert event.mapped_project_id == project.id and event.mapped_asset_unit_id == asset.id


def test_approved_old_asset_name_uses_alias_and_preserves_both_names(db_session):
    stock, ann, evidence, run = _base(db_session, "AAC")
    project = _project(db_session, stock, "gifford", "Gifford Creek")
    asset = AssetUnit(project_id=project.id, name="Yin", unit_type="deposit")
    db_session.add(asset); db_session.flush()
    identity = AssetUnitIdentity(
        asset_unit_id=asset.id, kind="alias", value="Yin Prospect", normalized_value="yin prospect",
        is_current=False, source="approved_fixture",
    )
    db_session.add(identity); db_session.flush()
    event = _event(db_session, ann, evidence, run, "Gifford Creek includes the Yin Prospect.")

    _, mappings = resolve_entities_for_run(db_session, run, [event], [])
    mapping = next(item for item in mappings if item.matched_entity_type == "asset_unit")
    assert mapping.status == "confirmed" and mapping.match_method == "alias_match"
    payload = _client(db_session).get(f"/api/p3/events/{event.id}/entity-mappings").json()
    asset_payload = next(item for item in payload if item["mention_type"] == "asset_unit")
    assert asset_payload["mention_text_raw"] == "Yin Prospect"
    assert asset_payload["matched_entity"]["name"] == "Yin"


def test_same_project_name_different_stocks_uses_relationship_and_does_not_merge(db_session):
    stock_a, ann, evidence, run = _base(db_session, "AAD")
    stock_b = Stock(code="ZZZ", name="ZZZ Resources", commodity="gold")
    db_session.add(stock_b); db_session.flush()
    project_a = _project(db_session, stock_a, "shared-a", "Shared Project")
    project_b = _project(db_session, stock_b, "shared-b", "Shared Project")
    event = _event(db_session, ann, evidence, run, "Shared Project development update.")

    _, mappings = resolve_entities_for_run(db_session, run, [event], [])
    db_session.commit()
    assert next(item for item in mappings if item.matched_entity_id == project_a.id).status == "confirmed"
    assert next(item for item in mappings if item.matched_entity_id == project_b.id).status == "review_needed"
    assert event.mapped_project_id == project_a.id
    assert db_session.query(Project).count() == 2


def test_missing_stock_relationship_and_parent_conflict_stay_review_needed_and_hidden(db_session):
    stock, ann, evidence, run = _base(db_session, "AAE")
    unrelated = Project(project_key="unrelated", name="Unrelated Project")
    parent = _project(db_session, stock, "parent", "Parent Project")
    other = _project(db_session, stock, "other", "Other Project")
    db_session.add(unrelated); db_session.flush()
    asset = AssetUnit(project_id=parent.id, name="Central Zone", unit_type="zone")
    db_session.add(asset); db_session.flush()
    event1 = _event(db_session, ann, evidence, run, "Unrelated Project update.")
    event2 = _event(db_session, ann, evidence, run, "Other Project work at Central Zone.", page=2)
    counts_before = (db_session.query(Project).count(), db_session.query(AssetUnit).count(), db_session.query(P01EntityProposal).count())

    _, mappings = resolve_entities_for_run(db_session, run, [event1, event2], [])
    db_session.commit()
    assert all(item.status == "review_needed" for item in mappings if item.matched_entity_id in {unrelated.id, asset.id})
    asset_mapping = next(item for item in mappings if item.matched_entity_type == "asset_unit")
    assert asset_mapping.parent_validation_result == "parent_project_conflict"
    assert event1.mapped_project_id is None and event1.project_mapping_status == "review_needed"
    assert event2.mapped_asset_unit_id is None and event2.asset_unit_mapping_status == "review_needed"
    assert counts_before == (db_session.query(Project).count(), db_session.query(AssetUnit).count(), db_session.query(P01EntityProposal).count())

    client = _client(db_session)
    ordinary = client.get(f"/api/p3/events/{event1.id}/entity-mappings").json()[0]
    assert ordinary["matched_entity"] is None and ordinary["matched_entity_id"] is None
    admin_rows = client.get("/api/admin/p3/entity-mappings/review-needed").json()
    assert any(item["candidate_entity"]["name"] == "Unrelated Project" for item in admin_rows)


def test_ambiguous_asset_without_explicit_parent_and_partial_names_do_not_match(db_session):
    stock, ann, evidence, run = _base(db_session, "AAF")
    project_a = _project(db_session, stock, "north", "North Project")
    project_b = _project(db_session, stock, "south", "South Project")
    db_session.add_all([
        AssetUnit(project_id=project_a.id, name="Twin Zone"),
        AssetUnit(project_id=project_b.id, name="Twin Zone"),
    ]); db_session.flush()
    ambiguous = _event(db_session, ann, evidence, run, "Results from Twin Zone are reported.")
    partial = _event(db_session, ann, evidence, run, "Results from North are reported.", page=2)

    mentions, mappings = resolve_entities_for_run(db_session, run, [ambiguous, partial], [])
    assert len([item for item in mentions if item.p3_event_id == ambiguous.id]) == 1
    assert all(item.status == "ambiguous" for item in mappings)
    assert not [item for item in mentions if item.p3_event_id == partial.id]
    assert ambiguous.mapped_asset_unit_id is None and ambiguous.asset_unit_mapping_status == "review_needed"


def test_former_project_name_is_distinct_from_alias(db_session):
    stock, ann, evidence, run = _base(db_session, "AAG")
    project = _project(db_session, stock, "new-name", "New Name Project")
    identity = ProjectIdentity(
        project_id=project.id, kind="name", value="Old Name Project", normalized_value="old name project",
        is_current=False, source="approved_fixture",
    )
    db_session.add(identity); db_session.flush()
    event = _event(db_session, ann, evidence, run, "Old Name Project update.")
    _, mappings = resolve_entities_for_run(db_session, run, [event], [])
    assert mappings[0].status == "confirmed"
    assert mappings[0].match_method == "former_name_match"
    assert mappings[0].matched_alias_id == identity.id


def test_nested_asset_unit_parent_is_validated_when_named(db_session):
    stock, ann, evidence, run = _base(db_session, "AAH")
    project = _project(db_session, stock, "nested", "Nested Project")
    parent = AssetUnit(project_id=project.id, name="Central Deposit", unit_type="deposit")
    db_session.add(parent); db_session.flush()
    child = AssetUnit(project_id=project.id, parent_asset_unit_id=parent.id, name="Eastern Zone", unit_type="zone")
    db_session.add(child); db_session.flush()
    event = _event(db_session, ann, evidence, run, "Nested Project: Eastern Zone within Central Deposit.")

    _, mappings = resolve_entities_for_run(db_session, run, [event], [])
    child_mapping = next(item for item in mappings if item.matched_entity_type == "asset_unit" and item.matched_entity_id == child.id)
    assert child_mapping.status == "confirmed"
    assert child_mapping.parent_validation_result == "parent_project_and_asset_unit_confirmed"
