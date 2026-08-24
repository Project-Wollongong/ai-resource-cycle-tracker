"""Daily report: persisted JSON + Telegram-HTML rendering. Push is optional."""

import json
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Announcement, DailyReport, ScoreSnapshot, Signal, Stock
from ..notify.email_stub import EmailNotifier
from ..notify.telegram import TelegramNotifier
from .watchlist import build_stock_view

DISCLAIMER = "Research only, not investment advice. 仅供研究参考，不构成投资建议。"
TOP_N = 10
REVIEW_LIMIT = 8


def build_daily_report(session: Session, run_stats: dict | None = None) -> DailyReport:
    report_date: date | None = session.query(func.max(ScoreSnapshot.date)).scalar()
    if report_date is None:
        report_date = date.today()

    stocks = session.query(Stock).filter_by(active=True).order_by(Stock.code).all()
    views = [build_stock_view(session, s) for s in stocks]
    scored = [v for v in views if v.latest_score is not None]
    scored.sort(key=lambda v: v.latest_score.cycle_score, reverse=True)

    top = [
        {
            "code": v.code,
            "name": v.name,
            "commodity": v.commodity,
            "cycle_score": round(v.latest_score.cycle_score, 1),
            "label": v.latest_score.label,
            "day_change_pct": v.day_change_pct,
        }
        for v in scored[:TOP_N]
    ]

    signal_rows = (
        session.query(Signal, Stock)
        .join(Stock, Signal.stock_id == Stock.id)
        .filter(Signal.date == report_date, Signal.source == "live")
        .order_by(Stock.code)
        .all()
    )
    signals = [
        {
            "code": stock.code,
            "type": sig.signal_type,
            "label": sig.label,
            "reason": sig.reason,
            "price": sig.price_at_signal,
        }
        for sig, stock in signal_rows
    ]

    ann_rows = (
        session.query(Announcement, Stock)
        .join(Stock, Announcement.stock_id == Stock.id)
        .filter(
            Announcement.ann_date >= datetime.combine(report_date, datetime.min.time()),
            Announcement.ann_date
            < datetime.combine(report_date + timedelta(days=1), datetime.min.time()),
            Announcement.ann_type != "OTHER",
        )
        .order_by(Announcement.type_score.desc())
        .limit(15)
        .all()
    )
    announcements = [
        {
            "code": stock.code,
            "type": ann.ann_type,
            "headline": ann.headline[:100],
            "price_sensitive": ann.price_sensitive,
            "url": ann.url,
            "quality": _primary_context_value(ann.ai_metrics, "interval_quality_label"),
            "materiality": _primary_context_value(ann.ai_metrics, "materiality_label"),
            "assessment": _primary_context_value(ann.ai_metrics, "qualitative_assessment"),
            "grade_thickness": _primary_context_value(ann.ai_metrics, "grade_thickness"),
        }
        for ann, stock in ann_rows
    ]

    movers = sorted(
        (
            {"code": v.code, "day_change_pct": v.day_change_pct}
            for v in views
            if v.day_change_pct is not None and abs(v.day_change_pct) >= 8.0
        ),
        key=lambda m: -abs(m["day_change_pct"]),
    )[:10]

    degraded = (run_stats or {}).get("blocked_sources", [])
    daily_review = build_daily_review(session, report_date, views, signal_rows)
    content = {
        "report_date": report_date.isoformat(),
        "daily_review": daily_review,
        "top": top,
        "signals": signals,
        "announcements": announcements,
        "movers": movers,
        "source_degraded": degraded,
        "disclaimer": DISCLAIMER,
    }

    report = session.query(DailyReport).filter_by(report_date=report_date).one_or_none()
    if report is None:
        report = DailyReport(report_date=report_date)
        session.add(report)
    report.content_json = json.dumps(content, ensure_ascii=False)
    report.content_text = render_telegram_html(content)
    session.commit()
    return report


