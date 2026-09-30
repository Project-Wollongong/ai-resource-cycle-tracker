import json

from ..models import Announcement, Signal, Stock
from ..schemas import AnnouncementOut, SignalOut, SignalReturnOut


def announcement_out(ann: Announcement, code: str) -> AnnouncementOut:
    evidence = ann.evidence_document
    return AnnouncementOut(
        id=ann.id,
        code=code,
        ann_id=ann.ann_id,
        headline=ann.headline,
        ann_date=ann.ann_date,
        url=ann.url,
        price_sensitive=ann.price_sensitive,
        ann_type=ann.ann_type,
        type_score=ann.type_score,
        matched_keywords=json.loads(ann.matched_keywords or "[]"),
        ai_summary=ann.ai_summary,
        ai_metrics=_json_object_or_none(ann.ai_metrics),
        evidence_document_id=evidence.id if evidence else None,
        evidence_status=evidence.evidence_status if evidence else "metadata_only",
        download_status=evidence.download_status if evidence else "pending",
        text_status=evidence.text_status if evidence else "pending",
        local_pdf_available=bool(evidence and evidence.local_original_path),
        page_count=evidence.page_count if evidence else None,
        file_size_bytes=evidence.file_size_bytes if evidence else None,
        hash_prefix=(evidence.file_hash_sha256 or evidence.content_hash)[:12] if evidence and (evidence.file_hash_sha256 or evidence.content_hash) else None,
        fetched_at=evidence.downloaded_at if evidence else None,
        evidence_error=evidence.error_message if evidence else None,
        evidence_retryable=bool(evidence and evidence.download_status == "failed" or evidence and evidence.text_status == "failed"),
        document_category=ann.document_category or "Other / Needs Review",
        official_header_type=ann.official_header_type,
        official_subtype=ann.official_subtype,
        standard_form=ann.standard_form,
        event_families=_json_list(ann.event_families_json),
        event_labels=_json_list(ann.event_labels_json),
        revision_tags=_json_list(ann.revision_tags_json),
        classification_source=ann.classification_source or "title_routing",
    )


def _json_object_or_none(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _json_list(raw: str | None) -> list[str]:
    if not raw: return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in data] if isinstance(data, list) else []


def signal_out(sig: Signal, stock: Stock) -> SignalOut:
    returns = sorted(sig.returns, key=lambda r: r.horizon_days)
    return SignalOut(
        id=sig.id,
        code=stock.code,
        stock_name=stock.name,
        date=sig.date,
        signal_type=sig.signal_type,
        source=sig.source,
        label=sig.label,
        reason=sig.reason,
        evidence=json.loads(sig.evidence or "{}"),
        price_at_signal=sig.price_at_signal,
        cycle_score_at_signal=sig.cycle_score_at_signal,
        returns=[
            SignalReturnOut(
                horizon_days=r.horizon_days,
                entry_price=r.entry_price,
                return_pct=r.return_pct,
                benchmark_return_pct=r.benchmark_return_pct,
                status=r.status,
            )
            for r in returns
        ],
    )
