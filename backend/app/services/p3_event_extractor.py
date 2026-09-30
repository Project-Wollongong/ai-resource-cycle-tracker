"""Compatibility entry point for evidence-scoped event extraction.

New parse code uses p3_classification_service so official metadata and headline
candidates can be reconciled. This function remains for callers that already
provide one evidence section.
"""
from .p3_family_rules import detect_family_events


def extract_events(text: str, section: str, page: int | None, reported_on=None) -> list[dict]:
    source = "body_fallback" if section in {"body", "body_fallback"} else "summary_confirmation"
    return detect_family_events(
        text,
        source_section="body_fallback" if source == "body_fallback" else section,
        source_page=page,
        classification_source=source,
        base_status="review_needed" if source == "body_fallback" else "auto_classified",
        reported_on=reported_on,
    )