def build_daily_review(
    session: Session,
    report_date: date,
    views,
    signal_rows: list[tuple[Signal, Stock]],
) -> dict:
    """Create the product-facing "what should I look at today?" sections."""

    stocks = {v.id: v for v in views}
    signal_map: dict[int, list[Signal]] = {}
    for sig, _stock in signal_rows:
        signal_map.setdefault(sig.stock_id, []).append(sig)

    today_snaps = (
        session.query(ScoreSnapshot, Stock)
        .join(Stock, ScoreSnapshot.stock_id == Stock.id)
        .filter(ScoreSnapshot.date == report_date, Stock.active.is_(True))
        .all()
    )
    previous = {
        snap.stock_id: _previous_snapshot(session, snap.stock_id, report_date)
        for snap, _stock in today_snaps
    }

    new_announcements = _announcements_by_stock(session, report_date)

    top_priority = []
    new_story = []
    market_confirmation = []
    rising_fast = []
    risk_alert = []

    for snap, stock in today_snaps:
        view = stocks.get(stock.id)
        components = _components(snap)
        prev = previous.get(stock.id)
        score_change = _score_change(snap, prev)
        signals = signal_map.get(stock.id, [])
        anns = new_announcements.get(stock.id, [])

        if snap.cycle_score >= 70 or snap.label == "High Priority":
            top_priority.append(
                _review_item(
                    stock,
                    view,
                    snap,
                    score_change,
                    reasons=_top_priority_reasons(snap, components, signals),
                    watch_next=[
                        "Check whether the story keeps receiving volume confirmation.",
                        "Read the primary announcement before making any investment decision.",
                    ],
                )
            )

        key_anns = [
            ann
            for ann in anns
            if ann.price_sensitive or ann.type_score >= 70 or ann.ann_type != "OTHER"
        ]
        if key_anns:
            best = max(key_anns, key=lambda ann: (ann.price_sensitive, ann.type_score))
            new_story.append(
                _review_item(
                    stock,
                    view,
                    snap,
                    score_change,
                    reasons=[
                        f"New {best.ann_type} announcement: {best.headline[:90]}",
                        f"Announcement Score is {snap.announcement_score:.1f}.",
                    ],
                    watch_next=[
                        "Confirm whether the announcement is material in the project context.",
                        "Watch the next 2-3 sessions for follow-through volume.",
                    ],
                    headline=best.headline[:120],
                    announcement_type=best.ann_type,
                )
            )

        if _has_market_confirmation(snap, signals):
            market_confirmation.append(
                _review_item(
                    stock,
                    view,
                    snap,
                    score_change,
                    reasons=_market_confirmation_reasons(snap, components, signals),
                    watch_next=[
                        "Look for continued liquidity rather than a one-day spike.",
                        "Compare the move against the latest announcement quality.",
                    ],
                )
            )

        if score_change is not None and score_change >= 10:
            rising_fast.append(
                _review_item(
                    stock,
                    view,
                    snap,
                    score_change,
                    reasons=[
                        f"Cycle Score rose {score_change:+.1f} points versus the previous snapshot.",
                        _main_score_driver(snap, components),
                    ],
                    watch_next=[
                        "Check which component drove the move before treating it as durable.",
                    ],
                )
            )

        risk_drop = (
            prev.risk_score - snap.risk_score
            if prev is not None and prev.risk_score is not None
            else None
        )
        risk_events = _risk_events(components)
        if snap.risk_score < 40 or (risk_drop is not None and risk_drop >= 10) or risk_events:
            reasons = [f"Risk Score is {snap.risk_score:.1f}."]
            if risk_drop is not None and risk_drop >= 10:
                reasons.append(f"Risk Score fell {risk_drop:.1f} points versus the previous snapshot.")
            reasons.extend(risk_events[:3])
            risk_alert.append(
                _review_item(
                    stock,
                    view,
                    snap,
                    score_change,
                    reasons=reasons,
                    watch_next=[
                        "Check financing, halt, liquidity, and cash runway details manually.",
                    ],
                )
            )

    return {
        "top_priority": _limit(top_priority, "cycle_score"),
        "new_story": _limit(new_story, "announcement_score"),
        "market_confirmation": _limit(market_confirmation, "funding_score"),
        "rising_fast": _limit(rising_fast, "score_change"),
        "risk_alert": _limit(risk_alert, "risk_severity"),
    }


def _primary_context_value(raw_metrics: str | None, key: str):
    context = _primary_qualitative_context(raw_metrics)
    return context.get(key) if context else None


def _primary_qualitative_context(raw_metrics: str | None) -> dict | None:
    if not raw_metrics:
        return None
    try:
        metrics = json.loads(raw_metrics)
    except json.JSONDecodeError:
        return None
    if not isinstance(metrics, dict):
        return None
    context = metrics.get("qualitative_context")
    return context if isinstance(context, dict) else None


