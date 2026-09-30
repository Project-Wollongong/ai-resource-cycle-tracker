import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.api.routes import admin
from app.api.security import require_admin_access
from app.database import Base
from app.models import Announcement, AssetUnit, AssetUnitIdentity, EvidenceDocument, P3Fact, Project, ProjectIdentity, Stock
from app.services.p3_database_consistency_audit import audit_database_consistency
from app.services.p3_entity_matching import contains_identity
from app.services.p3_parse_service import parse_evidence


ROOT = Path(__file__).parents[2]
SAMPLES = {sample["sample_id"]: sample for sample in json.loads((ROOT / "docs/beta02-acceptance/samples.json").read_text(encoding="utf-8"))["samples"]}


def _file_database(tmp_path):
    db_path = tmp_path / "data" / "tracker.db"
    db_path.parent.mkdir(parents=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return db_path, engine, sessionmaker(bind=engine, expire_on_commit=False)()


def _seed_s01(db):
    sample = SAMPLES["S01"]
    stock = Stock(code="CVV", name="Caravel Minerals", commodity="copper")
    project = Project(project_key="caravel-copper", name="Caravel Copper Project", commodity="copper")
    db.add_all([stock, project]); db.flush()
    db.add(ProjectIdentity(project_id=project.id, kind="name", value=project.name, normalized_value=project.name.casefold(), is_current=True, source="approved_test"))
    announcement = Announcement(stock_id=stock.id, ann_id=sample["asx_announcement_id"], headline=sample["headline"], ann_date=datetime.fromisoformat(sample["published_at"]), url=sample["pdf_url"], raw_payload=json.dumps(sample["asx_raw_metadata"]))
    db.add(announcement); db.flush()
    evidence = EvidenceDocument(
        stock_id=stock.id, announcement_id=announcement.id, source_type="asx_pdf", source_id=announcement.ann_id,
        title=announcement.headline, document_date=announcement.ann_date, url=announcement.url, source_url=announcement.url,
        local_original_path=str(ROOT / "docs/beta02-acceptance" / sample["local_pdf"]), file_hash_sha256=sample["sha256"],
        page_count=sample["page_count"], download_status="downloaded", text_status="extracted", evidence_status="text_ready",
    )
    db.add(evidence); db.commit()
    return project, parse_evidence(db, evidence)


def test_identity_matching_uses_complete_tokens():
    assert contains_identity("Yin Rare Earths deposit", "Yin") is True
    assert contains_identity("previously tested samples were re-assaying material", "Yin") is False
    assert contains_identity("Bolt Cutter Central drilling", "Bolt Cutter Central") is True


def test_consistency_audit_passes_for_formal_single_database_and_company_layer(tmp_path):
    db_path, engine, db = _file_database(tmp_path)
    project, run = _seed_s01(db)
    facts = db.query(P3Fact).filter_by(parse_run_id=run.id).all()
    assert db.query(Project).count() == 1 and db.query(AssetUnit).count() == 0
    assert any(fact.project_id == project.id for fact in facts)
    assert any(fact.project_id is None and fact.asset_unit_id is None and fact.project_attribution_status == "unknown" for fact in facts)

    result = audit_database_consistency(
        db, repo_root=tmp_path, expected_db_path=db_path,
        expected_counts={"stocks": 1, "projects": 1, "asset_units": 0},
    )
    assert result["status"] == "pass"
    assert result["database"]["database_files"] == [str(db_path.resolve())]
    assert next(check for check in result["checks"] if check["code"] == "company_layer_attribution")["status"] == "pass"
    assert next(check for check in result["checks"] if check["code"] == "no_p3_entity_autocreation")["status"] == "pass"
    db.close(); engine.dispose()


def test_audit_detects_asset_project_mismatch_without_creating_entities(tmp_path):
    db_path, engine, db = _file_database(tmp_path)
    project, run = _seed_s01(db)
    other = Project(project_key="gifford-creek", name="Gifford Creek Critical Metals Project")
    db.add(other); db.flush()
    db.add(ProjectIdentity(project_id=other.id, kind="name", value=other.name, normalized_value=other.name.casefold(), is_current=True, source="approved_test"))
    asset = AssetUnit(project_id=other.id, name="Yin")
    db.add(asset); db.flush()
    db.add(AssetUnitIdentity(asset_unit_id=asset.id, value="Yin", normalized_value="yin", is_current=True, source="approved_test"))
    fact = db.query(P3Fact).filter_by(parse_run_id=run.id).first()
    fact.asset_unit_id = asset.id
    fact.project_id = project.id
    fact.project_attribution_status = "inferred_from_context"
    db.commit()

    result = audit_database_consistency(
        db, repo_root=tmp_path, expected_db_path=db_path,
        expected_counts={"stocks": 1, "projects": 2, "asset_units": 1},
    )
    check = next(item for item in result["checks"] if item["code"] == "latest_fact_entity_consistency")
    assert result["status"] == "fail" and check["status"] == "fail"
    assert check["evidence"]["samples"][0]["reason"] in {"asset_project_mismatch", "context_inference"}
    assert db.query(Project).count() == 2 and db.query(AssetUnit).count() == 1
    db.close(); engine.dispose()


def test_consistency_audit_lists_yfinance_cache_without_treating_it_as_domain_database(tmp_path):
    db_path, engine, db = _file_database(tmp_path)
    _seed_s01(db)
    cache_path = tmp_path / "data" / "yfinance_cache" / "tkr-tz.db"
    cache_path.parent.mkdir(parents=True)
    cache_path.touch()

    result = audit_database_consistency(
        db, repo_root=tmp_path, expected_db_path=db_path,
        expected_counts={"stocks": 1, "projects": 1, "asset_units": 0},
    )

    assert result["status"] == "pass"
    assert result["database"]["database_files"] == [str(db_path.resolve())]
    assert result["database"]["non_application_cache_files"] == [str(cache_path.resolve())]
    db.close(); engine.dispose()


def test_admin_database_consistency_api_is_read_only(tmp_path):
    db_path, engine, db = _file_database(tmp_path)
    _seed_s01(db)
    app = FastAPI(); app.include_router(admin.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin_access] = lambda: True
    before = (db.query(Project).count(), db.query(AssetUnit).count(), db.query(P3Fact).count())
    response = TestClient(app).get("/api/admin/p3/database-consistency")
    # The API uses production path expectations, so a temp DB intentionally fails
    # the path check while still returning the full read-only evidence payload.
    assert response.status_code == 200
    assert response.json()["audit_version"] == "p3_database_consistency_v1"
    assert before == (db.query(Project).count(), db.query(AssetUnit).count(), db.query(P3Fact).count())
    db.close(); engine.dispose()
