"""Persist source-grounded P03 mentions and validated P01 entity mappings."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import Announcement, EntityMapping, EntityMention, P3Event, P3Fact, P3ParseRun
from .entity_alias_matcher import alias_candidates
from .entity_exact_matcher import CandidateOccurrence, EntityCandidate, exact_candidates, find_occurrences
from .entity_validation_service import validate_candidate
from .entity_mapping_review_service import mapping_is_human_locked


@dataclass(frozen=True)
class SourceRecord:
    event: P3Event | None
    fact: P3Fact | None
    text: str
    section: str
    page_start: int | None
    page_end: int | None


def resolve_entities_for_run(
    session: Session,
    run: P3ParseRun,
    events: list[P3Event],
    facts: list[P3Fact],
) -> tuple[list[EntityMention], list[EntityMapping]]:
    """Resolve known names only; never creates or modifies any P01 entity."""
    announcement = session.get(Announcement, run.announcement_id) if run.announcement_id else None
    if announcement is None:
        return [], []

    exact = exact_candidates(session)
    aliases = alias_candidates(session)
    mentions: list[EntityMention] = []
    mappings: list[EntityMapping] = []
    records = [SourceRecord(event, None, event.source_excerpt or "", event.source_section, event.source_page_start, event.source_page_end) for event in events]
    records.extend(SourceRecord(None, fact, fact.source_excerpt or "", fact.source_section, fact.source_page_start, fact.source_page_end) for fact in facts)

    for record in records:
        if not record.text.strip():
            continue
        record_mapping_start = len(mappings)
        occurrences = _ordered_occurrences(record.text, exact, aliases)
        groups: dict[tuple[int, int, str, str], list[EntityCandidate]] = defaultdict(list)
        raw_by_group: dict[tuple[int, int, str, str], str] = {}
        for occurrence in occurrences:
            key = (occurrence.start, occurrence.end, occurrence.candidate.mention_type, occurrence.normalized)
            groups[key].append(occurrence.candidate)
            raw_by_group[key] = occurrence.raw

        explicit_project_ids = {
            candidate.entity_id for group in groups.values() for candidate in group if candidate.mention_type == "project"
        }
        explicit_asset_ids = {
            candidate.entity_id for group in groups.values() for candidate in group if candidate.mention_type == "asset_unit"
        }
        for key in sorted(groups):
            # Re-invoking resolution for an existing Event/Fact must never
            # replace a human decision for the same entity type. Other entity
            # types in the record can still be resolved normally.
            if _record_entity_type_has_human_lock(session, record, key[2]):
                continue
            candidates = _unique_candidates(groups[key])
            mention = EntityMention(
                announcement_id=announcement.id,
                evidence_document_id=run.evidence_document_id,
                parse_run_id=run.id,
                p3_event_id=record.event.id if record.event else None,
                p3_fact_id=record.fact.id if record.fact else None,
                mention_type=key[2],
                mention_text_raw=raw_by_group[key],
                mention_text_normalized=key[3],
                source_section=record.section,
                source_page_start=record.page_start,
                source_page_end=record.page_end,
                source_excerpt=record.text,
            )
            session.add(mention)
            session.flush()
            mentions.append(mention)

            validation = [
                (candidate, validate_candidate(session, announcement, candidate, candidates, explicit_project_ids, explicit_asset_ids))
                for candidate in candidates
            ]
            confirmed = [item for item in validation if item[1][0]]
            # A mention can have only one confirmed result. Multiple otherwise
            # valid candidates stay ambiguous instead of being guessed.
            winning_id = confirmed[0][0].entity_id if len(confirmed) == 1 else None
            for candidate, (is_valid, stock_result, parent_result, reason) in validation:
                status = (
                    "confirmed"
                    if is_valid and candidate.entity_id == winning_id
                    else "ambiguous" if winning_id is None and len(candidates) > 1 else "review_needed"
                )
                if is_valid and winning_id is None:
                    reason = f"{reason} Multiple candidates remain after validation."
                mapping = EntityMapping(
                    entity_mention_id=mention.id,
                    matched_entity_type=candidate.mention_type,
                    matched_entity_id=candidate.entity_id,
                    matched_alias_id=candidate.alias_id,
                    match_method=candidate.match_method,
                    match_confidence=candidate.match_confidence,
                    status=status,
                    stock_validation_result=stock_result,
                    parent_validation_result=parent_result,
                    matching_reason=reason,
                )
                session.add(mapping)
                session.flush()
                mappings.append(mapping)
                if status == "confirmed":
                    _link_confirmed_mapping(record, mapping)
            if winning_id is None:
                _mark_review_needed(record, mention.mention_type, mappings[-1].id if mappings else None)
        _finalize_record_links(record, mappings[record_mapping_start:])
    session.flush()
    return mentions, mappings


def _ordered_occurrences(text: str, exact: list[EntityCandidate], aliases: list[EntityCandidate]) -> list[CandidateOccurrence]:
    exact_rows = find_occurrences(text, exact)
    exact_keys = {(row.start, row.end, row.candidate.mention_type, row.normalized) for row in exact_rows}
    alias_rows = [
        row for row in find_occurrences(text, aliases)
        if (row.start, row.end, row.candidate.mention_type, row.normalized) not in exact_keys
    ]
    combined = exact_rows + alias_rows
    # A full approved alias such as "Yin Prospect" must not be split into the
    # shorter current name "Yin" plus unrelated trailing text. Exact matching
    # still wins for identical spans; longest approved identity wins for a
    # contained span of the same entity and type.
    filtered = [
        row for row in combined
        if not any(
            other is not row
            and other.candidate.mention_type == row.candidate.mention_type
            and other.candidate.entity_id == row.candidate.entity_id
            and other.start <= row.start and other.end >= row.end
            and (other.end - other.start) > (row.end - row.start)
            for other in combined
        )
    ]
    return sorted(filtered, key=lambda row: (row.start, row.end, row.candidate.mention_type, row.candidate.entity_id))


def _unique_candidates(rows: list[EntityCandidate]) -> list[EntityCandidate]:
    output: list[EntityCandidate] = []
    seen: set[tuple[str, int, str, int | None]] = set()
    for row in rows:
        key = (row.mention_type, row.entity_id, row.match_method, row.alias_id)
        if key not in seen:
            seen.add(key)
            output.append(row)
    return output


def _link_confirmed_mapping(record: SourceRecord, mapping: EntityMapping) -> None:
    target = record.fact or record.event
    if target is None:
        return
    if mapping.matched_entity_type == "project":
        target.mapped_project_id = mapping.matched_entity_id
        target.project_mapping_id = mapping.id
        target.project_mapping_status = "confirmed"
    elif mapping.matched_entity_type == "asset_unit":
        target.mapped_asset_unit_id = mapping.matched_entity_id
        target.asset_unit_mapping_id = mapping.id
        target.asset_unit_mapping_status = "confirmed"


def _mark_review_needed(record: SourceRecord, mention_type: str, mapping_id: int | None) -> None:
    target = record.fact or record.event
    if target is None:
        return
    if mention_type == "project" and target.project_mapping_status != "confirmed":
        target.mapped_project_id = None
        target.project_mapping_id = mapping_id
        target.project_mapping_status = "review_needed"
    elif mention_type == "asset_unit" and target.asset_unit_mapping_status != "confirmed":
        target.mapped_asset_unit_id = None
        target.asset_unit_mapping_id = mapping_id
        target.asset_unit_mapping_status = "review_needed"


def _finalize_record_links(record: SourceRecord, mappings: list[EntityMapping]) -> None:
    """Avoid projecting multiple confirmed entities into a singular Event/Fact field."""
    target = record.fact or record.event
    if target is None:
        return
    for entity_type in ("project", "asset_unit"):
        confirmed = [item for item in mappings if item.status == "confirmed" and item.matched_entity_type == entity_type]
        entity_ids = {item.matched_entity_id for item in confirmed}
        if len(entity_ids) <= 1:
            continue
        if entity_type == "project":
            target.mapped_project_id = None
            target.project_mapping_id = None
            target.project_mapping_status = "review_needed"
        else:
            target.mapped_asset_unit_id = None
            target.asset_unit_mapping_id = None
            target.asset_unit_mapping_status = "review_needed"


def _record_entity_type_has_human_lock(session: Session, record: SourceRecord, entity_type: str) -> bool:
    target = record.fact or record.event
    if target is None:
        return False
    mapping_id = (
        target.project_mapping_id if entity_type == "project"
        else target.asset_unit_mapping_id if entity_type == "asset_unit"
        else None
    )
    if not mapping_id:
        return False
    mapping = session.get(EntityMapping, mapping_id)
    return bool(mapping and mapping_is_human_locked(mapping))
