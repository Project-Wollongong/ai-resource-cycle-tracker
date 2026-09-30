"""Revision modifiers and conservative P02 announcement-version linking."""
from __future__ import annotations

from difflib import SequenceMatcher
import re

from sqlalchemy.orm import Session

from ..models import Announcement, AnnouncementVersionRelation


REVISION_PATTERNS = (
    (r"\brevised\b|\brevision\b", "Revised", "revises"),
    (r"\bcorrection\b|\bcorrected\b", "Correction", "corrects"),
    (r"\breplacement\b|\breplaced\b", "Replacement", "replaces"),
    (r"\bretraction\b|\bretracted\b", "Retraction", "retracts"),
    (r"\bwithdrawal\b|\bwithdrawn\b", "Withdrawal", "withdraws"),
    (r"\bamended\b|\bamendment\b", "Amended", "amends"),
)


def revision_tags(text: str) -> list[str]:
    return [label for pattern, label, _ in REVISION_PATTERNS if re.search(pattern, text or "", re.I)]


def relation_type_for(text: str) -> str | None:
    return next((relation for pattern, _, relation in REVISION_PATTERNS if re.search(pattern, text or "", re.I)), None)


def connect_version_candidate(session: Session, announcement: Announcement) -> AnnouncementVersionRelation | None:
    """Create only a pending candidate; never overwrite or deactivate history."""
    relation_type = relation_type_for(announcement.headline)
    if not relation_type:
        return None
    existing = session.query(AnnouncementVersionRelation).filter_by(successor_announcement_id=announcement.id).first()
    if existing:
        return existing
    candidates = session.query(Announcement).filter(
        Announcement.stock_id == announcement.stock_id,
        Announcement.id != announcement.id,
        Announcement.ann_date <= announcement.ann_date,
    ).order_by(Announcement.ann_date.desc()).limit(30).all()
    current = _business_title(announcement.headline)
    scored = [(SequenceMatcher(None, current, _business_title(row.headline)).ratio(), row) for row in candidates]
    score, predecessor = max(scored, default=(0.0, None), key=lambda item: item[0])
    if predecessor is None or score < 0.5:
        return None
    relation = AnnouncementVersionRelation(
        predecessor_announcement_id=predecessor.id,
        successor_announcement_id=announcement.id,
        relation_type=relation_type,
        confidence=round(score, 3),
        status="pending_review",
        source="p3_revision_marker_v2",
    )
    session.add(relation)
    return relation


def _business_title(value: str) -> str:
    text = (value or "").casefold()
    for pattern, _, _ in REVISION_PATTERNS:
        text = re.sub(pattern, " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()
