"""Family-specific, source-grounded rules for P03 reported facts.

Rules are intentionally conservative: they emit only text explicitly present in
the document and never compute ratios, growth, runway, discounts or valuations.
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Iterable

from .p3_value_normalizer import currency, explicit_date, number, period_range, source_excerpt, unit
from .p3_resource_table import parse_resource_rows
from .p3_economics import extract_economics

EXTRACTOR_NAME = "deterministic_p3_fact_extractor"
EXTRACTOR_VERSION = "p3_fact_v3_entity_consistency"
FAMILY_ORDER = ("F04", "F08", "F06", "F02", "F01", "F03", "F05", "F07")


def extract_fact_candidates(events: Iterable, pages: list[str], sections: list[dict]) -> list[dict]:
    families = {event.primary_family for event in events if event.active_result}
    extractors = {
        "F04": _f04, "F08": _f08, "F06": _f06, "F02": _f02,
        "F01": _f01, "F03": _f03, "F05": _f05, "F07": _f07,
    }
    output: list[dict] = []
    for family in FAMILY_ORDER:
        if family in families:
            output.extend(extractors[family](pages, sections))
    return _dedupe(output)


def _candidate(
    family: str, fact_type: str, field_name: str, value_raw: str, page: int, text: str,
    start: int, end: int, sections: list[dict], *, value_numeric: float | None = None,
    value_text: str | None = None, unit_raw: str | None = None, currency_raw: str | None = None,
    quantity_type: str = "text", status: str = "reported", event_type_hint: str | None = None,
    period_start: date | None = None, period_end: date | None = None, as_of_date: date | None = None,
    effective_date: date | None = None, metadata: dict | None = None,
) -> dict:
    raw_unit, normalized_unit = unit(unit_raw)
    raw_currency, normalized_currency = currency(currency_raw)
    excerpt = source_excerpt(text, start, end)
    source_section = _section_name(page, excerpt, sections)
    review = "review_needed" if source_section == "body_fallback" or normalized_currency == "unknown" or normalized_unit == "unknown" else "proposed"
    confidence = 0.94 if source_section in {"summary", "highlights", "key_results", "executive_summary"} else 0.91 if source_section == "standard_form" else 0.76
    return {
        "fact_family": family, "fact_type": fact_type, "field_name": field_name,
        "value_raw": " ".join(str(value_raw).split()), "value_numeric": value_numeric,
        "value_text": value_text, "unit_raw": raw_unit, "unit_normalized": normalized_unit,
        "currency_raw": raw_currency, "currency_normalized": normalized_currency,
        "quantity_type": quantity_type, "period_start": period_start, "period_end": period_end,
        "as_of_date": as_of_date, "effective_date": effective_date, "status": status,
        "source_section": source_section, "source_page_start": page, "source_page_end": page,
        "source_excerpt": excerpt, "extractor_name": EXTRACTOR_NAME,
        "extractor_version": EXTRACTOR_VERSION, "extraction_confidence": confidence,
        "review_status": review, "event_type_hint": event_type_hint,
        "metadata": metadata or {},
    }


def _section_name(page: int, excerpt: str, sections: list[dict]) -> str:
    candidates = [section for section in sections if section.get("page") == page]
    for section in candidates:
        section_text = " ".join(section.get("text", "").split()).casefold()
        probe = " ".join(excerpt.split()).casefold()
        if probe[:70] in section_text or any(chunk in section_text for chunk in probe.split(" ")[:6] if len(chunk) > 8):
            return section.get("name", "body")
    if any(marker in excerpt.casefold() for marker in ("consolidated statement of cash flows", "appendix 5b", "current quarter")):
        return "standard_form"
    return "body_fallback"


def _find(pattern: str, text: str, flags: int = re.I | re.S):
    return re.finditer(pattern, text, flags)


def _f04(pages: list[str], sections: list[dict]) -> list[dict]:
    out: list[dict] = []
    for page, text in enumerate(pages, 1):
        for match in _find(r"\b(Scoping Study|PFS|DFS|BFS|Definitive Feasibility Study|Feasibility Study)\b", text):
            raw = match.group(1)
            mapped = "DFS" if raw.casefold() in {"dfs", "definitive feasibility study"} else raw
            status = "completed" if re.search(r"(?:completed|released)\s+(?:the\s+)?" + re.escape(raw), text[max(0, match.start()-80):match.end()+80], re.I) else "planned" if re.search(r"(?:expected|targeted|toward|towards|delivery|completing)", text[max(0, match.start()-100):match.end()+100], re.I) else "reported"
            out.append(_candidate("F04", "study_type", "Study Type", raw, page, text, match.start(), match.end(), sections, value_text=mapped, status=status, event_type_hint="Definitive Feasibility Study / DFS"))
        timing = re.search(r"rescheduled to\s+the fourth quarter of\s+(20\d{2}),\s+from\s+the\s+(September\s+20\d{2})\s+timing", text, re.I)
        if timing:
            revised = f"Q4 {timing.group(1)}"; previous = timing.group(2)
            pstart, pend, method = period_range(revised)
            meta = {"conversion_method": method, "timing_role": "revised"}
            out.append(_candidate("F04", "dfs_completion", "DFS Completion", revised, page, text, timing.start(), timing.end(), sections, value_text=revised, status="targeted", period_start=pstart, period_end=pend, event_type_hint="Project Schedule / Timeline Update", metadata=meta))
            out.append(_candidate("F04", "original_timing", "Previous Timing", previous, page, text, timing.start(), timing.end(), sections, value_text=previous, status="amended", event_type_hint="Project Delay", metadata={"timing_role": "original"}))
            out.append(_candidate("F04", "timeline_change", "Project Schedule Update", timing.group(0), page, text, timing.start(), timing.end(), sections, value_text=f"{previous} → {revised}", status="reported", event_type_hint="Project Delay", metadata={"change_type": "delay"}))
        for match in _find(r"Final Investment Decision\s*\(FID\)\s*targeted for\s+(?:the\s+)?(end of\s+20\d{2})", text):
            out.append(_candidate("F04", "fid_timing", "FID Target", match.group(1), page, text, match.start(), match.end(), sections, value_text=match.group(1), status="targeted", event_type_hint="FID Target"))
        for match in _find(r"process plant\s+capital cost estimate will be fully reviewed and accepted[^.]*", text):
            out.append(_candidate("F04", "capex_review", "CAPEX Review", match.group(0), page, text, match.start(), match.end(), sections, value_text="review before incorporation into study", status="planned", event_type_hint="CAPEX Review / Estimate Update"))
        for match in _find(r"(\d+(?:\.\d+)?)\s*ktpa\s+project development[^\n]*", text):
            out.append(_candidate("F04", "processing_capacity", "Processing Capacity", match.group(1), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(1)), unit_raw="ktpa", quantity_type="commodity_quantity", status="planned", event_type_hint="Engineering / FEED Update"))
        for match in _find(r"(?:anticipated\s+)?(?:±\s*)?(\d+)\s*year mine life", text):
            out.append(_candidate("F04", "mine_life", "Mine Life", match.group(0), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(1)), unit_raw="years", quantity_type="duration", status="forecast", event_type_hint="Development Schedule"))
        for match in _find(r"steady state annual production rate of\s+([\d]+\s*[-–]\s*[\d]+)\s*koz", text):
            out.append(_candidate("F04", "annual_production", "Annual Production", match.group(1), page, text, match.start(), match.end(), sections, value_text=match.group(1), unit_raw="koz", quantity_type="commodity_quantity", status="forecast", event_type_hint="Development Schedule"))
        for match in _find(r"(\d+(?:\.\d+)?)m\s+of development completed", text):
            out.append(_candidate("F04", "development_completed", "Development Completed", match.group(1), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(1)), unit_raw="m", quantity_type="amount", status="completed", event_type_hint="Construction Progress"))
        for match in _find(r"First ore is expected in\s+(CY\s*20\d{2})", text):
            raw = re.sub(r"\s+", "", match.group(1)); pstart, pend, method = period_range(raw)
            out.append(_candidate("F04", "first_ore_timing", "First Ore Timing", raw, page, text, match.start(), match.end(), sections, value_text=raw, quantity_type="date", status="forecast", period_start=pstart, period_end=pend, event_type_hint="First Ore Timing", metadata={"conversion_method": method}))
        for match in _find(r"DFS is on track for delivery\s+(H[12]\s+20\d{2})", text):
            raw = match.group(1); pstart, pend, method = period_range(raw)
            out.append(_candidate("F04", "dfs_completion", "DFS Completion", raw, page, text, match.start(), match.end(), sections, value_text=raw, quantity_type="date", status="targeted", period_start=pstart, period_end=pend, event_type_hint="Project Schedule / Timeline Update", metadata={"conversion_method": method}))
        # Project economics moved out to its own module: matching the acronym
        # alone found two capital estimates across seventy-two filings that
        # discuss one, while loosening the term without guarding the number
        # read years, ISO standard numbers and sensitivity steps as dollars.
        for item in extract_economics(text):
            metadata = {"basis": item["basis"]}
            if item["fact_type"] == "npv":
                metadata.update({
                    "discount_rate_pct": item.get("discount_rate_pct"),
                    "tax_basis": item.get("tax_basis"),
                    # an NPV without its discount rate cannot be compared with
                    # another NPV, so the gap is recorded rather than hidden
                    "complete": item.get("complete"),
                })
            if item.get("scale_word"):
                metadata["scale_word"] = item["scale_word"]
            out.append(_candidate(
                "F04", item["fact_type"], item["label"], item["raw"], page, text,
                item["start"], item["end"], sections,
                value_numeric=item["numeric"], unit_raw=item.get("unit"),
                currency_raw=item.get("currency"), quantity_type=item["quantity_type"],
                status="estimated", event_type_hint="Study Update", metadata=metadata,
            ))
    return out


def _quarter_end(value: date | None) -> date | None:
    """An Appendix 5B always reports to the last day of a quarter month.

    A date that is not one did not come from the form's header: either from the
    wrong sentence — HAS's March 2026 filing opens "Quarter ended, African
    Monazite feedstock secured: On 14 April 2026..." — or from a day digit that
    extraction split across two lines, which is how BMN's "31 MARCH" arrives as
    "1 MARCH". The month is trusted; the day is not.
    """
    if value is None or value.month not in (3, 6, 9, 12):
        return None
    return date(value.year, value.month, calendar.monthrange(value.year, value.month)[1])


def _section_8_item(text: str, label: str, next_item: str, shape: str) -> tuple[str, int, int] | None:
    """One section 8 figure, for filings whose lines the PDF broke apart.

    Some come out one glyph-run per line — "174,6" and "44" on separate lines —
    so nothing matches a line-based pattern. The span from an item's label to
    the next item number holds exactly one parenthetical and one figure, and
    that is what makes collapsing the whitespace inside it safe; the same move
    across a cash-flow table would weld adjacent columns into a single number.
    The anchored shape below is the guard: a window holding anything else
    yields nothing rather than a wrong figure.
    """
    match = re.search(rf"{label}(.{{0,200}}?)(?={next_item})", text, re.S | re.I)
    if not match:
        return None
    value = re.match(shape, re.sub(r"\s+", "", match.group(1)))
    return (value.group(1), match.start(), match.end()) if value else None


def _f08(pages: list[str], sections: list[dict]) -> list[dict]:
    out: list[dict] = []
    quarter_end: date | None = None
    # The cover-line fallback below is only trustworthy inside an actual
    # Appendix 5B; in a half-year account "period ended 30 June" names a
    # six-month period, and treating it as a quarter would misdate everything
    # read from it.
    is_appendix_5b = any(re.search(r"Total relevant outgoings", page, re.I) for page in pages)
    period_start: date | None = None
    ytd_start: date | None = None
    ytd_months: int | None = None
    for page, text in enumerate(pages, 1):
        # First *valid* quarter end, not first match: the phrase also occurs in
        # prose, where the date that follows belongs to a sentence.
        ended = next(
            (m for m in re.finditer(r"Quarter ended[\s\S]{0,180}?(\d{1,2}\s+[A-Za-z]+\s+20\d{2})", text, re.I)
             if _quarter_end(explicit_date(re.sub(r"\s+", " ", m.group(1))))),
            None,
        )
        if ended is None and is_appendix_5b:
            # Some filers title the cover page "FOR THE PERIOD ENDED 31 MARCH
            # 2026" and the form's own "Quarter ended" box survives extraction
            # only as "Q uarter ended ... 31 M arch 2026". The fallback is
            # anchored to its own line so that "reporting period ended ..."
            # inside a sentence cannot stand in for the quarter.
            ended = re.search(
                r"^[^\S\n]*for the (?:quarter|period) ended\s+(\d{1,2}\s+[A-Za-z]+\s+20\d{2})[^\S\n]*$",
                text, re.I | re.M)
        if ended:
            quarter_end = _quarter_end(explicit_date(re.sub(r"\s+", " ", ended.group(1))))
            if quarter_end:
                start_month = quarter_end.month - 2
                period_start = date(quarter_end.year, start_month, 1)
                ytd_match = re.search(r"Year to date\s*\((\d+)\s+months?\)", text, re.I)
                if ytd_match:
                    months = int(ytd_match.group(1)); ytd_months = months
                    absolute_month = quarter_end.year * 12 + quarter_end.month - months
                    ytd_start = date(absolute_month // 12, absolute_month % 12 + 1, 1)
            out.append(_candidate("F08", "reporting_period", "Reporting Period", ended.group(1), page, text, ended.start(), ended.end(), sections, value_text=ended.group(1), quantity_type="date", status="reported", period_start=period_start, period_end=quarter_end, as_of_date=quarter_end, event_type_hint="Reporting Period"))
        row_patterns = (
            (r"Net cash from / \(used in\) operating\s+activities\s+\(([\d,]+)\)\s+\(([\d,]+)\)", "operating_cash_flow", "Operating Cash Flow"),
            (r"Net cash from / \(used in\) investing\s+activities\s+\(([\d,]+)\)\s+\(([\d,]+)\)", "investing_cash_flow", "Investing Cash Flow"),
            (r"Net cash from / \(used in\) financing\s+activities\s+\(([\d,]+)\)\s+\(([\d,]+)\)", "financing_cash_flow", "Financing Cash Flow"),
        )
        for pattern, fact_type, field in row_patterns:
            for match in _find(pattern, text):
                current = -number(match.group(1))
                out.append(_candidate("F08", fact_type, field, f"({match.group(1)})", page, text, match.start(), match.end(), sections, value_numeric=current, unit_raw="$A’000", currency_raw="$A", quantity_type="amount", status="reported", period_start=period_start, period_end=quarter_end, as_of_date=quarter_end, event_type_hint="Periodic Cash Flow Update", metadata={"period_basis": "current_quarter", "year_to_date_raw": f"({match.group(2)})"}))
                out.append(_candidate("F08", fact_type, field, f"({match.group(2)})", page, text, match.start(), match.end(), sections, value_numeric=-number(match.group(2)), unit_raw="$A’000", currency_raw="$A", quantity_type="amount", status="reported", period_start=ytd_start, period_end=quarter_end, as_of_date=quarter_end, event_type_hint="Periodic Cash Flow Update", metadata={"period_basis": "year_to_date", "reported_months": ytd_months}))
        spend_patterns = (
            (r"\(a\) exploration & evaluation\s+\(([\d,]+)\)\s+\(([\d,]+)\)", "exploration_spend", "Exploration Spend"),
            (r"\(([\d,]+)\)\s+\(([\d,]+)\)\s+\(a\) exploration & evaluation", "exploration_spend", "Exploration Spend"),
            (r"\(e\) development\s+\(([\d,]+)\)\s+\(([\d,]+)\)", "development_spend", "Development Spend"),
            (r"\(e\) administration and corporate costs\s+\(([\d,]+)\)\s+\(([\d,]+)\)", "administration_spend", "Administration Spend"),
        )
        for pattern, fact_type, field in spend_patterns:
            for match in _find(pattern, text):
                out.append(_candidate("F08", fact_type, field, f"({match.group(1)})", page, text, match.start(), match.end(), sections, value_numeric=-number(match.group(1)), unit_raw="$A’000", currency_raw="$A", quantity_type="amount", status="reported", period_start=period_start, period_end=quarter_end, as_of_date=quarter_end, event_type_hint="Periodic Cash Flow Update", metadata={"period_basis": "current_quarter", "year_to_date_raw": f"({match.group(2)})", "cash_payment": True}))
                out.append(_candidate("F08", fact_type, field, f"({match.group(2)})", page, text, match.start(), match.end(), sections, value_numeric=-number(match.group(2)), unit_raw="$A’000", currency_raw="$A", quantity_type="amount", status="reported", period_start=ytd_start, period_end=quarter_end, as_of_date=quarter_end, event_type_hint="Periodic Cash Flow Update", metadata={"period_basis": "year_to_date", "reported_months": ytd_months, "cash_payment": True}))
        cash = re.search(r"Cash and cash equivalents at end of\s+(?:period|quarter)[^\d]*([\d,]+)\s+([\d,]+)", text, re.I | re.S)
        if cash:
            out.append(_candidate("F08", "cash_balance", "Cash Balance", cash.group(1), page, text, cash.start(), cash.end(), sections, value_numeric=number(cash.group(1)), unit_raw="$A’000", currency_raw="$A", quantity_type="amount", status="reported", period_start=period_start, period_end=quarter_end, as_of_date=quarter_end, event_type_hint="Period-end Cash Position", metadata={"period_basis": "period_end"}))
        # Appendix 5B section 8 is the funding-runway block the ASX mandates for
        # exploration entities. Items 8.3 and 8.6 are the two inputs P04 needs to
        # recompute runway; 8.7 is the entity's own stated figure, kept so the
        # derived value can be cross-checked against what the company published.
        # Parentheses are the form's sign: "(1,857)" is money going out, a bare
        # "454" is a net cash *inflow* for the quarter — which ASX then tells
        # the entity to follow by answering item 8.7 "N/A". Reading only the
        # parenthesised form made a company that had turned cash-flow positive
        # indistinguishable from one we held no figures for. The leading
        # "(item 8.1 + item 8.2)" is skipped as a unit so its own digits can
        # never be mistaken for the value.
        outgoings = re.search(r"8\.3\s+Total relevant outgoings\s*\([^)]{0,40}\)\s*(\([\d,]+\)|[\d,]+)", text, re.I)
        found = ((outgoings.group(1), outgoings.start(), outgoings.end()) if outgoings
                 else _section_8_item(text, r"Total relevant outgoings", r"8\s*\.\s*4",
                                      r"^\([^)]{0,40}\)(\([\d,]+\)|[\d,]+)$"))
        if found:
            token, span_start, span_end = found
            is_outflow = token.startswith("(")
            magnitude = number(token.strip("()"))
            out.append(_candidate("F08", "total_relevant_outgoings", "Total Relevant Outgoings", token, page, text, span_start, span_end, sections, value_numeric=-magnitude if is_outflow else magnitude, unit_raw="$A\u2019000", currency_raw="$A", quantity_type="amount", status="reported", period_start=period_start, period_end=quarter_end, as_of_date=quarter_end, event_type_hint="Periodic Cash Flow Update", metadata={"appendix_5b_item": "8.3", "period_basis": "current_quarter", "cash_direction": "outflow" if is_outflow else "net_inflow"}))
        funding = re.search(r"8\.6\s+Total available funding[^\n]*?([\d,]+)\s*\n", text, re.I)
        found = ((funding.group(1), funding.start(), funding.end()) if funding
                 else _section_8_item(text, r"Total available funding", r"8\s*\.\s*7",
                                      r"^\([^)]{0,40}\)([\d,]+)$"))
        if found:
            token, span_start, span_end = found
            out.append(_candidate("F08", "total_available_funding", "Total Available Funding", token, page, text, span_start, span_end, sections, value_numeric=number(token), unit_raw="$A\u2019000", currency_raw="$A", quantity_type="amount", status="reported", period_start=period_start, period_end=quarter_end, as_of_date=quarter_end, event_type_hint="Period-end Cash Position", metadata={"appendix_5b_item": "8.6", "period_basis": "period_end"}))
        # the value sits after the "(Item 8.6 divided by Item 8.3)" note, which
        # itself contains digits — skip the parenthetical before reading it
        quarters = re.search(r"8\.7\s+Estimated quarters of funding available\s*\(\s*Item[\s\S]{0,40}?\)\s*([\d]+(?:\.[\d]+)?|N/?A)", text, re.I)
        found = ((quarters.group(1), quarters.start(), quarters.end()) if quarters
                 else _section_8_item(text, r"Estimated quarters of funding available",
                                      r"8\s*\.\s*8|Note\s*:",
                                      r"^\([^)]{0,60}\)(\d+(?:\.\d+)?|N/?A)$"))
        if found and found[0].upper().replace("/", "") != "NA":
            token, span_start, span_end = found
            out.append(_candidate("F08", "estimated_quarters_funding", "Estimated Quarters of Funding", token, page, text, span_start, span_end, sections, value_numeric=number(token), unit_raw="quarters", quantity_type="ratio", status="reported", period_start=period_start, period_end=quarter_end, as_of_date=quarter_end, event_type_hint="Period-end Cash Position", metadata={"appendix_5b_item": "8.7", "entity_reported": True}))
        for match in _find(r"\$(\d+(?:\.\d+)?)M cash as at\s+(\d{1,2}\s+[A-Za-z]+\s+20\d{2})", text):
            as_of = explicit_date(match.group(2))
            out.append(_candidate("F08", "cash_balance", "Cash Balance", f"${match.group(1)}M", page, text, match.start(), match.end(), sections, value_numeric=number(match.group(1)), unit_raw="$M", currency_raw="$", quantity_type="amount", status="reported", as_of_date=as_of, event_type_hint="Period-end Cash Position"))
    return out


def _f06(pages: list[str], sections: list[dict]) -> list[dict]:
    out: list[dict] = []
    for page, text in enumerate(pages, 1):
        for match in _find(r"received firm commitments to raise\s+(A?\$)(\d+(?:\.\d+)?)\s*million", text):
            out.append(_candidate("F06", "funding_amount", "Funding Amount", f"{match.group(1)}{match.group(2)} million", page, text, match.start(), match.end(), sections, value_numeric=number(match.group(2)), unit_raw="$M", currency_raw=match.group(1), quantity_type="amount", status="committed", event_type_hint="Placement"))
        for match in _find(r"at\s+(A?\$)(\d+(?:\.\d+)?)\s+per share", text):
            out.append(_candidate("F06", "issue_price", "Issue Price", f"{match.group(1)}{match.group(2)} per share", page, text, match.start(), match.end(), sections, value_numeric=number(match.group(2)), unit_raw="$/share", currency_raw=match.group(1), quantity_type="amount", status="committed", event_type_hint="Placement"))
        for match in _find(r"issue of\s+([\d,]+)\s+fully paid ordinary shares", text):
            out.append(_candidate("F06", "new_securities_issued", "New Securities Issued", match.group(1), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(1)), unit_raw="shares", quantity_type="amount", status="committed", event_type_hint="Placement", metadata={"security_type": "fully paid ordinary shares"}))
        if re.search(r"\bPlacement\b", text, re.I):
            match = re.search(r"\bPlacement\b", text, re.I)
            out.append(_candidate("F06", "funding_method", "Funding Method", "Placement", page, text, match.start(), match.end(), sections, value_text="Placement", status="committed" if "firm commitments" in text.casefold() else "planned", event_type_hint="Placement"))
        for match in _find(r"Share Purchase Plan[\s\S]{0,400}?up\s+to an additional\s+(A?\$)([\d,]+)", text):
            out.append(_candidate("F06", "spp_limit", "SPP Amount / Limit", f"{match.group(1)}{match.group(2)}", page, text, match.start(), match.end(), sections, value_numeric=number(match.group(2)), unit_raw="$", currency_raw=match.group(1), quantity_type="amount", status="planned", event_type_hint="Share Purchase Plan / SPP", metadata={"limit_type": "up_to", "underwritten": False}))
        for match in _find(r"Share Purchase Plan to be launched[^\n]*", text):
            out.append(_candidate("F06", "funding_method", "Funding Method", "Share Purchase Plan", page, text, match.start(), match.end(), sections, value_text="SPP", status="planned", event_type_hint="Share Purchase Plan / SPP"))
        for match in _find(r"(?:net )?proceeds from the Placement to be used for\s+([^.]*)", text):
            out.append(_candidate("F06", "use_of_funds", "Use of Funds", match.group(1), page, text, match.start(), match.end(), sections, value_text=" ".join(match.group(1).split()), status="planned", event_type_hint="Placement"))
        for match in _find(r"(?:debt facility|loan facility)[^\d$A]{0,80}(A?\$|US\$)([\d,.]+)\s*(million|m)?", text):
            out.append(_candidate("F06", "facility_limit", "Facility Limit", match.group(0), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(2)), unit_raw=match.group(3), currency_raw=match.group(1), quantity_type="amount", status="reported", event_type_hint="Debt Facility"))
        for match in _find(r"(?:interest rate|coupon)[^\d]{0,30}(\d+(?:\.\d+)?)\s*%", text):
            out.append(_candidate("F06", "interest_rate", "Interest Rate", match.group(1), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(1)), unit_raw="%", quantity_type="percentage", status="reported", event_type_hint="Debt Facility"))
        for match in _find(r"(?:government )?grant[^\d$A]{0,80}(A?\$|US\$)([\d,.]+)\s*(million|m)?", text):
            status = "received" if "received" in match.group(0).casefold() else "granted" if "awarded" in match.group(0).casefold() else "pending"
            out.append(_candidate("F06", "government_grant_amount", "Government Grant Amount", match.group(0), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(2)), unit_raw=match.group(3), currency_raw=match.group(1), quantity_type="amount", status=status, event_type_hint="Government Grant"))
    return out


def _f02(pages: list[str], sections: list[dict]) -> list[dict]:
    out: list[dict] = []
    for page, text in enumerate(pages, 1):
        for match in _find(r"underground Reserve has increased by\s+(\d+(?:\.\d+)?)%\s+to\s+(\d+(?:\.\d+)?)koz\s+at\s+(\d+(?:\.\d+)?)g/t\s+Au", text):
            base = {"resource_or_reserve_type": "Ore Reserve", "commodity": "gold"}
            title_value = re.search(r"Reserve grows by\s+(\d+(?:\.\d+)?)%", text, re.I)
            increase_meta = {**base, "conflicts_with_title": bool(title_value and title_value.group(1) != match.group(1))}
            out.append(_candidate("F02", "reported_increase", "Reported Increase", match.group(1), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(1)), unit_raw="%", quantity_type="percentage", status="reported", event_type_hint="Ore Reserve Update", metadata=increase_meta))
            out.append(_candidate("F02", "contained_metal", "Contained Metal", match.group(2), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(2)), unit_raw="koz Au", quantity_type="commodity_quantity", status="reported", event_type_hint="Ore Reserve Update", metadata=base))
            out.append(_candidate("F02", "grade", "Grade", match.group(3), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(3)), unit_raw="g/t Au", quantity_type="commodity_quantity", status="reported", event_type_hint="Ore Reserve Update", metadata=base))
        title = re.search(r"Reserve grows by\s+(\d+(?:\.\d+)?)%", text, re.I)
        if title:
            out.append(_candidate("F02", "reported_increase", "Reported Increase", title.group(1), page, text, title.start(), title.end(), sections, value_numeric=number(title.group(1)), unit_raw="%", quantity_type="percentage", status="reported", event_type_hint="Ore Reserve Update", metadata={"resource_or_reserve_type": "Ore Reserve", "source_role": "title", "conflicts_with_summary": True}))
        for match in _find(r"In June\s+(20\d{2}),[^.]*updated Resource[^.]*of\s+(\d+(?:\.\d+)?)Moz\s+at\s+(\d+(?:\.\d+)?)g/t\s+Au", text):
            meta = {"resource_or_reserve_type": "Mineral Resource", "commodity": "gold", "reference_month": f"June {match.group(1)}"}
            out.append(_candidate("F02", "contained_metal", "Contained Metal", match.group(2), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(2)), unit_raw="Moz", quantity_type="commodity_quantity", status="historical_reference", event_type_hint="Ore Reserve Update", metadata=meta))
            out.append(_candidate("F02", "grade", "Grade", match.group(3), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(3)), unit_raw="g/t Au", quantity_type="commodity_quantity", status="historical_reference", event_type_hint="Ore Reserve Update", metadata=meta))
        for match in _find(r"Inferred Resources[^.]*are\s+(\d+(?:\.\d+)?)koz", text):
            out.append(_candidate("F02", "contained_metal", "Contained Metal", match.group(1), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(1)), unit_raw="koz Au", quantity_type="commodity_quantity", status="reported", event_type_hint="Ore Reserve Update", metadata={"resource_or_reserve_type": "Mineral Resource", "classification": "Inferred", "commodity": "gold"}))
        # Columns are matched to the table header rather than taken by position:
        # reading the first three numbers after the classification turns a
        # tantalum ppm figure into gold ounces on a polymetallic table, and the
        # result is plausible enough to pass unnoticed.
        for row in parse_resource_rows(text):
            if row.tonnage_mt is None or row.grade is None or row.classification == "Total":
                continue
            grade_value, grade_unit, commodity = row.grade
            meta = {
                "resource_or_reserve_type": "Ore Reserve",
                "classification": row.classification,
                "commodity": commodity,
                "column_aligned": True,
                # the row's offset on the page uniquely identifies it: one
                # document can carry several tables whose rows share a
                # classification, and pairing a tonnage to the wrong row's grade
                # fabricates exactly the error the P04 check looks for
                "table_row_ref": f"p{page}:{row.start}",
                "table_columns": [f"{column.label or '?'} ({column.unit})" for column in row.columns],
            }
            out.append(_candidate("F02", "resource_or_reserve_type", "Resource / Reserve Type", "Ore Reserve", page, text, row.start, row.end, sections, value_text="Ore Reserve", status="reported", event_type_hint="Ore Reserve Update", metadata=meta))
            if commodity:
                out.append(_candidate("F02", "commodity", "Commodity", commodity, page, text, row.start, row.end, sections, value_text=commodity, status="reported", event_type_hint="Ore Reserve Update", metadata=meta))
            out.append(_candidate("F02", "tonnage", "Tonnage", str(row.tonnage_mt), page, text, row.start, row.end, sections, value_numeric=row.tonnage_mt, unit_raw="Mt", quantity_type="commodity_quantity", status="reported", event_type_hint="Ore Reserve Update", metadata=meta))
            out.append(_candidate("F02", "grade", "Grade", str(grade_value), page, text, row.start, row.end, sections, value_numeric=grade_value, unit_raw=grade_unit, quantity_type="commodity_quantity", status="reported", event_type_hint="Ore Reserve Update", metadata=meta))
            if row.contained is not None:
                contained_value, contained_unit, _ = row.contained
                out.append(_candidate("F02", "contained_metal", "Contained Metal", str(contained_value), page, text, row.start, row.end, sections, value_numeric=contained_value, unit_raw=contained_unit, quantity_type="commodity_quantity", status="reported", event_type_hint="Ore Reserve Update", metadata=meta))
            out.append(_candidate("F02", "classification", "Classification", row.classification, page, text, row.start, row.end, sections, value_text=row.classification, status="reported", event_type_hint="Ore Reserve Update", metadata=meta))
    return out


def _f01(pages: list[str], sections: list[dict]) -> list[dict]:
    out: list[dict] = []
    hole_pattern = re.compile(r"\b((?:BCDD|BCRC|TAMT|TARC)\d{3})\b", re.I)
    interval_pattern = re.compile(r"(\d+(?:\.\d+)?)m\s*@\s*(\d+(?:\.\d+)?)%\s*Li2O\s*from\s*(\d+(?:\.\d+)?)m(?:\s*\((\d+(?:\.\d+)?)m\s+est\.\s*true width\)|\s*\(est\.\s*true width\))?", re.I)
    for page, text in enumerate(pages, 1):
        for match in interval_pattern.finditer(text):
            preceding = text[max(0, match.start()-180):match.start()]
            holes = list(hole_pattern.finditer(preceding))
            if not holes:
                continue
            hole = holes[-1].group(1).upper()
            interval_signature = ":".join(filter(None, (hole, match.group(1), match.group(2), match.group(3), match.group(4))))
            meta = {"hole_id": hole, "commodity": "Li2O", "reported_interval_group": interval_signature, "interval_signature": interval_signature, "included_interval": "including" in preceding[-25:].casefold()}
            values = (
                ("hole_id", "Hole ID", hole, None, None, "text"),
                ("interval_length", "Interval Length", match.group(1), number(match.group(1)), "m", "amount"),
                ("grade", "Grade", match.group(2), number(match.group(2)), "% Li2O", "commodity_quantity"),
                ("from_depth", "From Depth", match.group(3), number(match.group(3)), "m", "amount"),
            )
            for fact_type, field, raw, numeric, raw_unit, qtype in values:
                out.append(_candidate("F01", fact_type, field, raw, page, text, match.start(), match.end(), sections, value_numeric=numeric, value_text=raw if qtype == "text" else None, unit_raw=raw_unit, quantity_type=qtype, status="reported", event_type_hint="Drilling / Assay Results", metadata=meta))
            true_width = match.group(4) or (match.group(1) if "est. true width" in match.group(0).casefold() else None)
            if true_width:
                out.append(_candidate("F01", "true_width", "True Width", true_width, page, text, match.start(), match.end(), sections, value_numeric=number(true_width), unit_raw="m", quantity_type="amount", status="estimated", event_type_hint="Drilling / Assay Results", metadata=meta))
        for match in _find(r"maiden Mineral Resource Estimate expected in\s+(Q[1-4]\s+20\d{2})", text):
            pstart, pend, method = period_range(match.group(1))
            out.append(_candidate("F01", "resource_estimate_target", "Maiden MRE Target", match.group(1), page, text, match.start(), match.end(), sections, value_text=match.group(1), quantity_type="date", status="targeted", period_start=pstart, period_end=pend, event_type_hint="Drill Programme", metadata={"conversion_method": method, "not_a_published_resource": True}))
        for match in _find(r"Resource RC drilling complete,\s*resource modelling is underway,\s*estimation and reporting in\s+(Q[1-4])", text):
            out.append(_candidate("F01", "drilling_status", "Drilling Status", match.group(0), page, text, match.start(), match.end(), sections, value_text="RC drilling complete; resource modelling underway", status="completed", event_type_hint="Drilling Completed", metadata={"resource_reporting_target": match.group(1), "not_a_published_resource": True}))
    return out


def _f03(pages: list[str], sections: list[dict]) -> list[dict]:
    out: list[dict] = []
    for page, text in enumerate(pages, 1):
        for match in _find(r"Maiden metallurgical\s*\(sighter\) test work", text):
            out.append(_candidate("F03", "testwork_type", "Testwork Type", match.group(0), page, text, match.start(), match.end(), sections, value_text="metallurgical sighter testwork", status="completed", event_type_hint="Metallurgical Test Results", metadata={"scope": "testwork_not_commercial_production"}))
        result = re.search(r"Average recovery of\s+(\d+(?:\.\d+)?)%\s+with an average product grade of\s+(\d+(?:\.\d+)?)%\s*Li2O generated from\s+(\w+)\s+composites", text, re.I)
        if result:
            count_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
            meta = {"scope": "sighter_testwork", "sample_type": "composites"}
            out.append(_candidate("F03", "recovery", "Recovery", result.group(1), page, text, result.start(), result.end(), sections, value_numeric=number(result.group(1)), unit_raw="%", quantity_type="percentage", status="reported", event_type_hint="Recovery / Product Grade", metadata=meta))
            out.append(_candidate("F03", "product_grade", "Product Grade", result.group(2), page, text, result.start(), result.end(), sections, value_numeric=number(result.group(2)), unit_raw="% Li2O", quantity_type="commodity_quantity", status="reported", event_type_hint="Recovery / Product Grade", metadata=meta))
            count = count_words.get(result.group(3).casefold()) or number(result.group(3))
            out.append(_candidate("F03", "sample_count", "Sample / Composite", result.group(3), page, text, result.start(), result.end(), sections, value_numeric=count, unit_raw="composites", quantity_type="amount", status="reported", event_type_hint="Metallurgical Test Results", metadata=meta))
        for match in _find(r"Whole of Ore Flotation method", text):
            out.append(_candidate("F03", "processing_route", "Processing Route", "Whole of Ore Flotation", page, text, match.start(), match.end(), sections, value_text="Whole of Ore Flotation", status="reported", event_type_hint="Processing Route"))
        for match in _find(r"Further metallurgical testwork will[^.]*", text):
            out.append(_candidate("F03", "test_programme", "Test Programme", match.group(0), page, text, match.start(), match.end(), sections, value_text=" ".join(match.group(0).split()), status="planned", event_type_hint="Metallurgical Testwork Planned"))
    return out


def _f05(pages: list[str], sections: list[dict]) -> list[dict]:
    out: list[dict] = []
    for page, text in enumerate(pages, 1):
        permit = re.search(r"Native Vegetation Clearing Permit\s*\(\s*NVCP\s*\)[^.]*approved and has taken effect, with no appeals received", text, re.I)
        if permit:
            out.append(_candidate("F05", "permit_type", "Permit Type", "Native Vegetation Clearing Permit", page, text, permit.start(), permit.end(), sections, value_text="Native Vegetation Clearing Permit", status="granted", event_type_hint="Clearing Permit Status"))
            out.append(_candidate("F05", "permit_status", "Permit Status", "approved and effective; no appeals", page, text, permit.start(), permit.end(), sections, value_text="approved and effective; no appeals", status="effective", event_type_hint="Clearing Permit Status"))
        for match in _find(r"Purpose Permit\s+(CPS\s*\d+/\d+)", text):
            out.append(_candidate("F05", "permit_identifier", "Permit Identifier", match.group(1), page, text, match.start(), match.end(), sections, value_text=match.group(1), status="granted", event_type_hint="Clearing Permit Status"))
        support = re.search(r"DWER\)[\s\S]{0,140}?confirmed\s+technical\s+support\s+for\s+the\s+grant\s+of\s+the\s+Manna\s+Groundwater\s+Licence", text, re.I)
        if support:
            out.append(_candidate("F05", "permit_status", "Groundwater Licence Status", "technical support for grant", page, text, support.start(), support.end(), sections, value_text="technical support for grant", status="technical_support", event_type_hint="Groundwater Licence Status", metadata={"authority": "DWER", "not_formally_granted": True}))
            out.append(_candidate("F05", "authority", "Authority", "DWER", page, text, support.start(), support.end(), sections, value_text="Department of Water and Environmental Regulation", status="reported", event_type_hint="Groundwater Licence Status"))
        dmpe = re.search(r"granted\s+by\s+the\s+Department\s+of\s+Mines,\s+Petroleum\s+and\s+Exploration\s*\(DMPE\)", text, re.I)
        if dmpe:
            out.append(_candidate("F05", "authority", "Authority", "DMPE", page, text, dmpe.start(), dmpe.end(), sections, value_text="Department of Mines, Petroleum and Exploration", status="reported", event_type_hint="Clearing Permit Status"))
        auth = re.search(r"authorises clearing of up to\s+(\d+(?:\.\d+)?)\s+hectares[^.]*five-year term to\s+(\d{1,2}\s+[A-Za-z]+\s+20\d{2})", text, re.I)
        if auth:
            expiry = explicit_date(auth.group(2))
            out.append(_candidate("F05", "area", "Authorised Area", auth.group(1), page, text, auth.start(), auth.end(), sections, value_numeric=number(auth.group(1)), unit_raw="ha", quantity_type="amount", status="granted", event_type_hint="Clearing Permit Status"))
            out.append(_candidate("F05", "expiry_date", "Expiry Date", auth.group(2), page, text, auth.start(), auth.end(), sections, value_text=auth.group(2), quantity_type="date", status="granted", effective_date=expiry, event_type_hint="Clearing Permit Status"))
        works = re.search(r"remaining Works Approval is well progressed[\s\S]{0,160}?expected before the end of the\s+September 2026 quarter", text, re.I)
        if works:
            out.append(_candidate("F05", "permit_status", "Works Approval Status", "expected before end of September 2026 quarter", page, text, works.start(), works.end(), sections, value_text="expected before end of September 2026 quarter", status="pending", event_type_hint="Environmental Approval Status"))
    return out


def _f07(pages: list[str], sections: list[dict]) -> list[dict]:
    out: list[dict] = []
    for page, text in enumerate(pages, 1):
        earn = re.search(r"Two phase,\s*(A\$)(\d+(?:\.\d+)?)M earn-in[^.]*up to a\s+(\d+(?:\.\d+)?)% interest", text, re.I)
        if earn:
            out.append(_candidate("F07", "transaction_type", "Transaction Type", "Earn-in", page, text, earn.start(), earn.end(), sections, value_text="Earn-in", status="conditional", event_type_hint="Earn-in"))
            out.append(_candidate("F07", "earn_in_amount", "Earn-in Amount", f"{earn.group(1)}{earn.group(2)}M", page, text, earn.start(), earn.end(), sections, value_numeric=number(earn.group(2)), unit_raw="A$M", currency_raw=earn.group(1), quantity_type="amount", status="conditional", event_type_hint="Earn-in"))
            out.append(_candidate("F07", "maximum_ownership", "Maximum Ownership", earn.group(3), page, text, earn.start(), earn.end(), sections, value_numeric=number(earn.group(3)), unit_raw="%", quantity_type="percentage", status="conditional", event_type_hint="Earn-in", metadata={"not_current_ownership": True}))
        for match in _find(r"Core Energy will be appointed as the Manager[^.]*", text):
            out.append(_candidate("F07", "manager", "Manager", "Core Energy Minerals Limited", page, text, match.start(), match.end(), sections, value_text="Core Energy Minerals Limited", status="conditional", event_type_hint="Joint Venture", metadata={"operator_not_inferred": True}))
        for match in _find(r"Phase 1\s*-\s*Core Energy can acquire a\s+(\d+(?:\.\d+)?)% interest[^.]*expenditure of\s+(A\$)(\d+(?:\.\d+)?)M within\s+(\d+) months", text):
            meta = {"phase": 1, "duration_months": int(match.group(4))}
            out.append(_candidate("F07", "earn_in_percentage", "Earn-in Percentage", match.group(1), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(1)), unit_raw="%", quantity_type="percentage", status="conditional", event_type_hint="Earn-in", metadata=meta))
            out.append(_candidate("F07", "earn_in_amount", "Earn-in Amount", f"{match.group(2)}{match.group(3)}M", page, text, match.start(), match.end(), sections, value_numeric=number(match.group(3)), unit_raw="A$M", currency_raw=match.group(2), quantity_type="amount", status="conditional", event_type_hint="Earn-in", metadata=meta))
        for match in _find(r"Phase 2\s*-\s*Core Energy can acquire a further\s+(\d+(?:\.\d+)?)%[^.]*expenditure of\s+(A\$)(\d+(?:\.\d+)?)M within\s+(\d+) months", text):
            meta = {"phase": 2, "duration_months_after_phase_1": int(match.group(4))}
            out.append(_candidate("F07", "earn_in_percentage", "Earn-in Percentage", match.group(1), page, text, match.start(), match.end(), sections, value_numeric=number(match.group(1)), unit_raw="%", quantity_type="percentage", status="conditional", event_type_hint="Earn-in", metadata=meta))
            out.append(_candidate("F07", "earn_in_amount", "Earn-in Amount", f"{match.group(2)}{match.group(3)}M", page, text, match.start(), match.end(), sections, value_numeric=number(match.group(3)), unit_raw="A$M", currency_raw=match.group(2), quantity_type="amount", status="conditional", event_type_hint="Earn-in", metadata=meta))
        current = re.search(r"current shareholders[^.]*RMR\s*\((\d+(?:\.\d+)?)% equity interest[^.]*Nova Africa\)\s*\((\d+(?:\.\d+)?)%[^.]*Sixzone[^)]*\)\s*\((\d+(?:\.\d+)?)%", text, re.I)
        if current:
            for party, value in zip(("RMR", "Nova Africa", "Sixzone"), current.groups()):
                out.append(_candidate("F07", "current_ownership", "Current Ownership", value, page, text, current.start(), current.end(), sections, value_numeric=number(value), unit_raw="%", quantity_type="percentage", status="reported", event_type_hint="Joint Venture", metadata={"owner": party}))
        rights = re.search(r"Wildcat acquired the LCT Rights for\s+(E\d+/\d+)", text, re.I)
        if rights:
            out.append(_candidate("F07", "asset_rights", "Asset Rights", rights.group(1), page, text, rights.start(), rights.end(), sections, value_text=rights.group(1), status="completed", event_type_hint="Acquisition", metadata={"scope": "LCT Rights only"}))
    return out


def _dedupe(candidates: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    output: list[dict] = []
    for candidate in candidates:
        key = (
            candidate["fact_family"], candidate["fact_type"], candidate["field_name"],
            candidate["value_raw"], candidate["source_page_start"],
            candidate["source_excerpt"],
            candidate.get("period_start"), candidate.get("period_end"),
            candidate.get("metadata", {}).get("period_basis"),
            candidate.get("metadata", {}).get("reported_interval_group"),
            candidate.get("metadata", {}).get("owner"),
        )
        if key not in seen:
            seen.add(key); output.append(candidate)
    return output
