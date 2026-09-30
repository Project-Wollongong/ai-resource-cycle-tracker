"""Document routing plus evidence-backed P3 Event classification."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from .p3_document_router import DocumentRoute, route_document
from .p3_family_rules import FAMILY_ORDER, detect_family_events
from .p3_revision_marker import revision_tags


@dataclass(frozen=True)
class P3ClassificationResult:
    document: DocumentRoute
    events: list[dict[str, Any]]
    families: list[str]
    event_tags: list[str]
    revision_tags: list[str]
    review_needed: bool


def classify_announcement(
    headline: str,
    raw_payload: str | dict | None,
    evidence_sections: list[dict[str, Any]],
    *,
    reported_on=None,
) -> P3ClassificationResult:
    document = route_document(headline, raw_payload)
    revisions = revision_tags(headline)
    if document.non_core_bucket:
        return P3ClassificationResult(document, [], [], [], revisions, False)

    title_events = detect_family_events(
        headline,
        source_section="headline",
        source_page=None,
        classification_source="title_routing",
        base_status="review_needed",
        reported_on=reported_on,
    )
    title_families = {item["primary_family"] for item in title_events}
    events: list[dict[str, Any]] = []

    official_text = " / ".join(value for value in (document.official_header_type, document.official_subtype, document.standard_form, headline) if value)
    if document.default_family:
        official_events = detect_family_events(
            official_text,
            source_section="official_header",
            source_page=None,
            classification_source="official_header",
            base_status="auto_classified",
            reported_on=reported_on,
        )
        events.extend(item for item in official_events if item["primary_family"] == document.default_family)

    for section in evidence_sections:
        scope = str(section.get("name") or "body_fallback")
        is_fallback = scope == "body_fallback"
        source = "body_fallback" if is_fallback else "standard_form" if scope == "standard_form" else "summary_confirmation"
        events.extend(detect_family_events(
            str(section.get("text") or ""),
            source_section=scope,
            source_page=section.get("page"),
            classification_source=source,
            base_status="review_needed" if is_fallback else "auto_classified",
            reported_on=reported_on,
        ))

    if document.default_family == "F06":
        events = [event for event in events if not (
            event["primary_family"] in {"F01", "F04"}
            and (event["classification_source"] == "body_fallback" or any(marker in event["source_excerpt"].casefold() for marker in ("placement proceeds", "use of funds", "funds provide", "support priority initiatives")))
        )]
    if "reserve" in headline.casefold() and "resource" not in headline.casefold():
        events = [event for event in events if not (
            event["event_type"] == "Mineral Resource Update"
            and any(marker in event["source_excerpt"].casefold() for marker in ("previous", "in june", "in july", "in august", "released an updated resource"))
        )]

    evidence_families = {item["primary_family"] for item in events if item["classification_source"] not in {"official_header", "title_routing"}}
    conflicting_title = bool(title_families and evidence_families and not title_families.issubset(evidence_families))
    if conflicting_title:
        for event in events:
            event["classification_status"] = "review_needed"
            event["classification_reason"] += "; headline route conflicts with Summary/Highlights evidence"

    # A specific title is only a candidate. If no official/summary/body evidence
    # confirms it, retain it as a review-needed event rather than confirming it.
    confirmed_families = {item["primary_family"] for item in events}
    for item in title_events:
        if item["primary_family"] not in confirmed_families:
            item["classification_reason"] += "; title-only candidate requires evidence confirmation"
            events.append(item)

    if not events:
        excerpt = (evidence_sections[0].get("text") if evidence_sections else headline) or ""
        events.append({
            "event_family": "OTHER",
            "primary_family": "OTHER",
            "secondary_families_json": "[]",
            "event_type": "OTHER_NEEDS_REVIEW",
            "event_title": "Other / Needs Review",
            "event_status": "review_needed",
            "classification_status": "review_needed",
            "classification_source": "body_fallback" if evidence_sections and evidence_sections[0].get("name") == "body_fallback" else "title_routing",
            "classification_confidence": 0.2,
            "source_section": evidence_sections[0].get("name", "headline") if evidence_sections else "headline",
            "source_page_start": evidence_sections[0].get("page") if evidence_sections else None,
            "source_page_end": evidence_sections[0].get("page") if evidence_sections else None,
            "source_excerpt": str(excerpt)[:1500],
            "confidence": 0.2,
            "classification_reason": "No official form or specific F01-F08 evidence phrase was found",
            "reported_on": reported_on,
        })

    events = _dedupe(events)
    for event in events:
        event["revision_tags_json"] = json.dumps(revisions, ensure_ascii=False)
        event["original_classification_json"] = json.dumps(_classification_snapshot(event), ensure_ascii=False)
        event["active_result"] = True
    families = [family for family in FAMILY_ORDER if any(event["primary_family"] == family for event in events)]
    if any(event["primary_family"] == "OTHER" for event in events):
        families.append("OTHER")
    tags = list(dict.fromkeys(event["event_type"] for event in events if event["primary_family"] != "OTHER"))
    return P3ClassificationResult(document, events, families, tags, revisions, any(event["classification_status"] == "review_needed" for event in events))


def _dedupe(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {"summary_confirmation": 0, "standard_form": 1, "official_header": 2, "body_fallback": 3, "title_routing": 4}
    status_rank = {"proposed": 0, "planned": 0, "reported": 1, "ongoing": 1, "firm_commitments": 2, "technical_support": 2, "submitted": 2, "granted": 3, "completed": 3, "funds_received": 4}
    chosen: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for event in events:
        key = (event["primary_family"], event["event_type"])
        if key not in chosen:
            chosen[key] = event
            order.append(key)
        elif priority.get(event["classification_source"], 9) < priority.get(chosen[key]["classification_source"], 9):
            chosen[key] = event
        elif status_rank.get(event["event_status"], 1) > status_rank.get(chosen[key]["event_status"], 1):
            chosen[key]["event_status"] = event["event_status"]
            chosen[key]["classification_source"] = f"{chosen[key]['classification_source']}+{event['classification_source']}"
            chosen[key]["classification_reason"] += f"; status refined from {event['source_section']}"
            if event["classification_status"] == "review_needed":
                chosen[key]["classification_status"] = "review_needed"
        elif event["classification_source"] == "title_routing":
            chosen[key]["classification_reason"] += "; headline supplied the initial route candidate"
    return [chosen[key] for key in order]


def _classification_snapshot(event: dict[str, Any]) -> dict[str, Any]:
    return {key: event.get(key) for key in (
        "primary_family", "secondary_families_json", "event_type", "event_title",
        "classification_status", "classification_source", "classification_confidence",
        "revision_tags_json", "classification_reason", "event_status",
    )}
