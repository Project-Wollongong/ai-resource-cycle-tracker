"""Discover unresolved named sub-assets without modifying the P01 entity tree."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import Announcement, EntityMapping, EntityMention, P01EntityProposal, P3Event, P3Fact, P3ParseRun, Project
from .entity_exact_matcher import normalize_entity_name


ASSET_SUFFIXES = {
    "target", "prospect", "zone", "anomaly", "corridor", "trend", "area", "domain", "lens", "pipe", "block"
}
_CANDIDATE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])((?:[A-Z][A-Za-z0-9'’-]*|[A-Z]{2,}|\d+)(?:\s+(?:[A-Z][A-Za-z0-9'’-]*|[A-Z]{2,}|\d+)){0,3}\s+"
    r"(?:Target|Prospect|Zone|Anomaly|Corridor|Trend|Area|Domain|Lens|Pipe|Block))(?![A-Za-z0-9])"
)
_GENERIC_CANDIDATE_NAMES = {
    "exploration target", "drill target", "target area", "project area", "study area",
    "mineralised zone", "mineralized zone", "resource area", "licence area", "license area",
}


@dataclass(frozen=True)
class CandidateSource:
    event: P3Event | None
    fact: P3Fact | None
    text: str
    section: str
    page_start: int | None
    page_end: int | None


def discover_entity_candidates(
    session: Session,
    run: P3ParseRun,
    events: list[P3Event],
    facts: list[P3Fact],
    *,
    aggregate_proposals: bool = True,
) -> tuple[list[EntityMention], list[EntityMapping], list[P01EntityProposal]]:
    """Persist unknown names and aggregate proposals after independent repetition."""
    announcement = session.get(Announcement, run.announcement_id) if run.announcement_id else None
    if announcement is None:
        return [], [], []
    sources = [CandidateSource(row, None, row.source_excerpt or "", row.source_section, row.source_page_start, row.source_page_end) for row in events]
    sources.extend(CandidateSource(None, row, row.source_excerpt or "", row.source_section, row.source_page_start, row.source_page_end) for row in facts)
    mentions: list[EntityMention] = []
    mappings: list[EntityMapping] = []
    candidate_keys: set[tuple[str, int | None]] = set()

    for source in sources:
        if not source.text:
            continue
        source_event_id = source.event.id if source.event else None
        source_fact_id = source.fact.id if source.fact else None
        confirmed_names = {
            item.mention.mention_text_normalized
            for item in session.query(EntityMapping).join(EntityMention).filter(
                EntityMapping.status == "confirmed",
                EntityMention.parse_run_id == run.id,
                EntityMention.p3_event_id == source_event_id if source_event_id is not None else EntityMention.p3_fact_id == source_fact_id,
            ).all()
        }
        parent_project_id = _confirmed_parent_project_id(source)
        for match in _CANDIDATE_PATTERN.finditer(source.text):
            raw = match.group(1).strip()
            normalized = normalize_entity_name(raw)
            if (
                normalized in confirmed_names
                or normalized in _GENERIC_CANDIDATE_NAMES
                or normalized.split()[-1] not in ASSET_SUFFIXES
            ):
                continue
            exists = session.query(EntityMention).filter_by(
                parse_run_id=run.id, p3_event_id=source_event_id, p3_fact_id=source_fact_id,
                mention_type="asset_unit", mention_text_normalized=normalized,
            ).first()
            if exists:
                continue
            mention = EntityMention(
                announcement_id=announcement.id, evidence_document_id=run.evidence_document_id, parse_run_id=run.id,
                p3_event_id=source_event_id, p3_fact_id=source_fact_id, mention_type="asset_unit",
                mention_text_raw=raw, mention_text_normalized=normalized, source_section=source.section,
                source_page_start=source.page_start, source_page_end=source.page_end, source_excerpt=source.text,
            )
            session.add(mention); session.flush()
            mapping = EntityMapping(
                entity_mention_id=mention.id, matched_entity_type="asset_unit", matched_entity_id=None,
                match_method="unresolved_candidate", match_confidence=0.55, status="review_needed",
                stock_validation_result="announcement_stock_recorded",
                parent_validation_result="parent_project_confirmed" if parent_project_id else "parent_project_unconfirmed",
                matching_reason="Named sub-area was not found in approved P01 Asset Units or identities.",
                candidate_parent_project_id=parent_project_id,
                candidate_payload_json=json.dumps({"detected_type": normalized.split()[-1], "raw_name": raw}, ensure_ascii=False),
            )
            session.add(mapping); session.flush()
            mentions.append(mention); mappings.append(mapping)
            candidate_keys.add((normalized, parent_project_id))
            target = source.fact or source.event
            if target and target.asset_unit_mapping_status != "confirmed":
                target.mapped_asset_unit_id = None
                target.asset_unit_mapping_id = mapping.id
                target.asset_unit_mapping_status = "review_needed"

    proposals = []
    if aggregate_proposals:
        proposals = [proposal for key in candidate_keys if (proposal := aggregate_candidate_proposal(
            session, announcement.stock_id, key[0], key[1]
        )) is not None]
    session.flush()
    return mentions, mappings, proposals


def aggregate_unresolved_candidates(
    session: Session,
    stock_id: int,
    mappings: list[EntityMapping],
) -> list[P01EntityProposal]:
    """Promote only names with no known-entity fuzzy suggestion to P01 candidates."""
    keys: set[tuple[str, int | None]] = set()
    for mapping in mappings:
        has_known_suggestion = session.query(EntityMapping).filter(
            EntityMapping.entity_mention_id == mapping.entity_mention_id,
            EntityMapping.match_method.in_(["fuzzy_match", "model_suggestion"]),
            EntityMapping.matched_entity_id.is_not(None),
            EntityMapping.status.in_(["review_needed", "ambiguous", "confirmed"]),
        ).first()
        if has_known_suggestion is None:
            keys.add((mapping.mention.mention_text_normalized, mapping.candidate_parent_project_id))
    return [proposal for normalized, parent_id in keys if (proposal := aggregate_candidate_proposal(
        session, stock_id, normalized, parent_id
    )) is not None]


def aggregate_candidate_proposal(
    session: Session,
    stock_id: int,
    normalized_name: str,
    parent_project_id: int | None,
) -> P01EntityProposal | None:
    query = session.query(EntityMapping).join(EntityMention).join(Announcement, Announcement.id == EntityMention.announcement_id).filter(
        Announcement.stock_id == stock_id,
        EntityMention.mention_text_normalized == normalized_name,
        EntityMention.mention_type == "asset_unit",
        EntityMapping.match_method == "unresolved_candidate",
    )
    if parent_project_id is None:
        query = query.filter(EntityMapping.candidate_parent_project_id.is_(None))
    else:
        query = query.filter(EntityMapping.candidate_parent_project_id == parent_project_id)
    mappings = query.order_by(EntityMention.id).all()
    announcement_ids = sorted({row.mention.announcement_id for row in mappings})
    if len(announcement_ids) < 2:
        return None

    evidence_ids = sorted({row.mention.evidence_document_id for row in mappings})
    event_ids = sorted({row.mention.p3_event_id for row in mappings if row.mention.p3_event_id})
    fact_ids = sorted({row.mention.p3_fact_id for row in mappings if row.mention.p3_fact_id})
    dedupe_key = f"{stock_id}|new_asset_unit_candidate|{normalized_name}|{parent_project_id or 'unknown'}"
    proposal = session.query(P01EntityProposal).filter_by(dedupe_key=dedupe_key, status="pending").one_or_none()
    raw_name = mappings[0].mention.mention_text_raw
    parent = session.get(Project, parent_project_id) if parent_project_id else None
    support = [_support_payload(row) for row in mappings]
    if proposal is None:
        proposal = P01EntityProposal(
            stock_id=stock_id, target_level="asset_unit", proposed_project_name=parent.name if parent else "待确认",
            proposed_asset_name=raw_name, proposed_asset_type=normalized_name.split()[-1], source_type="p3_entity_candidate",
            source_ref="P3 aggregated evidence", source_page=mappings[0].mention.source_page_start,
            source_excerpt=mappings[0].mention.source_excerpt, proposal_type="new_asset_unit_candidate",
            proposed_name=raw_name, proposed_name_normalized=normalized_name, proposed_entity_type="asset_unit",
            proposed_parent_project_id=parent_project_id, created_by="rule", status="pending", dedupe_key=dedupe_key,
        )
        session.add(proposal); session.flush()
    proposal.source_p3_event_ids_json = json.dumps(event_ids)
    proposal.source_p3_fact_ids_json = json.dumps(fact_ids)
    proposal.source_evidence_document_ids_json = json.dumps(evidence_ids)
    proposal.source_announcement_ids_json = json.dumps(announcement_ids)
    proposal.supporting_mentions_json = json.dumps(support, ensure_ascii=False)
    proposal.supporting_announcement_count = len(announcement_ids)
    proposal.supporting_evidence_count = len(evidence_ids)
    proposal.supporting_event_count = len(event_ids)
    proposal.supporting_fact_count = len(fact_ids)
    proposal.source_pages_json = json.dumps(sorted({row.mention.source_page_start for row in mappings if row.mention.source_page_start}))
    proposal.source_excerpts_json = json.dumps(list(dict.fromkeys(row.mention.source_excerpt for row in mappings)), ensure_ascii=False)
    proposal.confidence = min(0.95, 0.65 + 0.1 * len(announcement_ids))
    proposal.proposed_payload_json = json.dumps({
        "candidate_kind": normalized_name.split()[-1], "parent_project_confirmed": parent_project_id is not None,
        "independent_announcement_threshold": 2, "auto_create_entity": False,
    }, ensure_ascii=False)
    for mapping in mappings:
        mapping.proposal_id = proposal.id
    return proposal


def _confirmed_parent_project_id(source: CandidateSource) -> int | None:
    target = source.fact or source.event
    if target and target.project_mapping_status == "confirmed":
        return target.mapped_project_id
    return None


def _support_payload(mapping: EntityMapping) -> dict:
    mention = mapping.mention
    return {
        "mention_id": mention.id, "mapping_id": mapping.id, "announcement_id": mention.announcement_id,
        "evidence_document_id": mention.evidence_document_id, "p3_event_id": mention.p3_event_id,
        "p3_fact_id": mention.p3_fact_id, "source_section": mention.source_section,
        "source_page_start": mention.source_page_start, "source_page_end": mention.source_page_end,
        "mention_text_raw": mention.mention_text_raw, "source_excerpt": mention.source_excerpt,
    }
