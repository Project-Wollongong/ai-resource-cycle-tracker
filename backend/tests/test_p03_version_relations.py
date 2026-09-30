from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import admin, p3
from app.api.security import require_admin_access
from app.models import (
    Announcement, AnnouncementVersionRelation, EvidenceDocument, P3Event, P3Fact,
    P3ParseRun, P3Statement, P3VersionRelation, P3VersionRelationChangeLog, Stock,
)
from app.services.p3_versioning_service import detect_version_relation_candidates


def _client(db):
    app = FastAPI()
    app.include_router(admin.router, prefix="/api")
    app.include_router(p3.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin_access] = lambda: True
    return TestClient(app)


def _announcement(db, stock, ann_id, headline, day):
    ann = Announcement(stock_id=stock.id, ann_id=ann_id, headline=headline,
                       ann_date=datetime(2026, 9, day), url=f"https://example.test/{ann_id}.pdf")
    db.add(ann); db.flush()
    evidence = EvidenceDocument(
        stock_id=stock.id, announcement_id=ann.id, source_type="fixture", source_id=ann_id,
        title=headline, document_date=ann.ann_date, url=ann.url, source_url=ann.url,
        page_count=2, evidence_status="text_ready", download_status="downloaded", text_status="extracted",
    )
    db.add(evidence); db.flush()
    run = P3ParseRun(evidence_document_id=evidence.id, announcement_id=ann.id, parser_name="test",
                     parser_version="version-v1", input_hash=ann_id.ljust(64, "0"), status="parsed")
    db.add(run); db.flush()
    return ann, evidence, run


def _event(db, stock, ann, evidence, run, title="DFS Schedule", event_type="PROJECT_SCHEDULE_UPDATE", family="F04", excerpt=""):
    row = P3Event(
        announcement_id=ann.id, evidence_document_id=evidence.id, parse_run_id=run.id, stock_id=stock.id,
        event_type=event_type, event_family=family, primary_family=family, event_title=title,
        source_section="highlights", source_page_start=1, source_page_end=1,
        source_excerpt=excerpt or title, validity_status="current",
    )
    db.add(row); db.flush(); return row


def _fact(db, stock, ann, evidence, run, event, fact_type, value, field_name=None, excerpt=None, period_end=None):
    row = P3Fact(
        announcement_id=ann.id, evidence_document_id=evidence.id, parse_run_id=run.id,
        p3_event_id=event.id, stock_id=stock.id, fact_family=event.primary_family,
        fact_type=fact_type, schema_name="test", field_name=field_name or fact_type.replace("_", " ").title(),
        value_raw=value, value_text=value, value_json="{}", period_end=period_end,
        source_section="highlights", source_page_start=1, source_page_end=1,
        source_excerpt=excerpt or value, review_status="confirmed", validity_status="current",
    )
    db.add(row); db.flush(); return row


def _seed_stock(db, code="CVV"):
    stock = Stock(code=code, name=f"{code} Mining", commodity="copper")
    db.add(stock); db.flush(); return stock


def test_cvv_dfs_revision_is_proposed_then_confirmed_without_deleting_history(db_session):
    stock = _seed_stock(db_session)
    old_ann, old_ev, old_run = _announcement(db_session, stock, "CVV-OLD", "DFS Completion Timing", 1)
    old_event = _event(db_session, stock, old_ann, old_ev, old_run, excerpt="DFS completion target September 2026")
    old_fact = _fact(db_session, stock, old_ann, old_ev, old_run, old_event, "dfs_completion", "September 2026", "DFS Completion Timing")
    new_ann, new_ev, new_run = _announcement(db_session, stock, "2924-03136859-6A1344354", "PS DFS Revised Completion Timing", 10)
    new_event = _event(db_session, stock, new_ann, new_ev, new_run, excerpt="Highlights: DFS completion revised to Q4 2026.")
    new_fact = _fact(db_session, stock, new_ann, new_ev, new_run, new_event, "dfs_completion", "Q4 2026", "DFS Completion Timing", "Highlights: DFS completion revised to Q4 2026.")
    db_session.add(AnnouncementVersionRelation(predecessor_announcement_id=old_ann.id, successor_announcement_id=new_ann.id,
                                               relation_type="revises", status="confirmed", source="fixture"))
    db_session.flush()

    relations = detect_version_relation_candidates(db_session, new_ann, [new_event], [new_fact])
    fact_relation = next(row for row in relations if row.predecessor_type == "fact")
    assert fact_relation.status == "proposed" and fact_relation.source_page_start == 1
    assert old_fact.validity_status == "current"
    pending = _client(db_session).get(f"/api/p3/facts/{old_fact.id}").json()
    assert pending["validity_status"] == "current"
    assert pending["display_validity_status"] == "correction_pending_review"

    response = _client(db_session).post(f"/api/admin/p3/version-relations/{fact_relation.id}/confirm", json={
        "reviewer": "p03-reviewer", "review_note": "CVV Highlights explicitly revises the DFS completion target",
    })
    assert response.status_code == 200, response.text
    db_session.refresh(old_fact); db_session.refresh(new_fact)
    assert old_fact.validity_status == "superseded" and new_fact.validity_status == "current"
    assert db_session.get(P3Fact, old_fact.id) is not None
    assert _client(db_session).get(f"/api/announcements/{old_ann.ann_id}/facts").json() == []
    assert [row["value_raw"] for row in _client(db_session).get(f"/api/announcements/{new_ann.ann_id}/facts").json()] == ["Q4 2026"]
    history = _client(db_session).get(f"/api/p3/facts/{old_fact.id}/history").json()
    assert {row["value_raw"] for row in history["versions"]} >= {"September 2026", "Q4 2026"}
    assert history["version_relations"][0]["source_excerpt"].startswith("Highlights")


