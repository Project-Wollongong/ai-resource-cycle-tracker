import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from ...models import AnalyticalSignal, ForwardCatalystMap, FusionRecord, P4Feature, Announcement, PriceBar, Project, ScoreSnapshot, Signal, Stock, StockProject
from ...schemas import (
    AnnouncementOut,
    Message,
    PriceBarOut,
    ScoreBrief,
    SignalOut,
    StockCreate,
    StockUpdate,
    StockWithScore,
    StockIdentityInput,
    StockIdentityOut,
    StockProjectOut,
    IdentityKind,
)
from ...services import stock_identity as identity
from ...services.watchlist import build_stock_view
from ..deps import get_db
from ..serializers import announcement_out, signal_out

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _get_stock_or_404(db: Session, code: str) -> Stock:
    try:
        stock = identity.find_current_or_historical(db, code)
    except identity.IdentityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if stock is None:
        raise HTTPException(status_code=404, detail=f"stock {code.upper()} not found")
    return stock


@router.get("", response_model=list[StockWithScore])
def list_stocks(active: bool | None = True, q: str | None = None,
                pilot_universe_member: bool | None = None, db: Session = Depends(get_db)):
    query = db.query(Stock)
    if active is not None:
        query = query.filter_by(active=active)
    if pilot_universe_member is not None:
        query = query.filter_by(pilot_universe_member=pilot_universe_member)
    stocks = query.order_by(Stock.code).all()
    if q and identity.normalize(q):
        term = identity.normalize(q)
        stocks = [s for s in stocks if any(term in identity.normalize(value) for value in
                  [s.code, s.name, *(r.value for r in s.identity_history)])]
    views = [build_stock_view(db, s) for s in stocks]
    views.sort(key=lambda v: v.latest_score.cycle_score if v.latest_score else -1, reverse=True)
    return views


@router.post("", response_model=StockWithScore, status_code=201)
def create_stock(payload: StockCreate, db: Session = Depends(get_db)):
    try:
        code = identity.ticker(payload.code)
        identity.validate_interval(payload.identity_effective_from, None)
        existing = db.query(Stock).filter_by(code=code).one_or_none()
        if existing is not None:
            if existing.active:
                raise identity.IdentityConflict(f"stock {code} already exists")
            identity.change_current_identity(db, existing, name=payload.name,
                exchange=payload.exchange if "exchange" in payload.model_fields_set else None,
                effective_from=payload.identity_effective_from)
            existing.active = True
            existing.commodity, existing.stage = payload.commodity, payload.stage
            stock = existing
            for field in ("trading_currency", "listing_status", "sector", "business_type", "pilot_universe_member"):
                if field in payload.model_fields_set:
                    setattr(stock, field, getattr(payload, field))
        else:
            identity.assert_new_stock_identity(db, code, payload.name)
            stock = Stock(**payload.model_dump(exclude={"identity_effective_from", "code", "name"}),
                          code=code, name=identity.clean(payload.name))
            db.add(stock)
            identity.ensure_current_identities(db, stock, source="api_create")
            for row in stock.identity_history:
                row.valid_from = payload.identity_effective_from
        db.commit()
        return build_stock_view(db, stock)
    except (ValueError, IntegrityError) as exc:
        _identity_error(db, exc)


def _identity_error(db: Session, exc: Exception):
    db.rollback()
    conflict = isinstance(exc, (identity.IdentityConflict, IntegrityError))
    detail = "identity conflicts with an existing record" if isinstance(exc, IntegrityError) else str(exc)
    raise HTTPException(status_code=409 if conflict else 422, detail=detail) from exc


@router.get("/resolve", response_model=StockWithScore)
def resolve_stock(identifier: str, as_of: date | None = None, kind: IdentityKind | None = None,
                  exchange: str | None = None, db: Session = Depends(get_db)):
    try:
        stock = identity.resolve_stock(db, identifier, as_of=as_of, kind=kind, exchange=exchange)
    except identity.IdentityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if stock is None:
        raise HTTPException(status_code=404, detail="stock identity not found")
    return build_stock_view(db, stock, include_components=True)


@router.get("/{code}/identities", response_model=list[StockIdentityOut])
def stock_identities(code: str, db: Session = Depends(get_db)):
    return _get_stock_or_404(db, code).identity_history


