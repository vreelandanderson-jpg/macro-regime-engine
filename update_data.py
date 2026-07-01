"""Live-only command-line updater for Macro Regime Engine v7.2."""

from __future__ import annotations

import argparse

from collectors import fetch_all
from config import DATABASE_PATH
from database import init_db, record_run, upsert_observations


def _source_filter(args: argparse.Namespace) -> set[str] | None:
    if args.prices_only or args.market_only:
        return {"yfinance", "computed"}
    if args.econ_only or args.bls_only:
        return {"bls"}
    return None


def _module_filter(args: argparse.Namespace) -> set[str] | None:
    if args.ai_only:
        return {"AI"}
    if args.macro_only:
        return {"Macro"}
    if args.internal_only:
        return {"Internal"}
    if args.global_only:
        return {"Global"}
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Update live macro regime data feeds. No FRED/demo mode.")
    parser.add_argument("--db", default=DATABASE_PATH, help="SQLite database path")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent workers for price/market feeds")
    parser.add_argument("--prices-only", action="store_true", help="Update yfinance price/rate/AI feeds plus computed curve proxies")
    parser.add_argument("--market-only", action="store_true", help="Alias for --prices-only")
    parser.add_argument("--econ-only", action="store_true", help="Update BLS economic feeds only")
    parser.add_argument("--bls-only", action="store_true", help="Alias for --econ-only")
    parser.add_argument("--ai-only", action="store_true", help="Update only AI module series")
    parser.add_argument("--macro-only", action="store_true", help="Update only Macro module series")
    parser.add_argument("--internal-only", action="store_true", help="Update only Internal Market Engine series")
    parser.add_argument("--global-only", action="store_true", help="Update only Global Markets series")
    args = parser.parse_args()

    init_db(args.db)
    data, errors = fetch_all(
        max_workers=args.workers,
        include_sources=_source_filter(args),
        include_modules=_module_filter(args),
    )
    inserted = upsert_observations(args.db, data)

    status = "ok" if not errors else ("partial_live_saved" if inserted > 0 else "failed")
    message = f"Inserted/updated {inserted} observations. Errors: {len(errors)}"
    record_run(args.db, status, message + (" | " + " ; ".join(errors[:8]) if errors else ""))

    print(message)
    if errors:
        print("Live feed issues:")
        for err in errors:
            print(f"- {err}")
        if inserted > 0:
            print("\nPartial success: successful live feeds were saved. Re-run later or isolate with --prices-only / --econ-only / --internal-only / --global-only.")


if __name__ == "__main__":
    main()