def test_confirmed_withdrawal_only_withdraws_the_target_fact(db_session):
    stock = _seed_stock(db_session, "WDR")
    old_ann, old_ev, old_run = _announcement(db_session, stock, "WDR-OLD", "Material Disclosure", 1)
    event = _event(db_session, stock, old_ann, old_ev, old_run, title="Financial Disclosure", event_type="CASH_POSITION", family="F08")
    withdrawn_fact = _fact(db_session, stock, old_ann, old_ev, old_run, event, "cash_balance", "A$5m", "Cash Balance")
    retained_fact = _fact(db_session, stock, old_ann, old_ev, old_run, event, "debt", "A$1m", "Debt")
    new_ann, new_ev, new_run = _announcement(db_session, stock, "WDR-NEW", "Withdrawal of Cash Balance disclosure", 5)
    withdrawal_event = _event(db_session, stock, new_ann, new_ev, new_run, title="Withdrawal", event_type="WITHDRAWAL", family="F08",
                              excerpt="The company withdraws the previously reported Cash Balance disclosure.")
    db_session.add(AnnouncementVersionRelation(predecessor_announcement_id=old_ann.id, successor_announcement_id=new_ann.id,
                                               relation_type="withdraws", status="confirmed", source="fixture"))
    db_session.flush()
    relations = detect_version_relation_candidates(db_session, new_ann, [withdrawal_event], [])
    relation = next(row for row in relations if row.predecessor_type == "fact")
    assert relation.successor_id is None and withdrawn_fact.validity_status == "current"
    response = _client(db_session).post(f"/api/admin/p3/version-relations/{relation.id}/confirm", json={
        "reviewer": "p03-reviewer", "review_note": "Company explicitly withdrew only the Cash Balance disclosure",
    })
    assert response.status_code == 200
    db_session.refresh(withdrawn_fact); db_session.refresh(retained_fact)
    assert withdrawn_fact.validity_status == "withdrawn"
    assert retained_fact.validity_status == "current"
    current_ids = {row["id"] for row in _client(db_session).get("/api/p3/facts?current_only=true").json()}
    assert withdrawn_fact.id not in current_ids and retained_fact.id in current_ids
    historical = _client(db_session).get("/api/p3/facts?current_only=false").json()
    assert withdrawn_fact.id in {row["id"] for row in historical}


def test_periodic_cash_and_new_drill_results_do_not_auto_supersede(db_session):
    stock = _seed_stock(db_session, "NEG")
    old_ann, old_ev, old_run = _announcement(db_session, stock, "NEG-Q1", "Quarterly Activities", 1)
    old_event = _event(db_session, stock, old_ann, old_ev, old_run, title="Quarterly Cash", event_type="CASH_POSITION", family="F08")
    old_cash = _fact(db_session, stock, old_ann, old_ev, old_run, old_event, "cash_balance", "A$5m", period_end=datetime(2026, 3, 31).date())
    new_ann, new_ev, new_run = _announcement(db_session, stock, "NEG-Q2", "Quarterly Activities", 10)
    new_event = _event(db_session, stock, new_ann, new_ev, new_run, title="Quarterly Cash", event_type="CASH_POSITION", family="F08")
    new_cash = _fact(db_session, stock, new_ann, new_ev, new_run, new_event, "cash_balance", "A$4m", period_end=datetime(2026, 6, 30).date())
    assert detect_version_relation_candidates(db_session, new_ann, [new_event], [new_cash]) == []
    assert old_cash.validity_status == new_cash.validity_status == "current"

    drill_ann, drill_ev, drill_run = _announcement(db_session, stock, "NEG-DRILL", "Results", 15)
    drill_event = _event(db_session, stock, drill_ann, drill_ev, drill_run, title="Drill Results", event_type="DRILL_RESULTS", family="F01")
    drill_fact = _fact(db_session, stock, drill_ann, drill_ev, drill_run, drill_event, "drill_interval", "12m @ 1%", "Drill Interval")
    assert detect_version_relation_candidates(db_session, drill_ann, [drill_event], [drill_fact]) == []
    assert db_session.query(P3VersionRelation).count() == 0


