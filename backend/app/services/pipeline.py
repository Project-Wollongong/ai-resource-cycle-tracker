"""Daily pipeline orchestration. Idempotent — any day can be safely rerun.

Steps: prices → commodities/benchmark → announcements (rate-limited) →
scores+snapshots → signals → forward-return fill → daily report → push.
Every per-stock step is isolated: one failing ticker degrades the run to
'partial' instead of killing it.
"""

import json
import logging
import random
import time
from datetime import datetime
from threading import Lock

from ..analysis.ai_stub import get_analyzer
from ..config import settings
from ..database import SessionLocal
from ..datasources.base import SourceBlockedError, get_announcement_source
from ..models import PipelineRun, PipelineRunItem, Stock
from .announcements import sync_announcements
from .backtest import fill_pending_returns
from .config_service import ensure_defaults, get_all_config, get_config
from .market_data import sync_all_instruments, sync_stock_prices
from .report import build_daily_report, push_daily_report
from .p4_feature_service import compute_all_features
from .scoring_service import score_and_signal_stock

logger = logging.getLogger(__name__)
_pipeline_lock = Lock()


def run_daily_pipeline(trigger: str = "manual", retry_of_run_id: int | None = None, only_failed_run_id: int | None = None, only_stock_id: int | None = None) -> dict:
    if not _pipeline_lock.acquire(blocking=False):
        logger.info("pipeline skipped for trigger=%s because another run is active", trigger)
        return {
            "skipped": True,
            "reason": "pipeline_already_running",
            "trigger": trigger,
        }
    try:
        return _run_daily_pipeline_unlocked(trigger, retry_of_run_id=retry_of_run_id, only_failed_run_id=only_failed_run_id, only_stock_id=only_stock_id)
    finally:
        _pipeline_lock.release()


