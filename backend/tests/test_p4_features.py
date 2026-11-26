"""P04 funding features derived from Appendix 5B section 8."""
import json
from datetime import date

from app.models import EvidenceDocument, P3Fact, P4Feature, Stock
from app.services.p4_feature_service import FORMULA_VERSION, compute_funding_features


def _fact(stock_id, evidence_id, fact_type, numeric, page=17, as_of=date(2026, 6, 30)):
    return P3Fact(
        stock_id=stock_id,
        evidence_document_id=evidence_id,
        fact_family="F08",
        fact_type=fact_type,
        field_name=fact_type,
        value_raw=str(numeric),
        value_json=json.dumps({"numeric": numeric}),
        source_page=page,
        as_of_date=as_of,
        unit="$A'000",
    )


def _stock(db_session, code="RUN"):
    """A stock plus the Appendix 5B the facts will hang off."""
    stock = Stock(code=code, name="Runway Co", commodity="rare_earth")
    db_session.add(stock)
    db_session.commit()
    evidence = EvidenceDocument(
        stock_id=stock.id, source_type="asx_pdf", source_id=f"{code}-5b",
        title="Quarterly Activities/Appendix 5B",
    )
    db_session.add(evidence)
    db_session.commit()
    return stock, evidence.id


def test_cash_runway_is_derived_with_full_lineage(db_session):
    stock, evidence_id = _stock(db_session)
    db_session.add_all([
        _fact(stock.id, evidence_id, "total_relevant_outgoings", -1222.0),
        _fact(stock.id, evidence_id, "total_available_funding", 3761.0),
        _fact(stock.id, evidence_id, "estimated_quarters_funding", 3.08),
    ])
    db_session.commit()

    result = compute_funding_features(db_session, stock.id)

    assert result["status"] == "ok"
    assert result["cash_runway_quarters"] == 3.08
    assert result["quarterly_burn"] == 1222.0
    # the entity publishes its own figure in item 8.7; ours must agree
    assert result["variance_vs_entity_reported"] == 0.0

    row = (
        db_session.query(P4Feature)
        .filter_by(stock_id=stock.id, feature_name="cash_runway_quarters")
        .one()
    )
    assert json.loads(row.value_json)["numeric"] == 3.08
    assert row.formula_version == FORMULA_VERSION
    # a number must be walkable back to the page it came from
    assert len(json.loads(row.input_refs_json)) == 3
    assert json.loads(row.evidence_json)["source_pages"]["total_relevant_outgoings"] == 17


def test_variance_surfaces_when_entity_figure_disagrees(db_session):
    """A parsing error or a company arithmetic slip must show up, not pass through."""
    stock, evidence_id = _stock(db_session, "VAR")
    db_session.add_all([
        _fact(stock.id, evidence_id, "total_relevant_outgoings", -1000.0),
        _fact(stock.id, evidence_id, "total_available_funding", 5000.0),
        _fact(stock.id, evidence_id, "estimated_quarters_funding", 2.0),  # entity says 2, maths says 5
    ])
    db_session.commit()

    result = compute_funding_features(db_session, stock.id)

    assert result["cash_runway_quarters"] == 5.0
    assert result["entity_reported_quarters"] == 2.0
    assert result["variance_vs_entity_reported"] == 3.0


def test_runway_below_two_quarters_is_flagged(db_session):
    """Under 2 quarters the ASX forces the entity to answer item 8.8 — the same
    level at which a dilutive raise becomes near-certain."""
    stock, evidence_id = _stock(db_session, "LOW")
    db_session.add_all([
        _fact(stock.id, evidence_id, "total_relevant_outgoings", -1000.0),
        _fact(stock.id, evidence_id, "total_available_funding", 1500.0),
    ])
    db_session.commit()

    compute_funding_features(db_session, stock.id)

    row = db_session.query(P4Feature).filter_by(
        stock_id=stock.id, feature_name="cash_runway_quarters"
    ).one()
    assert json.loads(row.metadata_json)["below_asx_disclosure_threshold"] is True


