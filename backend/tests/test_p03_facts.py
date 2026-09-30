import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import admin, p3
from app.api.security import require_admin_access
from app.models import Announcement, EvidenceDocument, P3Fact, P3FactReview, P3InformationPoint, Project, ProjectIdentity, Stock
from app.services.p3_information_point_service import information_point_summary
from app.services.p3_parse_service import parse_evidence
from app.services.p3_section_detector import detect_sections
from app.services.p3_summary_fact_pipeline import extract_summary_first_candidates, split_summary_bullets
from pypdf import PdfReader


ROOT = Path(__file__).parents[2]
SAMPLES = {sample["sample_id"]: sample for sample in json.loads((ROOT / "docs/beta02-acceptance/samples.json").read_text(encoding="utf-8"))["samples"]}


def _parse_sample(db, sample_id: str, suffix: str = ""):
    sample = SAMPLES[sample_id]
    stock = Stock(code=f"{sample['ticker']}{suffix}"[:10], name=f"{sample['ticker']} test", commodity="unknown")
    db.add(stock); db.flush()
    if sample_id == "S01":
        project = Project(project_key=f"caravel{suffix.casefold()}", name="Caravel Copper Project", commodity="copper")
        db.add(project); db.flush()
        db.add(ProjectIdentity(project_id=project.id, kind="name", value="Caravel Copper Project", normalized_value="caravel copper project", is_current=True, source="test"))
    ann_id = f"{sample['asx_announcement_id']}{suffix}"
    ann = Announcement(
        stock_id=stock.id, ann_id=ann_id, headline=sample["headline"],
        ann_date=datetime.fromisoformat(sample["published_at"]), url=sample["pdf_url"],
        raw_payload=json.dumps(sample["asx_raw_metadata"]),
    )
    db.add(ann); db.flush()
    pdf = ROOT / "docs/beta02-acceptance" / sample["local_pdf"]
    evidence = EvidenceDocument(
        stock_id=stock.id, announcement_id=ann.id, source_type="asx_pdf",
        source_id=ann_id, title=ann.headline, document_date=ann.ann_date, url=ann.url,
        source_url=ann.url, local_original_path=str(pdf), file_hash_sha256=sample["sha256"],
        page_count=sample["page_count"], download_status="downloaded", text_status="extracted",
        evidence_status="text_ready",
    )
    db.add(evidence); db.commit()
    run = parse_evidence(db, evidence)
    assert run.status in {"parsed", "review_needed"}, run.error_message
    facts = db.query(P3Fact).filter_by(parse_run_id=run.id).all()
    return ann, evidence, run, facts


