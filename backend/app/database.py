from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from . import models  # noqa: F401  (register mappings)

    Base.metadata.create_all(engine)
    _rebuild_expandable_review_tables_if_needed()
    _apply_lightweight_migrations()


def _rebuild_expandable_review_tables_if_needed() -> None:
    """Remove legacy closed-set checks while preserving every existing review row."""
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        mapping_sql = (cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='entity_mappings'").fetchone() or [""])[0] or ""
        if "ck_entity_mapping_status" in mapping_sql or "matched_entity_id INTEGER NOT NULL" in mapping_sql:
            cursor.execute("""CREATE TABLE entity_mappings_new (
                id INTEGER PRIMARY KEY, entity_mention_id INTEGER NOT NULL REFERENCES entity_mentions(id),
                matched_entity_type VARCHAR(20) NOT NULL, matched_entity_id INTEGER, matched_alias_id INTEGER,
                match_method VARCHAR(30) NOT NULL, match_confidence FLOAT NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'review_needed',
                stock_validation_result VARCHAR(80) NOT NULL DEFAULT 'not_applicable',
                parent_validation_result VARCHAR(80) NOT NULL DEFAULT 'not_applicable', matching_reason TEXT NOT NULL DEFAULT '',
                candidate_parent_project_id INTEGER REFERENCES projects(id), proposal_id INTEGER REFERENCES p01_entity_proposals(id),
                candidate_payload_json TEXT NOT NULL DEFAULT '{}', reviewed_by VARCHAR(120), reviewed_at DATETIME,
                review_note TEXT NOT NULL DEFAULT '', created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
            old_columns = {row[1] for row in cursor.execute("PRAGMA table_info(entity_mappings)")}
            new_columns = [row[1] for row in cursor.execute("PRAGMA table_info(entity_mappings_new)")]
            common = [name for name in new_columns if name in old_columns]
            names = ", ".join(common)
            cursor.execute(f"INSERT INTO entity_mappings_new ({names}) SELECT {names} FROM entity_mappings")
            cursor.execute("DROP TABLE entity_mappings")
            cursor.execute("ALTER TABLE entity_mappings_new RENAME TO entity_mappings")
            cursor.execute("CREATE INDEX ix_entity_mappings_entity_mention_id ON entity_mappings(entity_mention_id)")
            cursor.execute("CREATE INDEX ix_entity_mappings_status ON entity_mappings(status)")
            cursor.execute("CREATE INDEX ix_entity_mappings_proposal_id ON entity_mappings(proposal_id)")
            cursor.execute("CREATE INDEX ix_entity_mappings_candidate_parent_project_id ON entity_mappings(candidate_parent_project_id)")
            cursor.execute("CREATE UNIQUE INDEX uq_entity_mapping_confirmed_mention ON entity_mappings(entity_mention_id) WHERE status = 'confirmed'")

        proposal_sql = (cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='p01_entity_proposals'").fetchone() or [""])[0] or ""
        if "ck_p01_proposal_status" in proposal_sql:
            cursor.execute("""CREATE TABLE p01_entity_proposals_new (
                id INTEGER PRIMARY KEY, stock_id INTEGER NOT NULL REFERENCES stocks(id), target_level VARCHAR(20) NOT NULL DEFAULT 'project',
                proposed_project_name VARCHAR(160) NOT NULL, proposed_asset_name VARCHAR(160), proposed_asset_type VARCHAR(80),
                proposed_commodity VARCHAR(80), proposed_ownership_pct FLOAT, proposed_operator VARCHAR(160),
                source_type VARCHAR(40) NOT NULL DEFAULT 'manual', source_ref VARCHAR(200) NOT NULL DEFAULT '', source_page INTEGER,
                source_excerpt TEXT NOT NULL DEFAULT '', status VARCHAR(20) NOT NULL DEFAULT 'pending',
                proposal_type VARCHAR(60) NOT NULL DEFAULT 'new_project_candidate', proposed_name VARCHAR(160),
                proposed_name_normalized VARCHAR(200), proposed_entity_type VARCHAR(30), proposed_parent_project_id INTEGER REFERENCES projects(id),
                proposed_payload_json TEXT NOT NULL DEFAULT '{}', source_p3_event_ids_json TEXT NOT NULL DEFAULT '[]',
                source_p3_fact_ids_json TEXT NOT NULL DEFAULT '[]', source_evidence_document_ids_json TEXT NOT NULL DEFAULT '[]',
                source_announcement_ids_json TEXT NOT NULL DEFAULT '[]', supporting_mentions_json TEXT NOT NULL DEFAULT '[]',
                supporting_announcement_count INTEGER NOT NULL DEFAULT 0, supporting_evidence_count INTEGER NOT NULL DEFAULT 0,
                supporting_event_count INTEGER NOT NULL DEFAULT 0, supporting_fact_count INTEGER NOT NULL DEFAULT 0,
                source_pages_json TEXT NOT NULL DEFAULT '[]', source_excerpts_json TEXT NOT NULL DEFAULT '[]', confidence FLOAT,
                created_by VARCHAR(30) NOT NULL DEFAULT 'manual', dedupe_key VARCHAR(255), reviewer VARCHAR(120), reviewed_by VARCHAR(120),
                reviewed_at DATETIME, review_note TEXT NOT NULL DEFAULT '', correction_json TEXT NOT NULL DEFAULT '{}',
                project_id INTEGER REFERENCES projects(id), asset_unit_id INTEGER REFERENCES asset_units(id),
                resulting_entity_type VARCHAR(30), resulting_entity_id INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
            old_columns = {row[1] for row in cursor.execute("PRAGMA table_info(p01_entity_proposals)")}
            new_columns = [row[1] for row in cursor.execute("PRAGMA table_info(p01_entity_proposals_new)")]
            common = [name for name in new_columns if name in old_columns]
            names = ", ".join(common)
            cursor.execute(f"INSERT INTO p01_entity_proposals_new ({names}) SELECT {names} FROM p01_entity_proposals")
            cursor.execute("DROP TABLE p01_entity_proposals")
            cursor.execute("ALTER TABLE p01_entity_proposals_new RENAME TO p01_entity_proposals")
            cursor.execute("CREATE INDEX ix_p01_entity_proposals_stock_id ON p01_entity_proposals(stock_id)")
            cursor.execute("CREATE INDEX ix_p01_entity_proposals_status ON p01_entity_proposals(status)")
            cursor.execute("CREATE INDEX ix_p01_entity_proposals_proposal_type ON p01_entity_proposals(proposal_type)")
            cursor.execute("CREATE INDEX ix_p01_entity_proposals_proposed_parent_project_id ON p01_entity_proposals(proposed_parent_project_id)")
            cursor.execute("CREATE UNIQUE INDEX uq_p01_pending_proposal_dedupe ON p01_entity_proposals(dedupe_key) WHERE status = 'pending'")
        raw.commit()
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        raw.close()


def _apply_lightweight_migrations() -> None:
    """Keep local SQLite databases compatible with small additive schema changes."""
    with engine.begin() as conn:
        migrate_stock_identity(conn)
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(score_snapshots)")}
        if "sentiment_score" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE score_snapshots ADD COLUMN sentiment_score FLOAT NOT NULL DEFAULT 50.0"
            )
        signal_columns = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(analytical_signals)")
        }
        if signal_columns and "narrative" not in signal_columns:
            conn.exec_driver_sql("ALTER TABLE analytical_signals ADD COLUMN narrative TEXT")
        from .models import HistoricalAnalysisSnapshot

        HistoricalAnalysisSnapshot.__table__.create(bind=conn, checkfirst=True)
        from .models import HistoricalAnalysisReturn

        HistoricalAnalysisReturn.__table__.create(bind=conn, checkfirst=True)
        from .models import (
            AnalyticalSignal,
            AssetUnit,
            AssetUnitIdentity,
            AssetUnitProposal,
            AttentionState,
            CommodityRelationship,
            EvidenceDocument,
            EntityMapping,
            EntityMappingChangeLog,
            EntityMention,
            InstrumentMapping,
            MarketDataPoint,
            BackfillRun,
            BackfillRunItem,
            PipelineRunItem,
            AnnouncementVersionRelation,
            FusionRecord,
            P3Fact,
            P3FactReview,
            P3InformationPoint,
            P3InformationPointFact,
            P3Statement,
            P3ParseRun,
            P3Event,
            P3EventClassificationReview,
            P3VersionRelation,
            P3VersionRelationChangeLog,
            P01EntityProposal,
            P01EntityProposalReview,
            P4Feature,
            Position,
            PositionEvent,
            Project,
            ProjectIdentity,
            ProjectRelationship,
            StrategyLearningCandidate,
            StockProject,
            TradeDecision,
            TradeReview,
        )

        for table in (
            Project,
            ProjectIdentity,
            ProjectRelationship,
            AssetUnit,
            AssetUnitIdentity,
            AssetUnitProposal,
            CommodityRelationship,
            StockProject,
            EvidenceDocument,
            EntityMention,
            EntityMapping,
            EntityMappingChangeLog,
            InstrumentMapping,
            MarketDataPoint,
            BackfillRun,
            BackfillRunItem,
            PipelineRunItem,
            AnnouncementVersionRelation,
            P3Fact,
            P3FactReview,
            P3InformationPoint,
            P3InformationPointFact,
            P3Statement,
            P3ParseRun,
            P3Event,
            P3EventClassificationReview,
            P3VersionRelation,
            P3VersionRelationChangeLog,
            P01EntityProposal,
            P01EntityProposalReview,
            P4Feature,
            AnalyticalSignal,
            FusionRecord,
            AttentionState,
            TradeDecision,
            Position,
            PositionEvent,
            TradeReview,
            StrategyLearningCandidate,
        ):
            table.__table__.create(bind=conn, checkfirst=True)
        mapping_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(entity_mappings)")}
        for name, definition in {
            "candidate_parent_project_id": "INTEGER",
            "proposal_id": "INTEGER",
            "candidate_payload_json": "TEXT NOT NULL DEFAULT '{}'",
        }.items():
            if name not in mapping_columns:
                conn.exec_driver_sql(f"ALTER TABLE entity_mappings ADD COLUMN {name} {definition}")
        proposal_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(p01_entity_proposals)")}
        for name, definition in {
            "proposal_type": "VARCHAR(60) NOT NULL DEFAULT 'new_project_candidate'",
            "proposed_name": "VARCHAR(160)", "proposed_name_normalized": "VARCHAR(200)",
            "proposed_entity_type": "VARCHAR(30)", "proposed_parent_project_id": "INTEGER",
            "proposed_payload_json": "TEXT NOT NULL DEFAULT '{}'", "source_p3_event_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "source_p3_fact_ids_json": "TEXT NOT NULL DEFAULT '[]'", "source_evidence_document_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "source_announcement_ids_json": "TEXT NOT NULL DEFAULT '[]'", "supporting_mentions_json": "TEXT NOT NULL DEFAULT '[]'",
            "supporting_announcement_count": "INTEGER NOT NULL DEFAULT 0", "supporting_evidence_count": "INTEGER NOT NULL DEFAULT 0",
            "supporting_event_count": "INTEGER NOT NULL DEFAULT 0", "supporting_fact_count": "INTEGER NOT NULL DEFAULT 0",
            "source_pages_json": "TEXT NOT NULL DEFAULT '[]'", "source_excerpts_json": "TEXT NOT NULL DEFAULT '[]'",
            "confidence": "FLOAT", "created_by": "VARCHAR(30) NOT NULL DEFAULT 'manual'", "dedupe_key": "VARCHAR(255)",
            "reviewed_by": "VARCHAR(120)", "resulting_entity_type": "VARCHAR(30)", "resulting_entity_id": "INTEGER",
            "updated_at": "DATETIME",
        }.items():
            if name not in proposal_columns:
                conn.exec_driver_sql(f"ALTER TABLE p01_entity_proposals ADD COLUMN {name} {definition}")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_entity_mappings_proposal_id ON entity_mappings(proposal_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_entity_mappings_candidate_parent_project_id ON entity_mappings(candidate_parent_project_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p01_entity_proposals_proposal_type ON p01_entity_proposals(proposal_type)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p01_entity_proposals_proposed_parent_project_id ON p01_entity_proposals(proposed_parent_project_id)")
        conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_p01_pending_proposal_dedupe ON p01_entity_proposals(dedupe_key) WHERE status = 'pending'")
        signal_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(signals)")}
        for name, definition in {
            "event_key": "VARCHAR(80)",
            "role": "VARCHAR(10) NOT NULL DEFAULT 'primary'",
        }.items():
            if name not in signal_columns:
                conn.exec_driver_sql(f"ALTER TABLE signals ADD COLUMN {name} {definition}")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_signals_event_key ON signals(event_key)")
        evidence_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(evidence_documents)")}
        evidence_additions = {
            "source_url": "TEXT NOT NULL DEFAULT ''",
            "local_original_path": "TEXT",
            "local_raw_text_path": "TEXT",
            "file_hash_sha256": "VARCHAR(64)",
            "file_size_bytes": "INTEGER",
            "content_type": "VARCHAR(120)",
            "downloaded_at": "DATETIME",
            "text_extracted_at": "DATETIME",
            "evidence_status": "VARCHAR(30) NOT NULL DEFAULT 'metadata_only'",
            "download_status": "VARCHAR(20) NOT NULL DEFAULT 'pending'",
            "text_status": "VARCHAR(20) NOT NULL DEFAULT 'pending'",
            "error_message": "TEXT",
            "retry_count": "INTEGER NOT NULL DEFAULT 0",
            "last_retry_at": "DATETIME",
            "duplicate_of_id": "INTEGER",
        }
        for name, definition in evidence_additions.items():
            if name not in evidence_columns:
                conn.exec_driver_sql(f"ALTER TABLE evidence_documents ADD COLUMN {name} {definition}")
        for name, definition in {"historical_baseline": "BOOLEAN NOT NULL DEFAULT 0", "review_status": "VARCHAR(30) NOT NULL DEFAULT 'pending_review'", "imported_at": "DATETIME"}.items():
            if name not in evidence_columns:
                conn.exec_driver_sql(f"ALTER TABLE evidence_documents ADD COLUMN {name} {definition}")
        pipeline_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(pipeline_runs)")}
        for name, definition in {
            "pipeline_type": "VARCHAR(40) NOT NULL DEFAULT 'daily'", "provider": "VARCHAR(80) NOT NULL DEFAULT 'internal'", "started_at": "DATETIME",
            "total_items": "INTEGER NOT NULL DEFAULT 0", "succeeded_items": "INTEGER NOT NULL DEFAULT 0", "skipped_items": "INTEGER NOT NULL DEFAULT 0", "failed_items": "INTEGER NOT NULL DEFAULT 0",
            "retry_of_run_id": "INTEGER", "configuration_snapshot_json": "TEXT NOT NULL DEFAULT '{}'", "error_summary": "TEXT",
        }.items():
            if name not in pipeline_columns:
                conn.exec_driver_sql(f"ALTER TABLE pipeline_runs ADD COLUMN {name} {definition}")
        announcement_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(announcements)")}
        if "evidence_document_id" not in announcement_columns:
            conn.exec_driver_sql("ALTER TABLE announcements ADD COLUMN evidence_document_id INTEGER")
        for name, definition in {
            "document_category": "VARCHAR(80) NOT NULL DEFAULT 'Other / Needs Review'",
            "official_header_type": "VARCHAR(120)",
            "official_subtype": "VARCHAR(120)",
            "standard_form": "VARCHAR(80)",
            "event_families_json": "TEXT NOT NULL DEFAULT '[]'",
            "event_labels_json": "TEXT NOT NULL DEFAULT '[]'",
            "revision_tags_json": "TEXT NOT NULL DEFAULT '[]'",
            "classification_source": "VARCHAR(40) NOT NULL DEFAULT 'title_routing'",
            "classification_version": "VARCHAR(40) NOT NULL DEFAULT 'p03_family_v1'",
        }.items():
            if name not in announcement_columns:
                conn.exec_driver_sql(f"ALTER TABLE announcements ADD COLUMN {name} {definition}")
        p3_event_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(p3_events)")}
        if p3_event_columns and "event_family" not in p3_event_columns:
            conn.exec_driver_sql("ALTER TABLE p3_events ADD COLUMN event_family VARCHAR(10) NOT NULL DEFAULT 'OTHER'")
        p3_event_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(p3_events)")}
        for name, definition in {
            "primary_family": "VARCHAR(10) NOT NULL DEFAULT 'OTHER'",
            "secondary_families_json": "TEXT NOT NULL DEFAULT '[]'",
            "classification_status": "VARCHAR(30) NOT NULL DEFAULT 'auto_classified'",
            "classification_source": "VARCHAR(40) NOT NULL DEFAULT 'summary'",
            "classification_confidence": "FLOAT",
            "revision_tags_json": "TEXT NOT NULL DEFAULT '[]'",
            "classification_reason": "TEXT NOT NULL DEFAULT ''",
            "reviewed_by": "VARCHAR(120)",
            "reviewed_at": "DATETIME",
            "review_note": "TEXT NOT NULL DEFAULT ''",
            "original_classification_json": "TEXT NOT NULL DEFAULT '{}'",
            "active_result": "BOOLEAN NOT NULL DEFAULT 1",
            "mapped_project_id": "INTEGER",
            "mapped_asset_unit_id": "INTEGER",
            "project_mapping_id": "INTEGER",
            "asset_unit_mapping_id": "INTEGER",
            "project_mapping_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
            "asset_unit_mapping_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
            "validity_status": "VARCHAR(40) NOT NULL DEFAULT 'current'",
            "validity_reason": "TEXT NOT NULL DEFAULT ''",
            "validity_updated_at": "DATETIME",
        }.items():
            if name not in p3_event_columns:
                conn.exec_driver_sql(f"ALTER TABLE p3_events ADD COLUMN {name} {definition}")
        if p3_event_columns and "primary_family" not in p3_event_columns:
            conn.exec_driver_sql("UPDATE p3_events SET primary_family = event_family WHERE primary_family = 'OTHER'")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p3_events_mapped_project_id ON p3_events (mapped_project_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p3_events_mapped_asset_unit_id ON p3_events (mapped_asset_unit_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p3_events_project_mapping_id ON p3_events (project_mapping_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p3_events_asset_unit_mapping_id ON p3_events (asset_unit_mapping_id)")
        for table_name in ("p3_facts", "p3_statements"):
            result_columns = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})")}
            for name, definition in {
                "p3_event_id": "INTEGER",
                "parse_run_id": "INTEGER",
                "asset_unit_id": "INTEGER",
            }.items():
                if name not in result_columns:
                    conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}")
        fact_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(p3_facts)")}
        for name, definition in {
            "announcement_id": "INTEGER",
            "fact_family": "VARCHAR(10) NOT NULL DEFAULT 'OTHER'",
            "value_raw": "TEXT NOT NULL DEFAULT ''",
            "value_numeric": "FLOAT",
            "value_text": "TEXT",
            "unit_raw": "VARCHAR(60)",
            "unit_normalized": "VARCHAR(80)",
            "currency_raw": "VARCHAR(20)",
            "currency_normalized": "VARCHAR(20)",
            "quantity_type": "VARCHAR(30) NOT NULL DEFAULT 'text'",
            "period_start": "DATE",
            "period_end": "DATE",
            "as_of_date": "DATE",
            "effective_date": "DATE",
            "status": "VARCHAR(30) NOT NULL DEFAULT 'reported'",
            "project_attribution_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
            "source_section": "VARCHAR(40) NOT NULL DEFAULT 'body'",
            "source_page_start": "INTEGER",
            "source_page_end": "INTEGER",
            "extractor_name": "VARCHAR(80) NOT NULL DEFAULT 'deterministic_p3_fact_extractor'",
            "extraction_confidence": "FLOAT",
            "review_status": "VARCHAR(30) NOT NULL DEFAULT 'proposed'",
            "reviewed_by": "VARCHAR(120)",
            "reviewed_at": "DATETIME",
            "review_note": "TEXT NOT NULL DEFAULT ''",
            "original_extraction_json": "TEXT NOT NULL DEFAULT '{}'",
            "active_result": "BOOLEAN NOT NULL DEFAULT 1",
            "superseded_by_id": "INTEGER",
            "information_point_group_id": "INTEGER",
            "information_point_type": "VARCHAR(60)",
            "parent_fact_id": "INTEGER",
            "display_order": "INTEGER",
            "updated_at": "DATETIME",
            "mapped_project_id": "INTEGER",
            "mapped_asset_unit_id": "INTEGER",
            "project_mapping_id": "INTEGER",
            "asset_unit_mapping_id": "INTEGER",
            "project_mapping_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
            "asset_unit_mapping_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
            "validity_status": "VARCHAR(40) NOT NULL DEFAULT 'current'",
            "validity_reason": "TEXT NOT NULL DEFAULT ''",
            "validity_updated_at": "DATETIME",
        }.items():
            if name not in fact_columns:
                conn.exec_driver_sql(f"ALTER TABLE p3_facts ADD COLUMN {name} {definition}")
        # Backfill compatibility fields without inventing normalized values.
        conn.exec_driver_sql("UPDATE p3_facts SET source_page_start = source_page WHERE source_page_start IS NULL")
        conn.exec_driver_sql("UPDATE p3_facts SET unit_raw = unit WHERE unit_raw IS NULL AND unit IS NOT NULL")
        conn.exec_driver_sql("UPDATE p3_facts SET extraction_confidence = confidence WHERE extraction_confidence IS NULL")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p3_facts_information_point_group_id ON p3_facts (information_point_group_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p3_facts_information_point_type ON p3_facts (information_point_type)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p3_facts_parent_fact_id ON p3_facts (parent_fact_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p3_facts_mapped_project_id ON p3_facts (mapped_project_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p3_facts_mapped_asset_unit_id ON p3_facts (mapped_asset_unit_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p3_facts_project_mapping_id ON p3_facts (project_mapping_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p3_facts_asset_unit_mapping_id ON p3_facts (asset_unit_mapping_id)")
        # Existing information-point links are retained and projected onto the
        # new convenience columns; no historical Fact or link row is rewritten.
        if {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(p3_information_point_facts)")}:
            conn.exec_driver_sql("""
                UPDATE p3_facts
                SET information_point_group_id = (
                        SELECT link.information_point_id FROM p3_information_point_facts link
                        WHERE link.p3_fact_id = p3_facts.id ORDER BY link.id DESC LIMIT 1
                    ),
                    information_point_type = (
                        SELECT point.point_type FROM p3_information_point_facts link
                        JOIN p3_information_points point ON point.id = link.information_point_id
                        WHERE link.p3_fact_id = p3_facts.id ORDER BY link.id DESC LIMIT 1
                    ),
                    display_order = (
                        SELECT link.display_order FROM p3_information_point_facts link
                        WHERE link.p3_fact_id = p3_facts.id ORDER BY link.id DESC LIMIT 1
                    )
                WHERE EXISTS (
                    SELECT 1 FROM p3_information_point_facts link WHERE link.p3_fact_id = p3_facts.id
                )
            """)
            conn.exec_driver_sql("""
                UPDATE p3_facts
                SET parent_fact_id = (
                    SELECT parent_link.p3_fact_id
                    FROM p3_information_point_facts own_link
                    JOIN p3_information_point_facts parent_link
                      ON parent_link.information_point_id = own_link.information_point_id
                     AND parent_link.role = 'primary'
                    WHERE own_link.p3_fact_id = p3_facts.id
                    ORDER BY parent_link.id LIMIT 1
                )
                WHERE information_point_group_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM p3_information_point_facts own_link
                    WHERE own_link.p3_fact_id = p3_facts.id AND own_link.role = 'primary'
                  )
            """)
        statement_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(p3_statements)")}
        for name, definition in {
            "announcement_id": "INTEGER",
            "source_excerpt": "TEXT NOT NULL DEFAULT ''",
            "review_status": "VARCHAR(30) NOT NULL DEFAULT 'proposed'",
            "validity_status": "VARCHAR(40) NOT NULL DEFAULT 'current'",
            "validity_reason": "TEXT NOT NULL DEFAULT ''",
            "validity_updated_at": "DATETIME",
        }.items():
            if name not in statement_columns:
                conn.exec_driver_sql(f"ALTER TABLE p3_statements ADD COLUMN {name} {definition}")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p3_events_validity_status ON p3_events(validity_status)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p3_facts_validity_status ON p3_facts(validity_status)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_p3_statements_validity_status ON p3_statements(validity_status)")
        asset_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(asset_units)")}
        if "metadata_json" not in asset_columns:
            conn.exec_driver_sql("ALTER TABLE asset_units ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}' ")
        commodity_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(commodity_relationships)")}
        if "effective_from" not in commodity_columns:
            conn.exec_driver_sql("ALTER TABLE commodity_relationships ADD COLUMN effective_from DATE")
        if "effective_to" not in commodity_columns:
            conn.exec_driver_sql("ALTER TABLE commodity_relationships ADD COLUMN effective_to DATE")
        relationship_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(project_relationships)")}
        if "source_page" not in relationship_columns:
            conn.exec_driver_sql("ALTER TABLE project_relationships ADD COLUMN source_page INTEGER")
        if "source_excerpt" not in relationship_columns:
            conn.exec_driver_sql("ALTER TABLE project_relationships ADD COLUMN source_excerpt TEXT NOT NULL DEFAULT ''")


def migrate_stock_identity(conn) -> None:
    """Additive, repeatable migration. Preserve stock IDs and every old column.

    Existing active flags initialize Pilot membership once; they remain separate
    fields afterwards. Missing listing/classification/history dates stay unknown.
    """
    from .models import StockIdentity
    from .services.stock_identity import normalize

    columns = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(stocks)")}
    membership_missing = "pilot_universe_member" not in columns
    additions = {
        "exchange": "VARCHAR(20) NOT NULL DEFAULT 'ASX'",
        "trading_currency": "VARCHAR(3) NOT NULL DEFAULT 'AUD'",
        "listing_status": "VARCHAR(20) NOT NULL DEFAULT 'Unknown'",
        "sector": "VARCHAR(120)",
        "business_type": "VARCHAR(120)",
        "pilot_universe_member": "BOOLEAN NOT NULL DEFAULT 1",
    }
    for name, definition in additions.items():
        if name not in columns:
            conn.exec_driver_sql(f"ALTER TABLE stocks ADD COLUMN {name} {definition}")
    if membership_missing and "active" in columns:
        conn.exec_driver_sql("UPDATE stocks SET pilot_universe_member = active")
    StockIdentity.__table__.create(bind=conn, checkfirst=True)
    existing = set(conn.exec_driver_sql(
        "SELECT stock_id, kind FROM stock_identities WHERE is_current = 1"
    ).fetchall())
    for stock in conn.exec_driver_sql("SELECT id, code, name, exchange FROM stocks").mappings():
        for kind, field in (("ticker", "code"), ("company_name", "name")):
            if (stock["id"], kind) not in existing:
                conn.execute(StockIdentity.__table__.insert().values(
                    stock_id=stock["id"], kind=kind, value=stock[field],
                    normalized_value=normalize(stock[field]),
                    exchange=stock["exchange"] if kind == "ticker" else None,
                    is_current=True, source="legacy_baseline",
                ))
