"""Automatic event calendar for Macro Regime Engine v4.

The goal is to remove the need to hand-type dates.

How it works:
1. Try to pull exact official schedules from public pages when internet is available.
2. Add known/high-confidence scheduled events from embedded calendars.
3. Generate rule-based estimates for recurring events where exact public dates are not available.
4. Label each row as Official, Preset, Estimated, Weekly, or Optional API.

This keeps the dashboard useful even offline, while still upgrading itself when live sources work.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

REQUEST_TIMEOUT = 5
USER_AGENT = "MacroRegimeEngine/0.4 (+local dashboard)"
EVENT_COLUMNS = [
    "date",
    "day",
    "time_et",
    "event",
    "importance",
    "market_focus",
    "source",
    "exactness",
    "cause_risk",
    "watch_before",
    "watch_after",
    "likely_markets",
]


@dataclass(frozen=True)
class EventTemplate:
    event: str
    time_et: str
    importance: str
    market_focus: str
    cause_risk: str
    watch_before: str
    watch_after: str
    likely_markets: str


TEMPLATES: dict[str, EventTemplate] = {
    "CPI Inflation": EventTemplate(
        "CPI Inflation",
        "08:30",
        "High",
        "Inflation / rates / dollar / gold / AI growth",
        "Hot CPI can push 2Y/10Y yields and dollar up, pressuring QQQ/AI/gold. Soft CPI can create inflation-relief rally.",
        "Mark pre-release high/low; check DXY, 2Y, 10Y, QQQ, SMH, gold, VIX.",
        "Do not trust first spike only. Watch whether yields/dollar hold or fully reverse after 5-30 minutes.",
        "DXY, DGS2, DGS10, QQQ, SMH, NVDA, GLD, BTC, VIX",
    ),
    "PPI Inflation": EventTemplate(
        "PPI Inflation",
        "08:30",
        "Medium/High",
        "Wholesale inflation / margins / rates",
        "Hot PPI can raise inflation fear before CPI/PCE; soft PPI can cool rate pressure.",
        "Check if CPI/PCE sensitivity is active; compare dollar/yields reaction.",
        "If PPI moves yields but equities ignore it, the market may wait for CPI/PCE confirmation.",
        "DXY, DGS2, DGS10, SPY, QQQ, GLD",
    ),
    "Employment Situation / NFP": EventTemplate(
        "Employment Situation / NFP",
        "08:30",
        "High",
        "Labor / Fed / growth",
        "Strong jobs/wages can lift yields/dollar; weak jobs can cause recession fear or rate-cut relief.",
        "Separate payrolls, unemployment rate, and average hourly earnings. Check 2Y first.",
        "Second move matters. Strong headline with weak wages can reverse; weak headline with lower wages can risk-on.",
        "DGS2, DXY, QQQ, SPY, IWM, GLD, VIX",
    ),
    "Initial Jobless Claims": EventTemplate(
        "Initial Jobless Claims",
        "08:30",
        "Medium",
        "Labor stress / growth scare",
        "Rising claims can support cuts but hurt risk if the market reads recession stress.",
        "Check whether market is trading growth scare or inflation relief narrative.",
        "Claims only matter broadly if yields, dollar, and equities confirm the labor signal.",
        "DGS2, DXY, SPY, QQQ, IWM, VIX",
    ),
    "FOMC Statement": EventTemplate(
        "FOMC Statement",
        "14:00",
        "Extreme",
        "Fed policy / rates / dollar / risk",
        "Hawkish tone can pressure bonds, AI, equities and gold; dovish tone can ease liquidity if growth is stable.",
        "Know current market expectation; mark pre-FOMC range; avoid overtrusting the first statement move.",
        "Watch 14:00 statement reaction, then 14:30 Powell reaction. Real acceptance usually happens after the press conference.",
        "DGS2, DGS10, DXY, SPY, QQQ, SMH, GLD, VIX",
    ),
    "FOMC Press Conference": EventTemplate(
        "FOMC Press Conference",
        "14:30",
        "Extreme",
        "Fed tone / second reaction",
        "Powell Q&A can reverse the statement move or confirm it into trend continuation.",
        "Do not size aggressively before Q&A if the statement move is thin or one-sided.",
        "Acceptance after Q&A matters more than the first 14:00 impulse.",
        "DGS2, DGS10, DXY, SPY, QQQ, SMH, GLD, VIX",
    ),
    "PCE Inflation": EventTemplate(
        "PCE Inflation",
        "08:30",
        "High",
        "Fed-preferred inflation / rates",
        "Soft PCE can support rate-cut expectations; hot PCE can restart yield/dollar pressure.",
        "Check CPI/PPI context, 2Y yield, DXY, QQQ, gold.",
        "If yields fall but equities sell off, it may be growth fear, not clean inflation relief.",
        "DGS2, DGS10, DXY, QQQ, GLD, VIX",
    ),
    "ISM Manufacturing": EventTemplate(
        "ISM Manufacturing",
        "10:00",
        "Medium/High",
        "Growth / prices paid / industrials",
        "Weak new orders can signal growth scare; hot prices paid can pressure bonds.",
        "Watch copper, dollar, yields, industrials, small caps.",
        "Headline matters less than new orders, employment, and prices paid combination.",
        "DGS10, DXY, COPX, IWM, SPY, VIX",
    ),
    "ISM Services": EventTemplate(
        "ISM Services",
        "10:00",
        "High",
        "Services inflation / employment / growth",
        "Services prices/employment can reprice Fed expectations and move yields/dollar.",
        "Check QQQ/SPY location and 2Y/dollar before 10:00.",
        "If services prices spike and 2Y holds bid, growth/AI pressure can build.",
        "DGS2, DGS10, DXY, QQQ, SPY, VIX",
    ),
    "Retail Sales": EventTemplate(
        "Retail Sales",
        "08:30",
        "Medium/High",
        "Consumer demand / growth / inflation",
        "Strong sales can support growth but also lift yields; weak sales can start growth-scare reaction.",
        "Check discretionary stocks, yields, dollar, oil/gasoline backdrop.",
        "Classify reaction by yields: growth-on if equities rise calmly; stress if yields jump and QQQ rejects.",
        "DGS10, DXY, XLY, SPY, QQQ, VIX",
    ),
    "GDP": EventTemplate(
        "GDP",
        "08:30",
        "Medium/High",
        "Growth / recession / rates",
        "Strong GDP with calm inflation is risk support; strong GDP with yield spike can pressure growth.",
        "Check prior growth narrative, dollar, yields, copper, IWM.",
        "GDP revisions can matter less than inflation/labor unless market is already sensitive to growth risk.",
        "DGS10, DXY, SPY, IWM, copper, VIX",
    ),
    "EIA Crude Oil Inventories": EventTemplate(
        "EIA Crude Oil Inventories",
        "10:30",
        "Medium",
        "Oil / inflation / energy shock",
        "Inventory shock can move oil; broad macro impact needs oil move to hold and affect inflation/yields.",
        "Check oil structure, energy equities, dollar, inflation narrative.",
        "Oil spike matters more if DXY/yields/gold also react in inflation/fear direction.",
        "CL/OIL, XLE, DXY, DGS10, GLD",
    ),
    "Treasury Auction Watch": EventTemplate(
        "Treasury Auction Watch",
        "13:00",
        "Medium/High",
        "Bond supply / yields / equity pressure",
        "Weak auction demand can push yields up and pressure QQQ/AI; strong demand can give bond relief.",
        "Check 10Y/30Y, TLT, dollar, QQQ around 13:00 ET.",
        "Auction only matters if yields move and hold after the result.",
        "DGS10, DGS30, TLT, DXY, QQQ, SMH",
    ),
    "AI Mega-cap Earnings Watch": EventTemplate(
        "AI Mega-cap Earnings Watch",
        "After close / Before open",
        "High",
        "AI leadership / Nasdaq / semis",
        "AI earnings/guidance can shift Nasdaq and semiconductor leadership quickly.",
        "Check AI score, SMH/SOXX, QQQ, yields, and whether expectations are crowded.",
        "Guidance, capex, margins, and data-center demand often matter more than EPS headline.",
        "NVDA, MSFT, GOOGL, AMZN, META, AMD, AVGO, SMH, QQQ",
    ),
}

# Exact or known-high-confidence dates visible in official/current calendars when v4 was built.
# They keep the calendar useful even before live official page parsing succeeds.
PRESET_EVENTS: list[dict[str, str]] = [
    {"date": "2026-07-02", "event": "Employment Situation / NFP", "source": "Preset BLS schedule", "exactness": "Preset official date"},
    {"date": "2026-08-07", "event": "Employment Situation / NFP", "source": "Preset BLS schedule", "exactness": "Preset official date"},
    {"date": "2026-09-04", "event": "Employment Situation / NFP", "source": "Preset BLS schedule", "exactness": "Preset official date"},
    {"date": "2026-10-02", "event": "Employment Situation / NFP", "source": "Preset BLS schedule", "exactness": "Preset official date"},
    {"date": "2026-11-06", "event": "Employment Situation / NFP", "source": "Preset BLS schedule", "exactness": "Preset official date"},
    {"date": "2026-12-04", "event": "Employment Situation / NFP", "source": "Preset BLS schedule", "exactness": "Preset official date"},
    {"date": "2026-07-14", "event": "CPI Inflation", "source": "Preset BLS schedule", "exactness": "Preset official date"},
    {"date": "2026-08-12", "event": "CPI Inflation", "source": "Preset BLS schedule", "exactness": "Preset official date"},
    {"date": "2026-09-11", "event": "CPI Inflation", "source": "Preset BLS schedule", "exactness": "Preset official date"},
    {"date": "2026-10-14", "event": "CPI Inflation", "source": "Preset BLS schedule", "exactness": "Preset official date"},
    {"date": "2026-11-10", "event": "CPI Inflation", "source": "Preset BLS schedule", "exactness": "Preset official date"},
    {"date": "2026-12-10", "event": "CPI Inflation", "source": "Preset BLS schedule", "exactness": "Preset official date"},
    {"date": "2026-07-29", "event": "FOMC Statement", "source": "Preset Federal Reserve schedule", "exactness": "Preset official date"},
    {"date": "2026-07-29", "event": "FOMC Press Conference", "source": "Preset Federal Reserve schedule", "exactness": "Preset official date"},
    {"date": "2026-09-16", "event": "FOMC Statement", "source": "Preset Federal Reserve schedule", "exactness": "Preset official date"},
    {"date": "2026-09-16", "event": "FOMC Press Conference", "source": "Preset Federal Reserve schedule", "exactness": "Preset official date"},
    {"date": "2026-10-28", "event": "FOMC Statement", "source": "Preset Federal Reserve schedule", "exactness": "Preset official date"},
    {"date": "2026-10-28", "event": "FOMC Press Conference", "source": "Preset Federal Reserve schedule", "exactness": "Preset official date"},
    {"date": "2026-12-09", "event": "FOMC Statement", "source": "Preset Federal Reserve schedule", "exactness": "Preset official date"},
    {"date": "2026-12-09", "event": "FOMC Press Conference", "source": "Preset Federal Reserve schedule", "exactness": "Preset official date"},
]


def _today() -> pd.Timestamp:
    return pd.Timestamp(date.today()).normalize()


def _ensure_timestamp(value: str | date | datetime | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(value).normalize()


def _business_day(year: int, month: int, ordinal: int) -> pd.Timestamp:
    days = pd.bdate_range(start=f"{year}-{month:02d}-01", end=f"{year}-{month:02d}-28")
    # Extend to month-end for months with more days.
    days = pd.bdate_range(start=f"{year}-{month:02d}-01", end=(pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)))
    return days[ordinal - 1]


def _last_business_day(year: int, month: int) -> pd.Timestamp:
    return pd.bdate_range(start=f"{year}-{month:02d}-01", end=(pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)))[-1]


def _nth_weekday(year: int, month: int, weekday: int, ordinal: int) -> pd.Timestamp:
    start = pd.Timestamp(year=year, month=month, day=1)
    end = start + pd.offsets.MonthEnd(0)
    days = [d for d in pd.date_range(start, end, freq="D") if d.weekday() == weekday]
    return pd.Timestamp(days[ordinal - 1])


def _weekly_dates(start: pd.Timestamp, end: pd.Timestamp, weekday: int) -> list[pd.Timestamp]:
    # Monday=0 ... Sunday=6
    first = start + pd.Timedelta(days=(weekday - start.weekday()) % 7)
    return list(pd.date_range(first, end, freq="7D"))


def _event_row(event_date: pd.Timestamp | str, event: str, source: str, exactness: str) -> dict[str, str]:
    template = TEMPLATES[event]
    d = _ensure_timestamp(event_date)
    return {
        "date": d.strftime("%Y-%m-%d"),
        "day": d.strftime("%a"),
        "time_et": template.time_et,
        "event": event,
        "importance": template.importance,
        "market_focus": template.market_focus,
        "source": source,
        "exactness": exactness,
        "cause_risk": template.cause_risk,
        "watch_before": template.watch_before,
        "watch_after": template.watch_after,
        "likely_markets": template.likely_markets,
    }


def _append_rows(rows: list[dict[str, str]], dates: Iterable[pd.Timestamp], event: str, source: str, exactness: str) -> None:
    for d in dates:
        rows.append(_event_row(d, event, source, exactness))


def _official_bls_rows(today: pd.Timestamp, end: pd.Timestamp) -> list[dict[str, str]]:
    """Fetch exact BLS CPI/NFP/PPI dates from public schedule tables if available."""
    pages = [
        ("https://www.bls.gov/schedule/news_release/cpi.htm", "CPI Inflation"),
        ("https://www.bls.gov/schedule/news_release/empsit.htm", "Employment Situation / NFP"),
        ("https://www.bls.gov/schedule/news_release/ppi.htm", "PPI Inflation"),
    ]
    rows: list[dict[str, str]] = []
    headers = {"User-Agent": USER_AGENT}
    for url, event in pages:
        try:
            html = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT).text
            tables = pd.read_html(html)
        except Exception:
            continue
        for table in tables:
            columns = [str(c).strip().lower() for c in table.columns]
            date_col = next((table.columns[i] for i, c in enumerate(columns) if "release date" in c), None)
            time_col = next((table.columns[i] for i, c in enumerate(columns) if "release time" in c), None)
            if date_col is None:
                continue
            for _, record in table.iterrows():
                raw_date = str(record.get(date_col, "")).strip()
                if not raw_date or raw_date.lower() == "nan":
                    continue
                try:
                    # Add the year if pandas cannot infer it from text, using current/end year windows.
                    parsed = pd.to_datetime(raw_date, errors="coerce")
                    if pd.isna(parsed):
                        continue
                    d = pd.Timestamp(parsed).normalize()
                    if d.year < today.year:
                        d = d.replace(year=today.year)
                except Exception:
                    continue
                if today <= d <= end:
                    row = _event_row(d, event, "Official BLS schedule page", "Official fetched")
                    if time_col is not None and str(record.get(time_col, "")).strip().lower() != "nan":
                        raw_time = str(record.get(time_col, "")).strip().replace(" AM", "").replace(" PM", "")
                        if raw_time:
                            row["time_et"] = raw_time[:5]
                    rows.append(row)
            if rows:
                # Keep scanning other pages but avoid duplicate tables on same page.
                break
    return rows


def _official_fed_rows(today: pd.Timestamp, end: pd.Timestamp) -> list[dict[str, str]]:
    """Best-effort parse of Federal Reserve FOMC dates. Falls back to presets if parsing fails."""
    url = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    try:
        html = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT).text
        tables = pd.read_html(html)
    except Exception:
        return []

    rows: list[dict[str, str]] = []
    # Official page layout changes, so parse date-looking cells in a forgiving way.
    for table in tables:
        text_cells = table.astype(str).stack().tolist()
        for text in text_cells:
            if not any(month in text for month in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "January", "February", "March", "April", "June", "July", "September", "October", "December"]):
                continue
            # Keep this conservative; presets handle current year exactly.
            # If the page has easy-to-parse dates, pandas will often parse the last day in the range.
            try:
                parsed = pd.to_datetime(text, errors="coerce")
            except Exception:
                parsed = pd.NaT
            if pd.isna(parsed):
                continue
            d = pd.Timestamp(parsed).normalize()
            if today <= d <= end:
                rows.append(_event_row(d, "FOMC Statement", "Official Federal Reserve page", "Official fetched"))
                rows.append(_event_row(d, "FOMC Press Conference", "Official Federal Reserve page", "Official fetched"))
    return rows


def _read_env_key(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    env_file = Path(".env")
    if not env_file.exists():
        return ""
    try:
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            if key.strip() == name:
                return raw_value.strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def _trading_economics_rows(today: pd.Timestamp, end: pd.Timestamp) -> list[dict[str, str]]:
    """Optional live calendar source. Requires TRADING_ECONOMICS_KEY in .env/environment."""
    key = _read_env_key("TRADING_ECONOMICS_KEY")
    if not key:
        return []
    url = "https://api.tradingeconomics.com/calendar"
    params = {
        "c": key,
        "country": "United States",
        "d1": today.strftime("%Y-%m-%d"),
        "d2": end.strftime("%Y-%m-%d"),
        "format": "json",
    }
    try:
        response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    rows: list[dict[str, str]] = []
    keywords = {
        "cpi": "CPI Inflation",
        "consumer price": "CPI Inflation",
        "payroll": "Employment Situation / NFP",
        "employment": "Employment Situation / NFP",
        "jobless": "Initial Jobless Claims",
        "pce": "PCE Inflation",
        "ism manufacturing": "ISM Manufacturing",
        "ism services": "ISM Services",
        "retail sales": "Retail Sales",
        "gdp": "GDP",
        "crude oil inventories": "EIA Crude Oil Inventories",
    }
    for item in data if isinstance(data, list) else []:
        name = str(item.get("Event") or item.get("event") or "").lower()
        match = next((event for key_word, event in keywords.items() if key_word in name), None)
        if not match:
            continue
        raw_date = item.get("Date") or item.get("date")
        if not raw_date:
            continue
        try:
            dt = pd.Timestamp(raw_date)
        except Exception:
            continue
        d = dt.normalize()
        if today <= d <= end:
            row = _event_row(d, match, "Trading Economics API", "Live API")
            if dt.hour or dt.minute:
                row["time_et"] = dt.strftime("%H:%M")
            rows.append(row)
    return rows


def _estimated_rows(today: pd.Timestamp, end: pd.Timestamp) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    # Weekly known recurring events.
    _append_rows(rows, _weekly_dates(today, end, 3), "Initial Jobless Claims", "Automatic weekly schedule", "Weekly rule")  # Thu
    _append_rows(rows, _weekly_dates(today, end, 2), "EIA Crude Oil Inventories", "Automatic weekly schedule", "Weekly rule")  # Wed

    # Monthly rules. Exact dates can be overwritten by official/preset rows.
    cursor = pd.Timestamp(year=today.year, month=today.month, day=1)
    while cursor <= end:
        year = int(cursor.year)
        month = int(cursor.month)
        candidates = [
            (_business_day(year, month, 1), "ISM Manufacturing", "Auto calendar estimate", "Estimated recurring rule"),
            (_business_day(year, month, 3), "ISM Services", "Auto calendar estimate", "Estimated recurring rule"),
            (_nth_weekday(year, month, 4, 1), "Employment Situation / NFP", "Auto calendar estimate", "Estimated recurring rule"),
            (_business_day(year, month, 8), "CPI Inflation", "Auto calendar estimate", "Estimated recurring rule"),
            (_business_day(year, month, 9), "PPI Inflation", "Auto calendar estimate", "Estimated recurring rule"),
            (_business_day(year, month, 11), "Retail Sales", "Auto calendar estimate", "Estimated recurring rule"),
            (_last_business_day(year, month), "PCE Inflation", "Auto calendar estimate", "Estimated recurring rule"),
        ]
        # GDP: last Thursday-ish in Jan/Apr/Jul/Oct plus revisions after.
        if month in {1, 4, 7, 10}:
            candidates.append((_last_business_day(year, month) - pd.offsets.BDay(1), "GDP", "Auto calendar estimate", "Estimated recurring rule"))
        # Auction watch windows around common refunding/auction days. This is a watch placeholder, not exact CUSIP auction detail.
        candidates.extend(
            [
                (_business_day(year, month, 12), "Treasury Auction Watch", "Auto calendar estimate", "Estimated recurring watch window"),
                (_business_day(year, month, 18), "Treasury Auction Watch", "Auto calendar estimate", "Estimated recurring watch window"),
            ]
        )
        # AI earnings windows. These are watch windows because exact earnings dates move.
        if month in {2, 5, 8, 11}:
            candidates.append((_business_day(year, month, 18), "AI Mega-cap Earnings Watch", "Auto AI earnings season estimate", "Estimated earnings window"))
            candidates.append((_business_day(year, month, 20), "AI Mega-cap Earnings Watch", "Auto AI earnings season estimate", "Estimated earnings window"))
        for d, event, source, exactness in candidates:
            d = pd.Timestamp(d).normalize()
            if today <= d <= end:
                rows.append(_event_row(d, event, source, exactness))
        cursor = cursor + pd.offsets.MonthBegin(1)
    return rows


def _preset_rows(today: pd.Timestamp, end: pd.Timestamp) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in PRESET_EVENTS:
        d = _ensure_timestamp(item["date"])
        if today <= d <= end:
            rows.append(_event_row(d, item["event"], item["source"], item["exactness"]))
    return rows


def build_auto_event_calendar(
    today: str | date | datetime | pd.Timestamp | None = None,
    months_ahead: int = 6,
    include_live_sources: bool = True,
) -> pd.DataFrame:
    start = _ensure_timestamp(today) if today is not None else _today()
    end = start + pd.DateOffset(months=months_ahead)

    rows: list[dict[str, str]] = []
    rows.extend(_estimated_rows(start, end))
    rows.extend(_preset_rows(start, end))
    if include_live_sources:
        rows.extend(_official_bls_rows(start, end))
        rows.extend(_official_fed_rows(start, end))
        rows.extend(_trading_economics_rows(start, end))

    if not rows:
        return pd.DataFrame(columns=EVENT_COLUMNS)

    df = pd.DataFrame(rows)
    for col in EVENT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["priority"] = df["exactness"].map(
        {
            "Live API": 5,
            "Official fetched": 4,
            "Preset official date": 3,
            "Weekly rule": 2,
            "Estimated recurring watch window": 1,
            "Estimated earnings window": 1,
            "Estimated recurring rule": 1,
        }
    ).fillna(0)
    # Deduplicate by same date/event, keeping the most exact version.
    df = df.sort_values(["date", "event", "priority"], ascending=[True, True, False])
    df = df.drop_duplicates(subset=["date", "event"], keep="first")
    df["day"] = df["date"].dt.strftime("%a")
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df = df.sort_values(["date", "time_et", "importance", "event"])
    return df[EVENT_COLUMNS]


def event_summary(calendar: pd.DataFrame, days: int = 7) -> dict[str, int | str]:
    if calendar.empty:
        return {"next_event": "None", "events_next_window": 0, "high_importance_next_window": 0}
    today = _today()
    horizon = today + pd.Timedelta(days=days)
    dates = pd.to_datetime(calendar["date"], errors="coerce")
    upcoming = calendar[(dates >= today) & (dates <= horizon)].copy()
    high = upcoming[upcoming["importance"].astype(str).str.contains("High|Extreme", case=False, regex=True)]
    next_event = calendar.iloc[0]
    return {
        "next_event": f"{next_event['date']} {next_event['time_et']} ET - {next_event['event']}",
        "events_next_window": int(len(upcoming)),
        "high_importance_next_window": int(len(high)),
    }


if __name__ == "__main__":
    cal = build_auto_event_calendar()
    print(cal.to_string(index=False))
