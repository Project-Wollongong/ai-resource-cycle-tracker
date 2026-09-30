"""Read-only P01/P02/P03 database consistency audit.

The audit never creates, updates, or deletes domain rows.  It distinguishes the
latest effective parse state from immutable historical parser output so that an
old anomaly remains visible without making the current API result ambiguous.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from ..config import BASE_DIR, settings


REQUIRED_TABLES = {
    "stocks", "projects", "project_identities", "asset_units", "asset_unit_identities",
    "announcements", "evidence_documents", "p3_parse_runs", "p3_events", "p3_facts",
    "p3_information_points", "p3_information_point_facts",
}
LATEST_RUNS_SQL = """
SELECT MAX(id) AS run_id
FROM p3_parse_runs
WHERE status IN ('parsed', 'partial', 'review_needed')
GROUP BY evidence_document_id
"""


def audit_database_consistency(
    session: Session,
    *,
    repo_root: Path | None = None,
    expected_db_path: Path | None = None,
    expected_counts: dict[str, int] | None = None,
    scan_database_files: bool = True,
) -> dict[str, Any]:
    repo_root = (repo_root or BASE_DIR).resolve()
    expected_db_path = (expected_db_path or Path(settings.db_path)).resolve()
    expected_counts = expected_counts if expected_counts is not None else {"stocks": 32, "projects": 9, "asset_units": 5}
    checks: list[dict[str, Any]] = []

    bound_db = _bound_database_path(session)
    _check(
        checks, "formal_database_path", bound_db == expected_db_path, "critical",
        "Runtime database is data/tracker.db",
        {"expected": str(expected_db_path), "actual": str(bound_db) if bound_db else None},
    )
    if scan_database_files:
        db_files, cache_db_files = _database_files(repo_root)
    else:
        db_files, cache_db_files = [expected_db_path], []
    _check(
        checks, "single_database_file", db_files == [expected_db_path], "critical",
        "Only one application .db file exists in the workspace",
        {
            "expected": [str(expected_db_path)],
            "found": [str(path) for path in db_files],
            "non_application_cache_files": [str(path) for path in cache_db_files],
        },
    )

    tables = set(inspect(session.get_bind()).get_table_names())
    missing_tables = sorted(REQUIRED_TABLES - tables)
    _check(checks, "required_schema_tables", not missing_tables, "critical", "P01/P02/P03 tables share the formal database", {"missing_tables": missing_tables})
    if missing_tables:
        return _result(checks, expected_db_path, bound_db, db_files, cache_db_files, {})

    integrity = str(session.execute(text("PRAGMA integrity_check")).scalar() or "")
    _check(checks, "sqlite_integrity", integrity.casefold() == "ok", "critical", "SQLite structural integrity", {"result": integrity})
    foreign_key_rows = [tuple(row) for row in session.execute(text("PRAGMA foreign_key_check")).all()]
    _check(checks, "sqlite_foreign_keys", not foreign_key_rows, "critical", "SQLite declared foreign keys", {"violation_count": len(foreign_key_rows), "samples": foreign_key_rows[:20]})

    inventory = {
        "stocks": _count(session, "stocks"),
        "pilot_stocks": _scalar(session, "SELECT COUNT(*) FROM stocks WHERE pilot_universe_member = 1"),
        "projects": _count(session, "projects"),
        "asset_units": _count(session, "asset_units"),
        "announcements": _count(session, "announcements"),
        "evidence_documents": _count(session, "evidence_documents"),
        "p3_events": _count(session, "p3_events"),
        "p3_facts": _count(session, "p3_facts"),
        "p3_information_points": _count(session, "p3_information_points"),
    }
    count_differences = {name: {"expected": expected, "actual": inventory.get(name)} for name, expected in expected_counts.items() if inventory.get(name) != expected}
    _check(checks, "approved_entity_inventory", not count_differences, "medium", "Approved Stock/Project/Asset Unit inventory", {"counts": inventory, "differences": count_differences}, warning_on_failure=True)

    duplicate_projects = _rows(session, "SELECT lower(trim(name)) normalized_name, COUNT(*) count, group_concat(id) ids FROM projects GROUP BY lower(trim(name)) HAVING COUNT(*) > 1")
    duplicate_assets = _rows(session, "SELECT project_id, lower(trim(name)) normalized_name, COUNT(*) count, group_concat(id) ids FROM asset_units GROUP BY project_id, lower(trim(name)) HAVING COUNT(*) > 1")
    project_identity_collisions = _rows(session, "SELECT normalized_value, COUNT(DISTINCT project_id) count, group_concat(DISTINCT project_id) ids FROM project_identities WHERE is_current = 1 GROUP BY normalized_value HAVING COUNT(DISTINCT project_id) > 1")
    asset_identity_collisions = _rows(session, "SELECT normalized_value, COUNT(DISTINCT asset_unit_id) count, group_concat(DISTINCT asset_unit_id) ids FROM asset_unit_identities WHERE is_current = 1 GROUP BY normalized_value HAVING COUNT(DISTINCT asset_unit_id) > 1")
    entity_duplicates = duplicate_projects + duplicate_assets + project_identity_collisions + asset_identity_collisions
    _check(checks, "approved_entity_uniqueness", not entity_duplicates, "high", "No duplicate approved names or current identity collisions", {"violation_count": len(entity_duplicates), "samples": entity_duplicates[:20]})

    orphan_counts = {
        "stock": _scalar(session, "SELECT COUNT(*) FROM p3_facts f LEFT JOIN stocks s ON s.id=f.stock_id WHERE f.stock_id IS NOT NULL AND s.id IS NULL"),
        "project": _scalar(session, "SELECT COUNT(*) FROM p3_facts f LEFT JOIN projects p ON p.id=f.project_id WHERE f.project_id IS NOT NULL AND p.id IS NULL"),
        "asset_unit": _scalar(session, "SELECT COUNT(*) FROM p3_facts f LEFT JOIN asset_units a ON a.id=f.asset_unit_id WHERE f.asset_unit_id IS NOT NULL AND a.id IS NULL"),
        "announcement": _scalar(session, "SELECT COUNT(*) FROM p3_facts f LEFT JOIN announcements a ON a.id=f.announcement_id WHERE f.announcement_id IS NOT NULL AND a.id IS NULL"),
        "evidence_document": _scalar(session, "SELECT COUNT(*) FROM p3_facts f LEFT JOIN evidence_documents e ON e.id=f.evidence_document_id WHERE e.id IS NULL"),
        "event": _scalar(session, "SELECT COUNT(*) FROM p3_facts f LEFT JOIN p3_events e ON e.id=f.p3_event_id WHERE f.p3_event_id IS NULL OR e.id IS NULL"),
        "parse_run": _scalar(session, "SELECT COUNT(*) FROM p3_facts f LEFT JOIN p3_parse_runs r ON r.id=f.parse_run_id WHERE f.parse_run_id IS NULL OR r.id IS NULL"),
    }
    _check(checks, "p3_fact_foreign_keys", not any(orphan_counts.values()), "critical", "Every P3Fact references existing P01/P02/P03 parents", {"orphan_counts": orphan_counts})

    unapproved_references = _rows(session, """
        SELECT f.id, f.project_id, f.asset_unit_id,
               CASE WHEN f.project_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM project_identities i WHERE i.project_id=f.project_id AND i.is_current=1) THEN 'project_without_current_identity'
                    WHEN f.asset_unit_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM asset_unit_identities i WHERE i.asset_unit_id=f.asset_unit_id AND i.is_current=1) THEN 'asset_without_current_identity' END reason
        FROM p3_facts f
        WHERE (f.project_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM project_identities i WHERE i.project_id=f.project_id AND i.is_current=1))
           OR (f.asset_unit_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM asset_unit_identities i WHERE i.asset_unit_id=f.asset_unit_id AND i.is_current=1))
        LIMIT 20
    """)
    _check(checks, "p3_fact_approved_entities", not unapproved_references, "high", "Fact entity links use approved current identities", {"violation_count": len(unapproved_references), "samples": unapproved_references})

    current_entity_issues = _entity_issues(session, latest_only=True)
    historical_entity_issues = _entity_issues(session, latest_only=False)
    _check(checks, "latest_fact_entity_consistency", not current_entity_issues, "high", "Latest Facts use matching Project/Asset Unit pairs and avoid inferred context", {"violation_count": len(current_entity_issues), "samples": current_entity_issues[:20]})
    _check(checks, "historical_fact_entity_consistency", not historical_entity_issues, "medium", "Historical parser output entity attribution", {"violation_count": len(historical_entity_issues), "samples": historical_entity_issues[:20]}, warning_on_failure=True)

    company_count = _scalar(session, f"SELECT COUNT(*) FROM p3_facts WHERE parse_run_id IN ({LATEST_RUNS_SQL}) AND project_id IS NULL AND asset_unit_id IS NULL AND project_attribution_status='unknown'")
    invalid_company = _rows(session, f"""
        SELECT id, project_id, asset_unit_id, project_attribution_status
        FROM p3_facts
        WHERE parse_run_id IN ({LATEST_RUNS_SQL})
          AND ((project_id IS NULL AND asset_unit_id IS NULL AND project_attribution_status != 'unknown')
            OR ((project_id IS NOT NULL OR asset_unit_id IS NOT NULL) AND project_attribution_status = 'unknown'))
        LIMIT 20
    """)
    _check(checks, "company_layer_attribution", not invalid_company, "high", "Unconfirmed latest Facts remain at Company level", {"company_level_fact_count": company_count, "violation_count": len(invalid_company), "samples": invalid_company})

    lineage_issues = _rows(session, f"""
        SELECT f.id,
          CASE WHEN e.announcement_id != f.announcement_id THEN 'event_announcement'
               WHEN e.evidence_document_id != f.evidence_document_id THEN 'event_evidence'
               WHEN e.parse_run_id != f.parse_run_id THEN 'event_parse_run'
               WHEN d.announcement_id != f.announcement_id THEN 'evidence_announcement'
               WHEN r.evidence_document_id != f.evidence_document_id THEN 'run_evidence'
               WHEN r.announcement_id != f.announcement_id THEN 'run_announcement'
               WHEN f.stock_id IS NOT NULL AND a.stock_id != f.stock_id THEN 'announcement_stock'
          END reason
        FROM p3_facts f
        JOIN p3_events e ON e.id=f.p3_event_id
        JOIN evidence_documents d ON d.id=f.evidence_document_id
        JOIN p3_parse_runs r ON r.id=f.parse_run_id
        JOIN announcements a ON a.id=f.announcement_id
        WHERE f.parse_run_id IN ({LATEST_RUNS_SQL}) AND (
             e.announcement_id != f.announcement_id OR e.evidence_document_id != f.evidence_document_id
          OR e.parse_run_id != f.parse_run_id OR d.announcement_id != f.announcement_id
          OR r.evidence_document_id != f.evidence_document_id OR r.announcement_id != f.announcement_id
          OR (f.stock_id IS NOT NULL AND a.stock_id != f.stock_id))
        LIMIT 20
    """)
    _check(checks, "latest_fact_lineage", not lineage_issues, "critical", "Latest Fact -> Event -> Evidence -> Announcement -> Stock lineage", {"violation_count": len(lineage_issues), "samples": lineage_issues})

    point_issues = _rows(session, f"""
        SELECT f.id,
          CASE WHEN f.information_point_group_id IS NULL THEN 'missing_group'
               WHEN l.id IS NULL THEN 'missing_link'
               WHEN p.point_type != f.information_point_type THEN 'type_mismatch'
               WHEN l.display_order != f.display_order THEN 'display_order_mismatch'
               WHEN f.parent_fact_id IS NOT NULL AND (parent.information_point_group_id IS NULL OR parent.information_point_group_id != f.information_point_group_id) THEN 'parent_outside_group'
          END reason
        FROM p3_facts f
        LEFT JOIN p3_information_points p ON p.id=f.information_point_group_id
        LEFT JOIN p3_information_point_facts l ON l.p3_fact_id=f.id AND l.information_point_id=f.information_point_group_id
        LEFT JOIN p3_facts parent ON parent.id=f.parent_fact_id
        WHERE f.parse_run_id IN ({LATEST_RUNS_SQL}) AND (
             f.information_point_group_id IS NULL OR l.id IS NULL OR p.point_type != f.information_point_type
          OR l.display_order != f.display_order
          OR (f.parent_fact_id IS NOT NULL AND (parent.information_point_group_id IS NULL OR parent.information_point_group_id != f.information_point_group_id)))
        LIMIT 20
    """)
    _check(checks, "latest_information_point_integrity", not point_issues, "high", "Latest Information Point membership and parent/display order", {"violation_count": len(point_issues), "samples": point_issues})

    parser_created_entities = _rows(session, """
        SELECT 'project' entity_type, id, source FROM project_identities WHERE lower(source) LIKE 'p3%' OR lower(source) LIKE '%parser%'
        UNION ALL
        SELECT 'asset_unit', id, source FROM asset_unit_identities WHERE lower(source) LIKE 'p3%' OR lower(source) LIKE '%parser%'
        LIMIT 20
    """)
    _check(checks, "no_p3_entity_autocreation", not parser_created_entities, "critical", "P03 has not auto-created Project/Asset Unit identities", {"violation_count": len(parser_created_entities), "samples": parser_created_entities})

    return _result(checks, expected_db_path, bound_db, db_files, cache_db_files, inventory)


def _entity_issues(session: Session, *, latest_only: bool) -> list[dict]:
    scope = f"f.parse_run_id IN ({LATEST_RUNS_SQL}) AND " if latest_only else ""
    return _rows(session, f"""
        SELECT f.id, f.parse_run_id, f.fact_type, f.project_id, f.asset_unit_id,
               a.project_id approved_project_id, f.project_attribution_status,
               CASE WHEN f.asset_unit_id IS NOT NULL AND f.project_id IS NULL THEN 'asset_without_project'
                    WHEN f.asset_unit_id IS NOT NULL AND f.project_id != a.project_id THEN 'asset_project_mismatch'
                    WHEN f.project_attribution_status = 'inferred_from_context' THEN 'context_inference'
               END reason
        FROM p3_facts f
        LEFT JOIN asset_units a ON a.id=f.asset_unit_id
        WHERE {scope}(
             (f.asset_unit_id IS NOT NULL AND (f.project_id IS NULL OR f.project_id != a.project_id))
          OR f.project_attribution_status = 'inferred_from_context')
        ORDER BY f.id DESC LIMIT 100
    """)


def _database_files(repo_root: Path) -> tuple[list[Path], list[Path]]:
    """Separate application databases from known disposable library caches."""
    excluded = {".git", "node_modules", ".pytest_cache", "pytest-cache-files-r3lcxyem", ".venv", ".venv-win", ".venv-local"}
    candidates = [path.resolve() for path in repo_root.rglob("*.db") if not excluded.intersection(path.parts)]
    cache_files = sorted(path for path in candidates if "yfinance_cache" in {part.casefold() for part in path.parts})
    application_files = sorted(path for path in candidates if path not in cache_files)
    return application_files, cache_files


def _bound_database_path(session: Session) -> Path | None:
    database = session.get_bind().url.database
    if not database or database == ":memory:":
        return None
    return Path(database).resolve()


def _count(session: Session, table: str) -> int:
    return _scalar(session, f"SELECT COUNT(*) FROM {table}")


def _scalar(session: Session, sql: str) -> int:
    return int(session.execute(text(sql)).scalar() or 0)


def _rows(session: Session, sql: str) -> list[dict]:
    return [dict(row) for row in session.execute(text(sql)).mappings().all()]


def _check(checks: list[dict], code: str, passed: bool, severity: str, description: str, evidence: dict, *, warning_on_failure: bool = False) -> None:
    checks.append({
        "code": code,
        "status": "pass" if passed else "warning" if warning_on_failure else "fail",
        "severity": severity,
        "description": description,
        "evidence": evidence,
    })


def _result(
    checks: list[dict],
    expected: Path,
    bound: Path | None,
    files: list[Path],
    cache_files: list[Path],
    inventory: dict,
) -> dict:
    failures = [check for check in checks if check["status"] == "fail"]
    warnings = [check for check in checks if check["status"] == "warning"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_version": "p3_database_consistency_v1",
        "status": "fail" if failures else "warning" if warnings else "pass",
        "database": {
            "expected_path": str(expected), "runtime_path": str(bound) if bound else None,
            "database_files": [str(path) for path in files],
            "non_application_cache_files": [str(path) for path in cache_files],
        },
        "inventory": inventory,
        "summary": {"check_count": len(checks), "passed": sum(check["status"] == "pass" for check in checks), "warnings": len(warnings), "failed": len(failures)},
        "checks": checks,
    }
