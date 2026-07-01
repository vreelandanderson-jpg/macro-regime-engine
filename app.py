"""Macro Regime Engine v8 action console dashboard."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from config import DATABASE_PATH, SERIES
from database import init_db, load_observations, load_runs
from playbook import (
    auto_event_calendar_df,
    cause_effect_df,
    checklist_df,
    diagnostics_for_categories,
    event_watch_df,
    geopolitical_df,
    scenario_df,
)
from scoring import (
    compute_ai_regime,
    compute_global_regime,
    compute_internal_regime,
    compute_macro_regime,
    generate_ai_alerts,
    generate_alerts,
    generate_global_alerts,
    generate_internal_alerts,
)

APP_VERSION = "v8"
DB_PATH = Path(DATABASE_PATH)
LOCAL_TZ = ZoneInfo("America/Toronto")
ET_TZ = ZoneInfo("America/New_York")

st.set_page_config(page_title=f"Macro Regime Engine {APP_VERSION}", layout="wide", initial_sidebar_state="expanded")


# -----------------------------------------------------------------------------
# Cached data
# -----------------------------------------------------------------------------
@st.cache_data(ttl=10)
def cached_load_data(db_path: str) -> pd.DataFrame:
    return load_observations(db_path)


@st.cache_data(ttl=1800)
def cached_auto_events() -> pd.DataFrame:
    return auto_event_calendar_df(months_ahead=6, include_live_sources=True)


# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------
def _run_command(command: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=600)
        ok = proc.returncode == 0
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        cached_load_data.clear()
        cached_auto_events.clear()
        return ok, output.strip()
    except Exception as exc:  # noqa: BLE001 - this needs to show in the dashboard
        return False, str(exc)


def run_update() -> tuple[bool, str]:
    return _run_command([sys.executable, "update_data.py", "--db", str(DB_PATH)])


def run_market_update() -> tuple[bool, str]:
    return _run_command([sys.executable, "update_data.py", "--db", str(DB_PATH), "--prices-only"])


def run_econ_update() -> tuple[bool, str]:
    return _run_command([sys.executable, "update_data.py", "--db", str(DB_PATH), "--econ-only"])


def run_internal_update() -> tuple[bool, str]:
    return _run_command([sys.executable, "update_data.py", "--db", str(DB_PATH), "--internal-only"])


def run_global_update() -> tuple[bool, str]:
    return _run_command([sys.executable, "update_data.py", "--db", str(DB_PATH), "--global-only"])


def update_events() -> tuple[bool, str]:
    return _run_command([sys.executable, "update_events.py"])


PID_PATH = Path("live_updater.pid")
LOG_PATH = Path("live_updater.log")


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            proc = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, check=False, timeout=8)
            return str(pid) in (proc.stdout or "")
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def background_updater_status() -> tuple[bool, str]:
    if not PID_PATH.exists():
        return False, "OFF"
    try:
        pid = int(PID_PATH.read_text().strip())
    except Exception:
        return False, "OFF"
    return (_pid_is_running(pid), f"PID {pid}")


def start_background_updater(interval_seconds: int = 15) -> tuple[bool, str]:
    running, detail = background_updater_status()
    if running:
        return True, f"Already running ({detail})."
    cmd = [sys.executable, "live_updater.py", "--interval", str(interval_seconds), "--db", str(DB_PATH)]
    with LOG_PATH.open("a", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    PID_PATH.write_text(str(proc.pid), encoding="utf-8")
    return True, f"Background updater started. PID {proc.pid}."


def stop_background_updater() -> tuple[bool, str]:
    if not PID_PATH.exists():
        return True, "Background updater already stopped."
    try:
        pid = int(PID_PATH.read_text().strip())
    except Exception:
        PID_PATH.unlink(missing_ok=True)
        return True, "Background updater stopped."
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True, check=False, timeout=10)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    PID_PATH.unlink(missing_ok=True)
    cached_load_data.clear()
    return True, "Background updater stopped."


# -----------------------------------------------------------------------------
# Formatting helpers
# -----------------------------------------------------------------------------
def local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def fmt_time(dt: datetime | pd.Timestamp | None) -> str:
    if dt is None or pd.isna(dt):
        return "Unknown"
    if isinstance(dt, pd.Timestamp):
        dt = dt.to_pydatetime()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    else:
        dt = dt.astimezone(LOCAL_TZ)
    return dt.strftime("%-I:%M %p") if sys.platform != "win32" else dt.strftime("%#I:%M %p")


def fmt_datetime(dt: datetime | pd.Timestamp | None) -> str:
    if dt is None or pd.isna(dt):
        return "Unknown"
    if isinstance(dt, pd.Timestamp):
        dt = dt.to_pydatetime()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    else:
        dt = dt.astimezone(LOCAL_TZ)
    day_fmt = "%a, %b %-d, %Y" if sys.platform != "win32" else "%a, %b %#d, %Y"
    return f"{dt.strftime(day_fmt)} — {fmt_time(dt)}"


def fmt_date(dt: datetime | pd.Timestamp | str | None) -> str:
    if dt is None or pd.isna(dt):
        return "Unknown"
    dt = pd.to_datetime(dt, errors="coerce")
    if pd.isna(dt):
        return "Unknown"
    day_fmt = "%a, %b %-d, %Y" if sys.platform != "win32" else "%a, %b %#d, %Y"
    return dt.strftime(day_fmt)


def safe_num(value: object, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def score_class(score: float) -> str:
    if score >= 20:
        return "good"
    if score <= -20:
        return "bad"
    return "warn"


def score_arrow(score: float) -> str:
    if score >= 20:
        return "↗"
    if score <= -20:
        return "↘"
    return "→"


def short_score(score: float) -> str:
    return f"{score:.0f} / 100"


def parse_last_run_message(message: str) -> tuple[int | None, int | None]:
    inserted = None
    errors = None
    m = re.search(r"Inserted/updated\s+(\d+)", message or "")
    if m:
        inserted = int(m.group(1))
    e = re.search(r"Errors:\s*(\d+)", message or "")
    if e:
        errors = int(e.group(1))
    return inserted, errors


def event_local_dt(row: pd.Series) -> datetime | None:
    event_date = pd.to_datetime(row.get("date"), errors="coerce")
    if pd.isna(event_date):
        return None
    time_et = str(row.get("time_et", "")).strip()
    if not re.match(r"^\d{1,2}:\d{2}$", time_et):
        return None
    hour, minute = [int(x) for x in time_et.split(":")]
    return datetime.combine(event_date.date(), time(hour, minute), ET_TZ).astimezone(LOCAL_TZ)


def add_event_display(calendar: pd.DataFrame) -> pd.DataFrame:
    if calendar.empty:
        return calendar.copy()
    out = calendar.copy()
    today = pd.Timestamp.today().normalize()
    out["event_date"] = pd.to_datetime(out["date"], errors="coerce")
    out["days_away"] = (out["event_date"] - today).dt.days
    local_text = []
    countdown = []
    for _, row in out.iterrows():
        dt = event_local_dt(row)
        if dt is None:
            local_text.append(f"{fmt_date(row.get('date'))} — {row.get('time_et', 'Time TBA')}")
        else:
            local_text.append(fmt_datetime(dt))
        d = row.get("days_away")
        if pd.isna(d):
            countdown.append("Unknown")
        elif int(d) == 0:
            countdown.append("Today")
        elif int(d) == 1:
            countdown.append("Tomorrow")
        elif int(d) > 1:
            countdown.append(f"{int(d)} days")
        else:
            countdown.append("Passed")
    out["local_time"] = local_text
    out["countdown"] = countdown
    return out


def _format_view(table: pd.DataFrame) -> pd.DataFrame:
    view = table.copy()
    if view.empty:
        return view
    view["latest_date"] = pd.to_datetime(view["latest_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for col in ["latest_close", "change_pct", "score"]:
        view[col] = pd.to_numeric(view[col], errors="coerce").round(2)
    return view


def find_row(table: pd.DataFrame, name: str) -> pd.Series | None:
    if table.empty:
        return None
    row = table[table["name"].eq(name)]
    if row.empty:
        return None
    return row.iloc[0]


def find_symbol_row(table: pd.DataFrame, symbol: str) -> pd.Series | None:
    if table.empty:
        return None
    row = table[table["symbol"].eq(symbol)]
    if row.empty:
        return None
    return row.iloc[0]


def latest_update_text(runs: pd.DataFrame) -> str:
    if runs.empty:
        return "No update run yet"
    dt = runs.iloc[0].get("run_time")
    return fmt_datetime(dt)


def latest_run_dt(runs: pd.DataFrame) -> datetime | None:
    if runs.empty:
        return None
    dt = pd.to_datetime(runs.iloc[0].get("run_time"), errors="coerce")
    if pd.isna(dt):
        return None
    py_dt = dt.to_pydatetime()
    if py_dt.tzinfo is None:
        py_dt = py_dt.replace(tzinfo=LOCAL_TZ)
    else:
        py_dt = py_dt.astimezone(LOCAL_TZ)
    return py_dt


def seconds_since_last_run(runs: pd.DataFrame) -> float | None:
    dt = latest_run_dt(runs)
    if dt is None:
        return None
    return max(0.0, (local_now() - dt).total_seconds())


def human_age(seconds: float | None) -> str:
    if seconds is None:
        return "never"
    if seconds < 60:
        return f"{int(seconds)} sec ago"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    return f"{int(seconds // 3600)} hr ago"


# -----------------------------------------------------------------------------
# CSS + cards
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
    :root {
        --bg: #07111c;
        --panel: rgba(17, 29, 44, 0.92);
        --panel2: rgba(10, 22, 34, 0.94);
        --border: rgba(93, 124, 151, 0.28);
        --text: #e7eef7;
        --muted: #8ea4b8;
        --good: #29d66f;
        --bad: #ff4b45;
        --warn: #ffc83d;
        --info: #4aa3ff;
        --purple: #a770ff;
        --orange: #ff9c38;
    }
    .stApp {
        background: radial-gradient(circle at 10% 5%, rgba(30, 90, 160, 0.22), transparent 28%),
                    radial-gradient(circle at 90% 20%, rgba(93, 42, 150, 0.18), transparent 22%),
                    linear-gradient(180deg, #060d16 0%, #08121f 55%, #050a11 100%);
        color: var(--text);
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(9,19,32,0.98), rgba(4,10,17,0.98));
        border-right: 1px solid var(--border);
    }
    [data-testid="stSidebar"] * { color: var(--text); }
    .block-container { padding-top: .65rem; padding-bottom: .9rem; max-width: 1760px; }
    h1, h2, h3 { color: var(--text); letter-spacing: -0.02em; }
    .cmd-header {
        display:flex; align-items:center; gap:10px; padding: 0 0 8px 0;
    }
    .brand-orb {
        width:34px; height:34px; border-radius:11px;
        background: linear-gradient(135deg, #1d7eff, #7928ca 52%, #00f0a8);
        box-shadow: 0 0 30px rgba(74,163,255,0.35);
    }
    .brand-title { font-size: 1.05rem; font-weight: 800; line-height: 1.05; white-space:nowrap; }
    .brand-sub { color: var(--muted); font-size: .68rem; text-transform: uppercase; letter-spacing: .08em; }
    .top-time { text-align:right; color:var(--text); font-size:1.0rem; font-weight:800; }
    .top-time small { color:var(--muted); font-size:.65rem; font-weight:400; display:block; }
    .card {
        background: linear-gradient(180deg, rgba(20,34,50,0.96), rgba(10,20,32,0.96));
        border: 1px solid var(--border);
        border-radius: 13px;
        padding: 10px 11px;
        box-shadow: 0 10px 24px rgba(0,0,0,0.22);
        min-height: 92px;
        overflow:hidden;
    }
    .mini-card {
        background: rgba(10, 22, 34, 0.92);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 9px 10px;
        min-height: 74px;
    }
    .card-title { color:#d7e4ef; font-size:.66rem; font-weight:800; text-transform: uppercase; letter-spacing:.04em; margin-bottom:6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .card-value { font-size:.98rem; font-weight:900; margin:2px 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; word-break:keep-all; }
    .card-sub { color:var(--muted); font-size:.72rem; margin-top:3px; line-height:1.25; }
    .big-num { font-size:1.55rem; font-weight:900; line-height:1; }
    .good { color: var(--good); }
    .bad { color: var(--bad); }
    .warn { color: var(--warn); }
    .info { color: var(--info); }
    .purple { color: var(--purple); }
    .orange { color: var(--orange); }
    .badge { display:inline-block; border-radius:7px; padding:2px 6px; font-size:.58rem; font-weight:800; text-transform:uppercase; }
    .badge.good { background:rgba(41,214,111,.13); color:var(--good); border:1px solid rgba(41,214,111,.25); }
    .badge.bad { background:rgba(255,75,69,.13); color:var(--bad); border:1px solid rgba(255,75,69,.25); }
    .badge.warn { background:rgba(255,200,61,.13); color:var(--warn); border:1px solid rgba(255,200,61,.25); }
    .badge.info { background:rgba(74,163,255,.13); color:var(--info); border:1px solid rgba(74,163,255,.25); }
    .line-item { display:flex; gap:8px; align-items:flex-start; padding:6px 0; border-bottom:1px solid rgba(93,124,151,0.12); font-size:.78rem; line-height:1.32; }
    .line-item:last-child { border-bottom:0; }
    .alert-time { color:#ff4b45; font-size:.68rem; min-width:48px; }
    .muted { color:var(--muted); }
    .footer-bar { color: var(--muted); font-size:.70rem; border-top:1px solid var(--border); margin-top:14px; padding-top:8px; }
    div[data-testid="stMetric"] {
        background: rgba(10, 22, 34, 0.75);
        border: 1px solid rgba(93,124,151,0.22);
        border-radius: 12px;
        padding: 12px;
    }
    div[data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: 12px; overflow:hidden; }
    .stTextInput input, .stSelectbox [data-baseweb="select"] {
        background-color: rgba(10,22,34,.96) !important;
        border-color: rgba(93,124,151,.35) !important;
        color: var(--text) !important;
    }
    .stButton>button { border-radius: 10px; border:1px solid rgba(93,124,151,.35); background:rgba(12,28,44,.92); }

    /* v7.2 compact fixed command shell */
    .block-container { padding-top: .15rem !important; max-width: 1540px !important; }
    section.main div[data-testid="stHorizontalBlock"]:has(input[aria-label="Search anything"]) {
        position: sticky !important;
        top: 0 !important;
        z-index: 99999 !important;
        padding: 7px 8px 8px 8px !important;
        margin: -6px 0 10px 0 !important;
        background: linear-gradient(90deg, rgba(4,11,19,.98), rgba(8,18,31,.96), rgba(22,18,46,.94));
        border: 1px solid rgba(93,124,151,.25);
        border-top: 0;
        border-radius: 0 0 14px 14px;
        backdrop-filter: blur(14px);
        box-shadow: 0 12px 30px rgba(0,0,0,.34);
    }
    div[data-testid="stTextInput"] input[aria-label="Search anything"] {
        min-height: 36px !important;
        font-size: .82rem !important;
        border-radius: 12px !important;
    }
    [data-testid="stSidebar"] {
        min-width: 238px !important;
        max-width: 238px !important;
    }
    [data-testid="stSidebar"] .stRadio label { font-size: .82rem !important; }
    [data-testid="stSidebar"] .cmd-header { transform: scale(.88); transform-origin:left center; }
    .brand-title { font-size: .86rem !important; }
    .brand-sub { font-size: .58rem !important; }
    .brand-orb { width: 28px !important; height: 28px !important; border-radius: 9px !important; }
    .card { min-height: 78px !important; padding: 8px 9px !important; border-radius: 11px !important; }
    .mini-card { min-height: 64px !important; padding: 7px 8px !important; }
    .card-title { font-size: .58rem !important; margin-bottom: 4px !important; letter-spacing:.035em !important; }
    .card-value { font-size: .86rem !important; line-height: 1.08 !important; white-space: nowrap !important; word-break: keep-all !important; overflow:hidden !important; text-overflow:ellipsis !important; }
    .card-sub { font-size: .65rem !important; line-height: 1.18 !important; }
    .line-item { font-size:.68rem !important; padding:4px 0 !important; line-height:1.22 !important; }
    .big-num { font-size: 1.15rem !important; }
    .top-time { font-size:.82rem !important; }
    .top-time small { font-size:.56rem !important; }
    .badge { font-size:.50rem !important; padding: 1px 5px !important; }
    h1 { font-size: 1.35rem !important; }
    h2 { font-size: 1.05rem !important; }
    h3 { font-size: .95rem !important; }
    .stButton>button { min-height: 32px !important; padding: 4px 8px !important; font-size: .72rem !important; }
    div[data-testid="stDataFrame"] { font-size:.72rem !important; }
    .search-section-title { font-weight:900; font-size:.88rem; margin:10px 0 5px 0; color:#e7eef7; }
    .relation-chip { display:inline-block; margin:2px 4px 2px 0; padding:2px 7px; border-radius:999px; background:rgba(74,163,255,.10); border:1px solid rgba(74,163,255,.25); color:#dbeafe; font-size:.65rem; }

    /* v7.3: no hidden fixed overlay; search sits in normal visible flow */
    section.main div[data-testid="stHorizontalBlock"]:has(input[aria-label="Search anything"]) {
        position: relative !important;
        top: auto !important;
        z-index: 1 !important;
        padding: 0 !important;
        margin: 0 0 8px 0 !important;
        background: transparent !important;
        border: 0 !important;
        border-radius: 0 !important;
        backdrop-filter: none !important;
        box-shadow: none !important;
    }
    .search-shell {
        background: linear-gradient(90deg, rgba(10,22,34,.98), rgba(11,23,38,.95));
        border: 1px solid rgba(93,124,151,.30);
        border-radius: 14px;
        padding: 8px 10px 10px 10px;
        margin: 0 0 10px 0;
        box-shadow: 0 8px 22px rgba(0,0,0,.22);
    }
    .status-strip {
        background: rgba(10,22,34,.68);
        border: 1px solid rgba(93,124,151,.22);
        border-radius: 12px;
        padding: 6px 8px;
        min-height: 42px;
        font-size: .72rem;
    }
    .status-strip b { color:#e7eef7; }
    [data-testid="stSidebar"] { min-width: 220px !important; max-width: 220px !important; }


    /* v7.4 unified shell: prevent Streamlit Deploy/menu from covering app controls */
    header[data-testid="stHeader"] {
        height: 0rem !important;
        min-height: 0rem !important;
        background: transparent !important;
        visibility: hidden !important;
    }
    [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"], .stDeployButton, #MainMenu, footer {
        visibility: hidden !important;
        height: 0px !important;
        display: none !important;
    }
    .block-container { padding-top: 1.05rem !important; max-width: 1580px !important; }
    .command-shell {
        background: linear-gradient(90deg, rgba(9,21,34,.98), rgba(10,22,37,.96), rgba(21,18,43,.94));
        border: 1px solid rgba(93,124,151,.30);
        border-radius: 16px;
        padding: 8px 10px 9px 10px;
        margin: 0 0 8px 0;
        box-shadow: 0 10px 28px rgba(0,0,0,.26);
    }
    .command-title {
        font-size: .68rem;
        color: var(--muted);
        letter-spacing: .08em;
        text-transform: uppercase;
        margin: 0 0 5px 2px;
    }
    .command-status {
        background: rgba(4,13,22,.58);
        border: 1px solid rgba(93,124,151,.20);
        border-radius: 11px;
        padding: 5px 7px;
        min-height: 38px;
        font-size: .62rem;
        line-height: 1.16;
        overflow:hidden;
        white-space:nowrap;
        text-overflow:ellipsis;
    }
    .command-status b { font-size:.72rem; color:#e7eef7; }
    div[data-testid="stTextInput"] input[aria-label="Search anything"] {
        min-height: 38px !important;
        font-size: .84rem !important;
        border-radius: 12px !important;
    }
    .gauge-wrap {
        background: linear-gradient(180deg, rgba(20,34,50,0.78), rgba(8,18,29,0.88));
        border: 1px solid rgba(93,124,151,.25);
        border-radius: 13px;
        padding: 4px 4px 0 4px;
        min-height: 155px;
        overflow: hidden;
    }
    .gauge-caption {
        margin-top: -8px;
        text-align:center;
        font-size:.62rem;
        color: var(--muted);
        white-space: nowrap;
        overflow:hidden;
        text-overflow:ellipsis;
    }

    /* v7.5 timezone + clean command bar + auto rerun controls */
    .wide-status { min-height: 38px !important; padding: 8px 10px !important; }
    .auto-rerun-box {
        background: rgba(4,13,22,.58);
        border: 1px solid rgba(93,124,151,.20);
        border-radius: 11px;
        padding: 8px 10px;
        min-height: 36px;
        font-size: .68rem;
        line-height: 1.18;
        color: var(--muted);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .auto-rerun-box b { color:#e7eef7; }
    div[data-testid="stButton"] button { white-space: nowrap !important; min-width: 92px !important; }
    div[data-testid="stButton"] button p { white-space: nowrap !important; }
    div[data-testid="stToggle"] label, div[data-testid="stSelectbox"] label { font-size: .68rem !important; }
    .command-shell { margin-top: 4px !important; }

    /* v8 Action Console: decision-first visual system */
    .action-hero {
        background: radial-gradient(circle at 12% 20%, rgba(74,163,255,.18), transparent 30%),
                    linear-gradient(135deg, rgba(13,28,45,.98), rgba(7,17,28,.98) 55%, rgba(26,19,52,.92));
        border: 1px solid rgba(93,124,151,.34);
        border-radius: 18px;
        padding: 12px 14px;
        margin: 4px 0 10px 0;
        box-shadow: 0 14px 36px rgba(0,0,0,.32);
        overflow: hidden;
    }
    .action-kicker { font-size:.60rem; color:#8ea4b8; letter-spacing:.12em; text-transform:uppercase; font-weight:900; }
    .action-state { font-size:1.55rem; font-weight:1000; line-height:1.05; color:#e7eef7; letter-spacing:-.04em; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .action-line { color:#e7eef7; font-size:.86rem; font-weight:800; margin-top:5px; line-height:1.25; }
    .action-note { color:#8ea4b8; font-size:.70rem; margin-top:5px; line-height:1.22; }
    .action-pill { display:inline-block; border-radius:999px; padding:3px 8px; font-size:.58rem; font-weight:900; text-transform:uppercase; border:1px solid rgba(93,124,151,.30); background:rgba(10,22,34,.65); color:#dbeafe; margin-right:4px; }
    .action-board { display:grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap:8px; margin:8px 0 10px 0; }
    .action-tile { background: rgba(7,17,28,.82); border: 1px solid rgba(93,124,151,.25); border-radius: 13px; padding: 9px 10px; min-height: 92px; overflow:hidden; }
    .action-tile .label { color:#8ea4b8; font-size:.56rem; font-weight:900; letter-spacing:.08em; text-transform:uppercase; white-space:nowrap; }
    .action-tile .main { color:#e7eef7; font-size:.96rem; font-weight:1000; line-height:1.08; margin-top:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .action-tile .sub { color:#8ea4b8; font-size:.66rem; line-height:1.18; margin-top:5px; }
    .target-grid { display:grid; grid-template-columns: repeat(6, minmax(0,1fr)); gap:8px; margin:6px 0 10px 0; }
    .target-card { background: linear-gradient(180deg, rgba(20,34,50,.88), rgba(8,18,29,.92)); border:1px solid rgba(93,124,151,.25); border-radius:13px; padding:9px 10px; min-height:126px; overflow:hidden; }
    .target-symbol { font-size:.66rem; color:#8ea4b8; text-transform:uppercase; letter-spacing:.08em; font-weight:900; }
    .target-direction { font-size:.98rem; font-weight:1000; margin-top:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .target-number { font-size:1.18rem; font-weight:1000; color:#e7eef7; margin-top:3px; }
    .target-meta { color:#8ea4b8; font-size:.62rem; line-height:1.15; margin-top:4px; }
    .outcome-grid { display:grid; grid-template-columns: 1.25fr 1fr 1fr; gap:10px; margin:7px 0 10px 0; }
    .outcome-card { background: linear-gradient(180deg, rgba(16,31,48,.94), rgba(8,18,29,.94)); border: 1px solid rgba(93,124,151,.26); border-radius:15px; padding:11px 12px; min-height:174px; overflow:hidden; }
    .outcome-rank { font-size:.62rem; color:#8ea4b8; font-weight:900; text-transform:uppercase; letter-spacing:.08em; }
    .outcome-title { font-size:1.02rem; font-weight:1000; margin:4px 0 5px 0; color:#e7eef7; }
    .prob-bar { height:7px; border-radius:999px; background:rgba(93,124,151,.20); overflow:hidden; margin:7px 0; }
    .prob-fill { height:100%; border-radius:999px; background:linear-gradient(90deg,#ff4b45,#ffc83d,#29d66f); }
    .micro-list { margin:6px 0 0 0; padding:0; list-style:none; }
    .micro-list li { color:#dbeafe; font-size:.68rem; line-height:1.18; padding:2px 0; border-bottom:1px solid rgba(93,124,151,.10); }
    .micro-list li:last-child { border-bottom:0; }
    .decision-grid { display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap:10px; margin:7px 0 10px 0; }
    .decision-card { background: rgba(10,22,34,.88); border:1px solid rgba(93,124,151,.25); border-radius:14px; padding:10px 12px; min-height:190px; }
    .section-head { display:flex; align-items:center; justify-content:space-between; margin:14px 0 5px 0; }
    .section-title { font-size:.78rem; color:#e7eef7; font-weight:1000; letter-spacing:.08em; text-transform:uppercase; }
    .section-caption { color:#8ea4b8; font-size:.62rem; }

    /* v8.1 Global Live Action Engine: selectable live tiles */
    .live-action-note { color:#8ea4b8; font-size:.68rem; line-height:1.25; margin-top:-2px; margin-bottom:8px; }
    .live-detail-panel { background: linear-gradient(135deg, rgba(13,28,45,.98), rgba(8,18,29,.96) 60%, rgba(29,24,58,.88)); border:1px solid rgba(93,124,151,.30); border-radius:16px; padding:12px 14px; margin:8px 0 12px 0; box-shadow:0 12px 28px rgba(0,0,0,.24); }
    .selected-head { display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:8px; }
    .selected-title { font-size:1.05rem; font-weight:1000; color:#e7eef7; letter-spacing:-.02em; }
    .selected-sub { font-size:.66rem; color:#8ea4b8; line-height:1.2; }
    .tile-action-grid { display:grid; grid-template-columns: repeat(6, minmax(0,1fr)); gap:8px; margin-top:8px; }
    .tile-action-card { background:rgba(7,17,28,.82); border:1px solid rgba(93,124,151,.22); border-radius:12px; padding:9px 10px; min-height:88px; overflow:hidden; }
    .tile-action-card .label { font-size:.55rem; color:#8ea4b8; font-weight:900; letter-spacing:.08em; text-transform:uppercase; }
    .tile-action-card .main { font-size:.86rem; color:#e7eef7; font-weight:950; line-height:1.12; margin-top:4px; }
    .tile-action-card .sub { font-size:.62rem; color:#8ea4b8; line-height:1.16; margin-top:4px; }
    .global-live-strip { display:grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap:8px; margin:8px 0 10px 0; }
    .global-live-card { background:rgba(10,22,34,.72); border:1px solid rgba(93,124,151,.20); border-radius:12px; padding:8px 10px; min-height:68px; }
    .global-live-card .label { font-size:.55rem; color:#8ea4b8; font-weight:900; letter-spacing:.08em; text-transform:uppercase; }
    .global-live-card .main { font-size:.82rem; color:#e7eef7; font-weight:900; margin-top:3px; }
    .global-live-card .sub { font-size:.58rem; color:#8ea4b8; margin-top:2px; }
    @media (max-width: 1180px) { .tile-action-grid { grid-template-columns: repeat(2, minmax(0,1fr)); } .global-live-strip { grid-template-columns: repeat(2, minmax(0,1fr)); } }

    @media (max-width: 1180px) {
        .action-board { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .target-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .outcome-grid { grid-template-columns: 1fr; }
        .decision-grid { grid-template-columns: 1fr; }
        .action-state { font-size:1.25rem; }
    }

</style>
""",
    unsafe_allow_html=True,
)