def render_telegram_html(content: dict) -> str:
    lines = [f"<b>AI Resource Cycle Tracker - {content['report_date']}</b>", ""]

    daily_review = content.get("daily_review")
    if daily_review:
        lines.append("<b>Daily Review</b>")
        for key, title in [
            ("top_priority", "Top Priority"),
            ("new_story", "New Story"),
            ("market_confirmation", "Market Confirmation"),
            ("rising_fast", "Rising Fast"),
            ("risk_alert", "Risk Alert"),
        ]:
            items = daily_review.get(key, [])
            if not items:
                continue
            lines.append(f"<b>{title}</b>")
            for item in items[:5]:
                change = item.get("score_change")
                change_text = f" ({change:+.1f})" if change is not None else ""
                lines.append(
                    f"- {item['code']} {item['cycle_score']:.1f} - {item['label']}{change_text}: "
                    f"{item['reasons'][0]}"
                )
        lines.append("")

    lines.append("<b>Top Cycle Scores</b>")
    if content["top"]:
        for i, item in enumerate(content["top"], 1):
            change = (
                f" ({item['day_change_pct']:+.1f}%)" if item.get("day_change_pct") is not None else ""
            )
            lines.append(
                f"{i}. {item['code']} {item['cycle_score']} - {item['label']}{change}"
            )
    else:
        lines.append("(no scores yet)")

    lines.append("")
    lines.append(f"<b>Signals ({len(content['signals'])})</b>")
    if content["signals"]:
        for sig in content["signals"]:
            lines.append(f"- {sig['code']} [{sig['type']}] {sig['reason']}")
    else:
        lines.append("(none today)")

    if content["announcements"]:
        lines.append("")
        lines.append("<b>Key announcements</b>")
        for ann in content["announcements"]:
            ps = " [PS]" if ann["price_sensitive"] else ""
            lines.append(f"- {ann['code']} [{ann['type']}]{ps} {ann['headline']}")
            context_bits = []
            if ann.get("quality"):
                context_bits.append(f"quality={ann['quality']}")
            if ann.get("materiality"):
                context_bits.append(f"materiality={ann['materiality']}")
            if ann.get("grade_thickness") is not None:
                context_bits.append(f"GT={ann['grade_thickness']}")
            if context_bits:
                lines.append("  " + ", ".join(context_bits))
            if ann.get("assessment"):
                lines.append(f"  {ann['assessment']}")

    if content["movers"]:
        lines.append("")
        lines.append("<b>Movers >=8%</b>")
        lines.append(
            ", ".join(f"{m['code']} {m['day_change_pct']:+.1f}%" for m in content["movers"])
        )

    if content["source_degraded"]:
        lines.append("")
        lines.append(
            "Announcement source degraded for: " + ", ".join(content["source_degraded"])
        )

    lines.append("")
    lines.append(f"<i>{content['disclaimer']}</i>")
    return "\n".join(lines)


def _previous_snapshot(session: Session, stock_id: int, report_date: date) -> ScoreSnapshot | None:
    return (
        session.query(ScoreSnapshot)
        .filter(ScoreSnapshot.stock_id == stock_id, ScoreSnapshot.date < report_date)
        .order_by(ScoreSnapshot.date.desc())
        .first()
    )


def _announcements_by_stock(session: Session, report_date: date) -> dict[int, list[Announcement]]:
    rows = (
        session.query(Announcement)
        .filter(
            Announcement.ann_date >= datetime.combine(report_date, datetime.min.time()),
            Announcement.ann_date
            < datetime.combine(report_date + timedelta(days=1), datetime.min.time()),
        )
        .order_by(Announcement.type_score.desc())
        .all()
    )
    out: dict[int, list[Announcement]] = {}
    for ann in rows:
        out.setdefault(ann.stock_id, []).append(ann)
    return out


def _components(snapshot: ScoreSnapshot) -> dict:
    try:
        raw = json.loads(snapshot.components or "{}")
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _score_change(today: ScoreSnapshot, prev: ScoreSnapshot | None) -> float | None:
    if prev is None:
        return None
    return round(today.cycle_score - prev.cycle_score, 1)


def _review_item(
    stock: Stock,
    view,
    snap: ScoreSnapshot,
    score_change: float | None,
    reasons: list[str],
    watch_next: list[str],
    **extra,
) -> dict:
    item = {
        "code": stock.code,
        "name": stock.name,
        "commodity": stock.commodity,
        "stage": stock.stage,
        "cycle_score": round(snap.cycle_score, 1),
        "label": snap.label,
        "score_change": score_change,
        "day_change_pct": getattr(view, "day_change_pct", None) if view is not None else None,
        "announcement_score": round(snap.announcement_score, 1),
        "funding_score": round(snap.funding_score, 1),
        "commodity_score": round(snap.commodity_score, 1),
        "risk_score": round(snap.risk_score, 1),
        "risk_severity": round(100 - snap.risk_score, 1),
        "reasons": [r for r in reasons if r],
        "watch_next": watch_next,
    }
    item.update(extra)
    return item


