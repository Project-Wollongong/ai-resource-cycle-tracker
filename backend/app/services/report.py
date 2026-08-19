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
    content = {
        "report_date": report_date.isoformat(),
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