def test_missing_facts_produce_no_feature(db_session):
    stock, evidence_id = _stock(db_session, "NIL")
    result = compute_funding_features(db_session, stock.id)
    assert result["status"] == "insufficient_facts"
    assert db_session.query(P4Feature).filter_by(stock_id=stock.id).count() == 0


def test_recompute_under_same_version_updates_in_place(db_session):
    stock, evidence_id = _stock(db_session, "IDEM")
    db_session.add_all([
        _fact(stock.id, evidence_id, "total_relevant_outgoings", -1222.0),
        _fact(stock.id, evidence_id, "total_available_funding", 3761.0),
    ])
    db_session.commit()

    compute_funding_features(db_session, stock.id)
    compute_funding_features(db_session, stock.id)

    assert db_session.query(P4Feature).filter_by(
        stock_id=stock.id, feature_name="cash_runway_quarters"
    ).count() == 1


# --- dilution -------------------------------------------------------------

from datetime import datetime  # noqa: E402

from app.models import Announcement, PriceBar  # noqa: E402
from app.services.p4_feature_service import compute_placement_features  # noqa: E402


def _placement_setup(db_session, code, category, issue_price=0.10):
    stock, evidence_id = _stock(db_session, code)
    announcement = Announcement(
        stock_id=stock.id,
        ann_id=f"{code}-ann",
        headline="Institutional Placement",
        ann_date=datetime(2026, 9, 25),
        ann_type="PLACEMENT",
        document_category=category,
    )
    db_session.add(announcement)
    db_session.commit()
    fact = _fact(stock.id, evidence_id, "issue_price", issue_price)
    fact.announcement_id = announcement.id
    db_session.add(fact)
    for day, close in ((22, 0.135), (23, 0.135), (24, 0.135), (25, 0.10)):
        db_session.add(PriceBar(
            stock_id=stock.id, date=date(2026, 9, day),
            open=close, high=close, low=close, close=close, volume=1000,
        ))
    db_session.commit()
    return stock


def test_placement_discount_uses_the_close_before_the_announcement(db_session):
    """A raise is priced off the market it was negotiated against, so the
    reference is the prior close, not the (already re-rated) announcement day."""
    stock = _placement_setup(db_session, "PLC", "ISSUED CAPITAL")

    result = compute_placement_features(db_session, stock.id)

    assert result["status"] == "ok"
    assert result["prior_close"] == 0.135  # 24 Sep, not the 0.10 of the 25th
    assert result["placement_discount_pct"] == -25.93

    row = db_session.query(P4Feature).filter_by(
        stock_id=stock.id, feature_name="placement_discount_pct"
    ).one()
    assert json.loads(row.metadata_json)["deep_discount"] is True


def test_issue_prices_quoted_in_an_annual_report_are_ignored(db_session):
    """Annual reports restate historical option and share issue prices under the
    same P03 event type. Pricing a discount off those would compare a years-old
    figure against today's close, so the document category gates the feature."""
    stock = _placement_setup(db_session, "ANN", "PERIODIC REPORTS", issue_price=0.035)

    result = compute_placement_features(db_session, stock.id)

    assert result["status"] == "no_capital_raising_issue_price"
    assert db_session.query(P4Feature).filter_by(stock_id=stock.id).count() == 0


def test_shallow_discount_is_not_flagged_as_deep(db_session):
    stock = _placement_setup(db_session, "SHL", "ISSUED CAPITAL", issue_price=0.13)

    compute_placement_features(db_session, stock.id)

    row = db_session.query(P4Feature).filter_by(
        stock_id=stock.id, feature_name="placement_discount_pct"
    ).one()
    assert json.loads(row.metadata_json)["deep_discount"] is False


# --- resource reconciliation ---------------------------------------------

from app.services.p4_feature_service import compute_resource_reconciliation  # noqa: E402


