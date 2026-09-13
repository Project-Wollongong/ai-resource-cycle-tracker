import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...models import Position, Stock, StrategyLearningCandidate, TradeReview
from ...schemas import StrategyLearningCandidateOut, TradeReviewOut
from ...services.trade_review import create_trade_review_for_position
from ..deps import get_db
from ..security import require_admin_access

router = APIRouter(prefix="/trade-reviews", tags=["trade-reviews"])


@router.get("", response_model=list[TradeReviewOut])
def list_trade_reviews(
    code: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(TradeReview, Stock).join(Stock, TradeReview.stock_id == Stock.id)
    if code:
        q = q.filter(Stock.code == code.upper())
    rows = q.order_by(TradeReview.closed_at.desc(), TradeReview.id.desc()).limit(min(limit, 500)).all()
    return [_review_out(db, review, stock) for review, stock in rows]


@router.post("/positions/{position_id}", response_model=TradeReviewOut, dependencies=[Depends(require_admin_access)])
def create_trade_review(position_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(Position, Stock)
        .join(Stock, Position.stock_id == Stock.id)
        .filter(Position.id == position_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"position {position_id} not found")
    position, stock = row
    try:
        review = create_trade_review_for_position(db, position, stock)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _review_out(db, review, stock)


@router.get("/candidates/list", response_model=list[StrategyLearningCandidateOut])
def list_learning_candidates(
    status: str | None = "proposed",
    target_layer: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(StrategyLearningCandidate, Stock).join(Stock, StrategyLearningCandidate.stock_id == Stock.id)
    if status:
        q = q.filter(StrategyLearningCandidate.status == status)
    if target_layer:
        q = q.filter(StrategyLearningCandidate.target_layer == target_layer)
    rows = (
        q.order_by(StrategyLearningCandidate.created_at.desc(), StrategyLearningCandidate.id.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [_candidate_out(candidate, stock) for candidate, stock in rows]


@router.get("/{review_id}", response_model=TradeReviewOut)
def get_trade_review(review_id: int, db: Session = Depends(get_db)):
    review, stock = _review_and_stock(db, review_id)
    return _review_out(db, review, stock)


def _review_and_stock(db: Session, review_id: int) -> tuple[TradeReview, Stock]:
    row = (
        db.query(TradeReview, Stock)
        .join(Stock, TradeReview.stock_id == Stock.id)
        .filter(TradeReview.id == review_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"trade review {review_id} not found")
    return row


def _review_out(db: Session, review: TradeReview, stock: Stock) -> TradeReviewOut:
    candidates = (
        db.query(StrategyLearningCandidate)
        .filter_by(trade_review_id=review.id)
        .order_by(StrategyLearningCandidate.id.asc())
        .all()
    )
    return TradeReviewOut(
        id=review.id,
        position_id=review.position_id,
        code=stock.code,
        stock_name=stock.name,
        opened_at=review.opened_at,
        closed_at=review.closed_at,
        entry_price=review.entry_price,
        exit_price=review.exit_price,
        return_pct=review.return_pct,
        outcome_quality=review.outcome_quality,
        decision_quality=review.decision_quality,
        thesis_review=_loads(review.thesis_review_json, {}),
        signal_review=_loads(review.signal_review_json, {}),
        decision_review=_loads(review.decision_review_json, {}),
        position_management_review=_loads(review.position_management_review_json, {}),
        outcome_attribution=_loads(review.outcome_attribution_json, {}),
        state_transition_review=_loads(review.state_transition_review_json, {}),
        review_version=review.review_version,
        metadata=_loads(review.metadata_json, {}),
        learning_candidates=[_candidate_out(candidate, stock) for candidate in candidates],
        created_at=review.created_at,
    )


def _candidate_out(candidate: StrategyLearningCandidate, stock: Stock) -> StrategyLearningCandidateOut:
    return StrategyLearningCandidateOut(
        id=candidate.id,
        trade_review_id=candidate.trade_review_id,
        code=stock.code,
        candidate_type=candidate.candidate_type,
        target_layer=candidate.target_layer,
        title=candidate.title,
        rationale=candidate.rationale,
        evidence=_loads(candidate.evidence_json, {}),
        status=candidate.status,
        requires_backtest=candidate.requires_backtest,
        requires_human_approval=candidate.requires_human_approval,
        approved_at=candidate.approved_at,
        applied_at=candidate.applied_at,
        metadata=_loads(candidate.metadata_json, {}),
        created_at=candidate.created_at,
    )


def _loads(raw: str | None, default):
    if not raw:
        return default
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return default
    return value
