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
from ..models import PipelineRun, Stock
from .announcements import sync_announcements
from .backtest import fill_pending_returns
from .config_service import ensure_defaults, get_config
from .market_data import sync_all_instruments, sync_stock_prices
from .report import build_daily_report, push_daily_report
from .scoring_service import score_and_signal_stock

logger = logging.getLogger(__name__)
_pipeline_lock = Lock()


def run_daily_pipeline(trigger: str = "manual") -> dict:
    if not _pipeline_lock.acquire(blocking=False):
        logger.info("pipeline skipped for trigger=%s because another run is active", trigger)
        return {
            "skipped": True,
            "reason": "pipeline_already_running",
            "trigger": trigger,
        }
    try:
        return _run_daily_pipeline_unlocked(trigger)
    finally:
        _pipeline_lock.release()


def _run_daily_pipeline_unlocked(trigger: str) -> dict:
    started = time.time()
    with SessionLocal() as session:
        ensure_defaults(session)
        run = PipelineRun(trigger=trigger, status="running")
        session.add(run)
        session.commit()

        stats: dict = {
            "prices_added": 0,
            "instruments": {},
            "announcements_added": 0,
            "blocked_sources": [],
            "scored": 0,
            "signals_added": 0,
            "returns": {},
            "errors": [],
            "per_stock": {},
        }
        try:
            stocks = session.query(Stock).filter_by(active=True).order_by(Stock.code).all()
            thresholds = get_config(session, "signal_thresholds")
            weights = get_config(session, "weights")
            label_thresholds = get_config(session, "label_thresholds")
            commodity_map = get_config(session, "commodity_instruments")
            source = get_announcement_source(settings.announcement_source)
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
                try:
                    result = sync_announcements(
                        session, stock, source, analyzer, settings.announcement_fetch_count
                    )
                    stats["announcements_added"] += result["new"]
                except SourceBlockedError as exc:
                    # persistent block: stop hammering, degrade for the rest
                    logger.warning("announcement source blocked at %s: %s", stock.code, exc)
                    stats["blocked_sources"].append(stock.code)
                    source_blocked = True
                except Exception as exc:
                    logger.exception("announcement sync failed for %s", stock.code)
                    stats["errors"].append(f"announcements:{stock.code}:{exc}")
                    session.rollback()
                time.sleep(random.uniform(settings.request_delay_min, settings.request_delay_max))

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
