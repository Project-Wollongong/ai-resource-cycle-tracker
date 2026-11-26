"""Summary-first source planning for P03 reported-fact extraction.

The planner is deliberately separate from the family rules.  It decides *where*
rules are allowed to read: atomic Summary/Highlights bullets first, stable ASX
forms second when required fields are still absent, and document body last.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from .p3_fact_rules import extract_fact_candidates


SUMMARY_ORDER = {"summary": 0, "highlights": 1, "key_results": 2, "executive_summary": 3}
SUMMARY_NAMES = frozenset(SUMMARY_ORDER)
STANDARD_FORMS = frozenset({"Appendix 5B", "Appendix 4C"})


# A requirement is a semantic slot.  Any listed fact type satisfies the slot.
# Slots are activated by the classified Event, not merely by words in the body.
_EVENT_REQUIREMENTS: tuple[tuple[str, str, tuple[tuple[str, tuple[str, ...]], ...]], ...] = (
    ("F04", r"DFS|Feasibility|Study", (("study_type", ("study_type",)),)),
    ("F04", r"Schedule|Timeline", (("schedule_timing", ("dfs_completion", "first_ore_timing", "first_production_timing", "timeline_change")),)),
    ("F04", r"Delay", (("timeline_change", ("timeline_change",)), ("previous_timing", ("original_timing",)))),
    ("F04", r"FID", (("fid_timing", ("fid_timing",)),)),
    ("F04", r"CAPEX", (("capex", ("capex_review", "capex")),)),
    ("F04", r"Engineering|FEED", (("processing_capacity", ("processing_capacity",)),)),
    ("F04", r"Construction", (("construction_progress", ("development_completed", "construction_duration")),)),
    ("F04", r"First Ore", (("first_ore_timing", ("first_ore_timing",)),)),
    ("F08", r"Quarterly", (("reporting_period", ("reporting_period",)),)),
    ("F08", r"Cash Flow", (
        ("operating_cash_flow", ("operating_cash_flow",)),
        ("investing_cash_flow", ("investing_cash_flow",)),
        ("financing_cash_flow", ("financing_cash_flow",)),
        ("cash_balance", ("cash_balance",)),
        ("exploration_spend", ("exploration_spend",)),
        ("development_spend", ("development_spend",)),
        ("administration_spend", ("administration_spend",)),
        # Appendix 5B section 8 — the two inputs P04 needs to derive funding
        # runway, plus the entity's own stated figure to check the result against
        ("total_relevant_outgoings", ("total_relevant_outgoings",)),
        ("total_available_funding", ("total_available_funding",)),
        ("estimated_quarters_funding", ("estimated_quarters_funding",)),
    )),
    # section 8 lives only in Appendix 5B, so it hangs off the cash-flow event
    # above rather than the generic cash-position one — otherwise any document
    # merely mentioning a cash position reports section 8 as missing
    ("F08", r"Cash Position", (("cash_balance", ("cash_balance",)),)),
    ("F06", r"Placement", (
        ("funding_method", ("funding_method",)),
        ("funding_amount", ("funding_amount",)),
        ("issue_price", ("issue_price",)),
        ("new_securities", ("new_securities_issued",)),
        ("use_of_funds", ("use_of_funds",)),
    )),
    ("F06", r"Share Purchase Plan|SPP", (("spp_method", ("funding_method",)), ("spp_limit", ("spp_limit",)))),
    ("F06", r"Debt", (("facility_limit", ("facility_limit", "debt_principal")),)),
    ("F02", r"Reserve", (
        ("reserve_type", ("resource_or_reserve_type",)),
        ("classification", ("classification",)),
        ("tonnage", ("tonnage",)),
        ("grade", ("grade",)),
        ("contained_metal", ("contained_metal",)),
        ("reported_change", ("reported_increase", "reported_decrease")),
    )),
    ("F02", r"Resource", (
        ("resource_type", ("resource_or_reserve_type",)),
        ("classification", ("classification",)),
        ("tonnage", ("tonnage",)),
        ("grade", ("grade",)),
    )),
    ("F01", r"Drilling Results|Assay Results", (
        ("hole_id", ("hole_id",)), ("interval", ("interval_length",)),
        ("grade", ("grade",)), ("from_depth", ("from_depth",)),
    )),
    ("F01", r"Drilling Completed", (("drilling_status", ("drilling_status",)),)),
    ("F03", r"Metallurgical Test Results", (("testwork_type", ("testwork_type",)),)),
    ("F03", r"Recovery|Product Grade", (("recovery", ("recovery",)), ("product_grade", ("product_grade",)))),
    ("F03", r"Processing Route", (("processing_route", ("processing_route",)),)),
    ("F03", r"Planned|Commenced|Testwork Update", (("test_programme", ("test_programme", "testwork_type")),)),
    ("F05", r"Clearing Permit", (
        ("permit_type", ("permit_type",)), ("permit_status", ("permit_status",)),
        ("permit_identifier", ("permit_identifier",)), ("authority", ("authority",)),
        ("area", ("area",)), ("expiry_date", ("expiry_date",)),
    )),
    ("F05", r"Groundwater Licence", (("groundwater_status", ("permit_status",)), ("authority", ("authority",)))),
    ("F05", r"Environmental Approval", (("approval_status", ("permit_status",)),)),
    ("F05", r"Mining Lease", (("permit_type", ("permit_type",)), ("permit_status", ("permit_status",)))),
    ("F07", r"Earn-in", (
        ("transaction_type", ("transaction_type",)), ("earn_in_amount", ("earn_in_amount",)),
        ("earn_in_percentage", ("earn_in_percentage",)),
        ("maximum_ownership", ("maximum_ownership",)),
    )),
    ("F07", r"Joint Venture", (("manager", ("manager",)), ("current_ownership", ("current_ownership",)))),
    ("F07", r"Acquisition", (("asset_rights", ("asset_rights", "transaction_type")),)),
)


def split_summary_bullets(text: str) -> list[str]:
    """Return logical bullets while keeping wrapped PDF lines together."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return []

    # PDF extraction sometimes keeps several bullet glyphs on one physical line.
    expanded = re.sub(r"\s*([•●▪◦‣])\s*", r"\n\1 ", cleaned)
    lines = [line.strip() for line in expanded.splitlines() if line.strip()]
    if not lines:
        return []
    has_markers = any(re.match(r"^(?:[•●▪◦‣]|o\s+)", line) for line in lines)
    bullets: list[list[str]] = []
    for line in lines:
        marker = re.match(r"^(?:[•●▪◦‣]|o|[-–—])\s+(.+)$", line)
        if marker:
            bullets.append([marker.group(1)])
            continue
        if not bullets:
            bullets.append([line])
            continue
        # Unmarked ASX highlight boxes generally start a new item with a capital
        # letter; lowercase lines are layout wraps.  Conservative exceptions keep
        # project names attached to the preceding line.
        starts_item = not has_markers and bool(re.match(r"^[A-Z][A-Za-z$0-9]", line)) and not re.match(
            r"^(?:Rincon|Caravel|Trident|Manna|Bolt Cutter|Tabba Tabba)\b", line
        )
        if starts_item:
            bullets.append([line])
        else:
            bullets[-1].append(line)
    return [" ".join(parts).strip() for parts in bullets if parts]