def _resource_fact(stock_id, evidence_id, fact_type, value, unit, classification, event_id=900, row_ref="p1:0"):
    fact = _fact(stock_id, evidence_id, fact_type, value, as_of=None)
    fact.unit = unit
    fact.p3_event_id = event_id
    fact.metadata_json = json.dumps({
        "classification": classification,
        "column_aligned": True,
        "table_row_ref": row_ref,
    })
    return fact


def _resource_event(db_session, code, rows, event_id=900):
    """rows: [(classification, tonnage_mt, grade, grade_unit, contained, unit)]"""
    stock, evidence_id = _stock(db_session, code)
    announcement = Announcement(
        stock_id=stock.id, ann_id=f"{code}-mre", headline="Ore Reserve Statement",
        ann_date=datetime(2026, 9, 29), ann_type="JORC_MRE",
    )
    db_session.add(announcement)
    db_session.commit()
    for index, (classification, tonnage, grade, grade_unit, contained, contained_unit) in enumerate(rows):
        for fact_type, value, unit in (
            ("tonnage", tonnage, "Mt"),
            ("grade", grade, grade_unit),
            ("contained_metal", contained, contained_unit),
        ):
            fact = _resource_fact(stock.id, evidence_id, fact_type, value, unit, classification,
                                  event_id, row_ref=f"p1:{index}")
            fact.announcement_id = announcement.id
            db_session.add(fact)
    db_session.commit()
    return stock


def test_consistent_gold_table_reconciles(db_session):
    """3.9 Mt at 4.2 g/t is ~527 koz; a statement of 524 koz is the same orebody."""
    stock = _resource_event(db_session, "RES", [("Probable", 3.9, 4.2, "g/t Au", 524.0, "koz")])

    result = compute_resource_reconciliation(db_session, stock.id)

    assert result["status"] == "ok"
    row = db_session.query(P4Feature).filter_by(stock_id=stock.id, feature_group="resource").one()
    assert json.loads(row.metadata_json)["consistent"] is True
    assert abs(json.loads(row.value_json)["numeric"]) < 10


def test_percent_grade_reconciles_against_tonnes(db_session):
    """Lithium and base metals state a percent grade and contained tonnes."""
    stock = _resource_event(db_session, "LI", [("Indicated", 70.0, 1.01, "%", 709100.0, "t")])

    compute_resource_reconciliation(db_session, stock.id)

    row = db_session.query(P4Feature).filter_by(stock_id=stock.id, feature_group="resource").one()
    assert json.loads(row.metadata_json)["consistent"] is True


def test_polymetallic_column_misread_is_caught(db_session):
    """Reading a Ta2O5 ppm figure as gold ounces is wrong by orders of
    magnitude, which is the only reason it can be detected at all."""
    stock = _resource_event(db_session, "POLY", [("Probable", 36.8, 1.00, "g/t Au", 62.4, "koz")])

    compute_resource_reconciliation(db_session, stock.id)

    row = db_session.query(P4Feature).filter_by(stock_id=stock.id, feature_group="resource").one()
    metadata = json.loads(row.metadata_json)
    assert metadata["consistent"] is False
    assert metadata["likely_column_misread"] is True


def test_each_classification_row_is_reconciled_separately(db_session):
    """Pairing by classification is what makes multi-row tables checkable."""
    stock = _resource_event(db_session, "MULTI", [
        ("Probable", 3.9, 4.2, "g/t Au", 524.0, "koz"),
        ("Indicated", 3.1, 6.3, "g/t Au", 633.0, "koz"),
    ])

    result = compute_resource_reconciliation(db_session, stock.id)

    assert result["features"] == 2
    rows = db_session.query(P4Feature).filter_by(stock_id=stock.id, feature_group="resource").all()
    assert {json.loads(row.metadata_json)["classification"] for row in rows} == {"Probable", "Indicated"}
    assert all(json.loads(row.metadata_json)["consistent"] for row in rows)


