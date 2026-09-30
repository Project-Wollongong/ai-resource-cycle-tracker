"""Run the read-only P01/P02/P03 consistency audit against data/tracker.db."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.services.p3_database_consistency_audit import audit_database_consistency  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print the complete JSON payload")
    args = parser.parse_args()
    with SessionLocal() as session:
        result = audit_database_consistency(session)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        summary = result["summary"]
        print(f"P03 database consistency: {result['status']} ({summary['passed']} pass, {summary['warnings']} warning, {summary['failed']} fail)")
        print(f"Database: {result['database']['runtime_path']}")
        print("Inventory: " + ", ".join(f"{key}={value}" for key, value in result["inventory"].items()))
        for check in result["checks"]:
            if check["status"] != "pass":
                print(f"[{check['status'].upper()}] {check['code']}: {check['description']} - {json.dumps(check['evidence'], ensure_ascii=False)}")
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
