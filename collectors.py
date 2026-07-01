"""Live-only data collection utilities for Macro Regime Engine v7.

No demo path and no FRED dependency.
- yfinance: market prices, AI stocks, ETFs, commodity futures, crypto, yield proxies
- BLS public API: CPI, unemployment, nonfarm payrolls, PPI, wages
- computed: curve proxies generated from live yield proxies
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Iterable
from urllib.parse import quote

import pandas as pd
import requests
from pandas.tseries.offsets import MonthEnd

from config import SERIES, SeriesConfig

REQUEST_TIMEOUT = 45
BLS_REQUEST_TIMEOUT = 45
REQUEST_RETRIES = 3
USER_AGENT = "MacroRegimeEngine/0.7 (live-only local dashboard)"


class DataFetchError(RuntimeError):
    pass


def _get_json(url: str, timeout: int = REQUEST_TIMEOUT, retries: int = REQUEST_RETRIES) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            if response.status_code != 200:
                raise DataFetchError(f"HTTP {response.status_code}: {url}")
            return response.json()
        except Exception as exc:  # noqa: BLE001 - show feed issue clearly
            last_error = exc
            if attempt < retries:
                time.sleep(1.2 * attempt)
    raise DataFetchError(str(last_error))


def fetch_yfinance_series(series: SeriesConfig, period: str = "3y") -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise DataFetchError("yfinance is not installed. Run: python -m pip install -r requirements.txt") from exc

    try:
        raw = yf.download(
            tickers=series.symbol,
            period=period,
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False,
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as exc:
        raise DataFetchError(f"yfinance download failed for {series.symbol}: {exc}") from exc

    if raw.empty:
        raise DataFetchError(f"yfinance returned no rows for {series.symbol}")

    if isinstance(raw.columns, pd.MultiIndex):
        if ("Close", series.symbol) in raw.columns:
            close = raw[("Close", series.symbol)]
        elif "Close" in raw.columns.get_level_values(0):
            close = raw.xs("Close", axis=1, level=0).iloc[:, 0]
        else:
            raise DataFetchError(f"Unexpected yfinance columns for {series.symbol}: {raw.columns.tolist()}")
    elif "Close" in raw.columns:
        close = raw["Close"]
    elif "Adj Close" in raw.columns:
        close = raw["Adj Close"]
    else:
        raise DataFetchError(f"Unexpected yfinance columns for {series.symbol}: {raw.columns.tolist()}")

    df = pd.DataFrame({"date": close.index, "close": close.to_numpy()})
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.tz_localize(None)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"])
    if df.empty:
        raise DataFetchError(f"yfinance returned no clean close values for {series.symbol}")
    return _attach_metadata(df, series)


def _bls_start_year(years_back: int = 4) -> int:
    return max(2000, date.today().year - years_back)


def fetch_bls_series(series: SeriesConfig) -> pd.DataFrame:
    """Fetch a BLS time series using the no-key v1 public endpoint.

    This avoids FRED. BLS v1 usually returns recent history; enough for the
    dashboard's short/medium regime score.
    """
    url = f"https://api.bls.gov/publicAPI/v1/timeseries/data/{quote(series.symbol)}"
    data = _get_json(url, timeout=BLS_REQUEST_TIMEOUT, retries=REQUEST_RETRIES)

    status = str(data.get("status", ""))
    if status.upper() != "REQUEST_SUCCEEDED":
        messages = data.get("message") or []
        raise DataFetchError(f"BLS request failed for {series.symbol}: {messages}")

    series_blocks = data.get("Results", {}).get("series", [])
    if not series_blocks:
        raise DataFetchError(f"BLS returned no series block for {series.symbol}")

    rows: list[dict[str, object]] = []
    for item in series_blocks[0].get("data", []):
        period = str(item.get("period", ""))
        if not period.startswith("M") or period == "M13":
            continue
        try:
            year = int(item["year"])
            month = int(period[1:])
            value = float(str(item["value"]).replace(",", ""))
        except Exception:
            continue
        if year < _bls_start_year():
            continue
        dt = pd.Timestamp(year=year, month=month, day=1) + MonthEnd(0)
        rows.append({"date": dt, "close": value})

    if not rows:
        raise DataFetchError(f"BLS returned no recent monthly observations for {series.symbol}")
    df = pd.DataFrame(rows).sort_values("date")
    return _attach_metadata(df, series)


def _attach_metadata(df: pd.DataFrame, series: SeriesConfig) -> pd.DataFrame:
    out = df.copy()
    out["symbol"] = series.symbol
    out["name"] = series.name
    out["source"] = series.source
    out["category"] = series.category
    out["module"] = series.module
    return out[["symbol", "name", "source", "category", "module", "date", "close"]]


def fetch_series(series: SeriesConfig) -> pd.DataFrame:
    if series.source == "yfinance":
        return fetch_yfinance_series(series)
    if series.source == "bls":
        return fetch_bls_series(series)
    if series.source == "computed":
        raise DataFetchError("computed series are generated after base live feeds are loaded")
    raise ValueError(f"Unsupported source: {series.source}")


def _safe_fetch(series: SeriesConfig) -> tuple[pd.DataFrame | None, str | None]:
    try:
        frame = fetch_series(series)
        if frame.empty:
            return None, f"{series.name}: returned no rows"
        return frame, None
    except Exception as exc:
        return None, f"{series.name} ({series.symbol}): {exc}"


def _fetch_concurrent(series_items: list[SeriesConfig], max_workers: int) -> tuple[list[pd.DataFrame], list[str]]:
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    if not series_items:
        return frames, errors
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_safe_fetch, series) for series in series_items]
        for future in as_completed(futures):
            frame, error = future.result()
            if frame is not None:
                frames.append(frame)
            if error:
                errors.append(error)
    return frames, errors


def _fetch_sequential(series_items: list[SeriesConfig]) -> tuple[list[pd.DataFrame], list[str]]:
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    for series in series_items:
        frame, error = _safe_fetch(series)
        if frame is not None:
            frames.append(frame)
        if error:
            errors.append(error)
    return frames, errors


def _computed_curve(base: pd.DataFrame, config: SeriesConfig, left: str, right: str) -> pd.DataFrame | None:
    left_df = base[base["symbol"].eq(left)][["date", "close"]].rename(columns={"close": "left_close"})
    right_df = base[base["symbol"].eq(right)][["date", "close"]].rename(columns={"close": "right_close"})
    if left_df.empty or right_df.empty:
        return None
    merged = pd.merge(left_df, right_df, on="date", how="inner")
    if merged.empty:
        return None
    out = pd.DataFrame({"date": merged["date"], "close": merged["left_close"] - merged["right_close"]})
    out = out.dropna(subset=["date", "close"])
    if out.empty:
        return None
    return _attach_metadata(out, config)


def build_computed_series(frames: list[pd.DataFrame], computed_items: list[SeriesConfig]) -> tuple[list[pd.DataFrame], list[str]]:
    if not frames or not computed_items:
        return [], []
    base = pd.concat(frames, ignore_index=True)
    generated: list[pd.DataFrame] = []
    errors: list[str] = []
    for item in computed_items:
        if item.symbol == "CURVE_10Y_5Y":
            frame = _computed_curve(base, item, "^TNX", "^FVX")
        elif item.symbol == "CURVE_10Y_13W":
            frame = _computed_curve(base, item, "^TNX", "^IRX")
        else:
            frame = None
        if frame is None:
            errors.append(f"{item.name} ({item.symbol}): required live yield proxies not available")
        else:
            generated.append(frame)
    return generated, errors


def fetch_all(
    series_list: Iterable[SeriesConfig] = SERIES,
    max_workers: int = 8,
    include_sources: set[str] | None = None,
    include_modules: set[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    series_items = list(series_list)

    if include_sources:
        series_items = [series for series in series_items if series.source in include_sources]
    if include_modules:
        series_items = [series for series in series_items if series.module in include_modules]

    computed_items = [series for series in series_items if series.source == "computed"]
    yfinance_items = [series for series in series_items if series.source == "yfinance"]
    bls_items = [series for series in series_items if series.source == "bls"]

    yf_frames, yf_errors = _fetch_concurrent(yfinance_items, max_workers=max_workers)
    frames.extend(yf_frames)
    errors.extend(yf_errors)

    # BLS is official but slower; keep it sequential to avoid unnecessary throttling.
    bls_frames, bls_errors = _fetch_sequential(bls_items)
    frames.extend(bls_frames)
    errors.extend(bls_errors)

    computed_frames, computed_errors = build_computed_series(frames, computed_items)
    frames.extend(computed_frames)
    errors.extend(computed_errors)

    columns = ["symbol", "name", "source", "category", "module", "date", "close"]
    if not frames:
        return pd.DataFrame(columns=columns), errors
    return pd.concat(frames, ignore_index=True), errors
