import pytest

from app.analysis.p3_family_classifier import classify_families
from app.services.p3_classification_service import classify_announcement
from app.services.p3_family_rules import FAMILY_ORDER


def _events(title: str, summary: str, payload=None):
    return classify_announcement(title, payload or {}, [{"name": "highlights", "page": 1, "text": summary}]).events


def test_family_delivery_order_is_product_order():
    assert FAMILY_ORDER == ("F04", "F08", "F06", "F02", "F01", "F03", "F05", "F07")


@pytest.mark.parametrize(("family", "title", "evidence"), (
    ("F04", "DFS Update", "The DFS release has been rescheduled to Q4 2026."),
    ("F08", "Quarterly Activities", "Cash and cash equivalents at end of period were $2.0m."),
    ("F06", "Placement", "The company received firm commitments for the placement."),
    ("F02", "Reserve Update", "The Ore Reserve has increased by 30%."),
    ("F01", "Drill Results", "Drilling results include 8m @ 1.5% Li2O."),
    ("F03", "Metallurgy", "Metallurgical testwork results reported average recovery and product grade."),
    ("F05", "Mining Lease", "A mining lease application has been submitted."),
    ("F07", "Nova JV Earn-in", "A$5m earn-in agreement for the Nova Joint Venture."),
))
def test_each_family_requires_specific_evidence(family, title, evidence):
    assert family in {event["primary_family"] for event in _events(title, evidence)}


def test_dfs_revision_creates_schedule_and_delay_events_without_claiming_completion():
    result = classify_announcement("DFS Revised Completion Timing", {"announcementType": "PROGRESS REPORT"}, [{"name": "highlights", "page": 1, "text": "Release of the DFS has been rescheduled to Q4 2026 from September 2026."}])
    types = {event["event_type"] for event in result.events}
    assert {"Project Delay", "Project Schedule / Timeline Update"}.issubset(types)
    assert all(event["event_status"] != "completed" for event in result.events if event["event_type"].endswith("DFS"))
    assert result.revision_tags == ["Revised"]


def test_official_quarterly_header_beats_generic_title_and_appendix_3y_is_non_core():
    quarterly = classify_families("Positive Results and Update", {"announcementType": "QUARTERLY ACTIVITIES", "subType": "Appendix 5B"})
    assert quarterly.document_category == "Quarterly Report / Appendix 5B"
    assert quarterly.families == ["F08"]
    director = classify_families("Change of Director's Interest Notice", {"announcementType": "SECURITY HOLDER DETAILS", "formType": "Appendix 3Y"})
    assert director.families == []
    assert director.document_category == "Appendix 3Y"
    issue = classify_announcement("Update", {"formType": "Appendix 3B", "announcementType": "PROPOSED ISSUE OF SECURITIES"}, [])
    assert ("F06", "Proposed Issue of Securities") in {(event["primary_family"], event["event_type"]) for event in issue.events}


@pytest.mark.parametrize("headline", [
    "Quarterly Activities & Cash Flow Report - September 2026",   # AGY, no form number
    "Quarterly Activities & Cashflow Report - March 2026",        # AGY, "Cashflow" as one word
    "September 2026 Quarterly Report and Appendix 5B",            # ARU, month first
    "Quarterly Activities Report - December 2025",                # narrative half of a split filing
])
def test_a_quarterly_routes_on_its_headline_not_only_the_form_number(headline):
    """Section 8 is reached via this route, so a quarterly that misses it loses a
    whole cash-runway reading with nothing on screen to say so. AGY's September
    2026 filing went missing exactly this way."""
    result = classify_families(headline)

    assert result.document_category in {"Quarterly Report / Appendix 5B", "Quarterly Activities"}
    assert result.families == ["F08"]


def test_a_quarterly_index_rebalance_is_not_a_quarterly_report():
    # "Quarterly" alone must not route: this one is S&P's, not the company's.
    result = classify_families("S&P DJI Announces September 2026 Quarterly Rebalance")

    assert result.document_category != "Quarterly Report / Appendix 5B"
    assert result.families == []


@pytest.mark.parametrize("title", ["Update", "Results", "Project", "Positive", "Significant", "Positive Significant Update Results for Project"])
def test_generic_words_do_not_route_by_themselves(title):
    result = classify_families(title)
    assert result.families == []
    assert result.document_category == "Other / Needs Review"
    assert result.review_needed is True


def test_funding_commitment_proposal_and_receipt_are_distinct():
    committed = _events("Placement", "Firm commitments to raise A$3m under the placement.")
    proposed = _events("SPP launched", "A Share Purchase Plan will be launched.")
    received = _events("Placement proceeds", "Placement funds received and settled.")
    assert next(event for event in committed if event["event_type"] == "Placement")["event_status"] == "firm_commitments"
    assert next(event for event in proposed if event["event_type"] == "Share Purchase Plan / SPP")["event_status"] == "planned"
    assert next(event for event in received if event["event_type"] == "Placement")["event_status"] == "funds_received"


def test_resource_reserve_and_historical_reference_are_not_mixed():
    reserve = _events("Reserve grows", "The Ore Reserve has increased by 30%. In June 2026 the company released an updated Mineral Resource.")
    assert "Ore Reserve Update" in {event["event_type"] for event in reserve}
    assert "Mineral Resource Update" not in {event["event_type"] for event in reserve}
    future = _events("Drill Results", "Resource modelling is underway, with a maiden Mineral Resource Estimate expected in Q4 2026.")
    assert not any(event["primary_family"] == "F02" for event in future)


def test_withdrawal_is_a_modifier_on_the_business_event_not_a_family():
    result = classify_announcement("Withdrawal of Mineral Resource", {}, [{"name": "summary", "page": 1, "text": "The Mineral Resource withdrawal is effective immediately."}])
    event = next(event for event in result.events if event["event_type"] == "Mineral Resource Withdrawal")
    assert event["primary_family"] == "F02"
    assert event["event_status"] == "withdrawn"
    assert result.revision_tags == ["Withdrawal"]


def test_application_technical_support_and_grant_are_distinct_and_manager_is_not_operator():
    permit = _events("Permit update", "A mining lease application has been submitted. DWER confirmed technical support for the grant of the Groundwater Licence. The clearing permit is approved and in force.")
    statuses = {event["event_type"]: event["event_status"] for event in permit}
    assert statuses["Mining Lease Application"] == "submitted"
    assert statuses["Groundwater Licence Status"] == "technical_support"
    assert statuses["Clearing Permit Status"] == "granted"
    transaction = _events("Nova Joint Venture Earn-in", "Core Energy will be appointed as Manager during the earn-in.")
    assert all(event["event_type"] != "Operator Change" for event in transaction)