def _top_priority_reasons(snap: ScoreSnapshot, components: dict, signals: list[Signal]) -> list[str]:
    reasons = [
        f"Cycle Score is {snap.cycle_score:.1f}, placing it in {snap.label}.",
        _main_score_driver(snap, components),
    ]
    if signals:
        reasons.append("Live signal today: " + ", ".join(sig.signal_type for sig in signals[:3]) + ".")
    return reasons


def _main_score_driver(snap: ScoreSnapshot, components: dict) -> str:
    scores = {
        "announcement": snap.announcement_score,
        "commodity": snap.commodity_score,
        "resource": snap.resource_score,
        "risk": snap.risk_score,
        "sentiment": snap.sentiment_score,
    }
    driver = max(scores, key=scores.get)
    if driver == "announcement":
        best = _best_announcement(components)
        return f"Main driver is announcement strength{': ' + best if best else ''}."
    if driver == "commodity":
        return f"Main driver is commodity tailwind at {snap.commodity_score:.1f}."
    if driver == "resource":
        return f"Main driver is resource context at {snap.resource_score:.1f}."
    if driver == "risk":
        return f"Risk is supportive at {snap.risk_score:.1f}."
    return f"Sentiment is neutral/supportive at {snap.sentiment_score:.1f}."


def _best_announcement(components: dict) -> str | None:
    anns = components.get("announcement", {}).get("announcements", [])
    if not anns or not isinstance(anns, list):
        return None
    best = anns[0]
    if not isinstance(best, dict):
        return None
    headline = best.get("headline")
    ann_type = best.get("type")
    if headline and ann_type:
        return f"{ann_type} - {headline[:80]}"
    return headline[:80] if isinstance(headline, str) else None


def _has_market_confirmation(snap: ScoreSnapshot, signals: list[Signal]) -> bool:
    market_signals = {"REL_VOL_SPIKE", "BREAKOUT_60D", "BREAKOUT_252D"}
    return snap.funding_score >= 60 or any(sig.signal_type in market_signals for sig in signals)


def _market_confirmation_reasons(
    snap: ScoreSnapshot, components: dict, signals: list[Signal]
) -> list[str]:
    reasons = []
    market_signals = [
        sig.reason
        for sig in signals
        if sig.signal_type in {"REL_VOL_SPIKE", "BREAKOUT_60D", "BREAKOUT_252D"}
    ]
    if market_signals:
        reasons.extend(market_signals[:2])
    if snap.funding_score >= 60:
        reasons.append(f"Market Confirmation/Funding Score is {snap.funding_score:.1f}.")
    funding = components.get("funding", {})
    rel_vol = funding.get("rel_vol", {}) if isinstance(funding, dict) else {}
    if isinstance(rel_vol, dict) and rel_vol.get("value") is not None:
        reasons.append(f"Relative volume is {rel_vol['value']}x with turnover ${rel_vol.get('dollar_turnover')}.")
    return reasons or ["Market confirmation signal is present."]


def _risk_events(components: dict) -> list[str]:
    risk = components.get("risk", {})
    if not isinstance(risk, dict):
        return []
    events = risk.get("events", [])
    if not isinstance(events, list):
        return []
    out = []
    for event in events:
        if not isinstance(event, dict):
            continue
        reason = event.get("reason")
        headline = event.get("headline")
        adjustment = event.get("adjustment")
        if reason:
            out.append(f"{reason} ({adjustment}): {headline}")
    return out


def _limit(items: list[dict], sort_key: str) -> list[dict]:
    return sorted(
        items,
        key=lambda item: (item.get(sort_key) is not None, item.get(sort_key) or -999),
        reverse=True,
    )[:REVIEW_LIMIT]


def push_daily_report(session: Session, report: DailyReport) -> dict:
    channels = {
        "telegram": TelegramNotifier().send(report.content_text),
        "email": EmailNotifier().send(report.content_text),
    }
    sent_channels = [name for name, result in channels.items() if result.sent]
    errors = {name: result.error for name, result in channels.items() if result.error}
    skipped_channels = [name for name, result in channels.items() if result.skipped]

    report.pushed = bool(sent_channels)
    report.push_error = json.dumps(errors) if errors else None
    if sent_channels:
        report.pushed_at = datetime.utcnow()
    session.commit()
    return {
        "sent": bool(sent_channels),
        "sent_channels": sent_channels,
        "skipped_channels": skipped_channels,
        "errors": errors,
    }
