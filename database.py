"""SQLite storage layer for Macro Regime Engine."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    module TEXT NOT NULL DEFAULT 'Macro',
    date TEXT NOT NULL,
    close REAL,
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_observations_symbol_date
ON observations(symbol, date);

CREATE INDEX IF NOT EXISTS idx_observations_module_category
ON observations(module, category);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_time TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _ensure_columns(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(observations)").fetchall()}
    if "module" not in columns:
        conn.execute("ALTER TABLE observations ADD COLUMN module TEXT NOT NULL DEFAULT 'Macro'")


def init_db(db_path: str | Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _ensure_columns(conn)


def upsert_observations(db_path: str | Path, rows: pd.DataFrame) -> int:
    if rows.empty:
        return 0

    columns = ["symbol", "name", "source", "category", "module", "date", "close"]
    needed = set(columns)
    missing = needed - set(rows.columns)
    if missing == {"module"}:
        rows = rows.copy()
        rows["module"] = "Macro"
        missing = set()
    if missing:
        raise ValueError(f"Missing columns for database insert: {sorted(missing)}")

    clean = rows[columns].copy()
    clean["date"] = pd.to_datetime(clean["date"]).dt.strftime("%Y-%m-%d")
    clean["module"] = clean["module"].fillna("Macro")
    clean = clean.dropna(subset=["symbol", "date", "close"])

    records = list(clean.itertuples(index=False, name=None))
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _ensure_columns(conn)
        conn.executemany(
            """
            INSERT INTO observations(symbol, name, source, category, module, date, close)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, date) DO UPDATE SET
                name=excluded.name,
                source=excluded.source,
                category=excluded.category,
                module=excluded.module,
                close=excluded.close
            """,
            records,
        )
    return len(records)


def load_observations(db_path: str | Path) -> pd.DataFrame:
    init_db(db_path)
    with connect(db_path) as conn:
        df = pd.read_sql_query(
            """
            SELECT symbol, name, source, category, module, date, close
            FROM observations
            ORDER BY module, symbol, date
            """,
            conn,
            parse_dates=["date"],
        )
    return df


def record_run(db_path: str | Path, status: str, message: str) -> None:
    from datetime import datetime, timezone

    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO runs(run_time, status, message) VALUES (?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), status, message),
        )


def load_runs(db_path: str | Path, limit: int = 20) -> pd.DataFrame:
    init_db(db_path)
    with connect(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT run_time, status, message
            FROM runs
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(limit,),
            parse_dates=["run_time"],
        )
