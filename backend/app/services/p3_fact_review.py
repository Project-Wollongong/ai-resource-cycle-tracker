"""Helpers that preserve automatic P3 fact results during human review."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import P3Fact, P3FactReview


REVIEW_FIELDS = (
    "field_name", "value_raw", "value_numeric", "value_text", "unit_raw", "unit_normalized",
    "currency_raw", "currency_normalized", "quantity_type", "period_start", "period_end",
    "as_of_date", "effective_date", "status", "project_id", "asset_unit_id",
    "project_attribution_status", "review_status", "active_result",
)


def snapshot(fact: P3Fact) -> dict:
    return {field: _json_value(getattr(fact, field)) for field in REVIEW_FIELDS}


def apply_review(session: Session, fact: P3Fact, action: str, reviewer: str, note: str, changes: dict | None = None) -> P3Fact:
    before = snapshot(fact)
    if not fact.original_extraction_json or fact.original_extraction_json == "{}":
        fact.original_extraction_json = json.dumps(before, ensure_ascii=False)
    if changes:
        for field, value in changes.items():
            if field in REVIEW_FIELDS and field not in {"review_status", "active_result"}:
                setattr(fact, field, value)
    fact.review_status = "rejected" if action == "reject" else "confirmed"
    fact.active_result = action != "reject"
    fact.validity_status = "rejected" if action == "reject" else "current"
    fact.validity_reason = note if action == "reject" else ""
    fact.validity_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    fact.reviewed_by = reviewer
    fact.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    fact.review_note = note
    session.add(P3FactReview(
        p3_fact_id=fact.id, action=action, before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(snapshot(fact), ensure_ascii=False), reviewer=reviewer, review_note=note,
    ))
    return fact


def _json_value(value):
    return value.isoformat() if hasattr(value, "isoformat") else value
