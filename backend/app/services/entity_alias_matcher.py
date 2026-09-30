"""Alias/former-name candidate loading from approved P01 identity rows."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AssetUnitIdentity, ProjectIdentity, StockIdentity
from .entity_exact_matcher import EntityCandidate, normalize_entity_name


def alias_candidates(session: Session) -> list[EntityCandidate]:
    rows: list[EntityCandidate] = []
    for identity in session.query(StockIdentity).all():
        stock = identity.stock
        canonical = stock.code if identity.kind == "ticker" else stock.name
        if identity.is_current and normalize_entity_name(identity.value) == normalize_entity_name(canonical):
            continue
        method = "alias_match" if identity.kind == "alias" else "former_name_match"
        rows.append(EntityCandidate(
            "stock", stock.id, f"{stock.code} · {stock.name}", identity.value,
            method, 0.98 if method == "alias_match" else 0.97, alias_id=identity.id,
        ))
    for identity in session.query(ProjectIdentity).all():
        project = identity.project
        if identity.is_current and normalize_entity_name(identity.value) == normalize_entity_name(project.name):
            continue
        method = "alias_match" if identity.kind == "alias" else "former_name_match"
        rows.append(EntityCandidate(
            "project", project.id, project.name, identity.value, method,
            0.98 if method == "alias_match" else 0.97, alias_id=identity.id, project_id=project.id,
        ))
    for identity in session.query(AssetUnitIdentity).all():
        asset = identity.asset_unit
        if identity.is_current and normalize_entity_name(identity.value) == normalize_entity_name(asset.name):
            continue
        method = "alias_match" if identity.kind == "alias" else "former_name_match"
        rows.append(EntityCandidate(
            "asset_unit", asset.id, asset.name, identity.value, method,
            0.98 if method == "alias_match" else 0.97, alias_id=identity.id,
            project_id=asset.project_id, parent_asset_unit_id=asset.parent_asset_unit_id,
        ))
    return rows
