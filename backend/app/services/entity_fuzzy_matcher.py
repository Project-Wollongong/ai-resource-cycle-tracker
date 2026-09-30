"""Conservative fuzzy suggestions for unresolved P03 entity mentions.

Fuzzy matching is deliberately the last automatic matching step.  It never
confirms a mapping and never writes a P01 entity or identity.
"""
from __future__ import annotations

import json
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from ..models import Announcement, EntityMapping, EntityMention, P3Event, P3Fact
from .entity_alias_matcher import alias_candidates
from .entity_exact_matcher import EntityCandidate, exact_candidates, normalize_entity_name
from .entity_validation_service import validate_candidate


FUZZY_THRESHOLD = 0.84
FUZZY_AMBIGUITY_MARGIN = 0.04


def suggest_fuzzy_mappings(
    session: Session,
    mentions: list[EntityMention],
    *,
    threshold: float = FUZZY_THRESHOLD,
) -> list[EntityMapping]:
    """Create review-only suggestions after exact and alias matching failed."""
    pool = _candidate_pool(session)
    suggestions: list[EntityMapping] = []
    for mention in mentions:
        if _has_confirmed_or_human_mapping(session, mention.id):
            continue
        announcement = session.get(Announcement, mention.announcement_id)
        if announcement is None:
            continue
        target = session.get(P3Fact, mention.p3_fact_id) if mention.p3_fact_id else session.get(P3Event, mention.p3_event_id)
        explicit_project_ids = {
            project_id for project_id in (
                getattr(target, "mapped_project_id", None),
                getattr(target, "project_id", None),
            ) if project_id
        }
        scored: list[tuple[float, EntityCandidate, tuple[bool, str, str, str]]] = []
        for candidate in pool:
            if candidate.mention_type != mention.mention_type:
                continue
            score = _similarity(mention.mention_text_normalized, normalize_entity_name(candidate.matched_value))
            if score < threshold or score >= 1.0:
                continue
            validation = validate_candidate(
                session, announcement, candidate, [candidate], explicit_project_ids, set()
            )
            # A stock/parent conflict is useful audit evidence, but not a useful
            # fuzzy suggestion.  It stays represented by the unresolved row.
            if not validation[0]:
                continue
            scored.append((score, candidate, validation))
        if not scored:
            continue
        scored.sort(key=lambda row: (-row[0], row[1].entity_id, row[1].matched_value))
        best = scored[0][0]
        finalists = [row for row in scored if best - row[0] <= FUZZY_AMBIGUITY_MARGIN]
        ambiguous = len({(row[1].mention_type, row[1].entity_id) for row in finalists}) > 1
        for score, candidate, (_, stock_result, parent_result, reason) in finalists:
            if _same_open_suggestion(session, mention.id, "fuzzy_match", candidate.entity_id):
                continue
            mapping = EntityMapping(
                entity_mention_id=mention.id,
                matched_entity_type=candidate.mention_type,
                matched_entity_id=candidate.entity_id,
                matched_alias_id=candidate.alias_id,
                match_method="fuzzy_match",
                match_confidence=round(score, 6),
                status="ambiguous" if ambiguous else "review_needed",
                stock_validation_result=stock_result,
                parent_validation_result=parent_result,
                matching_reason=(
                    "Fuzzy name similarity passed Stock and parent validation; human confirmation is required. "
                    + reason
                ),
                candidate_parent_project_id=candidate.project_id,
                candidate_payload_json=json.dumps({
                    "algorithm": "difflib_sequence_matcher_v1",
                    "threshold": threshold,
                    "ambiguity_margin": FUZZY_AMBIGUITY_MARGIN,
                    "matched_value": candidate.matched_value,
                    "display_name": candidate.display_name,
                    "automatic_confirmation": False,
                }, ensure_ascii=False),
            )
            session.add(mapping)
            session.flush()
            suggestions.append(mapping)
    return suggestions


def _candidate_pool(session: Session) -> list[EntityCandidate]:
    rows = exact_candidates(session) + alias_candidates(session)
    output: list[EntityCandidate] = []
    seen: set[tuple[str, int, str]] = set()
    for row in rows:
        key = (row.mention_type, row.entity_id, normalize_entity_name(row.matched_value))
        if key not in seen:
            seen.add(key)
            output.append(row)
    return output


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    direct = SequenceMatcher(None, left, right).ratio()
    left_tokens = " ".join(sorted(left.split()))
    right_tokens = " ".join(sorted(right.split()))
    token_sorted = SequenceMatcher(None, left_tokens, right_tokens).ratio()
    return max(direct, token_sorted)


def _has_confirmed_or_human_mapping(session: Session, mention_id: int) -> bool:
    return session.query(EntityMapping).filter(
        EntityMapping.entity_mention_id == mention_id,
        (EntityMapping.status == "confirmed") | (EntityMapping.match_method == "manual_confirmation"),
    ).first() is not None


def _same_open_suggestion(session: Session, mention_id: int, method: str, entity_id: int) -> bool:
    return session.query(EntityMapping).filter(
        EntityMapping.entity_mention_id == mention_id,
        EntityMapping.match_method == method,
        EntityMapping.matched_entity_id == entity_id,
        EntityMapping.status.in_(["review_needed", "ambiguous", "confirmed"]),
    ).first() is not None