def extract_summary_first_candidates(
    events: Iterable, pages: list[str], sections: list[dict], standard_form: str | None
) -> tuple[list[dict], dict]:
    """Extract candidates using a strict, auditable source escalation policy."""
    active_events = [event for event in events if event.active_result]
    requirements = expected_field_requirements(active_events)
    summary_units = _summary_units(sections)
    summary_candidates: list[dict] = []
    for source in summary_units:
        candidates = _extract_one_source(active_events, source)
        for candidate in candidates:
            metadata = candidate.setdefault("metadata", {})
            metadata.update({
                "source_region": source["name"],
                "source_unit": source["source_unit"],
                "summary_bullet_index": source["bullet_index"],
                "source_priority": SUMMARY_ORDER[source["name"]],
                "summary_bullet_text": source.get("raw_text", source["text"]),
            })
        summary_candidates.extend(candidates)
    candidates = _prefer_higher_priority(summary_candidates)
    missing_after_summary = _missing(requirements, candidates)

    standard_candidates: list[dict] = []
    standard_used = bool(missing_after_summary and standard_form in STANDARD_FORMS)
    standard_pages: list[int] = []
    if standard_used:
        sources = _standard_form_sources(pages)
        standard_pages = [item["page"] for item in sources]
        standard_candidates = _gap_filling_candidates(
            _extract_source_batch(active_events, sources, len(pages)), requirements, missing_after_summary
        )
        _annotate(standard_candidates, "standard_form", 10)
        candidates = _prefer_higher_priority(candidates + standard_candidates)
    missing_after_standard = _missing(requirements, candidates)

    body_candidates: list[dict] = []
    body_used = bool(missing_after_standard)
    body_pages: list[int] = []
    if body_used:
        body_sources = [
            {"name": "body_fallback", "page": page, "text": text, "source_unit": f"body:p{page}"}
            for page, text in enumerate(pages, 1) if text.strip()
        ]
        body_pages = [item["page"] for item in body_sources]
        body_candidates = _gap_filling_candidates(
            _extract_source_batch(active_events, body_sources, len(pages)), requirements, missing_after_standard
        )
        _annotate(body_candidates, "body_fallback", 20)
        candidates = _prefer_higher_priority(candidates + body_candidates)
    _mark_source_conflicts(candidates)
    remaining = _missing(requirements, candidates)

    source_counts = defaultdict(int)
    for candidate in candidates:
        source_counts[candidate["source_section"]] += 1
    audit = {
        "policy": "summary_bullets_then_missing_fields_standard_form_then_body_v1",
        "summary_priority": ["summary", "highlights", "key_results", "executive_summary"],
        "summary_bullet_count": len(summary_units),
        "summary_fact_count": sum(1 for item in candidates if item["source_section"] in SUMMARY_NAMES),
        "fields_after_summary": sorted({item["fact_type"] for item in _prefer_higher_priority(summary_candidates)}),
        "missing_after_summary": missing_after_summary,
        "standard_form_used": standard_used,
        "standard_form_pages": standard_pages,
        "standard_form_fact_count": sum(1 for item in candidates if item["source_section"] == "standard_form"),
        "missing_after_standard_form": missing_after_standard,
        "body_fallback_used": body_used,
        "body_fallback_pages": body_pages,
        "body_fallback_fact_count": sum(1 for item in candidates if item["source_section"] == "body_fallback"),
        "remaining_missing_fields": remaining,
        "source_fact_counts": dict(source_counts),
    }
    return candidates, audit


