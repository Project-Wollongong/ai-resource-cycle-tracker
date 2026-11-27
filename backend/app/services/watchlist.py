import json

from sqlalchemy.orm import Session

from ..models import PriceBar, ScoreSnapshot, Signal, Stock
from ..schemas import ScoreBrief, StockWithScore


def build_stock_view(session: Session, stock: Stock, include_components: bool = False) -> StockWithScore:
    """Stock + latest score snapshot + latest price + same-day live signals."""
    view = StockWithScore.model_validate(stock)

    bars = (
        session.query(PriceBar)
        .filter_by(stock_id=stock.id)
        .order_by(PriceBar.date.desc())
        .limit(2)
        .all()
    )
    if bars:
        view.last_close = bars[0].close
        view.last_bar_date = bars[0].date
        if len(bars) == 2 and bars[1].close:
            view.day_change_pct = round((bars[0].close / bars[1].close - 1) * 100, 2)
        view.today_signals = [
            s.signal_type
            for s in session.query(Signal)
            .filter_by(stock_id=stock.id, date=bars[0].date, source="live")
            .all()
        ]

    snap = (
        session.query(ScoreSnapshot)
        .filter_by(stock_id=stock.id)
        .order_by(ScoreSnapshot.date.desc())
        .first()
    )
    if snap is not None:
        components = json.loads(snap.components) if snap.components else None
        view.latest_score = ScoreBrief(
            date=snap.date,
            funding_score=snap.funding_score,
            announcement_score=snap.announcement_score,
            resource_score=snap.resource_score,
            commodity_score=snap.commodity_score,
            risk_score=snap.risk_score,
            sentiment_score=snap.sentiment_score,
            cycle_score=snap.cycle_score,
            label=snap.label,
            components=components if include_components else None,
            component_sources=_sources(components),
        )
    return view


def _sources(components: dict | None) -> dict[str, str] | None:
    """Just the `source` of each sub-score.

    A measured 50 and a defaulted 50 are the same number meaning opposite
    things, and the scorer records which. Sending the marker without the rest
    of the components keeps a list response small while letting the ranking
    page stop guessing from the value.
    """
    if not components:
        return None
    found = {
        name: str(block["source"])
        for name, block in components.items()
        if isinstance(block, dict) and block.get("source")
    }
    return found or None