@pytest.mark.parametrize(
    ("sample_id", "required"),
    [
        ("S01", {"study_type", "dfs_completion", "original_timing", "timeline_change", "fid_timing", "capex_review"}),
        ("S02", {"reporting_period", "cash_balance", "operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "development_spend"}),
        ("S03", {"funding_amount", "funding_method", "issue_price", "new_securities_issued", "spp_limit", "use_of_funds"}),
        ("S04", {"reported_increase", "tonnage", "grade", "contained_metal", "classification", "mine_life", "first_ore_timing"}),
        ("S05", {"hole_id", "interval_length", "grade", "from_depth", "true_width", "resource_estimate_target", "cash_balance"}),
        ("S06", {"permit_type", "permit_status", "permit_identifier", "area", "expiry_date", "authority"}),
        ("S07", {"transaction_type", "earn_in_amount", "earn_in_percentage", "maximum_ownership", "current_ownership", "manager"}),
        ("S09", {"testwork_type", "recovery", "product_grade", "processing_route", "sample_count", "drilling_status"}),
    ],
)
def test_fixed_samples_extract_family_facts_with_lineage(db_session, sample_id, required):
    _, evidence, run, facts = _parse_sample(db_session, sample_id)
    assert required.issubset({fact.fact_type for fact in facts})
    assert all(fact.p3_event_id and fact.evidence_document_id == evidence.id and fact.parse_run_id == run.id for fact in facts)
    assert all(fact.source_page_start and fact.source_excerpt and fact.value_raw for fact in facts)
    assert all(fact.fact_type != "cash_runway" for fact in facts)


def test_periods_statuses_and_boundaries_are_not_conflated(db_session):
    _, _, _, quarterly = _parse_sample(db_session, "S02", "Q")
    operating = next(fact for fact in quarterly if fact.fact_type == "operating_cash_flow")
    assert operating.value_numeric == -220
    assert operating.period_start.isoformat() == "2026-04-01"
    assert operating.period_end.isoformat() == "2026-06-30"
    assert json.loads(operating.metadata_json)["year_to_date_raw"] == "(415)"
    operating_facts = [fact for fact in quarterly if fact.fact_type == "operating_cash_flow"]
    assert {json.loads(fact.metadata_json)["period_basis"] for fact in operating_facts} == {"current_quarter", "year_to_date"}
    assert {fact.value_numeric for fact in operating_facts} == {-220, -415}
    ytd = next(fact for fact in operating_facts if json.loads(fact.metadata_json)["period_basis"] == "year_to_date")
    assert ytd.period_start.isoformat() == "2026-01-01" and ytd.period_end.isoformat() == "2026-06-30"

    _, _, _, funding = _parse_sample(db_session, "S03", "F")
    assert next(fact for fact in funding if fact.fact_type == "funding_amount").status == "committed"
    assert all(fact.status != "received" for fact in funding)

    _, _, _, permits = _parse_sample(db_session, "S06", "P")
    groundwater = next(fact for fact in permits if fact.field_name == "Groundwater Licence Status")
    assert groundwater.status == "technical_support"
    assert json.loads(groundwater.metadata_json)["not_formally_granted"] is True

    _, _, _, transaction = _parse_sample(db_session, "S07", "T")
    maximum = next(fact for fact in transaction if fact.fact_type == "maximum_ownership")
    assert maximum.status == "conditional"
    assert not any(fact.field_name == "Operator" for fact in transaction)


def test_unconfirmed_fact_attribution_stays_at_company_level(db_session):
    _, _, _, facts = _parse_sample(db_session, "S01", "E")
    f04 = [fact for fact in facts if fact.fact_family == "F04"]
    explicit = [fact for fact in f04 if "Caravel Copper Project" in fact.source_excerpt]
    company_level = [fact for fact in f04 if fact.fact_type in {"fid_timing", "capex_review"}]
    assert explicit and all(fact.project_id is not None for fact in explicit)
    assert company_level and all(fact.project_id is None and fact.asset_unit_id is None for fact in company_level)
    assert all(fact.project_attribution_status == "unknown" for fact in company_level)


def test_resource_reserve_and_testwork_boundaries(db_session):
    _, _, _, resources = _parse_sample(db_session, "S04", "R")
    probable = [fact for fact in resources if json.loads(fact.metadata_json).get("classification") == "Probable"]
    assert probable and all(json.loads(fact.metadata_json)["resource_or_reserve_type"] == "Ore Reserve" for fact in probable)
    historical = [fact for fact in resources if fact.status == "historical_reference"]
    assert historical and all(json.loads(fact.metadata_json)["resource_or_reserve_type"] == "Mineral Resource" for fact in historical)
    increases = [fact for fact in resources if fact.fact_type == "reported_increase"]
    assert {fact.value_numeric for fact in increases} == {30, 32}
    assert all(fact.review_status == "review_needed" for fact in increases)

    _, _, _, metallurgy = _parse_sample(db_session, "S09", "M")
    recovery = next(fact for fact in metallurgy if fact.fact_type == "recovery")
    assert json.loads(recovery.metadata_json)["scope"] == "sighter_testwork"
    assert recovery.status == "reported"


def test_fact_api_filters_history_and_human_review(db_session):
    ann, _, _, facts = _parse_sample(db_session, "S01", "A")
    fact = next(item for item in facts if item.fact_type == "dfs_completion")
    app = FastAPI(); app.include_router(admin.router, prefix="/api"); app.include_router(p3.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin_access] = lambda: True
    client = TestClient(app)

    listed = client.get(f"/api/announcements/{ann.ann_id}/facts?family=F04&fact_type=dfs_completion")
    assert listed.status_code == 200 and len(listed.json()) == 1
    payload = listed.json()[0]
    assert payload["source_page"] == 1 and payload["event"] and payload["evidence_document"]

    corrected = client.put(f"/api/admin/p3/facts/{fact.id}", json={"reviewer": "tester", "review_note": "verified against page 1", "value_text": "Q4 2026"})
    assert corrected.status_code == 200 and corrected.json()["review_status"] == "confirmed"
    assert db_session.get(P3Fact, fact.id).original_extraction_json
    assert db_session.query(P3FactReview).filter_by(p3_fact_id=fact.id, action="correct").count() == 1
    history = client.get(f"/api/p3/facts/{fact.id}/history")
    assert history.status_code == 200 and history.json()["reviews"][0]["action"] == "correct"

    rerun = parse_evidence(db_session, db_session.get(EvidenceDocument, fact.evidence_document_id), parser_version="p3_reported_fact_v2")
    assert rerun.id != fact.parse_run_id
    assert db_session.get(P3Fact, fact.id).review_status == "confirmed"
    effective = client.get(f"/api/announcements/{ann.ann_id}/facts?fact_type=dfs_completion").json()
    assert any(item["id"] == fact.id for item in effective)


def test_missing_currency_is_preserved_as_unknown_and_needs_review(db_session):
    _, _, _, facts = _parse_sample(db_session, "S03", "U")
    amount = next(fact for fact in facts if fact.fact_type == "funding_amount")
    assert amount.currency_raw == "$"
    assert amount.currency_normalized == "unknown"
    assert amount.review_status == "review_needed"


def test_automatic_rerun_links_but_does_not_delete_previous_fact(db_session):
    _, evidence, first, facts = _parse_sample(db_session, "S02", "V")
    old = next(fact for fact in facts if fact.fact_type == "cash_balance")
    second = parse_evidence(db_session, evidence, parser_version="p3_reported_fact_v2")
    assert second.id != first.id
    db_session.refresh(old)
    assert old.superseded_by_id is not None
    assert old.active_result is False
    assert db_session.get(P3Fact, old.id) is not None


def test_information_point_groups_timeline_facts_without_padding(db_session):
    _, _, run, facts = _parse_sample(db_session, "S01", "I")
    points = db_session.query(P3InformationPoint).filter_by(parse_run_id=run.id).all()
    timeline = next(point for point in points if point.point_type == "timeline_change")
    component_types = {link.fact.fact_type for link in timeline.fact_links}
    assert {"dfs_completion", "original_timing", "timeline_change"}.issubset(component_types)
    assert timeline.fact_count == len(timeline.fact_links)
    assert len(points) < len(facts)
    summary = information_point_summary(points, len(facts))
    assert summary["count_status"] == "source_insufficient"
    assert summary["source_insufficient"] is True
    assert summary["target_min"] == 20 and summary["target_max"] == 50


def test_drill_intersection_is_one_point_with_atomic_components(db_session):
    _, _, run, _ = _parse_sample(db_session, "S05", "D")
    points = db_session.query(P3InformationPoint).filter_by(parse_run_id=run.id, point_type="drill_intersection").all()
    assert len(points) >= 10
    assert all({"hole_id", "interval_length", "grade", "from_depth"}.issubset({link.fact.fact_type for link in point.fact_links}) for point in points)
    assert all("@" in point.point_title and "from" in point.point_title for point in points)
    sample = points[0]
    ordered = [link.fact for link in sample.fact_links]
    assert [fact.fact_type for fact in ordered[:4]] == ["hole_id", "interval_length", "grade", "from_depth"]
    assert [fact.display_order for fact in ordered] == list(range(len(ordered)))
    assert all(fact.information_point_group_id == sample.id for fact in ordered)
    assert all(fact.information_point_type == "drill_intersection" for fact in ordered)
    assert ordered[0].parent_fact_id is None
    assert all(fact.parent_fact_id == ordered[0].id for fact in ordered[1:])


def test_reserve_table_row_and_cash_flow_are_logical_points(db_session):
    _, _, reserve_run, _ = _parse_sample(db_session, "S04", "G")
    reserve = next(point for point in db_session.query(P3InformationPoint).filter_by(parse_run_id=reserve_run.id, point_type="resource_reserve_row"))
    reserve_types = {link.fact.fact_type for link in reserve.fact_links}
    assert {"resource_or_reserve_type", "classification", "tonnage", "grade", "contained_metal"}.issubset(reserve_types)

    _, _, cash_run, _ = _parse_sample(db_session, "S02", "C")
    operating = db_session.query(P3InformationPoint).filter_by(parse_run_id=cash_run.id, point_type="operating_cash_flow").all()
    assert len(operating) == 2
    assert all(point.fact_count == 1 and point.source_section == "standard_form" for point in operating)
    assert any("Current Quarter" in point.point_title for point in operating)
    assert any("Year-to-Date" in point.point_title for point in operating)


def test_information_point_api_exposes_counts_sources_and_components(db_session):
    ann, _, _, _ = _parse_sample(db_session, "S01", "N")
    app = FastAPI(); app.include_router(p3.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    points = client.get(f"/api/announcements/{ann.ann_id}/information-points")
    assert points.status_code == 200 and points.json()
    assert {"point_type", "point_title", "fact_count", "source_section", "source_excerpt", "facts", "information_point_group_id", "information_point_type", "primary_fact_id"}.issubset(points.json()[0])
    component = points.json()[0]["facts"][0]
    assert {"information_point_group_id", "information_point_type", "parent_fact_id", "display_order"}.issubset(component)
    summary = client.get(f"/api/announcements/{ann.ann_id}/information-point-summary")
    assert summary.status_code == 200
    assert summary.json()["information_point_count"] == len(points.json())
    assert summary.json()["policy"].startswith("20-50")


def test_fact_api_filters_by_information_point_group_and_type(db_session):
    ann, _, run, _ = _parse_sample(db_session, "S05", "IP")
    point = db_session.query(P3InformationPoint).filter_by(parse_run_id=run.id, point_type="drill_intersection").first()
    app = FastAPI(); app.include_router(p3.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    payload = client.get(
        f"/api/announcements/{ann.ann_id}/facts",
        params={"information_point_group_id": point.id, "information_point_type": "drill_intersection"},
    ).json()
    assert len(payload) == point.fact_count
    assert {item["information_point_group_id"] for item in payload} == {point.id}
    assert [item["display_order"] for item in payload] == sorted(item["display_order"] for item in payload)


def _event(family: str, event_type: str):
    return SimpleNamespace(primary_family=family, event_type=event_type, event_title=event_type, active_result=True)


def test_summary_bullets_include_nested_and_inline_compound_items():
    text = """• Parent statement
o First nested fact
o Second nested fact • Inline third fact
continued detail"""
    assert split_summary_bullets(text) == [
        "Parent statement", "First nested fact", "Second nested fact", "Inline third fact continued detail",
    ]


def test_summary_first_splits_compound_bullet_into_multiple_facts_without_body():
    summary = (
        "• Maiden metallurgical (sighter) test work completed • Average recovery of 82.5% "
        "with an average product grade of 5.66% Li2O generated from three composites "
        "• Whole of Ore Flotation method"
    )
    pages = [summary + "\nBODY SHOULD NOT BE READ"]
    events = [
        _event("F03", "Metallurgical Test Results"),
        _event("F03", "Recovery / Product Grade"),
        _event("F03", "Processing Route"),
    ]
    candidates, audit = extract_summary_first_candidates(
        events, pages, [{"name": "summary", "page": 1, "text": summary}], None
    )
    assert {"testwork_type", "recovery", "product_grade", "sample_count", "processing_route"}.issubset(
        {item["fact_type"] for item in candidates}
    )
    assert audit["summary_bullet_count"] == 3
    assert audit["body_fallback_used"] is False
    assert audit["remaining_missing_fields"] == []
    assert all(item["source_section"] == "summary" for item in candidates)
    assert all(item["metadata"]["summary_bullet_index"] in {1, 2, 3} for item in candidates)


def test_missing_summary_fields_are_completed_from_body_only_after_gap_check():
    summary = "• received firm commitments to raise A$3 million • Placement"
    body = summary + "\nissue of 83,333,334 fully paid ordinary shares at A$0.036 per share. Net proceeds from the Placement to be used for project development."
    candidates, audit = extract_summary_first_candidates(
        [_event("F06", "Placement")], [body], [{"name": "highlights", "page": 1, "text": summary}], None
    )
    assert audit["missing_after_summary"] == ["F06.issue_price", "F06.new_securities", "F06.use_of_funds"]
    assert audit["standard_form_used"] is False
    assert audit["body_fallback_used"] is True
    assert audit["remaining_missing_fields"] == []
    assert next(item for item in candidates if item["fact_type"] == "funding_amount")["source_section"] == "highlights"
    assert next(item for item in candidates if item["fact_type"] == "issue_price")["source_section"] == "body_fallback"


def test_appendix_5b_uses_standard_form_for_f08_gaps_before_body():
    sample = SAMPLES["S02"]
    pdf = ROOT / "docs/beta02-acceptance" / sample["local_pdf"]
    pages = [page.extract_text() or "" for page in PdfReader(str(pdf)).pages]
    candidates, audit = extract_summary_first_candidates(
        [_event("F08", "Quarterly Activities"), _event("F08", "Periodic Cash Flow Update")],
        pages, detect_sections(pages), "Appendix 5B",
    )
    assert audit["missing_after_summary"]
    assert audit["standard_form_used"] is True
    assert audit["standard_form_fact_count"] > 0
    assert audit["body_fallback_used"] is False
    assert audit["remaining_missing_fields"] == []
    assert {"reporting_period", "cash_balance", "operating_cash_flow", "investing_cash_flow", "financing_cash_flow"}.issubset(
        {item["fact_type"] for item in candidates}
    )


def test_parse_run_persists_summary_first_audit_and_bullet_lineage(db_session):
    ann, _, run, facts = _parse_sample(db_session, "S03", "SF")
    audit = json.loads(run.output_summary_json)["fact_extraction"]
    grouping = json.loads(run.output_summary_json)["information_point_grouping"]
    assert audit["policy"].startswith("summary_bullets")
    assert audit["summary_bullet_count"] >= 3
    assert audit["body_fallback_used"] is True
    assert any(json.loads(fact.metadata_json).get("summary_bullet_index") for fact in facts if fact.source_section == "highlights")
    assert grouping["all_facts_preserved"] is True
    assert grouping["grouped_fact_count"] == len(facts)
    assert grouping["information_point_count"] <= grouping["atomic_fact_count"]

    app = FastAPI(); app.include_router(p3.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    payload = TestClient(app).get(f"/api/announcements/{ann.ann_id}/parse-status").json()
    assert payload["fact_extraction"]["summary_bullet_count"] == audit["summary_bullet_count"]
    assert payload["information_point_grouping"]["all_facts_preserved"] is True