def expected_field_requirements(events: Iterable) -> dict[str, tuple[str, ...]]:
    requirements: dict[str, tuple[str, ...]] = {}
    for event in events:
        description = f"{event.event_type} {event.event_title}"
        for family, pattern, slots in _EVENT_REQUIREMENTS:
            if event.primary_family == family and re.search(pattern, description, re.I):
                for slot, fact_types in slots:
                    requirements[f"{family}.{slot}"] = fact_types
    return requirements


def _summary_units(sections: list[dict]) -> list[dict]:
    units: list[dict] = []
    ordered = sorted(
        (item for item in sections if item.get("name") in SUMMARY_NAMES),
        key=lambda item: (SUMMARY_ORDER[item["name"]], item.get("page") or 0),
    )
    for section_index, section in enumerate(ordered, 1):
        parent_hole: str | None = None
        for bullet_index, bullet in enumerate(split_summary_bullets(section.get("text", "")), 1):
            hole = re.fullmatch(r"((?:BCDD|BCRC|TAMT|TARC)\d{3})", bullet.strip(), re.I)
            if hole:
                parent_hole = hole.group(1).upper()
            extraction_text = bullet
            if parent_hole and re.search(r"\d+(?:\.\d+)?m\s*@", bullet, re.I) and not re.search(r"\b(?:BCDD|BCRC|TAMT|TARC)\d{3}\b", bullet, re.I):
                extraction_text = f"{parent_hole}\n{bullet}"
            units.append({
                "name": section["name"], "page": section["page"], "text": extraction_text,
                "raw_text": bullet,
                "bullet_index": bullet_index,
                "source_unit": f"{section['name']}:p{section['page']}:s{section_index}:b{bullet_index}",
            })
    return units


