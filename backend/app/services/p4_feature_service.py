"""P04 derived features from P03 reported facts.

P03 records what a company stated; P04 turns those statements into comparable
numbers. Nothing here re-reads a document — every feature cites the P03 fact ids
it was computed from, so a number can always be traced back to the page it came
from. Features are append-only and carry a formula_version, so changing a
definition never rewrites history: recompute under a new version and compare.

The first feature group is funding, because for a pre-revenue explorer cash
runway is the hardest constraint there is — a good deposit still gets financed
at a discount when the money runs out.
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy.orm import Session

from ..models import P3Fact, P3ParseRun, P4Feature

FORMULA_VERSION = "funding_runway_v1"
FEATURE_GROUP = "funding"

# Appendix 5B item -> the P03 fact_type carrying it
ITEM_8_3 = "total_relevant_outgoings"
ITEM_8_6 = "total_available_funding"
ITEM_8_7 = "estimated_quarters_funding"


# P03 is append-only: re-parsing a document under a new parser leaves the old
# facts in place and marks their run superseded. P04 must read only the live
# run, or a corrected extraction silently loses to the figure it replaced.
def _live_facts(query):
    return query.outerjoin(P3ParseRun, P3Fact.parse_run_id == P3ParseRun.id).filter(
        (P3ParseRun.id.is_(None)) | (P3ParseRun.status != "superseded")
    )


def _latest_fact(session: Session, stock_id: int, fact_type: str) -> P3Fact | None:
    return (
        _live_facts(session.query(P3Fact))
        .filter(
            P3Fact.stock_id == stock_id,
            P3Fact.fact_type == fact_type,
            P3Fact.fact_family == "F08",
        )
        .order_by(P3Fact.as_of_date.desc(), P3Fact.id.desc())
        .first()
    )


def _numeric(fact: P3Fact | None) -> float | None:
    if fact is None:
        return None
    try:
        return json.loads(fact.value_json).get("numeric")
    except (ValueError, AttributeError):
        return None


def _upsert(
    session: Session,
    *,
    stock_id: int,
    as_of_date: date,
    feature_name: str,
    value: float,
    unit: str | None,
    input_refs: list[int],
    evidence: dict,
    metadata: dict,
    evidence_document_id: int | None,
) -> P4Feature:
    """One row per (stock, date, feature, formula version) — recomputing under
    the same version updates in place; a new version writes a new row."""
    row = (
        session.query(P4Feature)
        .filter_by(
            stock_id=stock_id,
            as_of_date=as_of_date,
            feature_group=FEATURE_GROUP,
            feature_name=feature_name,
            formula_version=FORMULA_VERSION,
        )
        .one_or_none()
    )
    if row is None:
        row = P4Feature(
            stock_id=stock_id,
            as_of_date=as_of_date,
            feature_group=FEATURE_GROUP,
            feature_name=feature_name,
            formula_version=FORMULA_VERSION,
        )
        session.add(row)
    row.value_json = json.dumps({"numeric": value}, ensure_ascii=False)
    row.unit = unit
    row.input_refs_json = json.dumps(input_refs)
    row.evidence_json = json.dumps(evidence, ensure_ascii=False, default=str)
    row.metadata_json = json.dumps(metadata, ensure_ascii=False, default=str)
    row.evidence_document_id = evidence_document_id
    return row


def _facts_by_quarter(session: Session, stock_id: int, fact_type: str) -> dict:
    """Every live reading of one item, keyed by the quarter it reports on."""
    rows = (
        _live_facts(session.query(P3Fact))
        .filter(
            P3Fact.stock_id == stock_id,
            P3Fact.fact_type == fact_type,
            P3Fact.fact_family == "F08",
        )
        .order_by(P3Fact.as_of_date, P3Fact.id)
        .all()
    )
    # a quarter re-filed under a corrected parse keeps the newest reading
    return {row.as_of_date: row for row in rows if row.as_of_date}


def compute_funding_features(session: Session, stock_id: int) -> dict:
    """Cash runway for every quarter on file, plus the change between them.

    Runway = total available funding (item 8.6) / total relevant outgoings
    (item 8.3). The entity publishes its own figure in item 8.7; we recompute
    rather than trust it and record the difference, so a parsing error or a
    company arithmetic slip surfaces instead of passing through silently.

    Computed per quarter rather than for the latest filing alone. A single
    runway says almost nothing — 3.08 quarters reads as comfortable — while the
    sequence behind it is the actual finding: four readings showing available
    funding down 79% say the company is heading for a raise. The quarter-on-
    quarter change is emitted as its own feature for the same reason.
    """
    outgoings_by_q = _facts_by_quarter(session, stock_id, ITEM_8_3)
    funding_by_q = _facts_by_quarter(session, stock_id, ITEM_8_6)
    reported_by_q = _facts_by_quarter(session, stock_id, ITEM_8_7)

    quarters = sorted(set(outgoings_by_q) & set(funding_by_q))
    if not quarters:
        return {"status": "insufficient_facts", "features": 0}

    written = 0
    history: list[dict] = []
    previous_funding: float | None = None

    for as_of in quarters:
        outgoings_fact = outgoings_by_q[as_of]
        funding_fact = funding_by_q[as_of]
        outgoings = _numeric(outgoings_fact)
        funding = _numeric(funding_fact)
        if outgoings is None or funding is None:
            continue
        burn = abs(outgoings)
        if burn == 0:
            continue

        reported = _numeric(reported_by_q.get(as_of))
        runway = round(funding / burn, 2)
        variance = round(runway - reported, 2) if reported is not None else None

        refs = [outgoings_fact.id, funding_fact.id]
        reported_fact = reported_by_q.get(as_of)
        if reported_fact is not None:
            refs.append(reported_fact.id)

        _upsert(
            session,
            stock_id=stock_id,
            as_of_date=as_of,
            feature_name="cash_runway_quarters",
            value=runway,
            unit="quarters",
            input_refs=refs,
            evidence={
                "formula": "total_available_funding / abs(total_relevant_outgoings)",
                "inputs": {
                    "total_available_funding": funding,
                    "total_relevant_outgoings": outgoings,
                },
                "source_pages": {
                    "total_available_funding": funding_fact.source_page,
                    "total_relevant_outgoings": outgoings_fact.source_page,
                },
                "entity_reported_quarters": reported,
                "variance_vs_entity_reported": variance,
            },
            metadata={
                "appendix_5b_items": ["8.3", "8.6", "8.7"],
                # 8.8 only has to be answered when the entity reports under 2
                # quarters, which is also the level at which a raise becomes
                # near-certain
                "below_asx_disclosure_threshold": runway < 2.0,
            },
            evidence_document_id=outgoings_fact.evidence_document_id,
        )
        _upsert(
            session,
            stock_id=stock_id,
            as_of_date=as_of,
            feature_name="quarterly_burn",
            value=burn,
            unit=outgoings_fact.unit,
            input_refs=[outgoings_fact.id],
            evidence={
                "formula": "abs(total_relevant_outgoings)",
                "inputs": {"total_relevant_outgoings": outgoings},
                "source_pages": {"total_relevant_outgoings": outgoings_fact.source_page},
            },
            metadata={"appendix_5b_items": ["8.3"]},
            evidence_document_id=outgoings_fact.evidence_document_id,
        )
        written += 2

        # The comparison the architecture asks for and a single filing can
        # never supply: how much the funding position moved since last quarter.
        if previous_funding not in (None, 0):
            change_pct = round((funding / previous_funding - 1) * 100, 1)
            _upsert(
                session,
                stock_id=stock_id,
                as_of_date=as_of,
                feature_name="available_funding_change_pct",
                value=change_pct,
                unit="%",
                input_refs=[funding_fact.id],
                evidence={
                    "formula": "available_funding / previous_quarter_available_funding - 1",
                    "inputs": {
                        "available_funding": funding,
                        "previous_quarter": previous_funding,
                    },
                },
                metadata={"depleting": change_pct < 0},
                evidence_document_id=funding_fact.evidence_document_id,
            )
            written += 1

        previous_funding = funding
        history.append(
            {
                "as_of_date": as_of,
                "cash_runway_quarters": runway,
                "quarterly_burn": burn,
                "available_funding": funding,
                "entity_reported_quarters": reported,
                "variance_vs_entity_reported": variance,
            }
        )

    if not history:
        return {"status": "insufficient_facts", "features": 0}

    session.commit()
    latest = history[-1]
    return {
        "status": "ok",
        "features": written,
        "quarters": len(history),
        # the latest quarter is promoted to the top level: callers that only
        # want "where does this stand now, and does it match what the company
        # said" should not have to walk the history to find out
        "as_of_date": latest["as_of_date"],
        "cash_runway_quarters": latest["cash_runway_quarters"],
        "quarterly_burn": latest["quarterly_burn"],
        "entity_reported_quarters": latest["entity_reported_quarters"],
        "variance_vs_entity_reported": latest["variance_vs_entity_reported"],
        "history": history,
    }


def compute_all_features(session: Session, stock_ids: list[int]) -> dict:
    """Every P04 group for every stock. Returns counts plus per-stock results."""
    results: dict[int, dict] = {}
    computed = skipped = 0
    for stock_id in stock_ids:
        per_stock = {
            "funding": compute_funding_features(session, stock_id),
            "dilution": compute_placement_features(session, stock_id),
            "resource": compute_resource_reconciliation(session, stock_id),
        }
        results[stock_id] = per_stock
        for result in per_stock.values():
            if result["status"] == "ok":
                computed += 1
            else:
                skipped += 1
    return {"computed": computed, "skipped": skipped, "results": results}


# kept so existing callers and tests referring to the funding-only entry point
# keep working while the pipeline moves to compute_all_features
def compute_all_funding_features(session: Session, stock_ids: list[int]) -> dict:
    results = {}
    computed = skipped = 0
    for stock_id in stock_ids:
        result = compute_funding_features(session, stock_id)
        results[stock_id] = result
        if result["status"] == "ok":
            computed += 1
        else:
            skipped += 1
    return {"computed": computed, "skipped": skipped, "results": results}


# --- dilution -----------------------------------------------------------

DILUTION_GROUP = "dilution"
DILUTION_FORMULA_VERSION = "placement_discount_v1"

# An issue price only means "this raise diluted holders at X" when it comes from
# a capital-raising announcement. The same fact_type is extracted from annual
# reports, where the figures are historical option and share issue prices with
# no relation to today's market — pricing a discount off those would compare a
# years-old number against the current close. The P03 event type does not
# separate the two (both classify as "Placement"), so gate on the document.
CAPITAL_RAISING_CATEGORIES = {"ISSUED CAPITAL", "Commercial / Corporate Transaction"}


def _prior_close(session: Session, stock_id: int, before: date) -> tuple[float, date] | None:
    """Last close strictly before the announcement — a placement is priced off
    the market the raise was negotiated against, not the day it was revealed."""
    from ..models import PriceBar

    row = (
        session.query(PriceBar.close, PriceBar.date)
        .filter(PriceBar.stock_id == stock_id, PriceBar.date < before)
        .order_by(PriceBar.date.desc())
        .first()
    )
    return (row[0], row[1]) if row else None


def compute_placement_features(session: Session, stock_id: int) -> dict:
    """Discount of the most recent placement against the pre-announcement close."""
    from ..models import Announcement

    fact = (
        _live_facts(session.query(P3Fact))
        .join(Announcement, P3Fact.announcement_id == Announcement.id)
        .filter(
            P3Fact.stock_id == stock_id,
            P3Fact.fact_type == "issue_price",
            Announcement.document_category.in_(CAPITAL_RAISING_CATEGORIES),
        )
        .order_by(Announcement.ann_date.desc(), P3Fact.id.desc())
        .first()
    )
    if fact is None:
        return {"status": "no_capital_raising_issue_price", "features": 0}

    issue_price = _numeric(fact)
    if not issue_price:
        return {"status": "no_issue_price_value", "features": 0}

    announcement = session.get(Announcement, fact.announcement_id)
    ann_date = announcement.ann_date.date() if announcement else None
    if ann_date is None:
        return {"status": "no_announcement_date", "features": 0}

    prior = _prior_close(session, stock_id, ann_date)
    if prior is None:
        return {"status": "no_prior_close", "features": 0}
    prior_close, prior_date = prior
    if prior_close <= 0:
        return {"status": "invalid_prior_close", "features": 0}

    discount_pct = round((issue_price / prior_close - 1) * 100, 2)
    _upsert_dilution(
        session,
        stock_id=stock_id,
        as_of_date=ann_date,
        feature_name="placement_discount_pct",
        value=discount_pct,
        unit="%",
        input_refs=[fact.id],
        evidence={
            "formula": "issue_price / prior_close - 1",
            "inputs": {"issue_price": issue_price, "prior_close": round(prior_close, 4)},
            "prior_close_date": prior_date,
            "announcement_date": ann_date,
            "announcement_headline": announcement.headline[:120] if announcement else None,
            "source_pages": {"issue_price": fact.source_page},
        },
        metadata={
            "document_category": announcement.document_category if announcement else None,
            # a deep discount is the market's price for taking the paper, and a
            # rough proxy for how urgently the company needed the money
            "deep_discount": discount_pct <= -20.0,
            "fact_review_status": fact.review_status,
        },
        evidence_document_id=fact.evidence_document_id,
    )
    session.commit()
    return {
        "status": "ok",
        "features": 1,
        "as_of_date": ann_date,
        "placement_discount_pct": discount_pct,
        "issue_price": issue_price,
        "prior_close": round(prior_close, 4),
    }


def _upsert_dilution(session: Session, **kwargs) -> P4Feature:
    """Same upsert contract as the funding group, under the dilution version."""
    stock_id = kwargs["stock_id"]
    as_of_date = kwargs["as_of_date"]
    feature_name = kwargs["feature_name"]
    row = (
        session.query(P4Feature)
        .filter_by(
            stock_id=stock_id,
            as_of_date=as_of_date,
            feature_group=DILUTION_GROUP,
            feature_name=feature_name,
            formula_version=DILUTION_FORMULA_VERSION,
        )
        .one_or_none()
    )
    if row is None:
        row = P4Feature(
            stock_id=stock_id,
            as_of_date=as_of_date,
            feature_group=DILUTION_GROUP,
            feature_name=feature_name,
            formula_version=DILUTION_FORMULA_VERSION,
        )
        session.add(row)
    row.value_json = json.dumps({"numeric": kwargs["value"]}, ensure_ascii=False)
    row.unit = kwargs["unit"]
    row.input_refs_json = json.dumps(kwargs["input_refs"])
    row.evidence_json = json.dumps(kwargs["evidence"], ensure_ascii=False, default=str)
    row.metadata_json = json.dumps(kwargs["metadata"], ensure_ascii=False, default=str)
    row.evidence_document_id = kwargs["evidence_document_id"]
    return row


# --- resource ------------------------------------------------------------

RESOURCE_GROUP = "resource"
RESOURCE_FORMULA_VERSION = "contained_metal_check_v1"

GRAMS_PER_TROY_OUNCE = 31.1034768
# Beyond this the two numbers cannot be describing the same orebody, so the
# extraction is wrong rather than the rounding being loose.
RECONCILIATION_TOLERANCE_PCT = 10.0


def _facts_for_event(session: Session, stock_id: int, fact_type: str, event_id: int) -> list[P3Fact]:
    return (
        _live_facts(session.query(P3Fact))
        .filter(
            P3Fact.stock_id == stock_id,
            P3Fact.fact_type == fact_type,
            P3Fact.p3_event_id == event_id,
        )
        .order_by(P3Fact.id)
        .all()
    )


def _announcement_date(session: Session, fact: P3Fact) -> date | None:
    from ..models import Announcement

    if not fact.announcement_id:
        return None
    announcement = session.get(Announcement, fact.announcement_id)
    return announcement.ann_date.date() if announcement and announcement.ann_date else None


def _row_key(fact: P3Fact) -> tuple[str, str] | None:
    """(classification, row reference) identifying the table row a fact came
    from. Without the row reference a document carrying several tables would
    merge their rows together."""
    try:
        metadata = json.loads(fact.metadata_json or "{}")
    except ValueError:
        return None
    classification = metadata.get("classification")
    row_ref = metadata.get("table_row_ref")
    if not classification or not row_ref:
        return None
    return classification, row_ref


def _implied_contained(tonnage_mt: float, grade: float, grade_unit: str, contained_unit: str):
    """Contained metal implied by tonnage x grade, in the table's own unit.

    Only the pairings a JORC table states unambiguously are handled: a precious
    metal in g/t reported as ounces, and a base metal or oxide in percent
    reported as tonnes. Anything else (ppm, lb, oz/t) is left alone rather than
    guessed at — a wrong conversion here would read as a data error in the
    source, which is precisely the signal this is meant to carry.
    """
    grade_base = grade_unit.split()[0] if grade_unit else ""
    contained = contained_unit.split()[0] if contained_unit else ""
    if grade_base == "g/t" and contained == "koz":
        return tonnage_mt * 1_000_000 * grade / GRAMS_PER_TROY_OUNCE / 1000, "koz"
    if grade_base == "g/t" and contained == "moz":
        return tonnage_mt * 1_000_000 * grade / GRAMS_PER_TROY_OUNCE / 1_000_000, "moz"
    if grade_base == "%" and contained == "t":
        return tonnage_mt * 1_000_000 * grade / 100, "t"
    if grade_base == "%" and contained == "kt":
        return tonnage_mt * 1_000_000 * grade / 100 / 1000, "kt"
    return None, None


def compute_resource_reconciliation(session: Session, stock_id: int) -> dict:
    """Check each reported classification row against tonnage x grade.

    JORC tables put every element of a polymetallic deposit in its own column,
    so a row reads `36.8 Mt | 1.00 % Li2O | 62.4 ppm Ta2O5`. A reader that takes
    columns by position turns that into a gold grade and a gold ounce count, and
    the result is plausible enough to pass unnoticed. Multiplying tonnage by
    grade catches it, because a mis-selected column is wrong by orders of
    magnitude rather than by rounding.

    Rows are paired by (event, classification), which the column-aligned
    extractor records; without a classification there is no reliable way to tell
    which tonnage belongs to which grade, so those rows are skipped.
    """
    facts = (
        _live_facts(session.query(P3Fact))
        .filter(
            P3Fact.stock_id == stock_id,
            P3Fact.fact_type.in_(("tonnage", "grade", "contained_metal")),
        )
        .order_by(P3Fact.id)
        .all()
    )
    if not facts:
        return {"status": "no_resource_facts", "features": 0}

    groups: dict[tuple, dict[str, list[P3Fact]]] = {}
    for fact in facts:
        row_key = _row_key(fact)
        if row_key is None or not fact.p3_event_id:
            continue
        classification, row_ref = row_key
        groups.setdefault((fact.p3_event_id, classification, row_ref), {}) \
              .setdefault(fact.fact_type, []).append(fact)

    checked = 0
    for (event_id, classification, row_ref), by_type in sorted(groups.items()):
        tonnages = by_type.get("tonnage", [])
        grades = by_type.get("grade", [])
        metals = by_type.get("contained_metal", [])
        if not (len(tonnages) == len(grades) == len(metals) == 1):
            continue
        tonnage, grade, metal = tonnages[0], grades[0], metals[0]
        tonnes_mt = _numeric(tonnage)
        grade_value = _numeric(grade)
        reported = _numeric(metal)
        if not tonnes_mt or not grade_value or not reported:
            continue

        implied, unit = _implied_contained(
            tonnes_mt, grade_value, (grade.unit or "").lower(), (metal.unit or "").lower()
        )
        if implied is None:
            continue

        variance_pct = round((implied / reported - 1) * 100, 1)
        consistent = abs(variance_pct) <= RECONCILIATION_TOLERANCE_PCT
        as_of = metal.as_of_date or tonnage.as_of_date or _announcement_date(session, metal)
        if as_of is None:
            continue

        _upsert_resource(
            session,
            stock_id=stock_id,
            as_of_date=as_of,
            feature_name=f"contained_metal_reconciliation_pct_{classification.lower()}_{row_ref.replace(':', '_')}",
            value=variance_pct,
            unit="%",
            input_refs=[tonnage.id, grade.id, metal.id],
            evidence={
                "formula": "tonnage x grade, converted to the table's contained unit",
                "inputs": {
                    "tonnage_mt": tonnes_mt,
                    "grade": grade_value,
                    "grade_unit": grade.unit,
                    "reported": reported,
                    "reported_unit": metal.unit,
                },
                "implied": round(implied, 1),
                "implied_unit": unit,
                "classification": classification,
                "source_pages": {"contained_metal": metal.source_page},
                "source_excerpt": (metal.source_excerpt or "")[:200],
            },
            metadata={
                "consistent": consistent,
                "likely_column_misread": abs(variance_pct) > 100.0,
                "classification": classification,
                "table_row_ref": row_ref,
                "p3_event_id": event_id,
            },
            evidence_document_id=metal.evidence_document_id,
        )
        checked += 1

    if checked == 0:
        return {"status": "no_reconcilable_rows", "features": 0}
    session.commit()
    return {"status": "ok", "features": checked}


def _upsert_resource(session: Session, **kwargs) -> P4Feature:
    row = (
        session.query(P4Feature)
        .filter_by(
            stock_id=kwargs["stock_id"],
            as_of_date=kwargs["as_of_date"],
            feature_group=RESOURCE_GROUP,
            feature_name=kwargs["feature_name"],
            formula_version=RESOURCE_FORMULA_VERSION,
        )
        .one_or_none()
    )
    if row is None:
        row = P4Feature(
            stock_id=kwargs["stock_id"],
            as_of_date=kwargs["as_of_date"],
            feature_group=RESOURCE_GROUP,
            feature_name=kwargs["feature_name"],
            formula_version=RESOURCE_FORMULA_VERSION,
        )
        session.add(row)
    row.value_json = json.dumps({"numeric": kwargs["value"]}, ensure_ascii=False)
    row.unit = kwargs["unit"]
    row.input_refs_json = json.dumps(kwargs["input_refs"])
    row.evidence_json = json.dumps(kwargs["evidence"], ensure_ascii=False, default=str)
    row.metadata_json = json.dumps(kwargs["metadata"], ensure_ascii=False, default=str)
    row.evidence_document_id = kwargs["evidence_document_id"]
    return row
