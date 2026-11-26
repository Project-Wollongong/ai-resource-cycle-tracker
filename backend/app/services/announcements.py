"""Fetch → classify → upsert announcements for one stock (+ AI-analyzer hook)."""

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..analysis.ai_stub import (
    AnnouncementAnalyzer,
    AnnouncementDocumentFetcher,
    insight_metrics_with_document,
)
from ..analysis.classifier import classify
from ..analysis.p3_family_classifier import classify_families
from ..config import market_tz
from ..datasources.base import AnnouncementSource
from ..models import Announcement, AnnouncementVersionRelation, Stock
from .evidence_service import ensure_evidence
from .qualitative_mining_context import enrich_qualitative_context
from .p3_parse_service import PARSER_VERSION, parse_evidence

logger = logging.getLogger(__name__)

_REVISION_TERMS = ("revised", "revision", "correction", "replacement", "replace", "withdrawal", "withdrawn", "amended")


def _normalise_announcement_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(market_tz()).replace(tzinfo=None)
    return value


def _detect_announcement_gap(session: Session, stock: Stock, source: AnnouncementSource, raws: list) -> dict | None:
    """Detect an unseen interval when a recent-only source is visibly capped."""
    limit = getattr(source, "recent_announcement_limit", None)
    if not limit or len(raws) < limit:
        return None
    latest_existing = (
        session.query(Announcement.ann_date)
        .filter(Announcement.stock_id == stock.id)
        .order_by(Announcement.ann_date.desc())
        .first()
    )
    if latest_existing is None:
        return None
    source_oldest = min(_normalise_announcement_datetime(raw.ann_date) for raw in raws)
    database_latest = latest_existing[0]
    if source_oldest.date() <= database_latest.date():
        return None
    days = (source_oldest.date() - database_latest.date()).days
    return {
        "stock_code": stock.code,
        "database_latest_date": database_latest.date().isoformat(),
        "source_oldest_date": source_oldest.date().isoformat(),
        "gap_days": days,
    }


def _candidate_version_relation(session: Session, announcement: Announcement, stock: Stock) -> None:
    headline = announcement.headline.casefold()
    if not any(term in headline for term in _REVISION_TERMS):
        return
    tokens = {token for token in headline.replace("-", " ").split() if len(token) > 3 and token not in _REVISION_TERMS}
    candidates = session.query(Announcement).filter(Announcement.stock_id == stock.id, Announcement.id != announcement.id).order_by(Announcement.ann_date.desc()).limit(50).all()
    prior = next((candidate for candidate in candidates if len(tokens & set(candidate.headline.casefold().replace("-", " ").split())) >= max(1, min(2, len(tokens)))), None)
    if prior is None:
        return
    relation_type = "revises" if "revis" in headline else "replaces" if "replace" in headline else "corrects" if "correct" in headline else "withdraws" if "withdraw" in headline else "related_to"
    exists = session.query(AnnouncementVersionRelation).filter_by(predecessor_announcement_id=prior.id, successor_announcement_id=announcement.id).first()
    if exists is None:
        session.add(AnnouncementVersionRelation(predecessor_announcement_id=prior.id, successor_announcement_id=announcement.id, relation_type=relation_type, confidence=0.65, status="pending_review", source="title_rule_candidate"))


def sync_announcements(
    session: Session,
    stock: Stock,
    source: AnnouncementSource,
    analyzer: AnnouncementAnalyzer,
    count: int = 20,
    document_fetcher: AnnouncementDocumentFetcher | None = None,
    include_evidence_stats: bool = False,
    download_evidence: bool = True,
    extract_evidence: bool = True,
    parse_p3: bool = True,
    parser_version: str = PARSER_VERSION,
) -> dict:
    """Returns {"new": n}. SourceBlockedError is NOT caught here — the pipeline
    handles degradation so it can mark the whole run, not just one stock."""
    raws = source.fetch(stock.code, count)
    # Gap detection is advisory. An unexpected source payload must never stop
    # price, scoring, or evidence work later in the pipeline.
    try:
        announcement_gap = _detect_announcement_gap(session, stock, source, raws)
    except Exception:
        logger.exception("announcement gap detection failed for %s", stock.code)
        announcement_gap = None
    new = 0
    evidence_downloaded = evidence_failed = text_extracted = text_failed = 0
    p3_parsed = p3_review_needed = p3_failed = p3_skipped = 0
    for raw in raws:
        exists = (
            session.query(Announcement.id)
            .filter_by(stock_id=stock.id, ann_id=raw.ann_id)
            .first()
        )
        if exists:
            continue
        classification = classify(raw.headline)
        family_classification = classify_families(raw.headline, raw.raw)
        # Store naive local (Australia/Sydney) so "announcement day" aligns
        # with ASX trading dates.
        ann_date = _normalise_announcement_datetime(raw.ann_date)
        announcement = Announcement(
            stock_id=stock.id,
            ann_id=raw.ann_id,
            headline=raw.headline,
            ann_date=ann_date,
            url=raw.url,
            price_sensitive=raw.price_sensitive,
            ann_type=classification.ann_type,
            type_score=classification.type_score,
            matched_keywords=json.dumps(classification.matched_keywords),
            raw_payload=json.dumps(raw.raw),
            document_category=family_classification.document_category,
            official_header_type=family_classification.official_header_type,
            official_subtype=family_classification.official_subtype,
            standard_form=family_classification.standard_form,
            event_families_json=json.dumps(family_classification.families, ensure_ascii=False),
            event_labels_json=json.dumps(family_classification.event_labels, ensure_ascii=False),
            revision_tags_json=json.dumps(family_classification.revision_tags, ensure_ascii=False),
            classification_source=family_classification.source,
        )
        document = None
        if analyzer.requires_document_text:
            fetcher = document_fetcher or AnnouncementDocumentFetcher()
            document = fetcher.fetch(raw.url)
        insight = analyzer.analyze(
            raw.headline,
            classification.ann_type,
            body_text=document.text if document is not None else None,
            source_url=raw.url,
        )
        if insight is not None:
            metrics = insight_metrics_with_document(insight, document)
            metrics = enrich_qualitative_context(
                session,
                stock.code,
                metrics,
                ann_type=classification.ann_type,
                price_sensitive=raw.price_sensitive,
            )
            announcement.ai_summary = insight.summary
            announcement.ai_metrics = json.dumps(metrics)
        session.add(announcement)
        session.flush()
        evidence = ensure_evidence(session, announcement, stock, download_enabled=download_evidence, extract_enabled=extract_evidence)
        _candidate_version_relation(session, announcement, stock)
        if evidence.download_status == "downloaded":
            evidence_downloaded += 1
        elif evidence.download_status == "failed":
            evidence_failed += 1
        if evidence.text_status == "extracted":
            text_extracted += 1
        elif evidence.text_status == "failed":
            text_failed += 1
        if parse_p3 and evidence.text_status == "extracted":
            parse_run = parse_evidence(session, evidence, parser_version)
            if parse_run.status == "parsed":
                p3_parsed += 1
            elif parse_run.status in {"review_needed", "partial"}:
                p3_review_needed += 1
            else:
                p3_failed += 1
        else:
            p3_skipped += 1
        new += 1
    session.commit()
    if include_evidence_stats:
        return {"new": new, "evidence_downloaded": evidence_downloaded, "evidence_failed": evidence_failed, "text_extracted": text_extracted, "text_failed": text_failed, "p3_parsed": p3_parsed, "p3_review_needed": p3_review_needed, "p3_failed": p3_failed, "p3_skipped": p3_skipped, "parser_version": parser_version, "announcement_gap": announcement_gap}
    return {"new": new}
