"""Build or verify the offline P03 fixed-sample acceptance baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402
    Announcement, AssetUnit, AssetUnitIdentity, EvidenceDocument, Project,
    ProjectIdentity, Stock,
)
from app.services.p3_acceptance_baseline import (  # noqa: E402
    build_fixed_sample_baseline, compare_fixed_sample_baseline, measure_fixed_sample,
)
from app.services.p3_fact_rules import EXTRACTOR_VERSION  # noqa: E402
from app.services.p3_parse_service import PARSER_VERSION, parse_evidence  # noqa: E402
from app.services.stock_identity import normalize  # noqa: E402


BASELINE_PATH = ROOT / "docs/beta02-acceptance/p03-fixed-sample-baseline-v2.json"
PROJECTS = (
    ("caravel-copper", "Caravel Copper Project", "copper"),
    ("rincon-lithium", "Rincon Lithium Project", "lithium"),
    ("tonopah-lithium", "Tonopah Lithium Project", "lithium"),
    ("trident", "Trident", "gold"),
    ("tabba-tabba", "Tabba Tabba", "lithium"),
    ("manna-lithium", "Manna Lithium Project", "lithium"),
    ("nova-joint-venture", "Nova Joint Venture", None),
    ("gifford-creek", "Gifford Creek Critical Metals Project", "rare_earth"),
    ("plutonic-gold-belt", "Plutonic Gold Belt", "gold"),
)
ASSET_UNITS = (
    ("tabba-tabba", "Bolt Cutter Central", "prospect", "lithium"),
    ("gifford-creek", "Yin", "deposit", "rare_earth"),
    ("tabba-tabba", "Hutt", "pegmatite", "lithium"),
    ("tabba-tabba", "Chewy", "pegmatite", "lithium"),
    ("tabba-tabba", "Leia", "pegmatite", "lithium"),
)


def build_current_baseline(selected: set[str] | None = None) -> dict:
    samples = json.loads((ROOT / "docs/beta02-acceptance/samples.json").read_text(encoding="utf-8"))["samples"]
    samples = [sample for sample in samples if selected is None or sample["sample_id"] in selected]
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        _seed_approved_entities(db)
        measurements = []
        stocks: dict[str, Stock] = {}
        for sample in samples:
            stock = stocks.get(sample["ticker"])
            if stock is None:
                stock = Stock(code=sample["ticker"], name=f"{sample['ticker']} fixed-sample acceptance", commodity="unknown")
                db.add(stock); db.flush(); stocks[sample["ticker"]] = stock
            announcement = Announcement(
                stock_id=stock.id, ann_id=sample["asx_announcement_id"], headline=sample["headline"],
                ann_date=datetime.fromisoformat(sample["published_at"]), url=sample["pdf_url"],
                raw_payload=json.dumps(sample["asx_raw_metadata"]),
            )
            db.add(announcement); db.flush()
            pdf = ROOT / "docs/beta02-acceptance" / sample["local_pdf"]
            actual_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
            if actual_hash != sample["sha256"]:
                raise RuntimeError(f"{sample['sample_id']} fixture hash mismatch: {actual_hash}")
            evidence = EvidenceDocument(
                stock_id=stock.id, announcement_id=announcement.id, source_type="asx_pdf",
                source_id=announcement.ann_id, title=announcement.headline, document_date=announcement.ann_date,
                url=announcement.url, source_url=announcement.url, local_original_path=str(pdf),
                file_hash_sha256=actual_hash, page_count=sample["page_count"], download_status="downloaded",
                text_status="extracted", evidence_status="text_ready",
            )
            db.add(evidence); db.commit()
            run = parse_evidence(db, evidence)
            if run.status not in {"parsed", "review_needed"}:
                raise RuntimeError(f"{sample['sample_id']} parse failed: {run.error_message}")
            measurement = measure_fixed_sample(db, sample, run)
            measurement["fixture_sha256_verified"] = True
            measurements.append(measurement)
        return build_fixed_sample_baseline(
            measurements, parser_version=PARSER_VERSION, extractor_version=EXTRACTOR_VERSION
        )
    finally:
        db.close(); engine.dispose()


def _seed_approved_entities(db) -> None:
    projects: dict[str, Project] = {}
    for key, name, commodity in PROJECTS:
        project = Project(project_key=key, name=name, commodity=commodity, active=True)
        db.add(project); db.flush(); projects[key] = project
        db.add(ProjectIdentity(
            project_id=project.id, kind="name", value=name, normalized_value=normalize(name),
            is_current=True, source="p01_fixed_acceptance_catalog",
        ))
    for project_key, name, unit_type, commodity in ASSET_UNITS:
        asset = AssetUnit(
            project_id=projects[project_key].id, name=name, unit_type=unit_type,
            commodity_override=commodity, active=True,
        )
        db.add(asset); db.flush()
        db.add(AssetUnitIdentity(
            asset_unit_id=asset.id, kind="name", value=name, normalized_value=normalize(name),
            is_current=True, source="p01_fixed_acceptance_catalog",
        ))
    db.commit()


def _print_table(baseline: dict) -> None:
    print("Sample  Facts  Points  Summary  Table  Body  Review  Missing  Project / Asset Unit")
    for item in baseline["samples"]:
        missing = item["unfound_fields"]
        missing_count = len(missing["family_rule_slots"]) + len(missing["required_fact_types"])
        projects = [row["project"] for row in item["attribution"]["projects"]]
        assets = [f"{row['project']} / {row['asset_unit']}" for row in item["attribution"]["asset_units"]]
        assigned = "; ".join(projects + assets) or "Company"
        print(
            f"{item['sample_id']:<6} {item['atomic_fact_count']:>5} {item['information_point_count']:>7} "
            f"{item['summary_information_point_count']:>8} {item['table_information_point_count']:>6} "
            f"{item['body_fallback_information_point_count']:>5} {item['review_needed_count']:>7} "
            f"{missing_count:>8}  {assigned}"
        )
        if missing_count:
            print(f"       unfound={json.dumps(missing, ensure_ascii=False)}")
        company_count = item["attribution"]["company_level_atomic_fact_count"]
        if company_count:
            print(f"       company_level_atomic_facts={company_count}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print the full generated baseline JSON")
    parser.add_argument("--check", action="store_true", help=f"compare with {BASELINE_PATH.relative_to(ROOT)}")
    parser.add_argument("--samples", help="comma-separated sample IDs; default is every fixed sample")
    args = parser.parse_args()
    selected = {item.strip().upper() for item in args.samples.split(",")} if args.samples else None
    actual = build_current_baseline(selected)
    if args.json:
        print(json.dumps(actual, ensure_ascii=False, indent=2))
    else:
        _print_table(actual)
    if not args.check:
        return 0
    expected = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    drift = compare_fixed_sample_baseline(actual, expected)
    if drift:
        print(f"Baseline drift: {len(drift)} field(s)")
        print(json.dumps(drift, ensure_ascii=False, indent=2))
        return 1
    print("Baseline check passed: no measured drift.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
