"""Import locally downloaded historical ASX PDFs and recompute their features."""

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Stock  # noqa: E402
from app.services.historical_evidence_import import import_historical_evidence, validate_historical_pdf  # noqa: E402
from app.services.evidence_text_extractor import extract_pdf_text  # noqa: E402
from app.services.p3_parse_service import parse_evidence  # noqa: E402
from app.services.p4_feature_service import compute_all_features  # noqa: E402


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
FILENAME = re.compile(r"^(?P<code>[A-Za-z0-9]{1,10})_(?P<date>\d{4}-\d{2}-\d{2})_(?P<kind>[^_]+(?:_[^_]+)*)\.pdf$", re.IGNORECASE)


def parse_filename(path: Path) -> tuple[str, datetime, str]:
    match = FILENAME.match(path.name)
    if match is None:
        raise ValueError("expected CODE_YYYY-MM-DD_TYPE.pdf")
    try:
        source_date = datetime.strptime(match.group("date"), "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("filename date is not a real calendar date") from exc
    return match.group("code").upper(), source_date, match.group("kind")


def _result(path: Path, status: str, reason: str = "", **extra) -> dict:
    return {"file": path.name, "status": status, "reason": reason, **extra}


# P03 routes a document by its headline: an Appendix 5B is only scanned past the
# summary section when the classifier recognises the standard form, and it
# recognises it from the wording ASX itself uses. A descriptive title such as
# "Historical 5B report 2024-12-31" classifies as nothing, so section 8 — the
# funding-runway block, which sits on page 30-odd of a combined filing — is
# never reached and the import silently yields no financial facts.
_ASX_TITLES = {
    "5B": "Quarterly Activities/Appendix 5B Cash Flow Report",
    "4C": "Quarterly Cash Flow Report Appendix 4C",
}


def _document_title(kind: str, source_date) -> str:
    """The ASX headline for this document kind, suffixed with its quarter."""
    base = _ASX_TITLES.get(kind.upper())
    quarter = source_date.date() if hasattr(source_date, "date") else source_date
    if base is None:
        return f"Historical {kind} report {quarter}"
    return f"{base} - {quarter}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", type=Path, default=ROOT / "data" / "inbox")
    parser.add_argument("--dry-run", action="store_true", help="report planned imports without writing data")
    parser.add_argument("--stock", help="only import one ASX code")
    args = parser.parse_args()
    inbox = args.inbox.expanduser().resolve()
    target = args.stock.upper() if args.stock else None
    files = sorted(inbox.glob("*.pdf")) if inbox.is_dir() else []
    results: list[dict] = []
    touched_stock_ids: set[int] = set()

    if not inbox.is_dir():
        print(json.dumps({"error": f"inbox does not exist: {inbox}"}, ensure_ascii=False))
        raise SystemExit(2)
    if not args.dry_run:
        init_db()

    with SessionLocal() as session:
        stocks = {stock.code: stock for stock in session.query(Stock).all()}
        for path in files:
            try:
                code, source_date, kind = parse_filename(path)
                if target and code != target:
                    results.append(_result(path, "skipped", "filtered by --stock")); continue
                stock = stocks.get(code)
                if stock is None:
                    results.append(_result(path, "skipped", f"stock code {code} is not in the watchlist")); continue
                if args.dry_run:
                    results.append(_result(path, "planned", f"{code} {source_date.date()} {kind}")); continue
                validate_historical_pdf(path)
                # Validate before creating any evidence row or storage directory:
                # damaged and image-only PDFs are skipped without side effects.
                extract_pdf_text(path)
                evidence, created = import_historical_evidence(
                    session, stock=stock, local_pdf_path=path,
                    title=_document_title(kind, source_date), source_date=source_date,
                )
                if not created:
                    results.append(_result(path, "skipped", "duplicate file hash", evidence_id=evidence.id)); continue
                run = parse_evidence(session, evidence)
                session.commit()
                touched_stock_ids.add(stock.id)
                results.append(_result(path, "success", parse_status=run.status, evidence_id=evidence.id))
            except Exception as exc:
                session.rollback()
                results.append(_result(path, "skipped", str(exc)))

        features = compute_all_features(session, sorted(touched_stock_ids)) if touched_stock_ids and not args.dry_run else None
    print(json.dumps({"inbox": str(inbox), "dry_run": args.dry_run, "results": results, "features": features}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