@router.get("/{code}/projects", response_model=list[StockProjectOut])
def stock_projects(code: str, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    links = (
        db.query(StockProject)
        .options(selectinload(StockProject.project).selectinload(Project.asset_units))
        .filter_by(stock_id=stock.id)
        .all()
    )
    return [
        {
            "id": link.project.id,
            "project_key": link.project.project_key,
            "name": link.project.name,
            "relationship_type": link.relationship_type,
            "ownership_pct": link.ownership_pct,
            "operator_name": next((r.operator_name for r in reversed(link.project.relationship_history) if r.stock_id == stock.id and r.effective_to is None), None),
            "effective_from": link.effective_from,
            "effective_to": link.effective_to,
            "asset_units": link.project.asset_units,
        }
        for link in links
    ]


@router.post("/{code}/identities", response_model=StockIdentityOut, status_code=201)
def add_stock_identity(code: str, payload: StockIdentityInput, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    try:
        row = identity.add_history(db, stock, **payload.model_dump())
        db.commit()
        return row
    except (ValueError, IntegrityError) as exc:
        _identity_error(db, exc)


@router.get("/{code}", response_model=StockWithScore)
def get_stock(code: str, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    return build_stock_view(db, stock, include_components=True)


@router.put("/{code}", response_model=StockWithScore)
def update_stock(code: str, payload: StockUpdate, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    try:
        identity.change_current_identity(db, stock, code=payload.code, name=payload.name,
            exchange=payload.exchange, effective_from=payload.identity_effective_from)
        for field in ("commodity", "stage", "notes", "active", "trading_currency",
                      "listing_status", "sector", "business_type", "pilot_universe_member"):
            value = getattr(payload, field)
            if value is not None:
                setattr(stock, field, value.upper() if field == "trading_currency" else value)
            elif field in {"sector", "business_type"} and field in payload.model_fields_set:
                setattr(stock, field, None)
        if payload.resource_score_override is not None:
            stock.resource_score_override = payload.resource_score_override
        if payload.risk_score_override is not None:
            stock.risk_score_override = payload.risk_score_override
        if payload.clear_resource_override:
            stock.resource_score_override = None
        if payload.clear_risk_override:
            stock.risk_score_override = None
        db.commit()
        return build_stock_view(db, stock, include_components=True)
    except (ValueError, IntegrityError) as exc:
        _identity_error(db, exc)


@router.delete("/{code}", response_model=Message)
def deactivate_stock(code: str, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    stock.active = False
    db.commit()
    return Message(detail=f"stock {stock.code} deactivated")


@router.get("/{code}/prices", response_model=list[PriceBarOut])
def stock_prices(code: str, days: int = 250, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    rows = (
        db.query(PriceBar)
        .filter_by(stock_id=stock.id)
        .order_by(PriceBar.date.desc())
        .limit(min(days, 600))
        .all()
    )
    return [PriceBarOut.model_validate(r) for r in reversed(rows)]


@router.get("/{code}/scores", response_model=list[ScoreBrief])
def stock_scores(code: str, days: int = 90, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    rows = (
        db.query(ScoreSnapshot)
        .filter_by(stock_id=stock.id)
        .order_by(ScoreSnapshot.date.desc())
        .limit(min(days, 400))
        .all()
    )
    return [
        ScoreBrief(
            date=r.date,
            funding_score=r.funding_score,
            announcement_score=r.announcement_score,
            resource_score=r.resource_score,
            commodity_score=r.commodity_score,
            risk_score=r.risk_score,
            sentiment_score=r.sentiment_score,
            cycle_score=r.cycle_score,
            label=r.label,
            components=json.loads(r.components or "{}"),
        )
        for r in reversed(rows)
    ]


@router.get("/{code}/announcements", response_model=list[AnnouncementOut])
def stock_announcements(code: str, limit: int = 50, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    rows = (
        db.query(Announcement)
        .filter_by(stock_id=stock.id)
        .order_by(Announcement.ann_date.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [announcement_out(a, stock.code) for a in rows]


@router.get("/{code}/signals", response_model=list[SignalOut])
def stock_signals(code: str, limit: int = 100, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(db, code)
    rows = (
        db.query(Signal)
        .filter_by(stock_id=stock.id)
        .options(joinedload(Signal.returns))
        .order_by(Signal.date.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [signal_out(s, stock) for s in rows]


@router.get("/{code}/features")
def stock_features(code: str, feature_group: str | None = None, db: Session = Depends(get_db)):
    """P04 derived features with their lineage.

    Every value carries the formula that produced it, the P03 fact ids it was
    computed from and the source page, so a number on screen can always be
    walked back to the sentence in the PDF it came from.
    """
    stock = _get_stock_or_404(db, code)
    query = db.query(P4Feature).filter_by(stock_id=stock.id)
    if feature_group:
        query = query.filter(P4Feature.feature_group == feature_group)
    rows = query.order_by(P4Feature.as_of_date.desc(), P4Feature.feature_name).all()
    return [
        {
            "feature_group": row.feature_group,
            "feature_name": row.feature_name,
            "value": json.loads(row.value_json).get("numeric"),
            "unit": row.unit,
            "as_of_date": row.as_of_date,
            "formula_version": row.formula_version,
            "input_fact_ids": json.loads(row.input_refs_json),
            "evidence": json.loads(row.evidence_json),
            "metadata": json.loads(row.metadata_json),
        }
        for row in rows
    ]


def _loads(raw: str | None, fallback):
    try:
        return json.loads(raw or "")
    except (TypeError, ValueError):
        return fallback


@router.get("/{code}/engines")
def stock_engine_readings(code: str, db: Session = Depends(get_db)):
    """What each P05 engine read, and what P06 made of the set.

    The engines write their findings and their narratives, and the fusion
    layer records where they agree and where they pull against each other,
    but none of it had a way out of the database. A verdict nobody can read
    the reasoning for is not much better than no verdict.
    """
    stock = _get_stock_or_404(db, code)
    fusion = (
        db.query(FusionRecord)
        .filter_by(stock_id=stock.id)
        .order_by(FusionRecord.fusion_date.desc(), FusionRecord.id.desc())
        .first()
    )
    if fusion is None:
        return {"as_of": None, "fusion": None, "engines": []}

    rows = (
        db.query(AnalyticalSignal)
        .filter_by(stock_id=stock.id, signal_date=fusion.fusion_date)
        .order_by(AnalyticalSignal.engine, AnalyticalSignal.id)
        .all()
    )

    engines: dict[str, dict] = {}
    for row in rows:
        metadata = _loads(row.metadata_json, {})
        bucket = engines.setdefault(
            row.engine,
            {"engine": row.engine, "logic_version": row.logic_version,
             "narrative": row.narrative, "readings": []},
        )
        # every reading of one engine on one day shares its narrative; keep the
        # first non-empty rather than repeating it per row
        bucket["narrative"] = bucket["narrative"] or row.narrative
        bucket["readings"].append({
            "lens": metadata.get("lens"),
            "direction": row.direction,
            "magnitude": metadata.get("magnitude_label"),
            "confidence": metadata.get("confidence_label"),
            "persistence": row.persistence,
            "summary": metadata.get("summary"),
            "drivers": _loads(row.key_drivers_json, []),
            "risks": _loads(row.key_risks_json, []),
            "dependency_group": row.dependency_group,
        })

    metadata = _loads(fusion.metadata_json, {})
    return {
        "as_of": fusion.fusion_date,
        "fusion": {
            "opportunity_strength": fusion.opportunity_strength,
            "confidence": fusion.confidence,
            "signal_structure": fusion.signal_structure,
            "evidence_independence": fusion.evidence_independence,
            "conflicts": _loads(fusion.conflicts_json, []),
            "blocking_conditions": _loads(fusion.blocking_conditions_json, []),
            "narrative": fusion.narrative,
            "strength_basis": metadata.get("strength_basis"),
            # what the retired Cycle Score lookup would have said, so the two
            # can be compared rather than one quietly replacing the other
            "cycle_score_strength": metadata.get("cycle_score_strength"),
        },
        "engines": sorted(engines.values(), key=lambda item: item["engine"]),
    }


@router.get("/{code}/catalyst-map")
def stock_catalyst_map(code: str, limit: int = 10, db: Session = Depends(get_db)):
    """The Catalyst Agent's running view of where a project stands.

    P05 calls this persistent internal state rather than an output, and it is
    appended per day rather than overwritten, because the change between two
    days is the finding. The history is returned alongside the current entry
    for that reason.
    """
    stock = _get_stock_or_404(db, code)
    rows = (
        db.query(ForwardCatalystMap)
        .filter_by(stock_id=stock.id)
        .order_by(ForwardCatalystMap.as_of_date.desc(), ForwardCatalystMap.id.desc())
        .limit(min(limit, 60))
        .all()
    )
    if not rows:
        return {"current": None, "history": []}

    def out(row: ForwardCatalystMap) -> dict:
        return {
            "as_of_date": row.as_of_date,
            "current_stage": row.current_stage,
            "previous_stage": row.previous_stage,
            "next_expected_event": row.next_expected_event,
            "expected_window": row.expected_window,
            "importance": row.importance,
            # qualitative by design: the pilot has no milestone probability
            # model and the PRD forbids inventing one where evidence is absent
            "probability": row.probability,
            "dependencies": _loads(row.dependencies_json, []),
            "bottlenecks": _loads(row.bottlenecks_json, []),
            "evidence_basis": _loads(row.evidence_basis_json, []),
            "change_since_previous": row.change_since_previous,
        }

    return {"current": out(rows[0]), "history": [out(row) for row in rows[1:]]}
