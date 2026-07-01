"""Macro Regime Engine v7.4 unified command-center dashboard."""

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

APP_VERSION = "v7.4"
DB_PATH = Path(DATABASE_PATH)
LOCAL_TZ = datetime.now().astimezone().tzinfo
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
    return datetime.now().astimezone()


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
            <div class="card-sub">Local time shown in regular 12-hour format.</div>
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
# Unified command bar + search
# -----------------------------------------------------------------------------
bg_running, bg_detail = background_updater_status()
age = seconds_since_last_run(runs)
live_klass = "good" if age is not None and age <= 45 else "warn" if age is not None and age <= 180 else "bad"
errors = feed_issue_count if feed_issue_count is not None else 0
inserted = inserted_count if inserted_count is not None else 0
health_overall = "Operational" if inserted > 0 and errors == 0 else "Partial" if inserted > 0 else "No Data"
health_klass = "good" if health_overall == "Operational" else "warn" if health_overall == "Partial" else "bad"
now = local_now()

st.markdown(
    f'''
    <div class="command-shell">
        <div class="command-title">Unified Command Center · Search · Live Status · Local 12-Hour Time</div>
    </div>
    ''',
    unsafe_allow_html=True,
)
cmd_search, cmd_time, cmd_live, cmd_data, cmd_start, cmd_stop, cmd_update = st.columns([4.2, .75, .85, 1.0, .68, .55, .62])
with cmd_search:
    global_query = st.text_input(
        "Search anything",
        placeholder="Search everything... NDX, QQQ, NVDA, internals, breadth, credit, gold, yields, dollar, CPI, FOMC, oil",
        label_visibility="collapsed",
        key="main_global_search",
    )
with cmd_time:
    st.markdown(f'<div class="command-status"><b>{fmt_time(now)}</b><br><span class="muted">Local</span></div>', unsafe_allow_html=True)
with cmd_live:
    st.markdown(
        f'<div class="command-status"><b>Pulse</b><br>{status_badge("LIVE" if live_klass == "good" else "STALE", live_klass)} <span class="muted">{human_age(age)}</span></div>',
        unsafe_allow_html=True,
    )
with cmd_data:
    health_detail = f"{inserted:,} saved" if inserted else "Run update"
    st.markdown(
        f'<div class="command-status"><b>Data</b><br>{status_badge(health_overall, health_klass)} <span class="muted">{health_detail}</span></div>',
        unsafe_allow_html=True,
    )
with cmd_start:
    if st.button("Start", use_container_width=True, help="Start background live updater"):
        ok, msg = start_background_updater(15)
        st.toast(msg, icon="✅" if ok else "⚠️")
        st.rerun()
with cmd_stop:
    if st.button("Stop", use_container_width=True, help="Stop background live updater"):
        ok, msg = stop_background_updater()
        st.toast(msg, icon="✅" if ok else "⚠️")
        st.rerun()
with cmd_update:
    if st.button("Now", use_container_width=True, help="Run one live update now"):
        ok, msg = run_update()
        st.toast("Live update complete" if ok else "Live update issue", icon="✅" if ok else "⚠️")
        if not ok:
            st.warning(msg[:900])
        st.rerun()

# No automatic browser reload. Data updates are handled by live_updater.py in the background.

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

