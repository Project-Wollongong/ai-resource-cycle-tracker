"""Compatibility facade for neutral P03 F01-F08 document routing."""
from dataclasses import dataclass, field

from ..services.p3_classification_service import classify_announcement
from ..services.p3_family_rules import FAMILY_NAMES


@dataclass(frozen=True)
class FamilyClassification:
    document_category: str
    families: list[str] = field(default_factory=list)
    event_labels: list[str] = field(default_factory=list)
    revision_tags: list[str] = field(default_factory=list)
    source: str = "title_routing"
    official_header_type: str | None = None
    official_subtype: str | None = None
    standard_form: str | None = None
    review_needed: bool = False


def classify_families(headline: str, raw_payload: str | dict | None = None, summary_text: str = "") -> FamilyClassification:
    sections = [{"name": "summary", "page": None, "text": summary_text}] if summary_text.strip() else []
    result = classify_announcement(headline, raw_payload, sections)
    return FamilyClassification(
        document_category=result.document.document_category,
        families=[family for family in result.families if family != "OTHER"],
        event_labels=result.event_tags,
        revision_tags=result.revision_tags,
        source="summary_confirmation" if summary_text.strip() else result.document.routing_source,
        official_header_type=result.document.official_header_type,
        official_subtype=result.document.official_subtype,
        standard_form=result.document.standard_form,
        review_needed=result.review_needed,
    )
