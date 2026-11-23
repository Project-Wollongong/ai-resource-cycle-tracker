"""What is worth looking at today, and why.

The ranking page answered "which stock scores highest", which is a different
question from the one actually asked each morning: what changed, and does
anything need attention. A score of 68 does not say whether it moved today.

Two kinds of item are surfaced, and they are deliberately not merged:

- things that happened today — a signal fired, an announcement landed
- standing states — a cash runway under two quarters, a deep placement
  discount, a resource table that does not reconcile

A standing state did not happen today, so each reason carries its own `as_of`.
Presenting a cash position dated three months ago as today's news would be the
same mistake as letting an empty panel read as a cleared check.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from ..analysis.signals import is_confirming
from ..models import Announcement, P4Feature, PriceBar, ScoreSnapshot, Signal, Stock

# Ordered by how loudly each should speak; also the sort order on the page.
LEVEL_RANK = {"critical": 0, "caution": 1, "watch": 2, "unconfirmed": 3}

# Announcement types worth surfacing on their own. The rest — governance
# statements, AGM notices, appendices — are filed and not raised, because 121 of
# the pilot's 145 announcements classify as OTHER and would bury everything else.
NOTABLE_ANNOUNCEMENTS = {
    "JORC_MRE": "资源量公告",
    "STUDY": "研究报告",
    "DRILL_RESULTS": "钻探结果",
    "QUARTERLY": "季度报告",
    "PLACEMENT": "配售融资",
    "OFFTAKE": "承购协议",
    "JV_FARMIN": "合资 / farm-in",
    "TRADING_HALT": "停牌",
}

# A signal's headline should name what fired, not a category: a substantial
# holder notice is not a price-volume anomaly, and calling it one makes the
# briefing describe something that did not happen.
SIGNAL_TITLE = {
    "REL_VOL_SPIKE": "量价异动",
    "BREAKOUT_60D": "突破 60 日高点",
    "BREAKOUT_252D": "突破年内高点",
    "KEY_ANNOUNCEMENT": "关键公告",
    "SCORE_CROSS_UP": "评分上穿",
}

RUNWAY_CRITICAL_QUARTERS = 2.0
RUNWAY_CAUTION_QUARTERS = 4.0


@dataclass
class Reason:
    kind: str  # signal | announcement | funding | dilution | resource
    level: str  # critical | caution | watch | unconfirmed
    title: str
    detail: str
    as_of: date | None
    evidence: dict = field(default_factory=dict)


def _loads(raw: str | None) -> dict:
    try:
        return json.loads(raw or "{}")
    except ValueError:
        return {}


def _market_date(session: Session) -> date | None:
    """Latest bar date across the universe — "today" on the market's calendar,
    which is what the page should align to when the market is shut."""
    from sqlalchemy import func

    return session.query(func.max(PriceBar.date)).scalar()


def _feature_reasons(session: Session, stock_id: int) -> list[Reason]:
    rows = session.query(P4Feature).filter_by(stock_id=stock_id).all()
    reasons: list[Reason] = []
    worst_resource: tuple[float, Reason] | None = None

    for row in rows:
        value = _loads(row.value_json).get("numeric")
        metadata = _loads(row.metadata_json)
        evidence = _loads(row.evidence_json)
        if value is None:
            continue

        if row.feature_name == "cash_runway_quarters":
            if value < RUNWAY_CRITICAL_QUARTERS:
                level, title = "critical", "资金紧张"
            elif value < RUNWAY_CAUTION_QUARTERS:
                level, title = "caution", "跑道偏短"
            else:
                continue
            months = round(value * 3)
            reasons.append(
                Reason(
                    kind="funding",
                    level=level,
                    title=title,
                    detail=f"现金跑道 {value:.2f} 个季度，约 {months} 个月后需要融资。",
                    as_of=row.as_of_date,
                    evidence={
                        "runway_quarters": value,
                        "entity_reported": evidence.get("entity_reported_quarters"),
                        "variance": evidence.get("variance_vs_entity_reported"),
                        "source_page": (evidence.get("source_pages") or {}).get(
                            "total_relevant_outgoings"
                        ),
                    },
                )
            )

        elif row.feature_name == "placement_discount_pct" and metadata.get("deep_discount"):
            inputs = evidence.get("inputs") or {}
            reasons.append(
                Reason(
                    kind="dilution",
                    level="caution",
                    title="深度折价",
                    detail=(
                        f"配售定价 {inputs.get('issue_price')}，较公告前收盘 "
                        f"{inputs.get('prior_close')} 折让 {abs(value):.1f}%。"
                    ),
                    as_of=row.as_of_date,
                    evidence={
                        "discount_pct": value,
                        "issue_price": inputs.get("issue_price"),
                        "prior_close": inputs.get("prior_close"),
                        "prior_close_date": evidence.get("prior_close_date"),
                    },
                )
            )

        elif row.feature_name.startswith("contained_metal_reconciliation_pct"):
            if metadata.get("consistent"):
                continue
            # a document can produce several failing rows; one reason carrying
            # the worst of them says as much as five saying the same thing
            misread = bool(metadata.get("likely_column_misread"))
            reason = Reason(
                kind="resource",
                level="critical" if misread else "caution",
                title="资源量数据不可信" if misread else "资源量与披露不符",
                detail=(
                    f"{metadata.get('classification')} 行按吨位 × 品位推算 "
                    f"{evidence.get('implied')} {evidence.get('implied_unit')}，"
                    f"公告披露 {(evidence.get('inputs') or {}).get('reported')}，"
                    f"相差 {value:.0f}%。"
                ),
                as_of=row.as_of_date,
                evidence={"variance_pct": value, "likely_column_misread": misread},
            )
            if worst_resource is None or abs(value) > worst_resource[0]:
                worst_resource = (abs(value), reason)

    if worst_resource is not None:
        reasons.append(worst_resource[1])
    return reasons


def _signal_reasons(session: Session, stock_id: int, on: date) -> list[Reason]:
    signals = (
        session.query(Signal)
        .filter_by(stock_id=stock_id, date=on, source="live")
        .order_by(Signal.id)
        .all()
    )
    # Secondary signals share one causal mechanism with their primary — a
    # breakout already requires volume — so they annotate rather than add.
    primaries = [s for s in signals if s.role != "secondary"]
    secondaries = [s.signal_type for s in signals if s.role == "secondary"]

    reasons = []
    for signal in primaries:
        confirming = is_confirming(signal.signal_type)
        title = SIGNAL_TITLE.get(signal.signal_type, "信号")
        reasons.append(
            Reason(
                kind="signal",
                level="watch" if confirming else "unconfirmed",
                title=title if confirming else f"{title}（仅关注）",
                detail=signal.reason,
                as_of=signal.date,
                evidence={
                    "signal_type": signal.signal_type,
                    "secondary": secondaries,
                    "confirming": confirming,
                },
            )
        )
    return reasons


def _announcement_reasons(session: Session, stock_id: int, on: date) -> list[Reason]:
    rows = (
        session.query(Announcement)
        .filter(Announcement.stock_id == stock_id)
        .order_by(Announcement.ann_date.desc())
        .limit(20)
        .all()
    )
    reasons = []
    for row in rows:
        if row.ann_date.date() != on or row.ann_type not in NOTABLE_ANNOUNCEMENTS:
            continue
        reasons.append(
            Reason(
                kind="announcement",
                level="watch",
                title=NOTABLE_ANNOUNCEMENTS[row.ann_type],
                detail=row.headline[:160],
                as_of=row.ann_date.date(),
                evidence={"ann_id": row.ann_id, "price_sensitive": row.price_sensitive},
            )
        )
    return reasons


def build_today(session: Session) -> dict:
    """Stocks with something to say today, plus the tickers that stayed quiet."""
    market_date = _market_date(session)
    stocks = session.query(Stock).filter_by(active=True).order_by(Stock.code).all()
    if market_date is None:
        return {
            "as_of": None,
            "scored": 0,
            "universe": len(stocks),
            "new_announcements": 0,
            "items": [],
            "quiet": [stock.code for stock in stocks],
        }

    items: list[dict] = []
    quiet: list[str] = []
    scored = 0
    new_announcements = 0

    for stock in stocks:
        bars = (
            session.query(PriceBar)
            .filter_by(stock_id=stock.id)
            .order_by(PriceBar.date.desc())
            .limit(2)
            .all()
        )
        snapshot = (
            session.query(ScoreSnapshot)
            .filter_by(stock_id=stock.id)
            .order_by(ScoreSnapshot.date.desc())
            .first()
        )
        if snapshot is not None and snapshot.date == market_date:
            scored += 1

        announcement_reasons = _announcement_reasons(session, stock.id, market_date)
        new_announcements += len(announcement_reasons)

        reasons = [
            *_feature_reasons(session, stock.id),
            *_signal_reasons(session, stock.id, market_date),
            *announcement_reasons,
        ]
        if not reasons:
            quiet.append(stock.code)
            continue

        reasons.sort(key=lambda r: LEVEL_RANK.get(r.level, 9))
        day_change = None
        if len(bars) == 2 and bars[1].close:
            day_change = round((bars[0].close / bars[1].close - 1) * 100, 2)

        items.append(
            {
                "code": stock.code,
                "name": stock.name,
                "commodity": stock.commodity,
                "last_close": bars[0].close if bars else None,
                "last_bar_date": bars[0].date if bars else None,
                "day_change_pct": day_change,
                "cycle_score": snapshot.cycle_score if snapshot else None,
                "label": snapshot.label if snapshot else None,
                "top_level": reasons[0].level,
                "reasons": [
                    {
                        "kind": r.kind,
                        "level": r.level,
                        "title": r.title,
                        "detail": r.detail,
                        "as_of": r.as_of,
                        "evidence": r.evidence,
                    }
                    for r in reasons
                ],
            }
        )

    items.sort(key=lambda item: (LEVEL_RANK.get(item["top_level"], 9), item["code"]))
    return {
        "as_of": market_date,
        "scored": scored,
        "universe": len(stocks),
        "new_announcements": new_announcements,
        "items": items,
        "quiet": quiet,
    }
