"""Backfill ai_summary / ai_metrics for announcements already stored.

The analyzer runs once, when an announcement is first ingested, and reads the
document over the network. Everything already in the database was ingested
under AI_ANALYZER=noop, so switching the setting changes nothing about it --
hence this one-off pass, which re-reads the text P03 already extracted instead
of fetching anything.

Order matters. `enrich_qualitative_context` compares an intercept against every
*other* announcement that already carries metrics, with no filter on date, so
processing newest-first would score a 2024 drill result against 2026 results
that had not happened yet. Oldest-first reproduces the order live ingest would
have seen, and nothing is compared against its own future.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.analysis.ai_stub import (  # noqa: E402
    AnnouncementDocument,
    get_analyzer,
    insight_metrics_with_document,
)
from app.database import SessionLocal  # noqa: E402
from app.models import Announcement, EvidenceDocument, Stock  # noqa: E402
from app.services.qualitative_mining_context import enrich_qualitative_context  # noqa: E402

MAX_CHARS = 20_000  # same bound the live fetcher applies


def _stored_text(evidence: EvidenceDocument | None) -> str | None:
    if evidence is None:
        return None
    for candidate in (evidence.local_raw_text_path, evidence.raw_text_path):
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path.read_text(errors="ignore")[:MAX_CHARS]
    return None


def run(analyzer_name: str, dry_run: bool, only: str | None) -> dict:
    analyzer = get_analyzer(analyzer_name)
    stats: Counter = Counter()
    labels: Counter = Counter()
    touched_stocks: set[str] = set()
    samples: list[dict] = []

    with SessionLocal() as session:
        query = (
            session.query(Announcement, Stock, EvidenceDocument)
            .join(Stock, Stock.id == Announcement.stock_id)
            .outerjoin(EvidenceDocument, EvidenceDocument.announcement_id == Announcement.id)
            .order_by(Announcement.ann_date.asc(), Announcement.id.asc())
        )
        if only:
            query = query.filter(Stock.code == only.upper())

        for announcement, stock, evidence in query.all():
            stats["seen"] += 1
            text = _stored_text(evidence)
            if not text:
                stats["no_stored_text"] += 1
                continue

            insight = analyzer.analyze(
                announcement.headline,
                announcement.ann_type,
                body_text=text,
                source_url=announcement.url,
            )
            if insight is None:
                stats["no_insight"] += 1
                continue
            stats["with_insight"] += 1

            document = AnnouncementDocument(
                url=announcement.url or "",
                text="",
                content_type="text/plain",
                status="stored",
            )
            metrics = insight_metrics_with_document(insight, document)
            if metrics.get("intercepts"):
                stats["with_intercepts"] += 1

            metrics = enrich_qualitative_context(
                session,
                stock.code,
                metrics,
                ann_type=announcement.ann_type,
                price_sensitive=announcement.price_sensitive,
            )
            context = metrics.get("qualitative_context")
            if context:
                stats["with_context"] += 1
                quality = context.get("interval_quality_label")
                labels[quality or "none"] += 1
                if quality and quality != "insufficient_history":
                    stats["with_real_label"] += 1
                    if len(samples) < 10:
                        samples.append({
                            "stock": stock.code,
                            "date": announcement.ann_date.date().isoformat(),
                            "headline": announcement.headline[:60],
                            "quality": quality,
                            "materiality": context.get("materiality_label"),
                            "company_history_count": context.get("company_history_count"),
                        })

            announcement.ai_summary = insight.summary
            announcement.ai_metrics = json.dumps(metrics, ensure_ascii=False)
            touched_stocks.add(stock.code)
            stats["written"] += 1
            # flushed, not committed: later announcements must see the earlier
            # ones to build their comparison set, exactly as live ingest does
            session.flush()

        if dry_run:
            session.rollback()
        else:
            session.commit()

    return {
        "analyzer": analyzer_name,
        "dry_run": dry_run,
        "counts": dict(stats),
        "interval_quality_labels": dict(labels),
        "stocks_touched": sorted(touched_stocks),
        "samples_with_a_real_label": samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analyzer", default="rules_fulltext")
    parser.add_argument("--dry-run", action="store_true", help="report, roll back, write nothing")
    parser.add_argument("--stock", default=None, help="limit to one code")
    args = parser.parse_args()

    print(json.dumps(run(args.analyzer, args.dry_run, args.stock), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