def _extract_one_source(events: list, source: dict) -> list[dict]:
    pages = [""] * int(source["page"])
    pages[int(source["page"]) - 1] = source["text"]
    return extract_fact_candidates(events, pages, [source])


def _extract_source_batch(events: list, sources: list[dict], page_count: int) -> list[dict]:
    sparse_pages = [""] * page_count
    for source in sources:
        sparse_pages[source["page"] - 1] = source["text"]
    return extract_fact_candidates(events, sparse_pages, sources)


def _standard_form_sources(pages: list[str]) -> list[dict]:
    # "for the period ended" picks up the cover page, which is where some
    # filers state the quarter being reported. Without it the only statement of
    # the period is the form's own "Quarter ended" box, and when extraction
    # breaks that into "Q uarter ended" the whole filing lands undated — which
    # is how CVV's March 2026 runway went missing.
    markers = ("cash and cash equivalents", "net cash from", "quarter ended",
               "exploration & evaluation", "for the period ended")
    return [
        {"name": "standard_form", "page": page, "text": text, "source_unit": f"standard_form:p{page}"}
        for page, text in enumerate(pages, 1)
        if any(marker in text.casefold() for marker in markers)
    ]


def _annotate(candidates: list[dict], region: str, priority: int) -> None:
    for candidate in candidates:
        metadata = candidate.setdefault("metadata", {})
        metadata.update({"source_region": region, "source_unit": f"{region}:p{candidate['source_page_start']}", "source_priority": priority})


def _missing(requirements: dict[str, tuple[str, ...]], candidates: list[dict]) -> list[str]:
    found = {item["fact_type"] for item in candidates}
    return sorted(slot for slot, accepted in requirements.items() if not found.intersection(accepted))


def _gap_filling_candidates(
    candidates: list[dict], requirements: dict[str, tuple[str, ...]], missing_slots: list[str]
) -> list[dict]:
    """Keep facts that fill a gap plus atomic companions from the same statement."""
    accepted = {fact_type for slot in missing_slots for fact_type in requirements.get(slot, ())}
    matching_groups = {
        (item["source_page_start"], item["source_excerpt"])
        for item in candidates if item["fact_type"] in accepted
    }
    return [
        item for item in candidates
        if item["fact_type"] in accepted
        or (item["source_page_start"], item["source_excerpt"]) in matching_groups
        or item.get("metadata", {}).get("conflicts_with_title")
        or item.get("metadata", {}).get("conflicts_with_summary")
    ]


def _prefer_higher_priority(candidates: list[dict]) -> list[dict]:
    """Remove exact semantic duplicates while retaining conflicting disclosures."""
    ranked = sorted(candidates, key=lambda item: item.get("metadata", {}).get("source_priority", 99))
    output: list[dict] = []
    seen: set[tuple] = set()
    for item in ranked:
        metadata = item.get("metadata", {})
        key = (
            item["fact_family"], item["fact_type"], item["field_name"],
            " ".join(str(item["value_raw"]).casefold().split()),
            item.get("period_start"), item.get("period_end"),
            metadata.get("period_basis"), metadata.get("interval_signature") or metadata.get("reported_interval_group"),
            metadata.get("owner"), metadata.get("phase"),
            metadata.get("resource_or_reserve_type"), metadata.get("classification"),
        )
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def _mark_source_conflicts(candidates: list[dict]) -> None:
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for item in candidates:
        grouped[(item["fact_family"], item["fact_type"], item["field_name"])].append(item)
    for items in grouped.values():
        values = {" ".join(str(item["value_raw"]).casefold().split()) for item in items}
        if len(values) <= 1:
            continue
        for item in items:
            item["review_status"] = "review_needed"
            item.setdefault("metadata", {})["source_value_conflict"] = True


def _collapse_wrapped_lines(value: str) -> str:
    # Retain nested `o` markers as boundaries so a parent and child statement do
    # not become one opaque paragraph.
    return " ".join(part.strip() for part in value.splitlines() if part.strip())