def show_search_results(query: str) -> bool:
    q = query.strip()
    if not q:
        return False

    topic_key, bundle = identify_search_topic(q)
    title = str(bundle.get("title")) if bundle else q.upper()
    st.markdown(f"### Search Intelligence: {title}")
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
    rates_score = safe_num(macro_cats[macro_cats["category"].eq("Rates")]["score"].iloc[0]) if not macro_cats[macro_cats["category"].eq("Rates")].empty else 0
    dollar_score = safe_num(macro_cats[macro_cats["category"].eq("Dollar")]["score"].iloc[0]) if not macro_cats[macro_cats["category"].eq("Dollar")].empty else 0
    commod_score = safe_num(macro_cats[macro_cats["category"].eq("Commodities")]["score"].iloc[0]) if not macro_cats[macro_cats["category"].eq("Commodities")].empty else 0
    sentiment = max(0, min(100, int((macro_result.score + 100) / 2)))
    liquidity_score = (rates_score + dollar_score) / 2.0
    risk_sentiment_score = (macro_result.score + ai_result.score + internal_result.score + global_result.score) / 4.0

    st.markdown("#### Regime Meter Gauges")
    meter_cols = st.columns(5)
    with meter_cols[0]:
        show_meter("Macro", macro_result.score, macro_result.regime)
    with meter_cols[1]:
        show_meter("AI Growth", ai_result.score, ai_result.regime)
    with meter_cols[2]:
        show_meter("Internals", internal_result.score, internal_result.regime)
    with meter_cols[3]:
        show_meter("Liquidity", liquidity_score, "Bonds + dollar pressure")
    with meter_cols[4]:
        show_meter("Risk", risk_sentiment_score, "Composite market tone")

    top_a, top_b, top_c, top_d = st.columns(4)
    with top_a:
        regime_card("Macro", macro_result.regime.replace(" / ", "/"), "Liquidity / risk", macro_result.score)
    with top_b:
        regime_card("AI / Tech", ai_result.regime.replace(" / ", "/"), "Leadership", ai_result.score, "purple" if ai_result.score >= 0 else "warn")
    with top_c:
        regime_card("Internals", internal_result.regime.replace(" / ", "/"), "Breadth / sectors / credit", internal_result.score)
    with top_d:
        regime_card("Global", global_result.regime.replace(" / ", "/"), "World confirmation", global_result.score)

    top2_a, top2_b, top2_c, top2_d = st.columns([1.0, 1.0, 1.0, 1.25])
    with top2_a:
        regime_card("Bonds", "Yields Firm" if rates_score < -10 else "Yield Relief" if rates_score > 10 else "Mixed", "Rate pressure", rates_score)
    with top2_b:
        regime_card("Dollar", "DXY Strong" if dollar_score < -10 else "DXY Soft" if dollar_score > 10 else "Mixed", "Dollar pressure", -dollar_score)
    with top2_c:
        regime_card("Commodities", "Inflation Watch" if commod_score < -10 else "Growth Support" if commod_score > 10 else "Mixed", "Gold / oil / copper", commod_score)
    with top2_d:
        show_data_health_compact()

    row1_a, row1_b, row1_c, row1_d = st.columns([1.45, 1.25, 1.25, 1.15])
    with row1_a:
        st.markdown('<div class="card"><div class="card-title">What Matters Now</div>', unsafe_allow_html=True)
        for idx, item in enumerate(what_matters_now(), start=1):
            klass = "bad" if any(w in item.lower() for w in ["pressure", "risk-off", "weak", "rising"] ) else "warn"
            st.markdown(f'<div class="line-item"><div class="{klass}"><b>{idx})</b></div><div>{item}</div></div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with row1_b:
        st.markdown('<div class="card"><div class="card-title">Next Major Event</div>', unsafe_allow_html=True)
        if calendar.empty:
            st.write("No event calendar loaded.")
        else:
            e = calendar.iloc[0]
            st.markdown(f'<div class="big-num warn">{e["countdown"]}</div>', unsafe_allow_html=True)
            st.markdown(f"**{e['event']}**")
            st.write(e["local_time"])
            st.caption("Why it matters")
            st.write(e.get("cause_risk", ""))
            st.caption("What to watch")
            st.write(e.get("watch_before", ""))
        st.markdown("</div>", unsafe_allow_html=True)
    with row1_c:
        show_alerts_compact(5)
    with row1_d:
        show_events_compact(5)

    st.subheader("Market Snapshot")
    market_snapshot_cards()

    r2a, r2b, r2c, r2d = st.columns([1.35, 1.2, 1.2, 1.0])
    with r2a:
        show_playbook_gold_card()
    with r2b:
        st.markdown('<div class="card"><div class="card-title">AI / Tech Leaders</div>', unsafe_allow_html=True)
        ai_leaders = ai_table[ai_table["category"].eq("AI Leaders")].copy()
        if ai_leaders.empty:
            st.write("No AI leader data loaded.")
        else:
            view = _format_view(ai_leaders).sort_values("score", ascending=False)
            st.dataframe(view[["symbol", "latest_close", "change_pct", "score"]], use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with r2c:
        st.markdown('<div class="card"><div class="card-title">Scenario Matrix</div>', unsafe_allow_html=True)
        st.dataframe(scenario_df().head(5), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with r2d:
        st.markdown('<div class="card"><div class="card-title">Live Source Map</div>', unsafe_allow_html=True)
        st.markdown('<div class="line-item"><div style="flex:1">Prices / AI / commodities</div><span class="badge good">yfinance</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="line-item"><div style="flex:1">Economy / inflation / jobs</div><span class="badge good">BLS</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="line-item"><div style="flex:1">Internals / sectors / credit</div><span class="badge good">yfinance</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="line-item"><div style="flex:1">Global market proxies</div><span class="badge good">yfinance</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="line-item"><div style="flex:1">Curves</div><span class="badge info">computed</span></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        f"<div class='footer-bar'>Last Updated: {latest_update_text(runs)} &nbsp; • &nbsp; All displayed event times are local 12-hour time &nbsp; • &nbsp; Data Source: live yfinance + BLS + internals + global proxies + computed curves</div>",
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
    st.caption("Automatic calendar. Times are converted from official/release time to your local 12-hour time when exact time is available.")
    cols = st.columns(4)
    cols[0].metric("Upcoming Events", len(calendar))
    cols[1].metric("High / Extreme", int(calendar[calendar["importance"].astype(str).str.contains("High|Extreme", case=False, regex=True)].shape[0]) if not calendar.empty else 0)
    cols[2].metric("Next Event", str(calendar.iloc[0]["event"])[:22] if not calendar.empty else "None")
    cols[3].metric("Local Time", fmt_time(local_now()))
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
    st.write("• Local computer time")
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