def test_rows_without_a_classification_are_skipped(db_session):
    """Without a classification there is no reliable way to tell which tonnage
    belongs to which grade, and a wrong pairing fabricates the very error this
    check exists to find."""
    stock, evidence_id = _stock(db_session, "NOCLS")
    for fact_type, value, unit in (
        ("tonnage", 3.9, "Mt"), ("grade", 4.2, "g/t Au"), ("contained_metal", 524.0, "koz")
    ):
        fact = _fact(stock.id, evidence_id, fact_type, value)
        fact.unit = unit
        fact.p3_event_id = 905
        db_session.add(fact)
    db_session.commit()

    result = compute_resource_reconciliation(db_session, stock.id)
    assert result["status"] == "no_reconcilable_rows"


def test_unsupported_unit_pairings_are_left_alone(db_session):
    """ppm against kt has no unambiguous conversion; guessing would read as a
    source data error."""
    stock = _resource_event(db_session, "PPM", [("Probable", 36.8, 62.4, "ppm", 366.0, "kt")])

    result = compute_resource_reconciliation(db_session, stock.id)
    assert result["status"] == "no_reconcilable_rows"


def test_every_quarter_on_file_gets_its_own_runway(db_session):
    """A single runway says almost nothing — 3.08 quarters reads as comfortable.
    The sequence is the finding, so each quarter is computed, not just the last."""
    stock, evidence_id = _stock(db_session, "SERIES")
    quarters = [
        (date(2025, 12, 31), -1000.0, 8000.0),
        (date(2026, 3, 31), -1000.0, 5000.0),
        (date(2026, 6, 30), -1000.0, 2000.0),
    ]
    for as_of, outgoings, funding in quarters:
        db_session.add_all([
            _fact(stock.id, evidence_id, "total_relevant_outgoings", outgoings, as_of=as_of),
            _fact(stock.id, evidence_id, "total_available_funding", funding, as_of=as_of),
        ])
    db_session.commit()

    result = compute_funding_features(db_session, stock.id)

    assert result["quarters"] == 3
    assert [h["cash_runway_quarters"] for h in result["history"]] == [8.0, 5.0, 2.0]
    # the latest quarter is what the top level reports
    assert result["cash_runway_quarters"] == 2.0
    assert result["as_of_date"] == date(2026, 6, 30)

    rows = db_session.query(P4Feature).filter_by(
        stock_id=stock.id, feature_name="cash_runway_quarters"
    ).all()
    assert len(rows) == 3


def test_quarter_on_quarter_change_is_emitted(db_session):
    """The comparison the architecture asks for and one filing can never give."""
    stock, evidence_id = _stock(db_session, "DELTA")
    for as_of, funding in ((date(2026, 3, 31), 4000.0), (date(2026, 6, 30), 1000.0)):
        db_session.add_all([
            _fact(stock.id, evidence_id, "total_relevant_outgoings", -500.0, as_of=as_of),
            _fact(stock.id, evidence_id, "total_available_funding", funding, as_of=as_of),
        ])
    db_session.commit()

    compute_funding_features(db_session, stock.id)

    row = db_session.query(P4Feature).filter_by(
        stock_id=stock.id, feature_name="available_funding_change_pct"
    ).one()
    assert json.loads(row.value_json)["numeric"] == -75.0
    assert json.loads(row.metadata_json)["depleting"] is True
    # the first quarter has nothing to compare against
    assert row.as_of_date == date(2026, 6, 30)


def test_a_single_quarter_emits_no_change_feature(db_session):
    stock, evidence_id = _stock(db_session, "ONEQ")
    db_session.add_all([
        _fact(stock.id, evidence_id, "total_relevant_outgoings", -1000.0),
        _fact(stock.id, evidence_id, "total_available_funding", 3000.0),
    ])
    db_session.commit()

    compute_funding_features(db_session, stock.id)

    assert db_session.query(P4Feature).filter_by(
        stock_id=stock.id, feature_name="available_funding_change_pct"
    ).count() == 0
