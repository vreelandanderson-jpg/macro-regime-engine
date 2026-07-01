"""Background live-price updater for Macro Regime Engine v7.3.

Runs prices-only updates on a loop so the dashboard does not turn into a full-page
loading state while data is being refreshed.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--db", default="macro_engine.sqlite")
    args = parser.parse_args()

    interval = max(10, int(args.interval))
    db_path = str(Path(args.db))
    print(f"[{datetime.now().isoformat(timespec='seconds')}] Background updater started. interval={interval}s db={db_path}", flush=True)

    while True:
        started = datetime.now().isoformat(timespec="seconds")
        cmd = [sys.executable, "update_data.py", "--prices-only", "--db", db_path]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=600)
            status = "ok" if proc.returncode == 0 else f"error:{proc.returncode}"
            output = (proc.stdout or proc.stderr or "").strip().replace("\n", " | ")[:500]
            print(f"[{started}] {status} {output}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[{started}] exception {exc}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
