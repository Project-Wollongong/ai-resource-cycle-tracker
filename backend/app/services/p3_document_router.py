"""ASX document routing. Official metadata describes the document, not every event."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any


@dataclass(frozen=True)
class DocumentRoute:
    document_category: str
    official_header_type: str | None
    official_subtype: str | None
    standard_form: str | None
    routing_source: str
    default_family: str | None = None
    non_core_bucket: str | None = None


def route_document(headline: str, raw_payload: str | dict[str, Any] | None = None) -> DocumentRoute:
    payload = _payload(raw_payload)
    header = _first(payload, "announcementType", "headerType", "type", "announcement_type")
    subtype = _first(payload, "subType", "announcementSubtype", "headerSubType", "subtype")
    form_value = _first(payload, "formType", "standardForm", "form", "documentType")
    official_text = " ".join(value for value in (header, subtype, form_value) if value)
    searchable = f"{official_text}\n{headline or ''}"
    standard_form = _standard_form(searchable)
    source = "official_header" if official_text.strip() else "title_routing"

    if standard_form == "Appendix 3Y" or re.search(r"director'?s interest notice|security holder details", searchable, re.I):
        return DocumentRoute("Appendix 3Y", header, subtype, standard_form or "Appendix 3Y", source, non_core_bucket="Ownership / Governance")
    if standard_form in {"Appendix 5B", "Appendix 4C"} or re.search(r"quarterly activities|quarterly cash\s*flow", official_text, re.I):
        category = "Quarterly Report / Appendix 5B" if standard_form == "Appendix 5B" else "Quarterly Activities"
        return DocumentRoute(category, header, subtype, standard_form, source, default_family="F08")
    if re.search(r"annual report|half[- ]year|financial report|full year", official_text, re.I):
        return DocumentRoute(header or "Financial Report", header, subtype, standard_form, source, default_family="F08")
    if standard_form in {"Appendix 3B", "Appendix 2A", "Appendix 3C", "Appendix 3G", "Appendix 3H"} or re.search(r"issued capital|proposed issue of securities|capital raising", official_text, re.I):
        return DocumentRoute(standard_form or header or "Funding / Capital", header, subtype, standard_form, source, default_family="F06")

    title = headline or ""
    for pattern, category in (
        (r"\bdfs\b|definitive feasibility|pre[- ]feasibility|scoping study", "Development / Study Announcement"),
        (r"placement|share purchase plan|\bspp\b|rights issue|entitlement offer", "Funding / Capital"),
        (r"mineral resource|ore reserve|reserve (?:update|grows?|growth)|\bmre\b", "Resource / Reserve Update"),
        (r"drill(?:ing)? results|assay results|drill programme|drill program", "Exploration / Drilling Update"),
        (r"metallurg|testwork|pilot plant", "Metallurgy / Processing Update"),
        (r"mining lease|groundwater licen[cs]e|environmental approval|clearing permit", "Permitting / Project Access"),
        (r"joint venture|farm[- ]in|earn[- ]in|acquisition|asset sale", "Commercial / Corporate Transaction"),
    ):
        if re.search(pattern, title, re.I):
            return DocumentRoute(category, header, subtype, standard_form, source)
    return DocumentRoute(header or "Other / Needs Review", header, subtype, standard_form, source)


def _payload(raw_payload: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw_payload, dict):
        return raw_payload
    if not raw_payload:
        return {}
    try:
        value = json.loads(raw_payload)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _first(payload: dict[str, Any], *keys: str) -> str | None:
    lowered = {str(key).casefold(): value for key, value in payload.items()}
    for key in keys:
        value = payload.get(key, lowered.get(key.casefold()))
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _standard_form(text: str) -> str | None:
    for form in ("Appendix 5B", "Appendix 4C", "Appendix 3Y", "Appendix 3B", "Appendix 2A", "Appendix 3C", "Appendix 3G", "Appendix 3H"):
        if re.search(rf"\b{re.escape(form)}\b", text, re.I):
            return form
    return None