def regime_card(title: str, value: str, subtitle: str, score: float | None, accent: str | None = None) -> None:
    score = 0.0 if score is None else float(score)
    klass = accent or score_class(score)
    st.markdown(
        f"""
        <div class="card">
            <div class="card-title">{title}</div>
            <div class="card-value {klass}">{value.upper()} <span style="float:right">{score_arrow(score)}</span></div>
            <div class="card-sub">{subtitle}</div>
            <div class="card-sub">Score: <b>{short_score(score)}</b></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def simple_card(title: str, value: str, subtitle: str = "", klass: str = "info") -> None:
    st.markdown(
        f"""
        <div class="mini-card">
            <div class="card-title">{title}</div>
            <div class="card-value {klass}">{value}</div>
            <div class="card-sub">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )




def gauge_color(score: float) -> str:
    if score >= 20:
        return "#29d66f"
    if score <= -20:
        return "#ff4b45"
    return "#ffc83d"


def gauge_label(score: float) -> str:
    if score >= 60:
        return "Strong support"
    if score >= 20:
        return "Supportive"
    if score <= -60:
        return "Heavy pressure"
    if score <= -20:
        return "Pressure"
    return "Mixed / neutral"


def show_meter(title: str, score: float, caption: str = "") -> None:
    score = max(-100.0, min(100.0, safe_num(score)))
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"font": {"size": 22, "color": "#e7eef7"}, "suffix": ""},
            title={"text": title, "font": {"size": 12, "color": "#e7eef7"}},
            gauge={
                "axis": {"range": [-100, 100], "tickwidth": 1, "tickcolor": "#8ea4b8", "tickfont": {"size": 8, "color": "#8ea4b8"}},
                "bar": {"color": gauge_color(score), "thickness": 0.28},
                "bgcolor": "rgba(8,18,29,0.80)",
                "borderwidth": 1,
                "bordercolor": "rgba(93,124,151,.30)",
                "steps": [
                    {"range": [-100, -60], "color": "rgba(255,75,69,.22)"},
                    {"range": [-60, -20], "color": "rgba(255,75,69,.12)"},
                    {"range": [-20, 20], "color": "rgba(255,200,61,.14)"},
                    {"range": [20, 60], "color": "rgba(41,214,111,.12)"},
                    {"range": [60, 100], "color": "rgba(41,214,111,.22)"},
                ],
                "threshold": {"line": {"color": "#e7eef7", "width": 2}, "thickness": 0.75, "value": score},
            },
        )
    )
    fig.update_layout(
        height=135,
        margin={"l": 8, "r": 8, "t": 22, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e7eef7"},
    )
    st.markdown('<div class="gauge-wrap">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown(f'<div class="gauge-caption">{caption or gauge_label(score)}</div></div>', unsafe_allow_html=True)


def status_badge(text: str, klass: str = "info") -> str:
    return f'<span class="badge {klass}">{text}</span>'


# -----------------------------------------------------------------------------
# Data prep
# -----------------------------------------------------------------------------
init_db(DB_PATH)
df = cached_load_data(str(DB_PATH))
macro_result, macro_table, macro_cats = compute_macro_regime(df)
ai_result, ai_table, ai_cats = compute_ai_regime(df)
internal_result, internal_table, internal_cats = compute_internal_regime(df)
global_result, global_table, global_cats = compute_global_regime(df)
runs = load_runs(DB_PATH)
last_message = str(runs.iloc[0]["message"]) if not runs.empty else ""
last_status = str(runs.iloc[0]["status"]) if not runs.empty else "none"
inserted_count, feed_issue_count = parse_last_run_message(last_message)
calendar = add_event_display(cached_auto_events())
combined_table = pd.concat([macro_table, ai_table, internal_table, global_table], ignore_index=True)


# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"""
        <div class="cmd-header">
            <div class="brand-orb"></div>
            <div>
                <div class="brand-title">MACRO REGIME ENGINE <span class="muted">{APP_VERSION}</span></div>
                <div class="brand-sub">Command Center</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    page = st.radio(
        "Navigation",
        [
            "Dashboard",
            "Macro",
            "AI / Tech",
            "Market Internals",
            "Sector Rotation",
            "Index Components",
            "Breadth",
            "Credit",
            "Volatility",
            "Global Markets",
            "Bonds & Rates",
            "Dollar",
            "Commodities",
            "Crypto",
            "Geopolitics",
            "Event Watch",
            "Alerts Center",
            "Playbook",
            "Scenario Matrix",
            "Charts",
            "Data Health",
            "Update Runs",
            "Settings",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")
    if st.button("Live update", use_container_width=True):
        ok, msg = run_update()
        st.success(msg) if ok else st.error(msg)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Prices", use_container_width=True):
            ok, msg = run_market_update()
            st.success(msg) if ok else st.error(msg)
    with c2:
        if st.button("Economy", use_container_width=True):
            ok, msg = run_econ_update()
            st.success(msg) if ok else st.error(msg)
    c3, c4 = st.columns(2)
    with c3:
        if st.button("Internals", use_container_width=True):
            ok, msg = run_internal_update()
            st.success(msg) if ok else st.error(msg)
    with c4:
        if st.button("Global", use_container_width=True):
            ok, msg = run_global_update()
            st.success(msg) if ok else st.error(msg)
    if st.button("Events", use_container_width=True):
        ok, msg = update_events()
        st.success(msg) if ok else st.error(msg)

    st.markdown("---")
    ny_now = datetime.now(ET_TZ)
    is_market_open = ny_now.weekday() < 5 and time(9, 30) <= ny_now.time() <= time(16, 0)
    session_class = "good" if is_market_open else "warn"
    session_text = "OPEN" if is_market_open else "CLOSED"
    st.markdown(
        f"""
        <div class="mini-card">
            <div class="card-title">Market Session</div>
            <div>New York {status_badge(session_text, session_class)}</div>
            <div class="card-sub">Eastern/Toronto time shown in regular 12-hour format.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    risk_class = score_class(macro_result.score)
    risk_text = "CAUTION" if abs(macro_result.score) < 60 else ("RISK SUPPORT" if macro_result.score > 0 else "HIGH PRESSURE")
    st.markdown(
        f"""
        <div class="mini-card" style="margin-top:12px;">
            <div class="card-title">Risk Mode</div>
            <div class="card-value {risk_class}">{risk_text}</div>
            <div class="card-sub">Macro score: {macro_result.score:.1f}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# Unified command bar + search + auto re-run
# -----------------------------------------------------------------------------
bg_running, bg_detail = background_updater_status()
age = seconds_since_last_run(runs)
live_klass = "good" if age is not None and age <= 45 else "warn" if age is not None and age <= 180 else "bad"
errors = feed_issue_count if feed_issue_count is not None else 0
inserted = inserted_count if inserted_count is not None else 0
health_overall = "Operational" if inserted > 0 and errors == 0 else "Partial" if inserted > 0 else "No Data"
health_klass = "good" if health_overall == "Operational" else "warn" if health_overall == "Partial" else "bad"
now = local_now()

if "auto_rerun_on" not in st.session_state:
    st.session_state.auto_rerun_on = True
if "auto_rerun_interval" not in st.session_state:
    st.session_state.auto_rerun_interval = 30

next_rerun = f"{st.session_state.auto_rerun_interval}s" if st.session_state.auto_rerun_on else "OFF"
last_run_display = latest_update_text(runs) if not runs.empty else "No run yet"

st.markdown(
    f'''
    <div class="command-shell">
        <div class="command-title">Unified Command Center · Search · Live Status · Eastern/Toronto 12-Hour Time · Auto Re-run</div>
    </div>
    ''',
    unsafe_allow_html=True,
)

cmd_search, cmd_status = st.columns([4.9, 2.1])
with cmd_search:
    global_query = st.text_input(
        "Search anything",
        placeholder="Search everything... NDX, QQQ, NVDA, internals, breadth, credit, gold, yields, dollar, CPI, FOMC, oil",
        label_visibility="collapsed",
        key="main_global_search",
    )
with cmd_status:
    health_detail = f"{inserted:,} saved" if inserted else "Run update"
    bg_badge = status_badge("RUNNING" if bg_running else "STOPPED", "good" if bg_running else "warn")
    st.markdown(
        f'''
        <div class="command-status wide-status">
            <b>{fmt_time(now)}</b> <span class="muted">Eastern</span>
            &nbsp; | &nbsp; Pulse {status_badge("LIVE" if live_klass == "good" else "STALE", live_klass)} <span class="muted">{human_age(age)}</span>
            &nbsp; | &nbsp; Data {status_badge(health_overall, health_klass)} <span class="muted">{health_detail}</span>
            &nbsp; | &nbsp; BG {bg_badge}
        </div>
        ''',
        unsafe_allow_html=True,
    )

ctrl1, ctrl2, ctrl3, ctrl4, ctrl5, ctrl6 = st.columns([1.0, .8, .95, .95, 1.05, 2.25])
with ctrl1:
    auto_on = st.toggle("Auto", value=st.session_state.auto_rerun_on, help="Auto re-run the dashboard view without using a full browser refresh.")
    st.session_state.auto_rerun_on = auto_on
with ctrl2:
    interval = st.selectbox("Interval", [15, 30, 60], index=[15, 30, 60].index(st.session_state.auto_rerun_interval), label_visibility="collapsed")
    st.session_state.auto_rerun_interval = int(interval)
with ctrl3:
    if st.button("Start Live", use_container_width=True, help="Start background live updater"):
        ok, msg = start_background_updater(15)
        st.toast(msg, icon="✅" if ok else "⚠️")
        st.rerun()
with ctrl4:
    if st.button("Stop Live", use_container_width=True, help="Stop background live updater"):
        ok, msg = stop_background_updater()
        st.toast(msg, icon="✅" if ok else "⚠️")
        st.rerun()
with ctrl5:
    if st.button("Update Now", use_container_width=True, help="Run one live update now"):
        ok, msg = run_update()
        st.toast("Live update complete" if ok else "Live update issue", icon="✅" if ok else "⚠️")
        if not ok:
            st.warning(msg[:900])
        st.rerun()
with ctrl6:
    st.markdown(
        f'''
        <div class="auto-rerun-box">
            <b>Auto Re-run:</b> {"ON" if st.session_state.auto_rerun_on else "OFF"}
            &nbsp; | &nbsp; <b>Every:</b> {next_rerun}
            &nbsp; | &nbsp; <b>Last Run:</b> {last_run_display}
        </div>
        ''',
        unsafe_allow_html=True,
    )

# Auto re-run without a browser page refresh. This only re-executes the Streamlit script.
if st.session_state.auto_rerun_on:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=int(st.session_state.auto_rerun_interval) * 1000, key="macro_engine_autorun")
    except Exception:
        # If the optional component is unavailable, keep the app usable instead of breaking the dashboard.
        pass

# Data itself is updated by live_updater.py in the background. Auto re-run only refreshes what the dashboard displays.

# -----------------------------------------------------------------------------
# Search results
# -----------------------------------------------------------------------------
def relationship_catalog() -> dict[str, dict[str, list[str] | str]]:
    return {
        "nasdaq": {
            "title": "Nasdaq / NDX / QQQ / Tech Growth",
            "aliases": ["ndx", "nasdaq", "qqq", "nq", "tech", "growth", "nas100", "us100"],
            "series": ["Nasdaq", "QQQ", "S&P 500", "Russell", "VIX", "US Dollar", "Yield", "Nvidia", "Microsoft", "AMD", "Broadcom", "Semiconductor"],
            "events": ["CPI", "PCE", "FOMC", "NFP", "ISM", "Treasury", "earnings", "AI"],
            "drivers_up": ["10Y/2Y yields falling", "Dollar softening", "VIX falling", "AI leaders confirming", "Cool CPI/PCE", "Dovish Fed repricing", "Strong mega-cap earnings"],
            "drivers_down": ["Yields rising", "Dollar strengthening", "VIX rising", "Hot CPI/PCE", "Hawkish Fed", "AI leaders breaking first", "Semiconductors losing leadership"],
            "watch": ["QQQ/NQ direction", "NVDA + SMH leadership", "DXY", "10Y yield", "VIX", "CPI/PCE/FOMC", "Treasury auctions"],
        },
        "ai": {
            "title": "AI / Semiconductors / Tech Leadership",
            "aliases": ["ai", "nvda", "nvidia", "smh", "soxx", "amd", "avgo", "msft", "semis", "semiconductors", "chips"],
            "series": ["Nvidia", "Microsoft", "AMD", "Broadcom", "Semiconductor", "AI", "QQQ", "Nasdaq", "TSM", "ASML", "Meta", "Amazon", "Google"],
            "events": ["earnings", "CPI", "FOMC", "PCE", "chip", "AI"],
            "drivers_up": ["NVDA/SMH leading", "QQQ confirming", "Yields stable or falling", "Capex/earnings guidance strong", "Risk appetite improving", "Dollar not pressuring growth"],
            "drivers_down": ["NVDA/SMH breaking first", "Yields rising", "QQQ lagging", "Earnings guidance weak", "Chip/export restrictions", "Crowded AI unwind"],
            "watch": ["NVDA", "SMH", "SOXX", "QQQ", "10Y yield", "DXY", "Mega-cap earnings", "chip restriction headlines"],
        },
        "gold": {
            "title": "Gold / Safety Bid / Real Yield Pressure",
            "aliases": ["gold", "gc", "xau", "xauusd", "safe haven", "safety"],
            "series": ["Gold", "US Dollar", "Yield", "Treasury", "VIX", "Oil"],
            "events": ["CPI", "PCE", "FOMC", "NFP", "geopolitical", "war", "auction"],
            "drivers_up": ["Real yields falling", "Dollar weakening", "Fear/geopolitical risk rising", "Fed cut expectations rising", "Inflation fear rising faster than yields"],
            "drivers_down": ["Real yields rising", "Dollar strengthening", "Risk-on returns", "Fed stays hawkish", "Inflation cools with no fear bid"],
            "watch": ["DXY", "10Y yield", "real-yield proxy", "CPI/PCE", "FOMC", "VIX", "geopolitical headlines"],
        },
        "oil": {
            "title": "Oil / Inflation Shock / Energy Risk",
            "aliases": ["oil", "wti", "crude", "cl", "energy", "opec"],
            "series": ["WTI", "Oil", "Energy", "US Dollar", "Copper", "Yield"],
            "events": ["EIA", "Crude", "OPEC", "CPI", "PCE", "geopolitical", "Middle East"],
            "drivers_up": ["Supply shock", "OPEC cuts", "Middle East risk", "Dollar softening", "Demand improving", "Inventory draw"],
            "drivers_down": ["Demand slowdown", "Inventory build", "Dollar strengthening", "OPEC supply increase", "Risk-off liquidation"],
            "watch": ["EIA inventories", "DXY", "10Y yield", "CPI impulse", "shipping routes", "OPEC headlines"],
        },
        "dollar": {
            "title": "Dollar / DXY / Liquidity Pressure",
            "aliases": ["dollar", "dxy", "usd", "uup", "greenback"],
            "series": ["US Dollar", "UUP", "Yield", "Treasury", "Gold", "S&P", "Nasdaq"],
            "events": ["CPI", "PCE", "FOMC", "NFP", "ISM", "Treasury"],
            "drivers_up": ["US yields rising", "Hawkish Fed", "Hot inflation", "Global risk-off", "US growth outperforming", "Safe-haven demand"],
            "drivers_down": ["Yields falling", "Dovish Fed", "Cool inflation", "Global risk-on", "Cut expectations rising"],
            "watch": ["2Y/10Y yields", "FOMC pricing", "CPI/PCE", "Gold reaction", "Nasdaq pressure", "VIX"],
        },
        "bonds": {
            "title": "Bonds / Rates / Yield Curve",
            "aliases": ["bond", "bonds", "yield", "yields", "10y", "2y", "30y", "curve", "rates", "treasury", "tlt"],
            "series": ["Yield", "Treasury", "T-Bill", "Curve", "TLT", "US Dollar", "Gold", "QQQ"],
            "events": ["CPI", "PCE", "FOMC", "NFP", "ISM", "Treasury auction", "GDP"],
            "drivers_up": ["Hot inflation", "Strong labor data", "Hawkish Fed", "Weak Treasury auctions", "Oil/inflation shock"],
            "drivers_down": ["Cool inflation", "Growth slowdown", "Dovish Fed", "Risk-off bond bid", "Strong auctions"],
            "watch": ["2Y yield", "10Y yield", "curve steepening/inversion", "CPI/PCE", "FOMC", "Treasury auctions", "Gold/QQQ reaction"],
        },
        "crypto": {
            "title": "Crypto / Bitcoin / Liquidity Appetite",
            "aliases": ["crypto", "bitcoin", "btc", "btcusd", "eth", "ethereum"],
            "series": ["Bitcoin", "BTC", "QQQ", "Nasdaq", "US Dollar", "VIX", "Yield"],
            "events": ["CPI", "FOMC", "PCE", "risk", "liquidity"],
            "drivers_up": ["Liquidity expanding", "Dollar weakening", "Yields falling", "Risk appetite strong", "ETF/flow support"],
            "drivers_down": ["Dollar rising", "Yields rising", "VIX rising", "Risk-off deleveraging", "Regulatory pressure"],
            "watch": ["BTC", "QQQ", "DXY", "10Y yield", "VIX", "liquidity regime"],
        },
        "internals": {
            "title": "Market Internals / Breadth / Components",
            "aliases": ["internals", "breadth", "advance decline", "ad line", "internal", "components", "market internal", "sector rotation", "equal weight"],
            "series": ["Breadth", "Equal Weight", "RSP", "QQQE", "Russell", "Sector", "Credit", "High Yield", "Junk", "Banks", "VIX", "VVIX", "SKEW", "Technology", "Financials", "Defensive", "Apple", "Tesla", "JPMorgan"],
            "events": ["CPI", "FOMC", "NFP", "Treasury", "earnings", "options", "VIX"],
            "drivers_up": ["More stocks participating", "Equal-weight ETFs outperform cap-weight indexes", "Credit/HYG confirming", "Cyclicals leading", "Volatility internals falling", "Banks confirming risk appetite"],
            "drivers_down": ["Index carried by only mega-caps", "Equal-weight ETFs lagging", "HYG/JNK weak", "Defensives leading", "VIX/VVIX/SKEW rising", "Banks/regional banks breaking"],
            "watch": ["RSP vs SPY", "QQQE vs QQQ", "Sector rotation", "HYG/JNK/LQD", "KRE/KBE", "VIX9D/VIX3M/VVIX", "leaders vs laggards"],
        },
        "global": {
            "title": "Global Markets / Regional Confirmation",
            "aliases": ["global", "world", "europe", "china", "japan", "canada", "india", "emerging markets", "eem", "acwi"],
            "series": ["Global", "Canada", "UK", "Germany", "France", "Japan", "China", "Hong Kong", "India", "Emerging", "ACWI"],
            "events": ["FOMC", "CPI", "China", "ECB", "BOJ", "geopolitical", "oil"],
            "drivers_up": ["Global indexes confirming US risk-on", "Dollar softening", "China/EM stabilizing", "Europe/Japan participating", "Commodity growth proxies firm"],
            "drivers_down": ["Global equities lag US", "Dollar strengthening", "China/EM weak", "Europe/Japan stress", "Geopolitical risk or oil shock"],
            "watch": ["ACWI", "EEM", "FXI", "EWJ", "EWG", "EWC", "DXY", "oil", "global bond pressure"],
        },
        "credit": {
            "title": "Credit / Banks / Financial Stress",
            "aliases": ["credit", "hyg", "jnk", "lqd", "banks", "kre", "kbe", "financial stress"],
            "series": ["High Yield", "Junk", "Investment Grade", "Regional Banks", "Bank ETF", "JPMorgan", "Goldman Sachs", "VIX", "Yield"],
            "events": ["FOMC", "Treasury", "CPI", "NFP", "bank", "credit"],
            "drivers_up": ["HYG/JNK firm", "Banks leading", "Rates stable", "VIX falling", "Risk appetite broadening"],
            "drivers_down": ["HYG/JNK weak", "LQD falling", "Regional banks weak", "Yields rising fast", "VIX rising", "Liquidity stress"],
            "watch": ["HYG", "JNK", "LQD", "KRE", "KBE", "JPM", "GS", "VIX", "2Y/10Y yields"],
        },
        "inflation": {
            "title": "Inflation / CPI / PCE / PPI",
            "aliases": ["inflation", "cpi", "pce", "ppi", "prices"],
            "series": ["CPI", "PCE", "PPI", "Oil", "Gold", "Yield", "US Dollar"],
            "events": ["CPI", "PCE", "PPI", "FOMC", "Oil", "ISM"],
            "drivers_up": ["Oil rising", "wages sticky", "PPI pressure", "services inflation", "supply shock"],
            "drivers_down": ["Oil falling", "wage cooling", "demand slowing", "goods disinflation", "productivity improving"],
            "watch": ["CPI YoY/MoM", "Core CPI", "PCE", "wages", "oil", "yields", "DXY"],
        },
    }


def identify_search_topic(query: str) -> tuple[str | None, dict[str, list[str] | str] | None]:
    q = query.lower().strip()
    for key, bundle in relationship_catalog().items():
        aliases = [str(x).lower() for x in bundle.get("aliases", [])]
        if q == key or any(q == a or q in a or a in q for a in aliases):
            return key, bundle
    return None, None


def mask_terms(table: pd.DataFrame, terms: list[str]) -> pd.Series:
    if table.empty:
        return pd.Series([], dtype=bool)
    mask = pd.Series(False, index=table.index)
    for term in terms:
        if not term:
            continue
        mask = mask | table.apply(lambda row: row.astype(str).str.contains(str(term), case=False, regex=False).any(), axis=1)
    return mask


def chip_list(items: list[str]) -> None:
    st.markdown(" ".join(f'<span class="relation-chip">{item}</span>' for item in items), unsafe_allow_html=True)


def compact_section(title: str) -> None:
    st.markdown(f'<div class="search-section-title">{title}</div>', unsafe_allow_html=True)



def alert_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    now_str = fmt_time(local_now())
    for msg in generate_alerts(macro_table, macro_cats):
        if "No major" in msg or "No observations" in msg:
            priority = "Medium"
        elif any(term in msg.lower() for term in ["dollar", "yield", "risk-off", "gold", "oil"]):
            priority = "High"
        else:
            priority = "Medium"
        rows.append({"time": now_str, "alert": msg, "priority": priority, "type": "Macro"})
    for msg in generate_ai_alerts(ai_table, macro_table):
        if "No major" in msg or "No AI" in msg:
            priority = "Medium"
        elif any(term in msg.lower() for term in ["breakdown", "pressure", "unwind", "weak"]):
            priority = "High"
        else:
            priority = "Medium"
        rows.append({"time": now_str, "alert": msg, "priority": priority, "type": "AI"})
    for msg in generate_internal_alerts(internal_table, macro_table):
        if "No internal" in msg:
            priority = "Medium"
        elif any(term in msg.lower() for term in ["weak", "credit", "volatility", "defensive", "pressure"]):
            priority = "High"
        else:
            priority = "Medium"
        rows.append({"time": now_str, "alert": msg, "priority": priority, "type": "Internals"})
    for msg in generate_global_alerts(global_table):
        priority = "High" if any(term in msg.lower() for term in ["weak", "stress", "only"]) else "Medium"
        rows.append({"time": now_str, "alert": msg, "priority": priority, "type": "Global"})
    return rows


# -----------------------------------------------------------------------------
# v8 Action engine: NOW -> TARGET -> OUTCOME -> CONFIRM -> INVALIDATE -> AVOID
# -----------------------------------------------------------------------------
def category_score(cats: pd.DataFrame, category: str) -> float:
    if cats.empty or "category" not in cats.columns:
        return 0.0
    row = cats[cats["category"].eq(category)]
    if row.empty:
        return 0.0
    return safe_num(row.iloc[0].get("score"))


def row_by_any(table: pd.DataFrame, names: list[str]) -> pd.Series | None:
    if table.empty:
        return None
    for name in names:
        row = table[table["name"].astype(str).str.lower().eq(name.lower())]
        if not row.empty:
            return row.iloc[0]
        row = table[table["symbol"].astype(str).str.lower().eq(name.lower())]
        if not row.empty:
            return row.iloc[0]
    for name in names:
        row = table[table["name"].astype(str).str.contains(name, case=False, regex=False, na=False)]
        if not row.empty:
            return row.iloc[0]
    return None


def level_text(row: pd.Series | None, direction: str, strength: float = 1.0) -> tuple[str, str]:
    if row is None or pd.isna(row.get("latest_close")):
        return "Waiting for live price", "Waiting for live price"
    close = safe_num(row.get("latest_close"))
    score = abs(safe_num(row.get("score")))
    step_pct = max(0.35, min(2.75, (score / 100.0) * 2.0 * max(0.6, strength)))
    reclaim_pct = max(0.25, min(1.35, step_pct * 0.55))
    if direction.lower().startswith("down"):
        target = close * (1 - step_pct / 100.0)
        invalid = close * (1 + reclaim_pct / 100.0)
        return f"{target:,.2f}", f"Reclaim > {invalid:,.2f}"
    if direction.lower().startswith("up"):
        target = close * (1 + step_pct / 100.0)
        invalid = close * (1 - reclaim_pct / 100.0)
        return f"{target:,.2f}", f"Fail < {invalid:,.2f}"
    low = close * (1 - step_pct / 200.0)
    high = close * (1 + step_pct / 200.0)
    return f"{low:,.2f}–{high:,.2f}", "Wait for clean break"


def strongest_pressure() -> tuple[str, float]:
    pieces: list[tuple[str, float]] = []
    for table in [macro_cats, ai_cats, internal_cats, global_cats]:
        if table is not None and not table.empty:
            for _, row in table.iterrows():
                pieces.append((str(row.get("category", "Unknown")), safe_num(row.get("score"))))
    if not pieces:
        return "No data", 0.0
    return min(pieces, key=lambda x: x[1])


def strongest_support() -> tuple[str, float]:
    pieces: list[tuple[str, float]] = []
    for table in [macro_cats, ai_cats, internal_cats, global_cats]:
        if table is not None and not table.empty:
            for _, row in table.iterrows():
                pieces.append((str(row.get("category", "Unknown")), safe_num(row.get("score"))))
    if not pieces:
        return "No data", 0.0
    return max(pieces, key=lambda x: x[1])


def build_action_read() -> dict[str, object]:
    rates = category_score(macro_cats, "Rates")
    dollar = category_score(macro_cats, "Dollar")
    commodities = category_score(macro_cats, "Commodities")
    volatility = category_score(macro_cats, "Volatility")
    liquidity = (rates + dollar) / 2.0
    composite = (macro_result.score + ai_result.score + internal_result.score + global_result.score) / 4.0
    pressure_name, pressure_score = strongest_pressure()
    support_name, support_score = strongest_support()
    negative_votes = sum(score < -15 for score in [macro_result.score, ai_result.score, internal_result.score, global_result.score, rates, dollar, liquidity])
    positive_votes = sum(score > 15 for score in [macro_result.score, ai_result.score, internal_result.score, global_result.score, rates, dollar, liquidity])
    if negative_votes >= 4 or composite <= -25:
        state = "Risk-Off Pressure"
        action = "Do not trust risk-on until dollar, yields, internals, and AI leadership cool together."
        main_pressure = "QQQ / AI / Growth"
        best_side = "Fade weak risk-on / protect longs"
    elif positive_votes >= 4 or composite >= 25:
        state = "Risk-On Support"
        action = "Risk appetite is supported while internals and leadership continue confirming."
        main_pressure = "Defensives / cash rotation"
        best_side = "Follow confirmed pullbacks"
    else:
        state = "Mixed Chop / Confirmation Needed"
        action = "Avoid chasing middle. Wait for dollar/yields and internals to agree."
        main_pressure = "Range-bound indexes"
        best_side = "Wait for confirmation"
    gold_row = row_by_any(combined_table, ["Gold Futures", "GC=F"])
    if commodities > 15 or (gold_row is not None and safe_num(gold_row.get("score")) > 15):
        support_asset = "Gold / commodities"
    elif internal_result.score < -20:
        support_asset = "Defensives / cash"
    else:
        support_asset = support_name
    confidence = int(max(35, min(92, 45 + abs(composite) * 0.35 + max(negative_votes, positive_votes) * 5)))
    return {"state": state, "action": action, "primary_driver": f"{pressure_name} ({pressure_score:.0f})", "support_driver": f"{support_name} ({support_score:.0f})", "main_pressure": main_pressure, "support_asset": support_asset, "best_side": best_side, "confidence": confidence, "rates": rates, "dollar": dollar, "commodities": commodities, "volatility": volatility, "liquidity": liquidity, "composite": composite}


def target_rows() -> list[dict[str, str]]:
    read = build_action_read()
    risk_off = safe_num(read["composite"]) < -15 or safe_num(read["liquidity"]) < -15
    qqq = row_by_any(combined_table, ["QQQ", "Nasdaq 100", "^NDX"])
    dxy = row_by_any(combined_table, ["US Dollar Index", "US Dollar ETF", "DX-Y.NYB", "UUP"])
    ten_y = row_by_any(combined_table, ["US 10Y Yield", "^TNX", "10Y"])
    gold = row_by_any(combined_table, ["Gold Futures", "GC=F"])
    vix = row_by_any(combined_table, ["VIX", "^VIX"])
    nvda = row_by_any(combined_table, ["Nvidia", "NVDA"])
    q_dir = "Downside pressure" if risk_off else "Upside / reclaim"
    d_dir = "Upside pressure" if safe_num(read["dollar"]) < -10 else "Downside / relief"
    y_dir = "Upside pressure" if safe_num(read["rates"]) < -10 else "Downside / relief"
    g_dir = "Upside safety bid" if risk_off or (gold is not None and safe_num(gold.get("score")) > 10) else "Range / wait"
    v_dir = "Upside fear expansion" if risk_off else "Downside compression"
    n_dir = "AI weakness watch" if ai_result.score < -10 or risk_off else "AI leadership watch"
    rows = []
    for label, row, direction, why, strength in [("QQQ / NDX", qqq, q_dir, "Growth target from macro + AI pressure", 1.0), ("DXY", dxy, d_dir, "Dollar confirms/denies liquidity pressure", 0.9), ("10Y Yield", ten_y, y_dir, "Yield pressure drives growth/AI valuation", 0.8), ("Gold", gold, g_dir, "Safety/inflation hedge target", 0.75), ("VIX", vix, v_dir, "Volatility confirms/denies risk tone", 0.9), ("NVDA", nvda, n_dir, "AI leadership confirmation target", 1.1)]:
        td = "down" if "Downside" in direction or "weakness" in direction or "compression" in direction else "up" if "Upside" in direction or "leadership" in direction else "range"
        tgt, invalid = level_text(row, td, strength)
        klass = "bad" if td == "down" and label in ["QQQ / NDX", "NVDA"] else "good" if td == "up" else "warn"
        rows.append({"asset": label, "direction": direction, "target": tgt, "invalid": invalid, "why": why, "klass": klass})
    return rows


def outcome_rows() -> list[dict[str, object]]:
    read = build_action_read()
    comp = safe_num(read["composite"])
    liq = safe_num(read["liquidity"])
    internals = internal_result.score
    ai = ai_result.score
    if comp <= -20 or liq <= -20:
        return [{"rank": "Outcome 1", "title": "Risk-Off Continuation", "prob": 55, "target": "QQQ/AI lower, DXY/yields firm, VIX bid", "confirm": "DXY up + yields up + internals weak", "invalidate": "QQQ reclaim + DXY rolls over + breadth improves"}, {"rank": "Outcome 2", "title": "Relief Bounce", "prob": 30, "target": "QQQ/NVDA bounce, VIX cools", "confirm": "Yields down + DXY down + AI leaders recover", "invalidate": "AI leaders fail / VIX expands"}, {"rank": "Outcome 3", "title": "Mixed Chop", "prob": 15, "target": "Range-bound fakeouts", "confirm": "No clear leader + mixed breadth", "invalidate": "Clean breakout with internals confirming"}]
    if comp >= 20 and internals >= 10:
        return [{"rank": "Outcome 1", "title": "Risk-On Continuation", "prob": 58, "target": "QQQ/AI higher, VIX lower, credit firm", "confirm": "Breadth improves + yields stable + AI leads", "invalidate": "DXY/yields spike + VIX rises"}, {"rank": "Outcome 2", "title": "Rotation / Pullback", "prob": 27, "target": "Index digestion, sector rotation", "confirm": "Leaders pause while internals hold", "invalidate": "Breadth turns negative"}, {"rank": "Outcome 3", "title": "Failed Risk-On", "prob": 15, "target": "Fakeout into pressure", "confirm": "DXY/yields rise against risk assets", "invalidate": "Fresh highs with internals"}]
    return [{"rank": "Outcome 1", "title": "Mixed Chop", "prob": 45, "target": "Range trades / two-sided action", "confirm": "Signals stay split", "invalidate": "Dollar, yields, internals align"}, {"rank": "Outcome 2", "title": "Risk-Off Break", "prob": 32 if ai < 0 else 25, "target": "QQQ lower, VIX higher", "confirm": "AI + breadth weaken together", "invalidate": "QQQ reclaim with breadth"}, {"rank": "Outcome 3", "title": "Risk-On Reclaim", "prob": 23 if ai < 0 else 30, "target": "QQQ/AI higher", "confirm": "DXY down + yields cool", "invalidate": "Reclaim fails"}]


def confirm_invalid_avoid() -> tuple[list[str], list[str], list[str]]:
    read = build_action_read()
    risk_off = safe_num(read["composite"]) < -15 or safe_num(read["liquidity"]) < -15
    if risk_off:
        return (["DXY holds firm / pushes higher", "2Y/10Y yields stay firm", "QQQ and NVDA fail reclaim", "VIX/VVIX bid stays active", "Breadth/equal-weight remains weak", "Credit/HYG does not confirm risk-on"], ["DXY rolls over", "Yields cool decisively", "QQQ reclaims pressure level", "AI leaders recover first", "VIX fades", "Breadth/equal-weight improves"], ["Avoid chasing shorts after large extension", "Avoid risk-off if VIX refuses to confirm", "Avoid trusting weakness if QQQ/NVDA reclaim quickly", "Avoid trading before major event release noise"])
    if safe_num(read["composite"]) > 15:
        return (["Breadth expands", "QQQ/NVDA/SMH lead", "VIX compresses", "DXY stays soft", "Yields stable or falling", "Credit/HYG confirms"], ["DXY spikes", "Yields spike", "Internals diverge", "AI leaders lag", "VIX rises while indexes hold", "Credit weakens"], ["Avoid chasing highs if internals are narrow", "Avoid risk-on if only mega-cap AI is holding", "Avoid longs into hot data event risk", "Avoid if VIX rises against the move"])
    return (["Wait for DXY + yields agreement", "Wait for QQQ + internals confirmation", "Wait for VIX direction", "Watch AI leaders vs equal-weight", "Check credit before trusting move"], ["No clean invalidation in chop", "A confirmed break with internals changes the read", "Event shock can reset the regime"], ["Avoid middle of range", "Avoid acting on one market alone", "Avoid over-weighting paragraph info over NOW/TARGET/CONFIRM", "Avoid trades without liquidity + internals agreement"])


def render_action_tiles() -> None:
    read = build_action_read()
    next_event = str(calendar.iloc[0]["event"]) if not calendar.empty else "No event"
    next_countdown = str(calendar.iloc[0]["countdown"]) if not calendar.empty else "Run event update"
    st.markdown(f'''
        <div class="action-hero">
            <div class="action-kicker">Action Console · Decision First</div>
            <div class="action-state">{read["state"]}</div>
            <div class="action-line">{read["action"]}</div>
            <div class="action-note"><span class="action-pill">Confidence {read["confidence"]}%</span><span class="action-pill">Best Side: {read["best_side"]}</span><span class="action-pill">Live Age: {human_age(seconds_since_last_run(runs))}</span></div>
        </div>
        <div class="action-board">
            <div class="action-tile"><div class="label">NOW</div><div class="main">{read["state"]}</div><div class="sub">Current regime from macro, AI, internals, and global pressure.</div></div>
            <div class="action-tile"><div class="label">DRIVER</div><div class="main">{read["primary_driver"]}</div><div class="sub">Largest pressure source currently pulling the tape.</div></div>
            <div class="action-tile"><div class="label">PRESSURE</div><div class="main">{read["main_pressure"]}</div><div class="sub">Most sensitive asset group if this read continues.</div></div>
            <div class="action-tile"><div class="label">SUPPORT</div><div class="main">{read["support_asset"]}</div><div class="sub">Area most likely to hold/benefit if pressure persists.</div></div>
            <div class="action-tile"><div class="label">NEXT RISK</div><div class="main">{next_event}</div><div class="sub">{next_countdown}</div></div>
        </div>
        ''', unsafe_allow_html=True)


def render_target_board() -> None:
    st.markdown('<div class="section-head"><div class="section-title">Target Board</div><div class="section-caption">Directional pressure levels from live prices</div></div>', unsafe_allow_html=True)
    html = ['<div class="target-grid">']
    for row in target_rows():
        html.append(f'''<div class="target-card"><div class="target-symbol">{row["asset"]}</div><div class="target-direction {row["klass"]}">{row["direction"]}</div><div class="target-number">{row["target"]}</div><div class="target-meta"><b>Cancel:</b> {row["invalid"]}</div><div class="target-meta">{row["why"]}</div></div>''')
    html.append('</div>')
    st.markdown(''.join(html), unsafe_allow_html=True)


def render_outcome_board() -> None:
    st.markdown('<div class="section-head"><div class="section-title">Outcome Board</div><div class="section-caption">Ranked scenario path</div></div>', unsafe_allow_html=True)
    html = ['<div class="outcome-grid">']
    for row in outcome_rows():
        prob = int(row["prob"])
        html.append(f'''<div class="outcome-card"><div class="outcome-rank">{row["rank"]} · {prob}%</div><div class="outcome-title">{row["title"]}</div><div class="prob-bar"><div class="prob-fill" style="width:{prob}%"></div></div><ul class="micro-list"><li><b>Target:</b> {row["target"]}</li><li><b>Confirm:</b> {row["confirm"]}</li><li><b>Invalidate:</b> {row["invalidate"]}</li></ul></div>''')
    html.append('</div>')
    st.markdown(''.join(html), unsafe_allow_html=True)


def render_decision_board() -> None:
    confirm, invalidate, avoid = confirm_invalid_avoid()
    st.markdown('<div class="section-head"><div class="section-title">Confirm / Invalidate / Avoid</div><div class="section-caption">Use this before trusting the read</div></div>', unsafe_allow_html=True)
    def card(title: str, items: list[str], klass: str) -> str:
        lis = ''.join(f'<li>{x}</li>' for x in items[:6])
        return f'<div class="decision-card"><div class="card-title {klass}">{title}</div><ul class="micro-list">{lis}</ul></div>'
    st.markdown('<div class="decision-grid">' + card('CONFIRM', confirm, 'good') + card('INVALIDATE', invalidate, 'bad') + card('AVOID', avoid, 'warn') + '</div>', unsafe_allow_html=True)


def render_action_meters() -> None:
    rates_score = category_score(macro_cats, "Rates")
    dollar_score = category_score(macro_cats, "Dollar")
    liquidity_score = (rates_score + dollar_score) / 2.0
    risk_sentiment_score = (macro_result.score + ai_result.score + internal_result.score + global_result.score) / 4.0
    st.markdown('<div class="section-head"><div class="section-title">Pressure Gauges</div><div class="section-caption">Kept central, not hidden</div></div>', unsafe_allow_html=True)
    meter_cols = st.columns(5)
    with meter_cols[0]: show_meter("Macro", macro_result.score, macro_result.regime)
    with meter_cols[1]: show_meter("AI Growth", ai_result.score, ai_result.regime)
    with meter_cols[2]: show_meter("Internals", internal_result.score, internal_result.regime)
    with meter_cols[3]: show_meter("Liquidity", liquidity_score, "Bonds + dollar pressure")
    with meter_cols[4]: show_meter("Risk", risk_sentiment_score, "Composite market tone")


def render_search_action_result(query: str, bundle: dict[str, list[str] | str] | None) -> None:
    st.markdown('<div class="section-head"><div class="section-title">Action Read</div><div class="section-caption">Search output converted into targets/outcomes</div></div>', unsafe_allow_html=True)
    render_action_tiles()
    render_target_board()
    render_decision_board()

def show_search_results(query: str) -> bool:
    q = query.strip()
    if not q:
        return False

    topic_key, bundle = identify_search_topic(q)
    title = str(bundle.get("title")) if bundle else q.upper()
    st.markdown(f"### Search Intelligence: {title}")
    render_search_action_result(q, bundle)
    found = False

    if bundle:
        found = True
        related_terms = list(bundle.get("series", [])) + list(bundle.get("aliases", []))
        market_mask = mask_terms(combined_table, related_terms)
        related_markets = combined_table[market_mask].copy() if not combined_table.empty else pd.DataFrame()

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            simple_card("Search Topic", str(bundle.get("title")), "Relationship result", "info")
        with c2:
            simple_card("Related Series", str(len(related_markets)), "Markets / indicators", "good" if len(related_markets) else "warn")
        with c3:
            simple_card("Live Pulse", human_age(seconds_since_last_run(runs)), "Last saved refresh", "good" if (seconds_since_last_run(runs) or 9999) < 60 else "warn")
        with c4:
            simple_card("Next Event", str(calendar.iloc[0]["event"])[:18] if not calendar.empty else "None", str(calendar.iloc[0]["countdown"]) if not calendar.empty else "", "warn")

        compact_section("Related assets / indicators")
        chip_list([str(x) for x in related_terms[:26]])
        if not related_markets.empty:
            view = _format_view(related_markets).sort_values(["module", "category", "score"], ascending=[True, True, False])
            st.dataframe(view[[c for c in ["module", "category", "symbol", "name", "latest_date", "latest_close", "change_pct", "score", "description"] if c in view.columns]], use_container_width=True, hide_index=True)

        d1, d2, d3 = st.columns(3)
        with d1:
            compact_section("What can push it up")
            for item in bundle.get("drivers_up", []):
                st.write(f"✅ {item}")
        with d2:
            compact_section("What can push it down")
            for item in bundle.get("drivers_down", []):
                st.write(f"❌ {item}")
        with d3:
            compact_section("Watch right now")
            for item in bundle.get("watch", []):
                st.write(f"• {item}")

        event_terms = list(bundle.get("events", [])) + [title]
        event_mask = mask_terms(calendar, event_terms) if not calendar.empty else pd.Series([], dtype=bool)
        compact_section("Upcoming events that can move this topic")
        if not calendar.empty and event_mask.any():
            cols = ["countdown", "local_time", "event", "importance", "market_focus", "cause_risk", "watch_before", "watch_after"]
            st.dataframe(calendar[event_mask][[c for c in cols if c in calendar.columns]].head(20), use_container_width=True, hide_index=True)
        else:
            st.caption("No exact matching upcoming event loaded yet. Check Event Watch for the full calendar.")

        compact_section("Active alerts connected to this search")
        alerts = pd.DataFrame(alert_rows())
        if not alerts.empty:
            alert_mask = mask_terms(alerts, related_terms + event_terms)
            if alert_mask.any():
                st.dataframe(alerts[alert_mask], use_container_width=True, hide_index=True)
            else:
                st.caption("No active alert directly matched. Watch the related drivers above.")

        compact_section("Playbook / scenario matches")
        play_terms = related_terms + event_terms + [topic_key or q]
        play = cause_effect_df()
        scen = scenario_df()
        geo = geopolitical_df()
        pmask = mask_terms(play, play_terms) if not play.empty else pd.Series([], dtype=bool)
        smask = mask_terms(scen, play_terms) if not scen.empty else pd.Series([], dtype=bool)
        gmask = mask_terms(geo, play_terms) if not geo.empty else pd.Series([], dtype=bool)
        if not play.empty and pmask.any():
            st.write("**Cause & Effect**")
            st.dataframe(play[pmask].head(12), use_container_width=True, hide_index=True)
        if not scen.empty and smask.any():
            st.write("**Scenario Matrix**")
            st.dataframe(scen[smask].head(8), use_container_width=True, hide_index=True)
        if not geo.empty and gmask.any():
            st.write("**Geopolitical Shock Watch**")
            st.dataframe(geo[gmask].head(8), use_container_width=True, hide_index=True)

    # Always include direct raw matches after relationship output.
    direct_found = False
    if not combined_table.empty:
        m = combined_table.apply(lambda row: row.astype(str).str.contains(q, case=False, regex=False).any(), axis=1)
        if m.any():
            found = True
            direct_found = True
            compact_section("Direct market / indicator matches")
            st.dataframe(_format_view(combined_table[m]), use_container_width=True, hide_index=True)

    for label, table in [
        ("Direct upcoming event matches", calendar),
        ("Direct cause & effect matches", cause_effect_df()),
        ("Direct scenario matches", scenario_df()),
        ("Direct geopolitical matches", geopolitical_df()),
        ("Direct event guide matches", event_watch_df()),
    ]:
        if table.empty:
            continue
        mask = table.apply(lambda row: row.astype(str).str.contains(q, case=False, regex=False).any(), axis=1)
        if mask.any():
            found = True
            compact_section(label)
            st.dataframe(table[mask].head(30), use_container_width=True, hide_index=True)

    if not found:
        st.warning("No result found. Try: NDX, QQQ, AI, NVDA, gold, dollar, yields, bonds, oil, CPI, FOMC, inflation, crypto.")
    elif not bundle and not direct_found:
        st.caption("Tip: broader searches like NDX, gold, dollar, yields, oil, or AI return full relationship maps.")
    return True


if show_search_results(global_query):
    st.stop()

if combined_table.empty and page != "Settings":
    st.warning("No live data loaded yet. Use the sidebar Live update, or run: python update_data.py")


# -----------------------------------------------------------------------------
# Component helpers
# -----------------------------------------------------------------------------
def what_matters_now() -> list[str]:
    items: list[str] = []
    for alert in generate_alerts(macro_table, macro_cats):
        if alert and "No major" not in alert:
            items.append(alert)
    for alert in generate_ai_alerts(ai_table, macro_table):
        if alert and "No major" not in alert:
            items.append(alert)
    for alert in generate_internal_alerts(internal_table, macro_table):
        if alert and "No major" not in alert:
            items.append(alert)
    for alert in generate_global_alerts(global_table):
        if alert and "No global" not in alert:
            items.append(alert)
    for item in diagnostics_for_categories(macro_cats)[:2]:
        items.append(item)
    for item in diagnostics_for_categories(ai_cats)[:2]:
        items.append(item)
    for item in diagnostics_for_categories(internal_cats)[:2]:
        items.append(item)
    if not calendar.empty:
        row = calendar.iloc[0]
        items.append(f"Next major time risk: {row['event']} — {row['countdown']} — {row['local_time']}.")
    if not items:
        items.append("No strong cross-market warning yet. Treat the tape as neutral until dollar, yields, volatility, and leadership agree.")
    # keep unique, preserve order
    unique: list[str] = []
    for item in items:
        if item not in unique:
            unique.append(item)
    return unique[:5]


def alert_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    now_str = fmt_time(local_now())
    for msg in generate_alerts(macro_table, macro_cats):
        if "No major" in msg or "No observations" in msg:
            priority = "Medium"
        elif any(term in msg.lower() for term in ["dollar", "yield", "risk-off", "gold", "oil"]):
            priority = "High"
        else:
            priority = "Medium"
        rows.append({"time": now_str, "alert": msg, "priority": priority, "type": "Macro"})
    for msg in generate_ai_alerts(ai_table, macro_table):
        if "No major" in msg or "No AI" in msg:
            priority = "Medium"
        elif any(term in msg.lower() for term in ["breakdown", "pressure", "unwind", "weak"]):
            priority = "High"
        else:
            priority = "Medium"
        rows.append({"time": now_str, "alert": msg, "priority": priority, "type": "AI"})
    for msg in generate_internal_alerts(internal_table, macro_table):
        if "No internal" in msg:
            priority = "Medium"
        elif any(term in msg.lower() for term in ["weak", "credit", "volatility", "defensive", "pressure"]):
            priority = "High"
        else:
            priority = "Medium"
        rows.append({"time": now_str, "alert": msg, "priority": priority, "type": "Internals"})
    for msg in generate_global_alerts(global_table):
        priority = "High" if any(term in msg.lower() for term in ["weak", "stress", "only"]) else "Medium"
        rows.append({"time": now_str, "alert": msg, "priority": priority, "type": "Global"})
    return rows


def show_alerts_compact(limit: int = 5) -> None:
    rows = alert_rows()[:limit]
    st.markdown('<div class="card"><div class="card-title">Alerts</div>', unsafe_allow_html=True)
    for row in rows:
        klass = "bad" if row["priority"] == "High" else "warn"
        st.markdown(
            f"""
            <div class="line-item">
                <div class="alert-time">{row['time']}</div>
                <div style="flex:1">{row['alert']}<br><span class="muted">{row['type']}</span></div>
                {status_badge(row['priority'], klass)}
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def show_events_compact(limit: int = 5) -> None:
    st.markdown('<div class="card"><div class="card-title">Event Countdown</div>', unsafe_allow_html=True)
    if calendar.empty:
        st.markdown('<div class="muted">No upcoming event calendar loaded.</div>', unsafe_allow_html=True)
    else:
        for _, row in calendar.head(limit).iterrows():
            klass = "bad" if "Extreme" in str(row.get("importance")) else "warn" if "High" in str(row.get("importance")) else "info"
            st.markdown(
                f"""
                <div class="line-item">
                    <div style="flex:1"><b>{row['event']}</b><br><span class="muted">{row['local_time']}</span></div>
                    {status_badge(str(row['countdown']), klass)}
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)


def current_series_snapshot(names: list[str]) -> pd.DataFrame:
    rows = []
    for name in names:
        row = find_row(combined_table, name)
        if row is not None:
            rows.append(row.to_dict())
    return pd.DataFrame(rows)


def market_snapshot_cards() -> None:
    names = ["S&P 500", "QQQ", "Equal Weight S&P 500", "High Yield Credit ETF", "US Dollar ETF", "US 10Y Yield", "Gold Futures", "Nvidia"]
    rows = current_series_snapshot(names)
    if rows.empty:
        st.info("No market snapshot data loaded yet.")
        return
    row_records = list(rows.iterrows())
    for start_idx in range(0, len(row_records), 4):
        cols = st.columns(4)
        for col, (_, row) in zip(cols, row_records[start_idx:start_idx + 4]):
            change = safe_num(row.get("change_pct"))
            score = safe_num(row.get("score"))
            klass = score_class(score)
            close = safe_num(row.get("latest_close"))
            with col:
                simple_card(
                    str(row.get("symbol")),
                    f"{close:,.2f}",
                    f"{change:+.2f}% | {row.get('name')}",
                    klass,
                )


# -----------------------------------------------------------------------------
# v8.1 Global live action engine: selectable tiles + asset action panel
# -----------------------------------------------------------------------------
LIVE_TILE_GROUPS = ["All", "Indexes", "AI / Tech", "Bonds", "Dollar", "Commodities", "Crypto", "Internals", "Credit", "Volatility", "Global"]

LIVE_TILE_DEFS = [
    {"key": "SPX", "label": "SPX", "group": "Indexes", "lookup": ["S&P 500", "^GSPC", "SPY"], "role": "risk_asset", "related": ["QQQ", "RSP", "VIX", "DXY", "10Y", "HYG"], "sensitivity": "Broad risk appetite"},
    {"key": "QQQ", "label": "QQQ / NDX", "group": "Indexes", "lookup": ["QQQ", "Nasdaq 100", "^NDX"], "role": "growth_asset", "related": ["NVDA", "SMH", "DXY", "10Y", "VIX", "QQQE"], "sensitivity": "Growth / AI / duration pressure"},
    {"key": "RSP", "label": "RSP", "group": "Internals", "lookup": ["Equal Weight S&P 500", "RSP"], "role": "internal", "related": ["SPX", "SPY", "Breadth", "Sectors"], "sensitivity": "Broad market participation"},
    {"key": "DXY", "label": "DXY / UUP", "group": "Dollar", "lookup": ["US Dollar Index", "US Dollar ETF", "DX-Y.NYB", "UUP"], "role": "pressure_up", "related": ["Gold", "QQQ", "10Y", "BTC", "Oil"], "sensitivity": "Dollar liquidity pressure"},
    {"key": "10Y", "label": "10Y Yield", "group": "Bonds", "lookup": ["US 10Y Yield", "^TNX"], "role": "pressure_up", "related": ["QQQ", "DXY", "Gold", "TLT", "Banks"], "sensitivity": "Rate / valuation pressure"},
    {"key": "VIX", "label": "VIX", "group": "Volatility", "lookup": ["VIX", "^VIX"], "role": "pressure_up", "related": ["SPX", "QQQ", "VVIX", "VIX9D", "Credit"], "sensitivity": "Fear / hedge demand"},
    {"key": "GOLD", "label": "Gold", "group": "Commodities", "lookup": ["Gold Futures", "GC=F"], "role": "neutral_asset", "related": ["DXY", "10Y", "Real yields", "VIX", "CPI"], "sensitivity": "Safety / inflation hedge"},
    {"key": "OIL", "label": "Oil", "group": "Commodities", "lookup": ["WTI Crude Oil", "CL=F", "Brent Crude Oil"], "role": "pressure_up", "related": ["CPI", "DXY", "Energy", "EIA", "Geopolitics"], "sensitivity": "Energy / inflation shock"},
    {"key": "NVDA", "label": "NVDA", "group": "AI / Tech", "lookup": ["Nvidia", "NVDA"], "role": "growth_asset", "related": ["SMH", "SOXX", "QQQ", "AMD", "AVGO", "AI"], "sensitivity": "AI leadership confirmation"},
    {"key": "SMH", "label": "SMH / SOXX", "group": "AI / Tech", "lookup": ["VanEck Semiconductor ETF", "iShares Semiconductor ETF", "SMH", "SOXX"], "role": "growth_asset", "related": ["NVDA", "AMD", "AVGO", "QQQ", "Yields"], "sensitivity": "Semiconductor leadership"},
    {"key": "HYG", "label": "HYG / Credit", "group": "Credit", "lookup": ["High Yield Credit ETF", "HYG", "Junk Bond ETF", "JNK"], "role": "credit", "related": ["SPX", "VIX", "Banks", "Yields"], "sensitivity": "Credit risk appetite"},
    {"key": "BTC", "label": "BTC", "group": "Crypto", "lookup": ["Bitcoin", "BTC-USD"], "role": "growth_asset", "related": ["DXY", "QQQ", "VIX", "Liquidity"], "sensitivity": "High-beta liquidity"},
    {"key": "GLOBAL", "label": "Global", "group": "Global", "lookup": ["Global ACWI ETF", "ACWI", "Emerging Markets ETF", "EEM"], "role": "risk_asset", "related": ["DXY", "Oil", "China", "Europe", "Japan"], "sensitivity": "World confirmation"},
]


def live_tile_defs_for_group(group: str) -> list[dict[str, object]]:
    if group == "All":
        return LIVE_TILE_DEFS
    return [tile for tile in LIVE_TILE_DEFS if tile["group"] == group]


def live_tile_row(tile: dict[str, object]) -> pd.Series | None:
    names = [str(x) for x in tile.get("lookup", [])]
    row = row_by_any(combined_table, names)
    if row is None:
        row = row_by_any(internal_table, names)
    if row is None:
        row = row_by_any(global_table, names)
    return row


def live_tile_state(tile: dict[str, object], row: pd.Series | None) -> dict[str, str | float]:
    if row is None:
        return {"price": "Waiting", "change": 0.0, "score": 0.0, "state": "No live row", "klass": "warn", "bias": "Wait", "target_dir": "range"}
    change = safe_num(row.get("change_pct"))
    score = safe_num(row.get("score"))
    role = str(tile.get("role", "risk_asset"))
    if role in ["pressure_up"]:
        if change > 0 or score < -15:
            state, klass, bias, target_dir = "Pressure Rising", "bad", "Upside pressure", "up"
        elif change < 0 or score > 15:
            state, klass, bias, target_dir = "Pressure Cooling", "good", "Downside relief", "down"
        else:
            state, klass, bias, target_dir = "Mixed", "warn", "Range / wait", "range"
    elif role in ["growth_asset", "risk_asset", "credit", "internal"]:
        if score > 15 or change > 0.35:
            state, klass, bias, target_dir = "Supportive", "good", "Upside / reclaim", "up"
        elif score < -15 or change < -0.35:
            state, klass, bias, target_dir = "Under Pressure", "bad", "Downside pressure", "down"
        else:
            state, klass, bias, target_dir = "Mixed", "warn", "Range / wait", "range"
    else:
        if score > 15 or change > 0.35:
            state, klass, bias, target_dir = "Bid / Firm", "good", "Upside pressure", "up"
        elif score < -15 or change < -0.35:
            state, klass, bias, target_dir = "Offered / Weak", "bad", "Downside pressure", "down"
        else:
            state, klass, bias, target_dir = "Mixed", "warn", "Range / wait", "range"
    return {"price": f"{safe_num(row.get('latest_close')):,.2f}", "change": change, "score": score, "state": state, "klass": klass, "bias": bias, "target_dir": target_dir}


def selected_tile() -> dict[str, object]:
    key = st.session_state.get("selected_live_tile", "QQQ")
    for tile in LIVE_TILE_DEFS:
        if tile["key"] == key:
            return tile
    return LIVE_TILE_DEFS[1]


def asset_rule_pack(tile: dict[str, object], row: pd.Series | None, state: dict[str, str | float]) -> dict[str, list[str] | str]:
    key = str(tile["key"])
    related = ", ".join([str(x) for x in tile.get("related", [])[:6]])
    common: dict[str, list[str] | str] = {
        "now": f"{tile['label']} is {state['state']} — {tile.get('sensitivity', 'live pressure read')}.",
        "driver": "Global live state recalculates macro, AI, internals, liquidity, alerts, targets and search results.",
        "related": related,
    }
    if key in ["QQQ", "NVDA", "SMH", "SPX", "BTC"]:
        common.update({"confirm": ["Price remains weak or fails reclaim", "DXY stays firm", "10Y yield does not cool", "VIX stays bid", "Internals/breadth fail to improve", "Related leaders lag"], "invalidate": ["DXY rolls over", "Yields cool", "VIX fades", "Breadth improves", "Related leaders reclaim", "Credit/HYG confirms risk appetite"], "avoid": ["Avoid trusting bounces if AI/semis lag", "Avoid chasing after extension", "Avoid action before event release noise", "Avoid longs if DXY/yields keep pressing"]})
    elif key in ["DXY", "10Y", "VIX", "OIL"]:
        common.update({"confirm": ["Tile continues higher", "Risk assets weaken against it", "Alerts confirm same driver", "Event risk supports pressure", "Internals deteriorate"], "invalidate": ["Tile rejects or rolls over", "QQQ/SPX reclaim", "VIX/credit calms", "Breadth improves", "Gold/oil reaction contradicts"], "avoid": ["Avoid forcing risk-off if pressure asset rejects", "Avoid stale signals after event passes", "Avoid reading one pressure asset alone"]})
    elif key in ["HYG", "RSP", "GLOBAL"]:
        common.update({"confirm": ["Participation keeps improving", "Credit and breadth hold", "Indexes confirm direction", "Volatility stays calm", "Sector leadership broadens"], "invalidate": ["Breadth rolls over", "HYG/JNK weakens", "VIX rises", "Defensives lead", "Only mega-caps hold the market"], "avoid": ["Avoid risk-on if participation is narrow", "Avoid trusting index strength without credit/breadth", "Avoid treating defensive rotation as clean risk-on"]})
    else:
        common.update({"confirm": ["Related markets agree", "Macro driver confirms", "Internals confirm", "Alerts support the read"], "invalidate": ["Related markets disagree", "Driver reverses", "Internals split", "Event shock resets the read"], "avoid": ["Avoid one-market decisions", "Avoid middle of range", "Avoid stale data"]})
    return common


def render_global_live_strip() -> None:
    read = build_action_read()
    health = data_health_summary()
    pieces = [("Action Console", str(read.get("state", "Mixed")), "Recalculated from live data"), ("Gauges", f"Macro {macro_result.score:.0f} / AI {ai_result.score:.0f}", "Scores update globally"), ("Targets", f"{len(target_rows())} live targets", "Pressure levels recalculated"), ("Alerts", f"{len(alert_rows())} active", "Live rule checks"), ("Data", str(health.get("overall", "Unknown")), str(health.get("detail", ""))[:28])]
    html = ['<div class="global-live-strip">']
    for label, main, sub in pieces:
        html.append(f'<div class="global-live-card"><div class="label">{label}</div><div class="main">{main}</div><div class="sub">{sub}</div></div>')
    html.append('</div>')
    st.markdown(''.join(html), unsafe_allow_html=True)


def render_selected_tile_panel() -> None:
    tile = selected_tile()
    row = live_tile_row(tile)
    state = live_tile_state(tile, row)
    target, invalid = level_text(row, str(state.get("target_dir", "range")), 1.0)
    pack = asset_rule_pack(tile, row, state)
    symbol = str(row.get("symbol")) if row is not None else str(tile["key"])
    name = str(row.get("name")) if row is not None else str(tile["label"])
    html = f"""
    <div class="live-detail-panel">
        <div class="selected-head">
            <div><div class="selected-title">{tile['label']} Action Panel</div><div class="selected-sub">{name} · {symbol} · selected tile controls the detail read.</div></div>
            {status_badge(str(state['state']), str(state['klass']))}
        </div>
        <div class="tile-action-grid">
            <div class="tile-action-card"><div class="label">NOW</div><div class="main">{pack['now']}</div><div class="sub">Price {state['price']} · {float(state['change']):+.2f}%</div></div>
            <div class="tile-action-card"><div class="label">TARGET</div><div class="main">{state['bias']}</div><div class="sub">Target: {target}</div></div>
            <div class="tile-action-card"><div class="label">INVALIDATION</div><div class="main">{invalid}</div><div class="sub">Cancels selected-tile pressure read.</div></div>
            <div class="tile-action-card"><div class="label">DRIVER</div><div class="main">{pack['driver']}</div><div class="sub">Global live engine, not tile-only.</div></div>
            <div class="tile-action-card"><div class="label">RELATED</div><div class="main">{pack['related']}</div><div class="sub">Watch confirmation across these.</div></div>
            <div class="tile-action-card"><div class="label">EVENT RISK</div><div class="main">{calendar.iloc[0]['event'] if not calendar.empty else 'No event loaded'}</div><div class="sub">{calendar.iloc[0]['countdown'] if not calendar.empty else 'Run update_events.py'}</div></div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    for col, title, items, klass in [(c1, "CONFIRM", pack["confirm"], "good"), (c2, "INVALIDATE", pack["invalidate"], "bad"), (c3, "AVOID", pack["avoid"], "warn")]:
        with col:
            st.markdown(f'<div class="decision-card"><div class="card-title {klass}">{title}</div><ul class="micro-list">' + ''.join(f'<li>{x}</li>' for x in items) + '</ul></div>', unsafe_allow_html=True)


def render_live_market_pulse() -> None:
    st.markdown('<div class="section-head"><div class="section-title">Live Market Pulse</div><div class="section-caption">Selectable tiles drive the action panel; live data recalculates the whole engine</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="live-action-note">Global live refresh updates Action Console, gauges, targets, outcomes, alerts, search and the selected asset panel. Tiles are the control surface, not the only live feature.</div>', unsafe_allow_html=True)
    render_global_live_strip()
    group = st.radio("Tile category", LIVE_TILE_GROUPS, horizontal=True, label_visibility="collapsed", key="live_tile_group")
    tiles = live_tile_defs_for_group(group)
    if not tiles:
        st.info("No live tiles in this category yet.")
        return
    for start_idx in range(0, len(tiles), 4):
        cols = st.columns(4)
        for col, tile in zip(cols, tiles[start_idx:start_idx + 4]):
            row = live_tile_row(tile)
            state = live_tile_state(tile, row)
            label = f"{tile['label']}\n{state['price']}  {float(state['change']):+.2f}%\n{state['state']}"
            with col:
                if st.button(label, key=f"live_tile_{tile['key']}", use_container_width=True):
                    st.session_state.selected_live_tile = tile["key"]
                    st.rerun()
    render_selected_tile_panel()


def show_playbook_gold_card() -> None:
    play = cause_effect_df()
    gold = play[play["area"].astype(str).str.contains("Gold", case=False, na=False)].head(2)
    st.markdown('<div class="card"><div class="card-title">Cause & Effect Example: Gold</div>', unsafe_allow_html=True)
    if gold.empty:
        st.write("Gold playbook not loaded.")
    else:
        cols = st.columns(3)
        with cols[0]:
            st.markdown("**Gold rises when**")
            st.write("✅ Real yields fall")
            st.write("✅ Dollar weakens")
            st.write("✅ War/fear rises")
            st.write("✅ Cut expectations increase")
        with cols[1]:
            st.markdown("**Gold falls when**")
            st.write("❌ Real yields rise")
            st.write("❌ Dollar strengthens")
            st.write("❌ Risk-on returns")
            st.write("❌ Fed stays hawkish")
        with cols[2]:
            st.markdown("**Watch right now**")
            st.write("DXY")
            st.write("10Y yield")
            st.write("Real yields")
            next_event = calendar.iloc[0]["event"] if not calendar.empty else "No event"
            st.write(f"Next event: {next_event}")
    st.markdown("</div>", unsafe_allow_html=True)


def data_health_summary() -> dict[str, str]:
    if runs.empty:
        return {"overall": "Unknown", "klass": "warn", "detail": "No update run yet"}
    errors = feed_issue_count if feed_issue_count is not None else 0
    inserted = inserted_count if inserted_count is not None else 0
    if errors == 0 and inserted > 0:
        return {"overall": "Operational", "klass": "good", "detail": f"{inserted:,} observations saved"}
    if errors > 0 and inserted > 0:
        return {"overall": "Partial", "klass": "warn", "detail": f"{inserted:,} saved, {errors} feed issues"}
    return {"overall": "Feed Issue", "klass": "bad", "detail": f"{errors} feed issues"}


def show_data_health_compact() -> None:
    health = data_health_summary()
    st.markdown(
        f"""
        <div class="card">
            <div class="card-title">Data Health</div>
            <div>All Systems {status_badge(health['overall'], health['klass'])}</div>
            <div class="card-sub">{health['detail']}</div>
            <div class="line-item"><div style="flex:1">Market data / AI prices</div>{status_badge('Live' if not combined_table.empty else 'Unknown', 'good' if not combined_table.empty else 'warn')}</div>
            <div class="line-item"><div style="flex:1">Market internals</div>{status_badge('Live' if not internal_table.empty else 'Unknown', 'good' if not internal_table.empty else 'warn')}</div>
            <div class="line-item"><div style="flex:1">Global markets</div>{status_badge('Live' if not global_table.empty else 'Unknown', 'good' if not global_table.empty else 'warn')}</div>
            <div class="line-item"><div style="flex:1">Event calendar</div>{status_badge('Live/Auto', 'good' if not calendar.empty else 'warn')}</div>
            <div class="line-item"><div style="flex:1">BLS economic data</div>{status_badge('Partial' if (feed_issue_count or 0) > 0 else 'Live', 'warn' if (feed_issue_count or 0) > 0 else 'good')}</div>
            <div class="card-sub">Last update: {latest_update_text(runs)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def bar_chart(cats: pd.DataFrame, title: str) -> None:
    if cats.empty:
        st.info("No category scores loaded yet.")
        return
    fig = px.bar(cats, x="category", y="score", title=title, text="score")
    fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
    fig.add_hline(y=0, line_width=1)
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)


def filter_df(df_to_filter: pd.DataFrame, query_key: str, placeholder: str = "Search table...") -> pd.DataFrame:
    query = st.text_input(placeholder, key=query_key)
    filtered = df_to_filter.copy()
    if query:
        mask = filtered.apply(lambda row: row.astype(str).str.contains(query, case=False, regex=False).any(), axis=1)
        filtered = filtered[mask]
    return filtered


# -----------------------------------------------------------------------------
# Pages
# -----------------------------------------------------------------------------
def page_dashboard() -> None:
    """v8.1 decision-first home screen with global live action engine."""
    render_action_tiles()
    render_action_meters()
    render_live_market_pulse()
    render_target_board()
    render_outcome_board()
    render_decision_board()

    st.markdown('<div class="section-head"><div class="section-title">Live Alerts / Event Risk / Health</div><div class="section-caption">Details stay below the action layer</div></div>', unsafe_allow_html=True)
    live_a, live_b, live_c = st.columns([1.15, .95, .9])
    with live_a:
        show_alerts_compact(6)
    with live_b:
        show_events_compact(6)
    with live_c:
        show_data_health_compact()

    low_a, low_b, low_c = st.columns([1.0, 1.0, 1.0])
    with low_a:
        st.markdown('<div class="card"><div class="card-title">Internal Confirmation</div>', unsafe_allow_html=True)
        metrics = internal_participation(internal_table)
        pct = metrics["positive_pct"]
        klass = "good" if pct >= 55 else "warn" if pct >= 40 else "bad"
        st.markdown(f'<div class="big-num {klass}">{pct:.0f}% positive</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-sub">Breadth / sectors / credit / vol participation</div>', unsafe_allow_html=True)
        leaders = metrics.get("leaders")
        if isinstance(leaders, pd.DataFrame) and not leaders.empty:
            st.dataframe(leaders[["symbol", "score"]].round(2), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with low_b:
        st.markdown('<div class="card"><div class="card-title">AI Leadership</div>', unsafe_allow_html=True)
        ai_leaders = ai_table[ai_table["category"].eq("AI Leaders")].copy()
        if ai_leaders.empty:
            st.write("No AI leader data loaded.")
        else:
            view = _format_view(ai_leaders).sort_values("score", ascending=False).head(6)
            st.dataframe(view[["symbol", "change_pct", "score"]], use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with low_c:
        st.markdown('<div class="card"><div class="card-title">Quick Market Snapshot</div>', unsafe_allow_html=True)
        market_snapshot_cards()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        f"<div class='footer-bar'>Last Updated: {latest_update_text(runs)} &nbsp; • &nbsp; Eastern/Toronto 12-hour time &nbsp; • &nbsp; Global live engine updates the full action console, not tiles alone.</div>",
        unsafe_allow_html=True,
    )


def page_macro(category: str | None = None) -> None:
    title = category if category else "Macro"
    st.header(title)
    table = macro_table if category is None else macro_table[macro_table["category"].eq(category)]
    cats = macro_cats if category is None else macro_cats[macro_cats["category"].eq(category)]
    top_cols = st.columns(4)
    with top_cols[0]:
        simple_card("Regime", macro_result.regime, macro_result.summary, score_class(macro_result.score))
    with top_cols[1]:
        simple_card("Score", f"{macro_result.score:.1f}", "Macro weighted score", score_class(macro_result.score))
    with top_cols[2]:
        simple_card("Loaded Series", str(len(table)), "Active rows in this view", "info")
    with top_cols[3]:
        simple_card("Feed Issues", str(feed_issue_count if feed_issue_count is not None else "Check runs"), "Latest update run", "bad" if (feed_issue_count or 0) > 0 else "good")
    bar_chart(cats, f"{title} Pressure Map")
    st.subheader("Alerts / Diagnostics")
    for item in generate_alerts(table, cats) if category is None else diagnostics_for_categories(cats):
        st.write(f"• {item}")
    st.subheader("Series Table")
    view = _format_view(filter_df(table, f"filter_{title}", f"Search {title}..."))
    st.dataframe(view, use_container_width=True, hide_index=True)


def page_ai() -> None:
    st.header("AI / Tech Command Center")
    top_cols = st.columns(4)
    with top_cols[0]:
        simple_card("AI Regime", ai_result.regime, ai_result.summary, score_class(ai_result.score))
    with top_cols[1]:
        simple_card("AI Score", f"{ai_result.score:.1f}", "Growth leadership score", score_class(ai_result.score))
    with top_cols[2]:
        leader_score = safe_num(ai_cats[ai_cats["category"].eq("AI Leaders")]["score"].iloc[0]) if not ai_cats[ai_cats["category"].eq("AI Leaders")].empty else 0
        simple_card("AI Leaders", f"{leader_score:.1f}", "NVDA/MSFT/GOOGL/META/AMZN etc.", score_class(leader_score))
    with top_cols[3]:
        semi_score = safe_num(ai_cats[ai_cats["category"].eq("Semiconductors")]["score"].iloc[0]) if not ai_cats[ai_cats["category"].eq("Semiconductors")].empty else 0
        simple_card("Semiconductors", f"{semi_score:.1f}", "SMH/SOXX/TSM/ASML/MU", score_class(semi_score))
    bar_chart(ai_cats, "AI Growth Pressure Map")
    st.subheader("AI Alerts")
    for item in generate_ai_alerts(ai_table, macro_table):
        st.write(f"• {item}")
    st.subheader("AI Tracked Names")
    view = _format_view(filter_df(ai_table, "filter_ai", "Search AI names, semis, cloud, infrastructure..."))
    st.dataframe(view, use_container_width=True, hide_index=True)


def internal_participation(table: pd.DataFrame) -> dict[str, object]:
    if table.empty:
        return {"positive_pct": 0.0, "negative_pct": 0.0, "leaders": [], "laggards": []}
    valid = table.dropna(subset=["score"]).copy()
    if valid.empty:
        return {"positive_pct": 0.0, "negative_pct": 0.0, "leaders": [], "laggards": []}
    positive_pct = float((valid["score"] > 0).mean() * 100.0)
    negative_pct = float((valid["score"] < 0).mean() * 100.0)
    leaders = valid.sort_values("score", ascending=False).head(5)[["symbol", "name", "score"]]
    laggards = valid.sort_values("score", ascending=True).head(5)[["symbol", "name", "score"]]
    return {
        "positive_pct": positive_pct,
        "negative_pct": negative_pct,
        "leaders": leaders,
        "laggards": laggards,
    }


def page_internal(category: str | None = None) -> None:
    title = category if category else "Market Internals"
    st.header(title)
    table = internal_table if category is None else internal_table[internal_table["category"].eq(category)]
    cats = internal_cats if category is None else internal_cats[internal_cats["category"].eq(category)]
    metrics = internal_participation(table)

    cols = st.columns(4)
    with cols[0]:
        simple_card("Internal Regime", internal_result.regime, "Breadth / sectors / credit / vol", score_class(internal_result.score))
    with cols[1]:
        simple_card("Internal Score", f"{internal_result.score:.1f}", "Weighted internal score", score_class(internal_result.score))
    with cols[2]:
        simple_card("Positive Participation", f"{metrics['positive_pct']:.0f}%", "Tracked internal proxies above 0 score", "good" if metrics['positive_pct'] >= 55 else "warn" if metrics['positive_pct'] >= 40 else "bad")
    with cols[3]:
        simple_card("Loaded Internals", str(len(table)), "Series in this view", "info")

    bar_chart(cats, f"{title} Pressure Map")

    st.subheader("Internal Read")
    for item in generate_internal_alerts(table if category else internal_table, macro_table):
        st.write(f"• {item}")

    lcol, rcol = st.columns(2)
    with lcol:
        st.subheader("Leaders")
        leaders = metrics.get("leaders")
        if isinstance(leaders, pd.DataFrame) and not leaders.empty:
            out = leaders.copy()
            out["score"] = out["score"].round(2)
            st.dataframe(out, use_container_width=True, hide_index=True)
        else:
            st.caption("No leader data yet.")
    with rcol:
        st.subheader("Laggards")
        laggards = metrics.get("laggards")
        if isinstance(laggards, pd.DataFrame) and not laggards.empty:
            out = laggards.copy()
            out["score"] = out["score"].round(2)
            st.dataframe(out, use_container_width=True, hide_index=True)
        else:
            st.caption("No laggard data yet.")

    st.subheader("Series Table")
    view = _format_view(filter_df(table, f"filter_internal_{title}", f"Search {title}: RSP, QQQE, sectors, HYG, VIX9D, banks, components..."))
    st.dataframe(view, use_container_width=True, hide_index=True)

    st.subheader("How to read this")
    st.write("• Index up + internals strong = move has broad confirmation.")
    st.write("• Index up + internals weak = narrow leadership / fakeout risk.")
    st.write("• Credit weak while equities hold = hidden stress.")
    st.write("• Defensive sectors leading while cyclicals lag = risk-off rotation under the surface.")
    st.write("• Volatility internals rising while index is flat = event/fear hedging pressure.")


def page_global() -> None:
    st.header("Global Markets")
    metrics = internal_participation(global_table)
    cols = st.columns(4)
    with cols[0]:
        simple_card("Global Regime", global_result.regime, global_result.summary, score_class(global_result.score))
    with cols[1]:
        simple_card("Global Score", f"{global_result.score:.1f}", "Regional confirmation score", score_class(global_result.score))
    with cols[2]:
        simple_card("Positive Regions", f"{metrics['positive_pct']:.0f}%", "Tracked global proxies supportive", "good" if metrics['positive_pct'] >= 55 else "warn" if metrics['positive_pct'] >= 40 else "bad")
    with cols[3]:
        simple_card("Loaded Markets", str(len(global_table)), "Global series", "info")
    bar_chart(global_cats, "Global Market Confirmation Map")
    st.subheader("Global Alerts")
    for item in generate_global_alerts(global_table):
        st.write(f"• {item}")
    st.subheader("Global Market Table")
    view = _format_view(filter_df(global_table, "filter_global", "Search Canada, UK, Germany, Japan, China, India, EM, ACWI..."))
    st.dataframe(view, use_container_width=True, hide_index=True)


def page_components() -> None:
    st.header("Index Components / Single-Stock Leadership")
    comp = internal_table[internal_table["category"].isin(["Index Components", "Single Stock Leadership"])].copy()
    if comp.empty:
        st.info("No component data loaded yet.")
        return
    metrics = internal_participation(comp)
    cols = st.columns(3)
    cols[0].metric("Positive Components", f"{metrics['positive_pct']:.0f}%")
    cols[1].metric("Negative Components", f"{metrics['negative_pct']:.0f}%")
    cols[2].metric("Tracked", len(comp))
    st.write("This page shows whether the index is being carried by a small group of heavyweights or supported by broader component strength.")
    view = _format_view(filter_df(comp, "filter_components", "Search AAPL, TSLA, JPM, CAT, DIA, OEF..."))
    st.dataframe(view.sort_values("score", ascending=False), use_container_width=True, hide_index=True)

def page_event_watch() -> None:
    st.header("Event Watch")
    st.caption("Automatic calendar. Times are converted from official/release time to your Eastern/Toronto 12-hour time when exact time is available.")
    cols = st.columns(4)
    cols[0].metric("Upcoming Events", len(calendar))
    cols[1].metric("High / Extreme", int(calendar[calendar["importance"].astype(str).str.contains("High|Extreme", case=False, regex=True)].shape[0]) if not calendar.empty else 0)
    cols[2].metric("Next Event", str(calendar.iloc[0]["event"])[:22] if not calendar.empty else "None")
    cols[3].metric("Eastern Time", fmt_time(local_now()))
    if not calendar.empty:
        show_events_compact(8)
        view_cols = ["countdown", "local_time", "event", "importance", "market_focus", "exactness", "cause_risk", "watch_before", "watch_after", "likely_markets"]
        st.subheader("Automatic upcoming calendar")
        st.dataframe(filter_df(calendar[view_cols], "filter_calendar", "Search CPI, FOMC, NFP, oil, earnings..."), use_container_width=True, hide_index=True)
    st.subheader("Recurring market-moving event guide")
    st.dataframe(filter_df(event_watch_df(), "filter_event_guide", "Search recurring guide..."), use_container_width=True, hide_index=True)


def page_alerts() -> None:
    st.header("Alerts Center")
    alerts = pd.DataFrame(alert_rows())
    if alerts.empty:
        st.info("No alerts generated yet.")
        return
    high = alerts[alerts["priority"].eq("High")].shape[0]
    cols = st.columns(3)
    cols[0].metric("Total Alerts", len(alerts))
    cols[1].metric("High Priority", high)
    cols[2].metric("Generated", fmt_time(local_now()))
    st.dataframe(filter_df(alerts, "filter_alerts", "Search alerts..."), use_container_width=True, hide_index=True)
    st.subheader("Alert logic examples")
    examples = [
        "Dollar rising + yields rising + Nasdaq falling = liquidity pressure pattern.",
        "Gold rising despite dollar strength = possible safety/geopolitical bid.",
        "Oil rising + yields rising = inflation pressure risk.",
        "NVDA falling while QQQ holds = AI leadership warning.",
        "VIX rising while SPX is flat = hidden hedging/fear pressure.",
    ]
    for item in examples:
        st.write(f"• {item}")


def page_playbook() -> None:
    st.header("Cause & Effect Playbook")
    st.caption("Use this page for: what can cause this, what confirms it, what can invalidate it, and what to watch now.")
    st.dataframe(filter_df(cause_effect_df(), "filter_playbook", "Search dollar, yields, gold, oil, AI, inflation, recession..."), use_container_width=True, hide_index=True)


def page_scenario() -> None:
    st.header("Scenario Matrix")
    st.caption("Cross-market combinations converted into a regime read.")
    st.dataframe(filter_df(scenario_df(), "filter_scenario", "Search scenario..."), use_container_width=True, hide_index=True)


def page_geo() -> None:
    st.header("Geopolitical / Shock Watch")
    st.caption("First-order and second-order effects from headline shocks.")
    st.dataframe(filter_df(geopolitical_df(), "filter_geo", "Search shock, oil, sanctions, war, chip export controls..."), use_container_width=True, hide_index=True)


def page_charts() -> None:
    st.header("Charts")
    if combined_table.empty:
        st.info("No series loaded yet.")
        return
    groups = {
        "Liquidity": ["US Dollar Index", "US Dollar ETF", "13W T-Bill Yield", "US 5Y Yield", "US 10Y Yield", "US 30Y Yield", "Long Treasury Bond ETF", "10Y-5Y Curve Proxy"],
        "Risk": ["S&P 500", "Nasdaq 100", "QQQ", "Russell 2000", "VIX"],
        "AI": ["Nvidia", "VanEck Semiconductor ETF", "iShares Semiconductor ETF", "Microsoft", "AMD", "Broadcom"],
        "Commodities": ["Gold Futures", "WTI Crude Oil", "Copper Futures", "Uranium ETF"],
        "Crypto": ["Bitcoin"],
        "Internals": ["Equal Weight S&P 500", "Equal Weight Nasdaq 100", "High Yield Credit ETF", "Regional Banks ETF", "VIX 9-Day", "VVIX", "Technology Sector", "Financials Sector"],
        "Global": ["Global ACWI ETF", "Emerging Markets ETF", "Canada ETF", "Germany ETF", "Japan ETF", "China Large-Cap ETF", "India ETF"],
        "Inflation/Economy": ["CPI", "PPI Final Demand", "Unemployment Rate", "Nonfarm Payrolls", "Average Hourly Earnings"],
    }
    group = st.selectbox("Chart group", list(groups))
    available_names = [n for n in groups[group] if n in combined_table["name"].tolist()]
    selected = st.selectbox("Choose series", available_names or combined_table["name"].tolist())
    period = st.radio("Time window", ["1M", "3M", "6M", "1Y", "3Y", "All"], horizontal=True)
    symbol = combined_table.loc[combined_table["name"].eq(selected), "symbol"].iloc[0]
    chart_df = df[df["symbol"].eq(symbol)].sort_values("date")
    days = {"1M": 31, "3M": 93, "6M": 186, "1Y": 365, "3Y": 1095}.get(period)
    if days:
        cutoff = chart_df["date"].max() - pd.Timedelta(days=days)
        chart_df = chart_df[chart_df["date"] >= cutoff]
    if chart_df.empty:
        st.warning("No chart data for this series.")
    else:
        fig = px.line(chart_df, x="date", y="close", title=selected)
        fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)


def page_data_health() -> None:
    st.header("Data Health")
    health = data_health_summary()
    cols = st.columns(4)
    cols[0].metric("Overall", health["overall"])
    cols[1].metric("Inserted/Updated", f"{inserted_count:,}" if inserted_count is not None else "Unknown")
    cols[2].metric("Feed Issues", feed_issue_count if feed_issue_count is not None else "Unknown")
    cols[3].metric("Last Update", fmt_time(runs.iloc[0]["run_time"]) if not runs.empty else "None")
    st.info("If prices-only works but economy-only fails, market/rate/AI prices are live while BLS economic feeds are delayed. Successful feeds are still saved.")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Test prices-only feed", use_container_width=True):
            ok, msg = run_market_update()
            st.success(msg) if ok else st.error(msg)
    with c2:
        if st.button("Test economy-only feed", use_container_width=True):
            ok, msg = run_econ_update()
            st.success(msg) if ok else st.error(msg)
    with c3:
        if st.button("Test all feeds", use_container_width=True):
            ok, msg = run_update()
            st.success(msg) if ok else st.error(msg)
    st.subheader("Recent runs")
    st.dataframe(runs, use_container_width=True, hide_index=True)


def page_update_runs() -> None:
    st.header("Update Runs")
    if runs.empty:
        st.write("No update run recorded yet.")
    else:
        display = runs.copy()
        display["local_run_time"] = display["run_time"].apply(fmt_datetime)
        st.dataframe(display[["local_run_time", "status", "message"]], use_container_width=True, hide_index=True)
    st.code("python update_data.py\npython update_data.py --prices-only\npython update_data.py --econ-only\npython update_events.py\nstreamlit run app.py", language="powershell")


def page_settings() -> None:
    st.header("Settings")
    st.write("Time display is locked to your requested default:")
    st.write("• Eastern/Toronto time")
    st.write("• Regular 12-hour format")
    st.write("• Event times convert from New York release time when the event has an exact scheduled time")
    st.subheader("Run commands")
    st.code("python -m pip install -r requirements.txt\npython update_data.py\npython update_events.py\nstreamlit run app.py", language="powershell")
    st.subheader("Tracked coverage")
    macro_target = sum(1 for item in SERIES if item.module == "Macro")
    ai_target = sum(1 for item in SERIES if item.module == "AI")
    internal_target = sum(1 for item in SERIES if item.module == "Internal")
    global_target = sum(1 for item in SERIES if item.module == "Global")
    st.write(f"Macro series: **{macro_target}**")
    st.write(f"AI series: **{ai_target}**")
    st.write(f"Internal market series: **{internal_target}**")
    st.write(f"Global market series: **{global_target}**")
    st.write(f"Total tracked: **{macro_target + ai_target + internal_target + global_target}**")


# Render selected page
if page == "Dashboard":
    page_dashboard()
elif page == "Macro":
    page_macro()
elif page == "AI / Tech":
    page_ai()
elif page == "Market Internals":
    page_internal()
elif page == "Sector Rotation":
    page_internal("Sector Rotation")
elif page == "Index Components":
    page_components()
elif page == "Breadth":
    page_internal("Breadth")
elif page == "Credit":
    page_internal("Credit")
elif page == "Volatility":
    page_internal("Volatility Internals")
elif page == "Global Markets":
    page_global()
elif page == "Bonds & Rates":
    page_macro("Rates")
elif page == "Dollar":
    page_macro("Dollar")
elif page == "Commodities":
    page_macro("Commodities")
elif page == "Crypto":
    page_macro("Crypto")
elif page == "Geopolitics":
    page_geo()
elif page == "Event Watch":
    page_event_watch()
elif page == "Alerts Center":
    page_alerts()
elif page == "Playbook":
    page_playbook()
elif page == "Scenario Matrix":
    page_scenario()
elif page == "Charts":
    page_charts()
elif page == "Data Health":
    page_data_health()
elif page == "Update Runs":
    page_update_runs()
elif page == "Settings":
    page_settings()
