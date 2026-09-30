"""Import the source-backed P01 baseline from the fixed ASX review set.

This script deliberately imports only the explicitly listed, page-located candidates.
Rows remain marked source_candidate until a human reviewer confirms materiality.
"""
import json
from datetime import datetime
from pathlib import Path

from app.database import SessionLocal, init_db
from app.models import (
    AssetUnit,
    AssetUnitIdentity,
    CommodityRelationship,
    EvidenceDocument,
    Project,
    ProjectIdentity,
    ProjectRelationship,
    Stock,
    StockProject,
)
from app.services.stock_identity import normalize

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "docs/beta02-acceptance/samples.json"

# Only names explicitly present in the fixed ASX sample register are included.
PROJECTS = [
    ("CVV", "caravel-copper", "Caravel Copper Project", "copper", "S01", "dfs_release_timing"),
    ("AGY", "rincon-lithium", "Rincon Lithium Project", "lithium", "S02", "project_development"),
    ("AGY", "tonopah-lithium", "Tonopah Lithium Project", "lithium", "S02", "project_development"),
    ("CYL", "trident", "Trident", "gold", "S04", "trident_underground_reserve"),
    ("CYL", "plutonic-gold-belt", "Plutonic Gold Belt", "gold", "S04", "trident_underground_reserve"),
    ("WC8", "tabba-tabba", "Tabba Tabba", "lithium", "S05", "bcrc115_intersections"),
    ("GL1", "manna-lithium", "Manna Lithium Project", "lithium", "S06", "clearing_permit_status"),
    ("DYL", "nova-joint-venture", "Nova Joint Venture", None, "S07", "earn_in_terms"),
    ("DRE", "gifford-creek", "Gifford Creek Critical Metals Project", "rare_earth", "S10", "study_and_approval_work"),
]
ASSETS = [
    ("tabba-tabba", "bolt-cutter-central", "Bolt Cutter Central", "prospect", "lithium", "S05", "bcrc115_intersections"),
    ("tabba-tabba", "hutt", "Hutt", "pegmatite", "lithium", "S05", "tamt038_intersection"),
    ("tabba-tabba", "chewy", "Chewy", "pegmatite", "lithium", "S05", "tamt038_intersection"),
    ("tabba-tabba", "leia", "Leia", "pegmatite", "lithium", "S05", "tamt038_intersection"),
    ("gifford-creek", "yin", "Yin", "deposit", "rare_earth", "S10", "mining_lease_application"),
]
RELATIONSHIPS = [
    ("AGY", "rincon-lithium", "jv_interest", 77.5, None, "S02", "rincon_interest"),
    ("DYL", "nova-joint-venture", "operator_reference", None, "RMR", "S07", "current_jv_interests"),
]


