import json
from pathlib import Path

from pypdf import PdfReader

from app.services.p3_classification_service import classify_announcement
from app.services.p3_section_detector import detect_sections


ROOT = Path(__file__).parents[2]
SAMPLES = {sample["sample_id"]: sample for sample in json.loads((ROOT / "docs/beta02-acceptance/samples.json").read_text(encoding="utf-8"))["samples"]}


def classify_sample(sample_id: str):
    sample = SAMPLES[sample_id]
    pages = [page.extract_text() or "" for page in PdfReader(ROOT / "docs/beta02-acceptance" / sample["local_pdf"]).pages]
    sections = detect_sections(pages)
    ranked = sorted(sections, key=lambda item: (0 if item["name"] in {"summary", "executive_summary"} else 1 if item["name"] == "highlights" else 2, item["page"]))
    if ranked:
        inputs = [item for item in ranked if item["page"] == ranked[0]["page"]][:2]
    else:
        inputs = [{"name": "body_fallback", "page": 1, "text": pages[0]}]
    prelim = classify_announcement(sample["headline"], sample["asx_raw_metadata"], [])
    if ranked and prelim.document.default_family == "F06":
        inputs.append({"name": "body_fallback", "page": 1, "text": pages[0]})
    if prelim.document.standard_form in {"Appendix 5B", "Appendix 4C"}:
        inputs.extend({"name": "standard_form", "page": number, "text": text} for number, text in enumerate(pages, 1) if any(marker in text.casefold() for marker in ("cash and cash equivalents", "net cash from", "quarter ended")))
    return classify_announcement(sample["headline"], sample["asx_raw_metadata"], inputs)


def _types(result):
    return {(event["primary_family"], event["event_type"]) for event in result.events}


def test_s01_dfs_delay_and_revision():
    result = classify_sample("S01")
    assert {("F04", "Project Delay"), ("F04", "Project Schedule / Timeline Update")}.issubset(_types(result))
    assert "Revised" in result.revision_tags
    assert all(not (event["event_type"].endswith("DFS") and event["event_status"] == "completed") for event in result.events)


def test_s02_quarterly_cash_flow_and_development_events():
    result = classify_sample("S02")
    assert {("F08", "Period-end Cash Position"), ("F08", "Periodic Cash Flow Update"), ("F04", "Engineering / FEED Update")}.issubset(_types(result))
    assert any(event["source_section"] == "standard_form" and event["source_page_start"] for event in result.events if event["primary_family"] == "F08")


def test_s03_firm_commitment_and_planned_spp_are_not_cash_received():
    result = classify_sample("S03")
    placement = next(event for event in result.events if event["event_type"] == "Placement")
    spp = next(event for event in result.events if event["event_type"] == "Share Purchase Plan / SPP")
    assert placement["event_status"] == "firm_commitments"
    assert spp["event_status"] == "planned"
    assert all(event["event_status"] != "funds_received" for event in result.events)


def test_s04_ore_reserve_is_not_a_new_mineral_resource_event():
    result = classify_sample("S04")
    assert ("F02", "Ore Reserve Update") in _types(result)
    assert ("F02", "Mineral Resource Update") not in _types(result)
    assert ("F04", "Project Schedule / Timeline Update") in _types(result)


def test_s05_drilling_can_coexist_with_study_transaction_and_cash():
    result = classify_sample("S05")
    families = {event["primary_family"] for event in result.events}
    assert {"F01", "F04", "F07", "F08"}.issubset(families)
    assert "F02" not in families


def test_s06_body_fallback_preserves_permit_states_and_requires_review():
    result = classify_sample("S06")
    statuses = {event["event_type"]: event["event_status"] for event in result.events}
    assert statuses["Clearing Permit Status"] == "granted"
    assert statuses["Groundwater Licence Status"] == "technical_support"
    assert statuses["Environmental Approval Status"] == "pending"
    assert result.review_needed is True


def test_s07_earn_in_is_conditional_and_manager_is_not_operator():
    result = classify_sample("S07")
    assert {("F07", "Farm-in / Farm-out"), ("F07", "Earn-in"), ("F07", "Joint Venture")}.issubset(_types(result))
    assert next(event for event in result.events if event["event_type"] == "Earn-in")["event_status"] == "conditional"
    assert all(event["event_type"] != "Operator Change" for event in result.events)


def test_s08_appendix_3y_is_not_a_core_event():
    result = classify_sample("S08")
    assert result.document.standard_form == "Appendix 3Y"
    assert result.events == []


def test_s09_metallurgy_test_results_are_not_operating_recovery():
    result = classify_sample("S09")
    assert {("F03", "Metallurgical Test Results"), ("F03", "Recovery / Product Grade"), ("F01", "Drilling Completed"), ("F08", "Period-end Cash Position")}.issubset(_types(result))
    assert all(event["event_type"] != "Production / Operational Periodic Update" for event in result.events)
    assert all(event["source_excerpt"] for event in result.events)
