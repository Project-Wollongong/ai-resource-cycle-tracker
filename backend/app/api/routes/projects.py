import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ...models import AssetUnit, AssetUnitIdentity, AssetUnitProposal, CommodityRelationship, Project, ProjectIdentity, ProjectRelationship, StockProject
from ...schemas import (
    AssetUnitCreate,
    AssetUnitIdentityInput,
    AssetUnitIdentityOut,
    AssetUnitOut,
    AssetUnitProposalCreate,
    AssetUnitProposalOut,
    CommodityRelationshipInput,
    CommodityRelationshipOut,
    ProjectCreate,
    ProjectIdentityInput,
    ProjectIdentityOut,
    ProjectOut,
    ProjectRelationshipCreate,
    ProjectRelationshipOut,
)
from ...services.stock_identity import clean, normalize
from ..deps import get_db

router = APIRouter(prefix="/projects", tags=["projects"])


def _identity_values(payload):
    value = clean(payload.value)
    if not value:
        raise HTTPException(status_code=422, detail="identity value cannot be empty")
    if payload.valid_from and payload.valid_to and payload.valid_from >= payload.valid_to:
        raise HTTPException(status_code=422, detail="valid_to must be after valid_from")
    return value, normalize(value)


def _check_project_identity(db, project_id, payload, exclude_id=None):
    value, normalized = _identity_values(payload)
    query = db.query(ProjectIdentity).filter(ProjectIdentity.project_id == project_id, ProjectIdentity.normalized_value == normalized)
    if exclude_id is not None:
        query = query.filter(ProjectIdentity.id != exclude_id)
    for row in query.all():
        if row.valid_to is None or payload.valid_from is None or row.valid_from is None or row.valid_from < payload.valid_to:
            if payload.valid_to is None or row.valid_from is None or payload.valid_to > row.valid_from:
                raise HTTPException(status_code=409, detail="overlapping project identity history")
    return value, normalized


def _check_asset_identity(db, asset_unit_id, payload, exclude_id=None):
    value, normalized = _identity_values(payload)
    query = db.query(AssetUnitIdentity).filter(AssetUnitIdentity.asset_unit_id == asset_unit_id, AssetUnitIdentity.normalized_value == normalized)
    if exclude_id is not None:
        query = query.filter(AssetUnitIdentity.id != exclude_id)
    for row in query.all():
        if row.valid_to is None or payload.valid_from is None or row.valid_from is None or row.valid_from < payload.valid_to:
            if payload.valid_to is None or row.valid_from is None or payload.valid_to > row.valid_from:
                raise HTTPException(status_code=409, detail="overlapping asset identity history")
    return value, normalized


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    if db.query(Project).filter_by(project_key=payload.project_key).first():
        raise HTTPException(status_code=409, detail="project key already exists")
    project = Project(**payload.model_dump(exclude={"stock_ids"}))
    db.add(project)
    db.flush()
    for stock_id in dict.fromkeys(payload.stock_ids):
        db.add(StockProject(stock_id=stock_id, project_id=project.id))
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(active: bool | None = True, db: Session = Depends(get_db)):
    query = db.query(Project).options(selectinload(Project.asset_units))
    if active is not None:
        query = query.filter(Project.active == active)
    return query.order_by(Project.name).all()


@router.get("/{project_key}", response_model=ProjectOut)
def get_project(project_key: str, db: Session = Depends(get_db)):
    project = db.query(Project).options(selectinload(Project.asset_units)).filter_by(project_key=project_key).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.get("/{project_key}/identities", response_model=list[ProjectIdentityOut])