def main():
    init_db()
    samples = {s["sample_id"]: s for s in json.loads(SAMPLES.read_text(encoding="utf-8"))["samples"]}
    with SessionLocal() as db:
        evidence_by_sample = {}
        for sample_id, sample in samples.items():
            evidence = db.query(EvidenceDocument).filter_by(source_type="asx_pdf", source_id=sample["asx_announcement_id"]).one_or_none()
            if evidence is None:
                evidence = EvidenceDocument(
                    stock_id=db.query(Stock).filter_by(code=sample["ticker"]).one().id,
                    source_type="asx_pdf",
                    source_id=sample["asx_announcement_id"],
                    title=sample["headline"],
                    url=sample["pdf_url"],
                    metadata_json=json.dumps({"sample_id": sample_id, "pdf_page": sample.get("source_review", {}).get("pages", [1])[0], "status": "source_candidate"}, ensure_ascii=False),
                )
                db.add(evidence)
                db.flush()
            evidence_by_sample[sample_id] = evidence

        project_by_key = {}
        for ticker, key, name, commodity, sample_id, fact_field in PROJECTS:
            stock = db.query(Stock).filter_by(code=ticker).one()
            sample = samples[sample_id]
            fact = next((f for f in sample.get("facts", []) if f.get("field") == fact_field), {})
            project = db.query(Project).filter_by(project_key=key).one_or_none()
            if project is None:
                project = Project(project_key=key, name=name, commodity=commodity, active=True, metadata_json=json.dumps({"verification_status": "source_candidate", "source_sample_id": sample_id, "source_document_key": sample["asx_announcement_id"], "source_pdf_page": fact.get("pdf_page", 1), "source_excerpt": fact.get("source_excerpt", "")}, ensure_ascii=False))
                db.add(project)
                db.flush()
            project_by_key[key] = project
            if not db.query(ProjectIdentity).filter_by(project_id=project.id, kind="name", normalized_value=normalize(name)).first():
                db.add(ProjectIdentity(project_id=project.id, kind="name", value=name, normalized_value=normalize(name), is_current=True, source=f"asx:{sample['asx_announcement_id']}"))
            if not db.query(StockProject).filter_by(stock_id=stock.id, project_id=project.id).first():
                db.add(StockProject(stock_id=stock.id, project_id=project.id, relationship_type="related_stock", metadata_json=json.dumps({"verification_status": "source_candidate", "source_sample_id": sample_id}, ensure_ascii=False)))
            if commodity and not db.query(CommodityRelationship).filter_by(project_id=project.id, commodity=commodity).first():
                db.add(CommodityRelationship(project_id=project.id, commodity=commodity, relationship_type="economic_exposure", is_economic=True, source=f"asx:{sample['asx_announcement_id']}"))

        for parent_key, key, name, unit_type, commodity, sample_id, fact_field in ASSETS:
            project = project_by_key[parent_key]
            sample = samples[sample_id]
            fact = next((f for f in sample.get("facts", []) if f.get("field") == fact_field), {})
            asset = db.query(AssetUnit).filter_by(project_id=project.id, name=name).one_or_none()
            if asset is None:
                asset = AssetUnit(project_id=project.id, name=name, unit_type=unit_type, commodity_override=commodity, active=True)
                db.add(asset)
                db.flush()
            asset.metadata_json = json.dumps({"verification_status": "source_candidate", "source_sample_id": sample_id, "source_document_key": sample["asx_announcement_id"], "source_pdf_page": fact.get("pdf_page", 1), "source_excerpt": fact.get("source_excerpt", "")}, ensure_ascii=False) if hasattr(asset, "metadata_json") else None
            if not db.query(AssetUnitIdentity).filter_by(asset_unit_id=asset.id, normalized_value=normalize(name)).first():
                db.add(AssetUnitIdentity(asset_unit_id=asset.id, kind="name", value=name, normalized_value=normalize(name), is_current=True, source=f"asx:{sample['asx_announcement_id']}"))
            if not db.query(CommodityRelationship).filter_by(asset_unit_id=asset.id, commodity=commodity).first():
                db.add(CommodityRelationship(asset_unit_id=asset.id, commodity=commodity, relationship_type="economic_exposure", is_economic=True, source=f"asx:{sample['asx_announcement_id']}"))
        for ticker, project_key, relationship_type, ownership_pct, operator_name, sample_id, fact_field in RELATIONSHIPS:
            stock = db.query(Stock).filter_by(code=ticker).one()
            project = project_by_key[project_key]
            sample = samples[sample_id]
            fact = next((f for f in sample.get("facts", []) if f.get("field") == fact_field), {})
            exists = db.query(ProjectRelationship).filter_by(stock_id=stock.id, project_id=project.id, relationship_type=relationship_type).first()
            if exists is None:
                db.add(ProjectRelationship(stock_id=stock.id, project_id=project.id, relationship_type=relationship_type, ownership_pct=ownership_pct, operator_name=operator_name, source=f"asx:{sample['asx_announcement_id']}", source_page=fact.get("pdf_page", 1), source_excerpt=fact.get("source_excerpt", "")))
        db.commit()
        print("P01 source-backed baseline imported; all rows remain verification_status=source_candidate")


if __name__ == "__main__":
    main()
