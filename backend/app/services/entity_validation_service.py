"""Stock and hierarchy validation for deterministic P03 entity candidates."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Announcement, StockProject
from .entity_exact_matcher import EntityCandidate


def project_link_is_effective(session: Session, stock_id: int, project_id: int, at: datetime | None) -> bool:
    links = session.query(StockProject).filter_by(stock_id=stock_id, project_id=project_id).all()
    day = at.date() if at else None
    return any(
        (day is None or link.effective_from is None or link.effective_from <= day)
        and (day is None or link.effective_to is None or day < link.effective_to)
        for link in links
    )


def validate_candidate(
    session: Session,
    announcement: Announcement,
    candidate: EntityCandidate,
    same_mention_candidates: list[EntityCandidate],
    explicit_project_ids: set[int],
    explicit_asset_ids: set[int],
) -> tuple[bool, str, str, str]:
    """Return confirmed, stock result, parent result, human-readable reason."""
    if candidate.mention_type == "stock":
        ok = candidate.entity_id == announcement.stock_id
        return ok, "stock_confirmed" if ok else "stock_conflict", "not_applicable", (
            "Mention resolves to the announcement stock." if ok else "Mention resolves to a different stock."
        )

    project_id = candidate.project_id
    stock_ok = bool(project_id and project_link_is_effective(session, announcement.stock_id, project_id, announcement.ann_date))
    stock_result = "stock_project_relationship_confirmed" if stock_ok else "stock_project_relationship_missing_or_conflict"

    if candidate.mention_type == "project":
        valid_for_stock = [row for row in same_mention_candidates if row.project_id and project_link_is_effective(
            session, announcement.stock_id, row.project_id, announcement.ann_date
        )]
        unique_for_stock = len({row.entity_id for row in valid_for_stock}) == 1
        confirmed = stock_ok and unique_for_stock
        reason = "Approved Stock ↔ Project relationship confirmed." if confirmed else (
            "Project name is ambiguous for this stock." if stock_ok else "No approved Stock ↔ Project relationship for this announcement."
        )
        return confirmed, stock_result, "not_applicable", reason

    if candidate.mention_type == "asset_unit":
        if explicit_project_ids:
            parent_ok = candidate.project_id in explicit_project_ids
            parent_result = "parent_project_confirmed" if parent_ok else "parent_project_conflict"
        else:
            unique_asset = len({row.entity_id for row in same_mention_candidates}) == 1
            parent_ok = unique_asset and stock_ok
            parent_result = "unique_asset_and_stock_confirmed" if parent_ok else "parent_project_not_explicit_or_asset_ambiguous"
        other_explicit_assets = explicit_asset_ids - {candidate.entity_id}
        parent_asset_ok = not candidate.parent_asset_unit_id or not other_explicit_assets or candidate.parent_asset_unit_id in other_explicit_assets
        if not parent_asset_ok:
            parent_result = "parent_asset_unit_conflict"
        elif candidate.parent_asset_unit_id and candidate.parent_asset_unit_id in other_explicit_assets:
            parent_result = "parent_project_and_asset_unit_confirmed" if parent_ok else parent_result
        confirmed = stock_ok and parent_ok and parent_asset_ok
        reason = "Asset Unit parent Project and Stock relationship confirmed." if confirmed else (
            "Asset Unit parent Asset Unit conflicts with the Asset Unit named in this source." if not parent_asset_ok else
            "Asset Unit parent Project conflicts with the Project named in this source." if explicit_project_ids and not parent_ok
            else "Asset Unit could not be uniquely validated against its parent Project and announcement Stock."
        )
        return confirmed, stock_result, parent_result, reason

    # CommodityRelationship is the approved P01 commodity association in the
    # current schema. It is confirmed only when exactly one candidate belongs
    # to a Project linked to the announcement Stock.
    valid_for_stock = [row for row in same_mention_candidates if row.project_id and project_link_is_effective(
        session, announcement.stock_id, row.project_id, announcement.ann_date
    )]
    unique_for_stock = len({row.entity_id for row in valid_for_stock}) == 1
    confirmed = stock_ok and unique_for_stock
    return confirmed, stock_result, "commodity_parent_confirmed" if confirmed else "commodity_parent_ambiguous", (
        "Approved commodity relationship is unique for the announcement Stock." if confirmed
        else "Commodity alone does not uniquely identify a Project or Asset Unit."
    )