def _run_daily_pipeline_unlocked(trigger: str, retry_of_run_id: int | None = None, only_failed_run_id: int | None = None, only_stock_id: int | None = None) -> dict:
    started = time.time()
    with SessionLocal() as session:
        ensure_defaults(session)
        run = PipelineRun(trigger=trigger, pipeline_type="daily", provider=settings.announcement_source, status="running", retry_of_run_id=retry_of_run_id, started_at=datetime.utcnow(), configuration_snapshot_json=json.dumps(get_all_config(session), ensure_ascii=False, default=str))
        session.add(run)
        session.commit()

        stats: dict = {
            "prices_added": 0,
            "instruments": {},
            "announcements_added": 0,
            "evidence_downloaded": 0,
            "evidence_download_failed": 0,
            "evidence_text_extracted": 0,
            "evidence_text_failed": 0,
            "evidence_skipped": 0,
            "p3_parsed": 0,
            "p3_review_needed": 0,
            "p3_failed": 0,
            "p3_skipped": 0,
            "p4_features_computed": 0,
            "p4_features_skipped": 0,
            "blocked_sources": [],
            "scored": 0,
            "signals_added": 0,
            "returns": {},
            "errors": [],
            "per_stock": {},
        }
        try:
            stocks_query = session.query(Stock).filter_by(active=True)
            if only_stock_id is not None:
                stocks_query = stocks_query.filter(Stock.id == only_stock_id)
            if only_failed_run_id is not None:
                failed_stock_ids = [row[0] for row in session.query(PipelineRunItem.stock_id).filter_by(run_id=only_failed_run_id, status="failed").all() if row[0] is not None]
                stocks_query = stocks_query.filter(Stock.id.in_(failed_stock_ids)) if failed_stock_ids else stocks_query.filter(False)
            stocks = stocks_query.order_by(Stock.code).all()
            run.total_items = len(stocks)
            thresholds = get_config(session, "signal_thresholds")
            weights = get_config(session, "weights")
            label_thresholds = get_config(session, "label_thresholds")
            commodity_map = get_config(session, "commodity_instruments")
            ingestion = get_config(session, "ingestion")
            announcement_config = ingestion.get("announcements", {}) if isinstance(ingestion, dict) else {}
            source_name = announcement_config.get("provider") or settings.announcement_source
            source = get_announcement_source(source_name)
            analyzer = get_analyzer(settings.ai_analyzer)

            # 1) prices
            for stock in stocks:
                try:
                    added = sync_stock_prices(session, stock)
                    stats["prices_added"] += added
                except Exception as exc:
                    logger.exception("price sync failed for %s", stock.code)
                    stats["errors"].append(f"prices:{stock.code}:{exc}")
                    session.rollback()

            # 2) commodity proxies + benchmark
            stats["instruments"] = sync_all_instruments(session)

            # 3) announcements — polite per-company rate limiting
            source_blocked = False
            for stock in stocks:
                if source_blocked:
                    break
                item = PipelineRunItem(run_id=run.id, stock_id=stock.id, provider=source_name, item_type="announcements", status="running", started_at=datetime.utcnow())
                session.add(item)
                session.flush()
                try:
                    result = sync_announcements(
                        session, stock, source, analyzer, int(announcement_config.get("max_items", settings.announcement_fetch_count)),
                        include_evidence_stats=True,
                        download_evidence=bool(announcement_config.get("download_pdf", True)),
                        extract_evidence=bool(announcement_config.get("extract_text", True)),
                        parse_p3=bool(announcement_config.get("parse_p3", True)),
                        parser_version=str(announcement_config.get("parser_version") or "p3_reported_fact_v7_version_relations"),
                    )
                    stats["announcements_added"] += result["new"]
                    stats["evidence_downloaded"] += result.get("evidence_downloaded", 0)
                    stats["evidence_download_failed"] += result.get("evidence_failed", 0)
                    stats["evidence_text_extracted"] += result.get("text_extracted", 0)
                    stats["evidence_text_failed"] += result.get("text_failed", 0)
                    stats["p3_parsed"] += result.get("p3_parsed", 0)
                    stats["p3_review_needed"] += result.get("p3_review_needed", 0)
                    stats["p3_failed"] += result.get("p3_failed", 0)
                    stats["p3_skipped"] += result.get("p3_skipped", 0)
                    item.status = "success" if result.get("new", 0) else "skipped"
                    item.metadata_json = json.dumps(result, ensure_ascii=False, default=str)
                except SourceBlockedError as exc:
                    # persistent block: stop hammering, degrade for the rest
                    logger.warning("announcement source blocked at %s: %s", stock.code, exc)
                    stats["blocked_sources"].append(stock.code)
                    source_blocked = True
                    item.status = "failed"
                    item.error_message = str(exc)
                except Exception as exc:
                    logger.exception("announcement sync failed for %s", stock.code)
                    stats["errors"].append(f"announcements:{stock.code}:{exc}")
                    session.rollback()
                    item = PipelineRunItem(run_id=run.id, stock_id=stock.id, provider=settings.announcement_source, item_type="announcements", status="failed", error_message=str(exc), finished_at=datetime.utcnow())
                    session.add(item)
                item.finished_at = datetime.utcnow()
                session.flush()
                time.sleep(random.uniform(settings.request_delay_min, settings.request_delay_max))

            # 3b) P04 derived features — runs after P03 facts land, before
            # scoring, so anything consuming features sees the current quarter
            try:
                p4 = compute_all_features(session, [stock.id for stock in stocks])
                stats["p4_features_computed"] = p4["computed"]
                stats["p4_features_skipped"] = p4["skipped"]
            except Exception as exc:
                logger.exception("P04 feature computation failed")
                stats["errors"].append(f"p4:{exc}")
                session.rollback()

            # 4+5) scores, snapshots, signals
            for stock in stocks:
                try:
                    result = score_and_signal_stock(
                        session, stock, thresholds, weights, label_thresholds, commodity_map
                    )
                    stats["per_stock"][stock.code] = result
                    if "cycle_score" in result:
                        stats["scored"] += 1
                    stats["signals_added"] += result.get("signals", 0)
                except Exception as exc:
                    logger.exception("scoring failed for %s", stock.code)
                    stats["errors"].append(f"score:{stock.code}:{exc}")
                    session.rollback()

            # 6) fill forward returns
            stats["returns"] = fill_pending_returns(session)

            # 7) report + 8) push
            report = build_daily_report(session, stats)
            stats["report_date"] = report.report_date.isoformat()
            stats["push"] = push_daily_report(session, report)

            run.status = (
                "partial" if stats["errors"] or stats["blocked_sources"] else "success"
            )
            item_counts = {status: session.query(PipelineRunItem).filter_by(run_id=run.id, status=status).count() for status in ("success", "skipped", "failed")}
            run.succeeded_items = item_counts["success"]
            run.skipped_items = item_counts["skipped"]
            run.failed_items = item_counts["failed"]
            run.error_summary = "; ".join((stats["errors"] + [f"blocked:{x}" for x in stats["blocked_sources"]])[:10]) or None
        except Exception as exc:
            logger.exception("pipeline run failed")
            stats["errors"].append(f"fatal:{exc}")
            run.status = "failed"
        finally:
            stats["duration_s"] = round(time.time() - started, 1)
            run.stats_json = json.dumps(stats, ensure_ascii=False, default=str)
            run.finished_at = datetime.utcnow()
            session.commit()
        return stats
