"""Deterministic exact-name matching against approved P01 entities."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import AssetUnit, CommodityRelationship, Project, Stock


_PUNCTUATION = re.compile(r"[\s\-‐‑‒–—―.,:;()\[\]{}'\"’]+")


def normalize_entity_name(value: str) -> str:
    """Apply only the normalization allowed by P03 entity matching step 1."""
    value = unicodedata.normalize("NFKC", value or "").casefold().strip()
    return _PUNCTUATION.sub(" ", value).strip()


@dataclass(frozen=True)
class EntityCandidate:
    mention_type: str
    entity_id: int
    display_name: str
    matched_value: str
    match_method: str
    match_confidence: float
    alias_id: int | None = None
    project_id: int | None = None
    parent_asset_unit_id: int | None = None


@dataclass(frozen=True)
class CandidateOccurrence:
    start: int
    end: int
    raw: str
    normalized: str
    candidate: EntityCandidate


def exact_candidates(session: Session) -> list[EntityCandidate]:
    rows: list[EntityCandidate] = []
    for stock in session.query(Stock).all():
        rows.extend((
            EntityCandidate("stock", stock.id, f"{stock.code} · {stock.name}", stock.code, "exact_match", 1.0),
            EntityCandidate("stock", stock.id, f"{stock.code} · {stock.name}", stock.name, "exact_match", 1.0),
        ))
    for project in session.query(Project).filter(Project.active.is_(True)).all():
        rows.append(EntityCandidate("project", project.id, project.name, project.name, "exact_match", 1.0, project_id=project.id))
    for asset in session.query(AssetUnit).filter(AssetUnit.active.is_(True)).all():
        rows.append(EntityCandidate(
            "asset_unit", asset.id, asset.name, asset.name, "exact_match", 1.0,
            project_id=asset.project_id, parent_asset_unit_id=asset.parent_asset_unit_id,
        ))
    for relation in session.query(CommodityRelationship).all():
        project_id = relation.project_id or (relation.asset_unit.project_id if relation.asset_unit else None)
        rows.append(EntityCandidate(
            "commodity", relation.id, relation.commodity, relation.commodity, "exact_match", 1.0,
            project_id=project_id,
        ))
    return _deduplicate(rows)


def find_occurrences(text: str, candidates: list[EntityCandidate]) -> list[CandidateOccurrence]:
    occurrences: list[CandidateOccurrence] = []
    for candidate in candidates:
        normalized = normalize_entity_name(candidate.matched_value)
        if not normalized:
            continue
        tokens = normalized.split()
        separator = r"[\s\-‐‑‒–—―.,:;()\[\]{}'\"’]+"
        pattern = r"(?<![0-9A-Za-z])" + separator.join(re.escape(token) for token in tokens) + r"(?![0-9A-Za-z])"
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            raw = match.group(0)
            occurrences.append(CandidateOccurrence(
                start=match.start(), end=match.end(), raw=raw,
                normalized=normalize_entity_name(raw), candidate=candidate,
            ))
    return occurrences


def _deduplicate(rows: list[EntityCandidate]) -> list[EntityCandidate]:
    seen: set[tuple] = set()
    output: list[EntityCandidate] = []
    for row in rows:
        key = (row.mention_type, row.entity_id, normalize_entity_name(row.matched_value), row.match_method, row.alias_id)
        if key not in seen:
            seen.add(key)
            output.append(row)
    return output
