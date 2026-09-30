"""The sole P01 write boundary for entity proposals and P3 remapping."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import (
    Announcement, AssetUnit, AssetUnitIdentity, CommodityRelationship, EntityMapping,
    EntityMappingChangeLog, EntityMention, P01EntityProposal, P01EntityProposalReview,
    P3Event, P3Fact, Project, ProjectIdentity, ProjectRelationship, StockProject,
)
from .entity_exact_matcher import normalize_entity_name


def review_proposal(
    session: Session,
    proposal: P01EntityProposal,
    action: str,
    reviewer: str,
    review_note: str = "",
    correction: dict | None = None,
) -> P01EntityProposal:
    if proposal.status != "pending":
        raise ValueError("proposal has already been finalized")
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    before = proposal_snapshot(proposal)
    correction = correction or {}
    if action == "correct":
        _apply_correction(session, proposal, correction)
        proposal.status = "pending"
    elif action == "reject":
        proposal.status = "rejected"
    elif action == "approve":
        _approve(session, proposal, reviewer, review_note)
    elif action in {"merge", "split", "rename", "adjust_project_asset_level", "adjust_commodity", "adjust_ownership", "adjust_operator"}:
        _apply_correction(session, proposal, correction)
        proposal.proposed_payload_json = _merge_payload(proposal.proposed_payload_json, {"review_action": action})
        _approve(session, proposal, reviewer, review_note)
    else:
        raise ValueError("unsupported review action")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    proposal.reviewer = reviewer.strip()
    proposal.reviewed_by = reviewer.strip()
    proposal.reviewed_at = now
    proposal.review_note = review_note
    history = _json_object(proposal.correction_json)
    history.setdefault("history", []).append({
        "action": action, "reviewer": reviewer.strip(), "at": now.isoformat(),
        "note": review_note, "changes": correction,
    })
    proposal.correction_json = json.dumps(history, ensure_ascii=False)
    after = proposal_snapshot(proposal)
    session.add(P01EntityProposalReview(
        proposal_id=proposal.id, action=action, before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(after, ensure_ascii=False), reviewer=reviewer.strip(), review_note=review_note,
    ))
    session.flush()
    return proposal


def _approve(session: Session, proposal: P01EntityProposal, reviewer: str, note: str) -> None:
    proposal_type = proposal.proposal_type or (
        "new_asset_unit_candidate" if proposal.target_level == "asset_unit" else "new_project_candidate"
    )
    if proposal_type == "new_asset_unit_candidate":
        asset = _approve_new_asset(session, proposal)
        _backfill_asset_mappings(session, proposal, asset, reviewer, note)
    elif proposal_type == "new_project_candidate":
        project = _approve_new_project(session, proposal)
        _backfill_project_mappings(session, proposal, project, reviewer, note)
        if proposal.target_level == "asset_unit" and proposal.proposed_asset_name:
            proposal.proposed_parent_project_id = project.id
            asset = _approve_new_asset(session, proposal)
            _backfill_asset_mappings(session, proposal, asset, reviewer, note)
    elif proposal_type in {"project_alias_candidate", "project_rename_candidate"}:
        project = _target_project(session, proposal)
        _approve_project_identity(session, proposal, project, rename=proposal_type.endswith("rename_candidate"))
        _backfill_project_mappings(session, proposal, project, reviewer, note)
    elif proposal_type in {"asset_unit_alias_candidate", "asset_unit_rename_candidate"}:
        asset = _target_asset(session, proposal)
        _approve_asset_identity(session, proposal, asset, rename=proposal_type.endswith("rename_candidate"))
        _backfill_asset_mappings(session, proposal, asset, reviewer, note)
    elif proposal_type in {"project_hierarchy_change_candidate", "asset_unit_hierarchy_change_candidate"}:
        asset = _target_asset(session, proposal)
        payload = _json_object(proposal.proposed_payload_json)
        parent_project_id = proposal.proposed_parent_project_id or payload.get("project_id")
        if not parent_project_id or session.get(Project, parent_project_id) is None:
            raise ValueError("hierarchy approval requires an approved parent Project")
        asset.project_id = int(parent_project_id)
        asset.parent_asset_unit_id = payload.get("parent_asset_unit_id")
        _set_result(proposal, "asset_unit", asset.id)
    elif proposal_type == "commodity_relationship_candidate":
        payload = _json_object(proposal.proposed_payload_json)
        commodity = proposal.proposed_commodity or payload.get("commodity")
        if not commodity:
            raise ValueError("commodity relationship approval requires commodity")
        project_id = payload.get("project_id") or proposal.proposed_parent_project_id
        asset_id = payload.get("asset_unit_id")
        relation = CommodityRelationship(project_id=project_id if not asset_id else None, asset_unit_id=asset_id,
                                           commodity=commodity, source=f"proposal:{proposal.id}")
        session.add(relation); session.flush(); _set_result(proposal, "commodity_relationship", relation.id)
    elif proposal_type in {"ownership_relationship_candidate", "operator_relationship_candidate"}:
        payload = _json_object(proposal.proposed_payload_json)
        project_id = proposal.proposed_parent_project_id or payload.get("project_id")
        if not project_id:
            raise ValueError("relationship approval requires Project")
        relation = ProjectRelationship(
            stock_id=proposal.stock_id, project_id=project_id,
            relationship_type="ownership" if proposal_type.startswith("ownership") else "operator",
            ownership_pct=proposal.proposed_ownership_pct, operator_name=proposal.proposed_operator,
            source=f"proposal:{proposal.id}", source_page=proposal.source_page, source_excerpt=proposal.source_excerpt,
        )
        session.add(relation); session.flush(); _set_result(proposal, "project_relationship", relation.id)
    elif proposal_type == "merge_candidate":
        payload = _json_object(proposal.proposed_payload_json)
        if payload.get("target_asset_unit_id"):
            asset = session.get(AssetUnit, payload["target_asset_unit_id"])
            if asset is None: raise ValueError("merge target Asset Unit not found")
            _add_asset_alias(session, asset, proposal.proposed_name or proposal.proposed_asset_name or "", proposal.id)
            _set_result(proposal, "asset_unit", asset.id)
            _backfill_asset_mappings(session, proposal, asset, reviewer, note)
        elif payload.get("target_project_id"):
            project = session.get(Project, payload["target_project_id"])
            if project is None: raise ValueError("merge target Project not found")
            _add_project_alias(session, project, proposal.proposed_name or proposal.proposed_project_name, proposal.id)
            _set_result(proposal, "project", project.id)
            _backfill_project_mappings(session, proposal, project, reviewer, note)
        else:
            raise ValueError("merge approval requires a target entity")
    elif proposal_type == "split_candidate":
        if proposal.proposed_entity_type == "asset_unit":
            asset = _approve_new_asset(session, proposal); _backfill_asset_mappings(session, proposal, asset, reviewer, note)
        else:
            project = _approve_new_project(session, proposal)
            _backfill_project_mappings(session, proposal, project, reviewer, note)
    else:
        raise ValueError(f"unsupported proposal type: {proposal_type}")
    proposal.status = "approved"


def _approve_new_project(session: Session, proposal: P01EntityProposal) -> Project:
    name = (proposal.proposed_name or proposal.proposed_project_name or "").strip()
    if not name or name == "待确认":
        raise ValueError("project approval requires a confirmed name")
    key_base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:70] or f"project-{proposal.id}"
    key = key_base
    suffix = 2
    while session.query(Project).filter_by(project_key=key).first():
        key = f"{key_base}-{suffix}"; suffix += 1
    project = Project(project_key=key, name=name, commodity=proposal.proposed_commodity,
                      metadata_json=json.dumps({"p01_proposal_id": proposal.id}, ensure_ascii=False))
    session.add(project); session.flush()
    session.add(ProjectIdentity(project_id=project.id, kind="name", value=name,
                                normalized_value=normalize_entity_name(name), is_current=True, source=f"proposal:{proposal.id}"))
    session.add(StockProject(stock_id=proposal.stock_id, project_id=project.id, relationship_type="approved_proposal"))
    proposal.project_id = project.id
    _set_result(proposal, "project", project.id)
    return project


def _approve_new_asset(session: Session, proposal: P01EntityProposal) -> AssetUnit:
    project_id = proposal.proposed_parent_project_id or proposal.project_id
    if not project_id:
        # Legacy baseline proposals create their Project in the same approval.
        project = _approve_new_project(session, proposal)
        project_id = project.id
    project = session.get(Project, project_id)
    if project is None or not session.query(StockProject).filter_by(stock_id=proposal.stock_id, project_id=project.id).first():
        raise ValueError("asset approval requires an approved Stock ↔ Parent Project relationship")
    name = (proposal.proposed_name or proposal.proposed_asset_name or "").strip()
    if not name:
        raise ValueError("asset approval requires proposed name")
    normalized = normalize_entity_name(name)
    existing = next((
        row for row in session.query(AssetUnit).filter_by(project_id=project.id).all()
        if normalize_entity_name(row.name) == normalized
    ), None)
    if existing:
        asset = existing
    else:
        payload = _json_object(proposal.proposed_payload_json)
        asset = AssetUnit(
            project_id=project.id, parent_asset_unit_id=payload.get("parent_asset_unit_id"), name=name,
            unit_type=proposal.proposed_asset_type, country=payload.get("country"), region=payload.get("region"),
            commodity_override=proposal.proposed_commodity,
            metadata_json=json.dumps({"materiality_status": "approved", "p01_proposal_id": proposal.id,
                                      "source_evidence_ids": _json_list(proposal.source_evidence_document_ids_json)}, ensure_ascii=False),
        )
        session.add(asset); session.flush()
        session.add(AssetUnitIdentity(asset_unit_id=asset.id, kind="name", value=name,
                                      normalized_value=normalized, is_current=True, source=f"proposal:{proposal.id}"))
    proposal.project_id = project.id
    proposal.asset_unit_id = asset.id
    _set_result(proposal, "asset_unit", asset.id)
    return asset


def _backfill_asset_mappings(session: Session, proposal: P01EntityProposal, asset: AssetUnit, reviewer: str, note: str) -> None:
    _backfill_historical_mappings(session, proposal, "asset_unit", asset.id, asset.project_id, reviewer, note)


def _backfill_project_mappings(session: Session, proposal: P01EntityProposal, project: Project, reviewer: str, note: str) -> None:
    _backfill_historical_mappings(session, proposal, "project", project.id, project.id, reviewer, note)


def _backfill_historical_mappings(
    session: Session,
    proposal: P01EntityProposal,
    entity_type: str,
    entity_id: int,
    parent_project_id: int,
    reviewer: str,
    note: str,
) -> None:
    """Backfill every safely scoped historical mention after P01 approval.

    Scope is deliberately stricter for Asset Units: Stock, normalized name and
    confirmed/candidate parent Project must all agree.  Existing human decisions
    are immutable and are never replaced by this batch operation.
    """
    normalized = proposal.proposed_name_normalized or normalize_entity_name(
        proposal.proposed_name or proposal.proposed_asset_name or proposal.proposed_project_name
    )
    mentions = session.query(EntityMention).join(
        Announcement, Announcement.id == EntityMention.announcement_id
    ).filter(
        Announcement.stock_id == proposal.stock_id,
        EntityMention.mention_type == entity_type,
        EntityMention.mention_text_normalized == normalized,
    ).order_by(EntityMention.id).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    created = skipped_scope = skipped_human = already_confirmed = 0
    for mention in mentions:
        target = session.get(P3Fact, mention.p3_fact_id) if mention.p3_fact_id else session.get(P3Event, mention.p3_event_id)
        old_rows = session.query(EntityMapping).filter_by(entity_mention_id=mention.id).order_by(EntityMapping.id).all()
        if entity_type == "asset_unit":
            target_parent = getattr(target, "mapped_project_id", None) or getattr(target, "project_id", None)
            candidate_parents = {row.candidate_parent_project_id for row in old_rows if row.candidate_parent_project_id}
            if parent_project_id != target_parent and parent_project_id not in candidate_parents:
                skipped_scope += 1
                continue
        confirmed = [row for row in old_rows if row.status == "confirmed"]
        if confirmed:
            current = confirmed[-1]
            if current.matched_entity_type == entity_type and current.matched_entity_id == entity_id:
                _link_backfilled_target(target, current, entity_type, entity_id)
                already_confirmed += 1
                continue
            # Neither P01 batch approval nor a future parser may override a
            # prior manual/P01 confirmation.  Conflicting automatic confirmed
            # rows are also left for explicit review rather than silently moved.
            skipped_human += 1
            continue
        relevant = [row for row in old_rows if row.matched_entity_type == entity_type]
        if not relevant:
            skipped_scope += 1
            continue
        old = relevant[-1]
        before = _mapping_snapshot(old)
        for row in relevant:
            if row.status in {"review_needed", "ambiguous"}:
                row.status = "superseded"
        alias_id = _approved_identity_id(session, entity_type, entity_id, normalized)
        new = EntityMapping(
            entity_mention_id=mention.id, matched_entity_type=entity_type, matched_entity_id=entity_id,
            matched_alias_id=alias_id, match_method="p01_proposal_approved", match_confidence=1.0,
            status="confirmed", stock_validation_result="p01_human_approved",
            parent_validation_result="parent_project_confirmed" if entity_type == "asset_unit" else "not_applicable",
            matching_reason=f"P01 proposal {proposal.id} approved; historical mention backfilled within Stock/parent scope.",
            candidate_parent_project_id=parent_project_id, proposal_id=proposal.id,
            candidate_payload_json=json.dumps({
                "historical_backfill": True, "source_mapping_ids": [row.id for row in relevant],
                "human_locked": True, "automatic_overwrite_allowed": False,
            }, ensure_ascii=False),
            reviewed_by=reviewer, reviewed_at=now, review_note=note,
        )
        session.add(new); session.flush()
        _link_backfilled_target(target, new, entity_type, entity_id)
        session.add(EntityMappingChangeLog(
            entity_mention_id=mention.id, old_mapping_id=old.id, new_mapping_id=new.id, proposal_id=proposal.id,
            action="p01_proposal_approved_historical_backfill", before_json=json.dumps(before, ensure_ascii=False),
            after_json=json.dumps(_mapping_snapshot(new), ensure_ascii=False), reviewer=reviewer, review_note=note,
        ))
        created += 1
    payload = _json_object(proposal.proposed_payload_json)
    payload["historical_backfill"] = {
        "entity_type": entity_type, "entity_id": entity_id, "normalized_name": normalized,
        "created_count": created, "already_confirmed_count": already_confirmed,
        "skipped_scope_count": skipped_scope, "skipped_existing_confirmation_count": skipped_human,
        "automatic_overwrite_count": 0,
    }
    proposal.proposed_payload_json = json.dumps(payload, ensure_ascii=False)


def _approved_identity_id(session: Session, entity_type: str, entity_id: int, normalized: str) -> int | None:
    model = ProjectIdentity if entity_type == "project" else AssetUnitIdentity
    key = "project_id" if entity_type == "project" else "asset_unit_id"
    row = session.query(model).filter(
        getattr(model, key) == entity_id,
        model.normalized_value == normalized,
    ).order_by(model.id.desc()).first()
    return row.id if row else None


def _link_backfilled_target(target, mapping: EntityMapping, entity_type: str, entity_id: int) -> None:
    if target is None:
        return
    if entity_type == "project":
        target.project_id = entity_id
        target.mapped_project_id = entity_id
        target.project_mapping_id = mapping.id
        target.project_mapping_status = "confirmed"
    else:
        target.asset_unit_id = entity_id
        target.mapped_asset_unit_id = entity_id
        target.asset_unit_mapping_id = mapping.id
        target.asset_unit_mapping_status = "confirmed"
        if isinstance(target, P3Fact):
            target.project_attribution_status = "confirmed"


def _apply_correction(session: Session, proposal: P01EntityProposal, changes: dict) -> None:
    allowed = {
        "proposed_name", "proposed_project_name", "proposed_asset_name", "proposed_asset_type",
        "proposed_entity_type", "proposed_parent_project_id", "proposed_commodity", "proposed_ownership_pct",
        "proposed_operator", "proposed_payload_json", "source_excerpt",
    }
    for field, value in changes.items():
        if field not in allowed:
            raise ValueError(f"unsupported correction field: {field}")
        if field == "proposed_parent_project_id" and value is not None and session.get(Project, value) is None:
            raise ValueError("corrected parent Project not found")
        if field == "proposed_payload_json" and isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False)
        setattr(proposal, field, value)
    name = proposal.proposed_name or proposal.proposed_asset_name or proposal.proposed_project_name
    proposal.proposed_name_normalized = normalize_entity_name(name)
    proposal.dedupe_key = f"{proposal.stock_id}|{proposal.proposal_type}|{proposal.proposed_name_normalized}|{proposal.proposed_parent_project_id or 'unknown'}"


def _approve_project_identity(session: Session, proposal: P01EntityProposal, project: Project, rename: bool) -> None:
    name = proposal.proposed_name or proposal.proposed_project_name
    if rename:
        for row in project.identity_history:
            row.is_current = False
        project.name = name
        session.flush()
        session.add(ProjectIdentity(project_id=project.id, kind="name", value=name, normalized_value=normalize_entity_name(name), is_current=True, source=f"proposal:{proposal.id}"))
    else:
        _add_project_alias(session, project, name, proposal.id)
    _set_result(proposal, "project", project.id)


def _approve_asset_identity(session: Session, proposal: P01EntityProposal, asset: AssetUnit, rename: bool) -> None:
    name = proposal.proposed_name or proposal.proposed_asset_name or ""
    if rename:
        for row in asset.identity_history:
            row.is_current = False
        asset.name = name
        session.flush()
        session.add(AssetUnitIdentity(asset_unit_id=asset.id, kind="name", value=name, normalized_value=normalize_entity_name(name), is_current=True, source=f"proposal:{proposal.id}"))
    else:
        _add_asset_alias(session, asset, name, proposal.id)
    _set_result(proposal, "asset_unit", asset.id)


def _add_project_alias(session, project, name, proposal_id):
    normalized = normalize_entity_name(name)
    if not session.query(ProjectIdentity).filter_by(project_id=project.id, normalized_value=normalized).first():
        session.add(ProjectIdentity(project_id=project.id, kind="alias", value=name, normalized_value=normalized, is_current=False, source=f"proposal:{proposal_id}"))


def _add_asset_alias(session, asset, name, proposal_id):
    normalized = normalize_entity_name(name)
    if not session.query(AssetUnitIdentity).filter_by(asset_unit_id=asset.id, normalized_value=normalized).first():
        session.add(AssetUnitIdentity(asset_unit_id=asset.id, kind="alias", value=name, normalized_value=normalized, is_current=False, source=f"proposal:{proposal_id}"))


def _target_project(session, proposal):
    payload = _json_object(proposal.proposed_payload_json)
    row = session.get(Project, payload.get("target_project_id") or proposal.proposed_parent_project_id or proposal.project_id)
    if row is None: raise ValueError("target Project not found")
    return row


def _target_asset(session, proposal):
    payload = _json_object(proposal.proposed_payload_json)
    row = session.get(AssetUnit, payload.get("target_asset_unit_id") or proposal.asset_unit_id)
    if row is None: raise ValueError("target Asset Unit not found")
    return row


def _set_result(proposal, entity_type, entity_id):
    proposal.resulting_entity_type = entity_type; proposal.resulting_entity_id = entity_id


def proposal_snapshot(proposal: P01EntityProposal) -> dict:
    return {key: getattr(proposal, key) for key in (
        "id", "status", "proposal_type", "stock_id", "proposed_name", "proposed_name_normalized",
        "proposed_entity_type", "proposed_parent_project_id", "proposed_project_name", "proposed_asset_name",
        "proposed_asset_type", "proposed_commodity", "proposed_payload_json", "confidence",
        "resulting_entity_type", "resulting_entity_id",
    )}


def _mapping_snapshot(mapping):
    return {key: getattr(mapping, key) for key in (
        "id", "entity_mention_id", "matched_entity_type", "matched_entity_id", "match_method", "status",
        "candidate_parent_project_id", "proposal_id", "matching_reason",
    )}


def _merge_payload(raw, changes):
    value = _json_object(raw); value.update(changes); return json.dumps(value, ensure_ascii=False)


def _json_object(raw):
    if isinstance(raw, dict): return raw
    try: value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError): return {}
    return value if isinstance(value, dict) else {}


def _json_list(raw):
    try: value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError): return []
    return value if isinstance(value, list) else []


def _json_list_of_objects(raw):
    return [item for item in _json_list(raw) if isinstance(item, dict)]