def list_project_identities(project_key: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return db.query(ProjectIdentity).filter_by(project_id=project.id).order_by(ProjectIdentity.id).all()


@router.post("/{project_key}/identities", response_model=ProjectIdentityOut, status_code=201)
def add_project_identity(project_key: str, payload: ProjectIdentityInput, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    value, normalized = _check_project_identity(db, project.id, payload)
    if payload.is_current and db.query(ProjectIdentity).filter_by(project_id=project.id, is_current=True).first():
        raise HTTPException(status_code=409, detail="project already has a current identity")
    row = ProjectIdentity(project_id=project.id, value=value, normalized_value=normalized, **payload.model_dump(exclude={"value"}))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{project_key}/identities/{identity_id}", response_model=ProjectIdentityOut)
def update_project_identity(project_key: str, identity_id: int, payload: ProjectIdentityInput, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    row = db.query(ProjectIdentity).filter_by(id=identity_id, project_id=project.id if project else -1).one_or_none()
    if project is None or row is None:
        raise HTTPException(status_code=404, detail="project identity not found")
    value, normalized = _check_project_identity(db, project.id, payload, identity_id)
    if payload.is_current and not row.is_current and db.query(ProjectIdentity).filter(ProjectIdentity.project_id == project.id, ProjectIdentity.is_current == True, ProjectIdentity.id != identity_id).first():
        raise HTTPException(status_code=409, detail="project already has a current identity")
    for field, field_value in payload.model_dump(exclude={"value"}).items():
        setattr(row, field, field_value)
    row.value, row.normalized_value = value, normalized
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{project_key}/identities/{identity_id}")
def delete_project_identity(project_key: str, identity_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    row = db.query(ProjectIdentity).filter_by(id=identity_id, project_id=project.id if project else -1).one_or_none()
    if project is None or row is None:
        raise HTTPException(status_code=404, detail="project identity not found")
    if row.is_current or row.source != "manual":
        raise HTTPException(status_code=409, detail="confirmed/current identity history cannot be deleted")
    db.delete(row)
    db.commit()
    return {"detail": "project identity deleted"}


@router.get("/{project_key}/assets/{asset_id}/identities", response_model=list[AssetUnitIdentityOut])
def list_asset_identities(project_key: str, asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(AssetUnit).join(Project).filter(Project.project_key == project_key, AssetUnit.id == asset_id).one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="asset unit not found")
    return db.query(AssetUnitIdentity).filter_by(asset_unit_id=asset.id).order_by(AssetUnitIdentity.id).all()


@router.post("/{project_key}/assets/{asset_id}/identities", response_model=AssetUnitIdentityOut, status_code=201)
def add_asset_identity(project_key: str, asset_id: int, payload: AssetUnitIdentityInput, db: Session = Depends(get_db)):
    asset = db.query(AssetUnit).join(Project).filter(Project.project_key == project_key, AssetUnit.id == asset_id).one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="asset unit not found")
    value, normalized = _check_asset_identity(db, asset.id, payload)
    if payload.is_current and db.query(AssetUnitIdentity).filter_by(asset_unit_id=asset.id, is_current=True).first():
        raise HTTPException(status_code=409, detail="asset unit already has a current identity")
    row = AssetUnitIdentity(asset_unit_id=asset.id, value=value, normalized_value=normalized, **payload.model_dump(exclude={"value"}))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{project_key}/assets/{asset_id}/identities/{identity_id}", response_model=AssetUnitIdentityOut)
def update_asset_identity(project_key: str, asset_id: int, identity_id: int, payload: AssetUnitIdentityInput, db: Session = Depends(get_db)):
    asset = db.query(AssetUnit).join(Project).filter(Project.project_key == project_key, AssetUnit.id == asset_id).one_or_none()
    row = db.query(AssetUnitIdentity).filter_by(id=identity_id, asset_unit_id=asset.id if asset else -1).one_or_none()
    if asset is None or row is None:
        raise HTTPException(status_code=404, detail="asset unit identity not found")
    value, normalized = _check_asset_identity(db, asset.id, payload, identity_id)
    for field, field_value in payload.model_dump(exclude={"value"}).items():
        setattr(row, field, field_value)
    row.value, row.normalized_value = value, normalized
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{project_key}/assets/{asset_id}/identities/{identity_id}")
def delete_asset_identity(project_key: str, asset_id: int, identity_id: int, db: Session = Depends(get_db)):
    asset = db.query(AssetUnit).join(Project).filter(Project.project_key == project_key, AssetUnit.id == asset_id).one_or_none()
    row = db.query(AssetUnitIdentity).filter_by(id=identity_id, asset_unit_id=asset.id if asset else -1).one_or_none()
    if asset is None or row is None:
        raise HTTPException(status_code=404, detail="asset unit identity not found")
    if row.is_current or row.source != "manual":
        raise HTTPException(status_code=409, detail="confirmed/current identity history cannot be deleted")
    db.delete(row)
    db.commit()
    return {"detail": "asset unit identity deleted"}


@router.post("/{project_key}/asset-proposals", response_model=AssetUnitProposalOut, status_code=201)
def create_asset_proposal(project_key: str, payload: AssetUnitProposalCreate, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    proposal = AssetUnitProposal(project_id=project.id, **payload.model_dump())
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


@router.get("/{project_key}/asset-proposals", response_model=list[AssetUnitProposalOut])
def list_asset_proposals(project_key: str, status: str | None = None, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    query = db.query(AssetUnitProposal).filter_by(project_id=project.id)
    if status is not None:
        if status not in {"pending", "approved", "rejected"}:
            raise HTTPException(status_code=422, detail="invalid proposal status")
        query = query.filter_by(status=status)
    return query.order_by(AssetUnitProposal.id).all()


@router.put("/{project_key}/asset-proposals/{proposal_id}", response_model=AssetUnitProposalOut)
def review_asset_proposal(project_key: str, proposal_id: int, status: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    proposal = db.query(AssetUnitProposal).filter_by(id=proposal_id, project_id=project.id if project else -1).one_or_none()
    if project is None or proposal is None:
        raise HTTPException(status_code=404, detail="asset unit proposal not found")
    if status not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="status must be approved or rejected")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail="proposal has already been reviewed")
    proposal.status = status
    if status == "approved":
        asset = AssetUnit(project_id=project.id, name=proposal.proposed_name, unit_type=proposal.proposed_type, metadata_json=json.dumps({"materiality_status": "approved", "proposal_id": proposal.id, "rationale": proposal.rationale, "source_page": proposal.source_page, "source_excerpt": proposal.source_excerpt}, ensure_ascii=False))
        db.add(asset)
        db.flush()
        proposal.asset_unit_id = asset.id
        db.add(AssetUnitIdentity(asset_unit_id=asset.id, kind="name", value=asset.name, normalized_value=normalize(asset.name), is_current=True, source=f"proposal:{proposal.id}"))
    db.commit()
    db.refresh(proposal)
    return proposal


@router.post("/{project_key}/assets", response_model=AssetUnitOut, status_code=201)
def create_asset_unit(project_key: str, payload: AssetUnitCreate, db: Session = Depends(get_db)):
    raise HTTPException(status_code=409, detail="Asset Unit requires an approved materiality proposal")


def _check_project_relationship_overlap(db, project_id, payload, exclude_id=None):
    if payload.effective_from and payload.effective_to and payload.effective_from >= payload.effective_to:
        raise HTTPException(status_code=422, detail="effective_to must be after effective_from")
    query = db.query(ProjectRelationship).filter(
        ProjectRelationship.project_id == project_id,
        ProjectRelationship.stock_id == payload.stock_id,
        ProjectRelationship.relationship_type == payload.relationship_type,
    )
    if exclude_id is not None:
        query = query.filter(ProjectRelationship.id != exclude_id)
    for row in query.all():
        if (payload.effective_to is None or row.effective_from is None or payload.effective_to > row.effective_from) and (row.effective_to is None or payload.effective_from is None or payload.effective_from < row.effective_to):
            raise HTTPException(status_code=409, detail="overlapping ownership/operator relationship history")


@router.get("/{project_key}/relationships", response_model=list[ProjectRelationshipOut])
def list_project_relationships(project_key: str, as_of: date | None = None, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    rows = db.query(ProjectRelationship).filter_by(project_id=project.id).order_by(ProjectRelationship.id).all()
    if as_of:
        rows = [r for r in rows if (r.effective_from is None or r.effective_from <= as_of) and (r.effective_to is None or as_of < r.effective_to)]
    return rows


@router.post("/{project_key}/relationships", response_model=ProjectRelationshipOut, status_code=201)
def add_project_relationship(project_key: str, payload: ProjectRelationshipCreate, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    _check_project_relationship_overlap(db, project.id, payload)
    relationship = ProjectRelationship(project_id=project.id, **payload.model_dump())
    db.add(relationship)
    db.commit()
    db.refresh(relationship)
    return relationship


@router.put("/{project_key}/relationships/{relationship_id}", response_model=ProjectRelationshipOut)
def update_project_relationship(project_key: str, relationship_id: int, payload: ProjectRelationshipCreate, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    row = db.query(ProjectRelationship).filter_by(id=relationship_id, project_id=project.id if project else -1).one_or_none()
    if project is None or row is None:
        raise HTTPException(status_code=404, detail="project relationship not found")
    _check_project_relationship_overlap(db, project.id, payload, relationship_id)
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{project_key}/relationships/{relationship_id}")
def delete_project_relationship(project_key: str, relationship_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    row = db.query(ProjectRelationship).filter_by(id=relationship_id, project_id=project.id if project else -1).one_or_none()
    if project is None or row is None:
        raise HTTPException(status_code=404, detail="project relationship not found")
    if row.source != "manual":
        raise HTTPException(status_code=409, detail="source-backed relationship history cannot be deleted")
    db.delete(row)
    db.commit()
    return {"detail": "project relationship deleted"}


def _validate_commodity_interval(payload):
    if payload.effective_from and payload.effective_to and payload.effective_from >= payload.effective_to:
        raise HTTPException(status_code=422, detail="effective_to must be after effective_from")


def _check_commodity_overlap(db, *, project_id=None, asset_unit_id=None, commodity: str, start=None, end=None, exclude_id=None):
    query = db.query(CommodityRelationship).filter(CommodityRelationship.commodity == commodity)
    query = query.filter(CommodityRelationship.project_id == project_id) if project_id is not None else query.filter(CommodityRelationship.asset_unit_id == asset_unit_id)
    if exclude_id is not None:
        query = query.filter(CommodityRelationship.id != exclude_id)
    for row in query.all():
        if (end is None or row.effective_from is None or end > row.effective_from) and (row.effective_to is None or start is None or start < row.effective_to):
            raise HTTPException(status_code=409, detail="overlapping commodity relationship history")


def _active_commodity_rows(rows, as_of):
    if as_of is None:
        return rows
    return [r for r in rows if (r.effective_from is None or r.effective_from <= as_of) and (r.effective_to is None or as_of < r.effective_to)]


@router.get("/{project_key}/commodities", response_model=list[CommodityRelationshipOut])
def list_project_commodities(project_key: str, as_of: date | None = None, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return _active_commodity_rows(db.query(CommodityRelationship).filter_by(project_id=project.id).order_by(CommodityRelationship.id).all(), as_of)


@router.post("/{project_key}/commodities", response_model=CommodityRelationshipOut, status_code=201)
def add_project_commodity(project_key: str, payload: CommodityRelationshipInput, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    _validate_commodity_interval(payload)
    commodity = clean(payload.commodity).casefold()
    _check_commodity_overlap(db, project_id=project.id, commodity=commodity, start=payload.effective_from, end=payload.effective_to)
    row = CommodityRelationship(project_id=project.id, commodity=commodity, **payload.model_dump(exclude={"commodity"}))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{project_key}/commodities/{relationship_id}", response_model=CommodityRelationshipOut)
def update_project_commodity(project_key: str, relationship_id: int, payload: CommodityRelationshipInput, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    row = db.query(CommodityRelationship).filter_by(id=relationship_id, project_id=project.id if project else -1).one_or_none()
    if project is None or row is None:
        raise HTTPException(status_code=404, detail="project commodity relationship not found")
    _validate_commodity_interval(payload)
    commodity = clean(payload.commodity).casefold()
    _check_commodity_overlap(db, project_id=project.id, commodity=commodity, start=payload.effective_from, end=payload.effective_to, exclude_id=row.id)
    for field, value in payload.model_dump(exclude={"commodity"}).items():
        setattr(row, field, value)
    row.commodity = commodity
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{project_key}/commodities/{relationship_id}")
def delete_project_commodity(project_key: str, relationship_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(project_key=project_key).one_or_none()
    row = db.query(CommodityRelationship).filter_by(id=relationship_id, project_id=project.id if project else -1).one_or_none()
    if project is None or row is None:
        raise HTTPException(status_code=404, detail="project commodity relationship not found")
    if row.source != "manual":
        raise HTTPException(status_code=409, detail="source-backed commodity history cannot be deleted")
    db.delete(row)
    db.commit()
    return {"detail": "commodity relationship deleted"}


@router.get("/{project_key}/assets/{asset_id}/commodities", response_model=list[CommodityRelationshipOut])
def list_asset_commodities(project_key: str, asset_id: int, as_of: date | None = None, db: Session = Depends(get_db)):
    asset = db.query(AssetUnit).join(Project).filter(Project.project_key == project_key, AssetUnit.id == asset_id).one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="asset unit not found")
    return _active_commodity_rows(db.query(CommodityRelationship).filter_by(asset_unit_id=asset.id).order_by(CommodityRelationship.id).all(), as_of)


@router.post("/{project_key}/assets/{asset_id}/commodities", response_model=CommodityRelationshipOut, status_code=201)
def add_asset_commodity(project_key: str, asset_id: int, payload: CommodityRelationshipInput, db: Session = Depends(get_db)):
    asset = db.query(AssetUnit).join(Project).filter(Project.project_key == project_key, AssetUnit.id == asset_id).one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="asset unit not found")
    _validate_commodity_interval(payload)
    commodity = clean(payload.commodity).casefold()
    _check_commodity_overlap(db, asset_unit_id=asset.id, commodity=commodity, start=payload.effective_from, end=payload.effective_to)
    row = CommodityRelationship(asset_unit_id=asset.id, commodity=commodity, **payload.model_dump(exclude={"commodity"}))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{project_key}/assets/{asset_id}/commodities/{relationship_id}", response_model=CommodityRelationshipOut)
def update_asset_commodity(project_key: str, asset_id: int, relationship_id: int, payload: CommodityRelationshipInput, db: Session = Depends(get_db)):
    asset = db.query(AssetUnit).join(Project).filter(Project.project_key == project_key, AssetUnit.id == asset_id).one_or_none()
    row = db.query(CommodityRelationship).filter_by(id=relationship_id, asset_unit_id=asset.id if asset else -1).one_or_none()
    if asset is None or row is None:
        raise HTTPException(status_code=404, detail="asset commodity relationship not found")
    _validate_commodity_interval(payload)
    commodity = clean(payload.commodity).casefold()
    _check_commodity_overlap(db, asset_unit_id=asset.id, commodity=commodity, start=payload.effective_from, end=payload.effective_to, exclude_id=row.id)
    for field, value in payload.model_dump(exclude={"commodity"}).items():
        setattr(row, field, value)
    row.commodity = commodity
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{project_key}/assets/{asset_id}/commodities/{relationship_id}")
def delete_asset_commodity(project_key: str, asset_id: int, relationship_id: int, db: Session = Depends(get_db)):
    asset = db.query(AssetUnit).join(Project).filter(Project.project_key == project_key, AssetUnit.id == asset_id).one_or_none()
    row = db.query(CommodityRelationship).filter_by(id=relationship_id, asset_unit_id=asset.id if asset else -1).one_or_none()
    if asset is None or row is None:
        raise HTTPException(status_code=404, detail="asset commodity relationship not found")
    if row.source != "manual":
        raise HTTPException(status_code=409, detail="source-backed commodity history cannot be deleted")
    db.delete(row)
    db.commit()
    return {"detail": "commodity relationship deleted"}