def test_relations_support_event_fact_statement_and_reject_has_no_effect(db_session):
    stock = _seed_stock(db_session, "ALL")
    ann1, ev1, run1 = _announcement(db_session, stock, "ALL-1", "Original", 1)
    ann2, ev2, run2 = _announcement(db_session, stock, "ALL-2", "Correction", 2)
    event1 = _event(db_session, stock, ann1, ev1, run1)
    event2 = _event(db_session, stock, ann2, ev2, run2)
    fact1 = _fact(db_session, stock, ann1, ev1, run1, event1, "dfs_completion", "September 2026")
    fact2 = _fact(db_session, stock, ann2, ev2, run2, event2, "dfs_completion", "Q4 2026")
    statement1 = P3Statement(announcement_id=ann1.id, evidence_document_id=ev1.id, p3_event_id=event1.id,
                             parse_run_id=run1.id, stock_id=stock.id, statement_type="schedule",
                             statement_text="September 2026", source_page=1, source_excerpt="September 2026")
    statement2 = P3Statement(announcement_id=ann2.id, evidence_document_id=ev2.id, p3_event_id=event2.id,
                             parse_run_id=run2.id, stock_id=stock.id, statement_type="schedule",
                             statement_text="Q4 2026", source_page=1, source_excerpt="Corrected to Q4 2026")
    db_session.add_all([statement1, statement2]); db_session.flush()
    relations = [
        P3VersionRelation(predecessor_type="event", predecessor_id=event1.id, successor_type="event", successor_id=event2.id,
                          relation_type="corrects", status="proposed", source_announcement_id=ann2.id,
                          source_evidence_document_id=ev2.id, source_page_start=1, source_excerpt="Correction"),
        P3VersionRelation(predecessor_type="fact", predecessor_id=fact1.id, successor_type="fact", successor_id=fact2.id,
                          relation_type="corrects", status="proposed", source_announcement_id=ann2.id,
                          source_evidence_document_id=ev2.id, source_page_start=1, source_excerpt="Correction"),
        P3VersionRelation(predecessor_type="statement", predecessor_id=statement1.id, successor_type="statement", successor_id=statement2.id,
                          relation_type="corrects", status="proposed", source_announcement_id=ann2.id,
                          source_evidence_document_id=ev2.id, source_page_start=1, source_excerpt="Correction"),
    ]
    db_session.add_all(relations); db_session.commit()
    response = _client(db_session).post(f"/api/admin/p3/version-relations/{relations[1].id}/reject", json={
        "reviewer": "reviewer", "review_note": "The extracted values refer to different scopes",
    })
    assert response.status_code == 200
    db_session.refresh(fact1); db_session.refresh(fact2)
    assert fact1.validity_status == fact2.validity_status == "current"
    assert {row.predecessor_type for row in relations} == {"event", "fact", "statement"}


def test_correct_confirmed_relation_recalculates_status_and_keeps_change_log(db_session):
    stock = _seed_stock(db_session, "COR")
    ann1, ev1, run1 = _announcement(db_session, stock, "COR-1", "Original", 1)
    ann2, ev2, run2 = _announcement(db_session, stock, "COR-2", "Revised", 2)
    event1 = _event(db_session, stock, ann1, ev1, run1)
    event2 = _event(db_session, stock, ann2, ev2, run2)
    old = _fact(db_session, stock, ann1, ev1, run1, event1, "dfs_completion", "September 2026")
    new = _fact(db_session, stock, ann2, ev2, run2, event2, "dfs_completion", "Q4 2026")
    relation = P3VersionRelation(predecessor_type="fact", predecessor_id=old.id, successor_type="fact", successor_id=new.id,
                                 relation_type="revises", status="proposed", source_announcement_id=ann2.id,
                                 source_evidence_document_id=ev2.id, source_page_start=1, source_excerpt="Revised timing")
    db_session.add(relation); db_session.commit()
    client = _client(db_session)
    assert client.post(f"/api/admin/p3/version-relations/{relation.id}/confirm", json={
        "reviewer": "reviewer", "review_note": "Confirmed revision",
    }).status_code == 200
    db_session.refresh(old); assert old.validity_status == "superseded"
    corrected = client.put(f"/api/admin/p3/version-relations/{relation.id}", json={
        "reviewer": "reviewer-2", "review_note": "Relationship is contextual, not substitutive",
        "relation_type": "related_to",
    })
    assert corrected.status_code == 200, corrected.text
    db_session.refresh(old); assert old.validity_status == "current"
    logs = db_session.query(P3VersionRelationChangeLog).filter_by(relation_id=relation.id).all()
    assert [row.action for row in logs] == ["confirm", "correct"]
    assert '"relation_type": "revises"' in logs[1].before_json
    assert '"relation_type": "related_to"' in logs[1].after_json
