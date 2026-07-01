"""Macro and AI regime scoring logic.

Score interpretation:
    +60 to +100  = strong supportive / risk-on
    +20 to +60   = mild supportive / risk-on
    -20 to +20   = neutral/mixed
    -20 to -60   = mild pressure / risk-off
    -60 to -100  = strong pressure / risk-off
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from config import AI_CATEGORY_WEIGHTS, CATEGORY_WEIGHTS, GLOBAL_CATEGORY_WEIGHTS, INTERNAL_CATEGORY_WEIGHTS, MACRO_CATEGORY_WEIGHTS, SERIES, SeriesConfig

LOOKBACK_DAYS = 20


@dataclass(frozen=True)
class RegimeResult:
    score: float
    regime: str
    summary: str


def pct_change_over_lookback(series_df: pd.DataFrame, lookback: int = LOOKBACK_DAYS) -> float | None:
    clean = series_df.dropna(subset=["close"]).sort_values("date")
    if len(clean) < 2:
        return None
    current = float(clean["close"].iloc[-1])
    if len(clean) > lookback:
        previous = float(clean["close"].iloc[-lookback - 1])
    else:
        previous = float(clean["close"].iloc[0])
    if previous == 0 or math.isnan(previous) or math.isnan(current):
        return None
    return ((current / previous) - 1.0) * 100.0


def zlike_score(change_pct: float, scale: float = 3.0) -> float:
    """Compress noisy percentage changes into a -100 to +100 score."""
    return math.tanh(change_pct / scale) * 100.0


def direction_adjusted_score(change_pct: float, direction: str) -> float:
    raw = zlike_score(change_pct)
    if direction == "risk_on":
        return raw
    if direction == "risk_off":
        return -raw
    # Neutral series are context-dependent; they matter but with reduced force.
    return raw * 0.35


def _series_for_module(series_list: Iterable[SeriesConfig], module: str | None) -> list[SeriesConfig]:
    items = list(series_list)
    if module is None:
        return items
    return [s for s in items if s.module == module]


def build_score_table(
    df: pd.DataFrame,
    series_list: Iterable[SeriesConfig] = SERIES,
    module: str | None = None,
) -> pd.DataFrame:
    rows: list[dict] = []
    columns = [
        "symbol",
        "name",
        "category",
        "module",
        "latest_date",
        "latest_close",
        "change_pct",
        "score",
        "direction",
        "description",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)

    selected_series = _series_for_module(series_list, module)
    series_map = {s.symbol: s for s in selected_series}
    work = df.copy()
    if "module" not in work.columns:
        work["module"] = work["symbol"].map({s.symbol: s.module for s in SERIES}).fillna("Macro")
    if module is not None:
        work = work[work["symbol"].isin(series_map)]

    for symbol, group in work.groupby("symbol"):
        config = series_map.get(symbol)
        if config is None:
            continue
        clean = group.sort_values("date").dropna(subset=["close"])
        if clean.empty:
            continue
        change = pct_change_over_lookback(clean)
        score = None if change is None else direction_adjusted_score(change, config.direction)
        rows.append(
            {
                "symbol": symbol,
                "name": config.name,
                "category": config.category,
                "module": config.module,
                "latest_date": clean["date"].iloc[-1],
                "latest_close": float(clean["close"].iloc[-1]),
                "change_pct": change,
                "score": score,
                "direction": config.direction,
                "description": config.description,
            }
        )

    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).sort_values(["module", "category", "name"])


def category_scores(score_table: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.DataFrame:
    if score_table.empty:
        return pd.DataFrame(columns=["category", "score", "weight", "weighted_score"])

    weights = weights or CATEGORY_WEIGHTS
    grouped = score_table.dropna(subset=["score"]).groupby("category", as_index=False)["score"].mean()
    grouped["weight"] = grouped["category"].map(weights).fillna(0.05)
    total_weight = grouped["weight"].sum()
    if total_weight <= 0:
        grouped["weighted_score"] = 0.0
    else:
        grouped["weighted_score"] = grouped["score"] * grouped["weight"] / total_weight
    return grouped.sort_values("category")


def regime_from_score(score: float) -> str:
    if score >= 60:
        return "Strong Risk-On"
    if score >= 20:
        return "Mild Risk-On"
    if score <= -60:
        return "Strong Risk-Off"
    if score <= -20:
        return "Mild Risk-Off"
    return "Neutral / Mixed"


def ai_regime_from_score(score: float) -> str:
    if score >= 60:
        return "AI Risk-On / Leadership Expansion"
    if score >= 20:
        return "AI Mild Risk-On"
    if score <= -60:
        return "AI Breakdown / Growth Stress"
    if score <= -20:
        return "AI Pullback / Rotation Pressure"
    return "AI Neutral / Mixed"


def summarize_regime(score: float, cats: pd.DataFrame, label: str = "Macro") -> str:
    regime = ai_regime_from_score(score) if label == "AI" else regime_from_score(score)
    if cats.empty:
        return f"No {label.lower()} data available yet. Run the live data update first."

    strongest = cats.sort_values("weighted_score", ascending=False).head(1)
    weakest = cats.sort_values("weighted_score", ascending=True).head(1)
    pos = strongest.iloc[0]
    neg = weakest.iloc[0]
    return (
        f"{regime}. Strongest supportive area: {pos['category']} ({pos['score']:.1f}). "
        f"Largest pressure area: {neg['category']} ({neg['score']:.1f})."
    )


def compute_regime(
    df: pd.DataFrame,
    module: str | None = None,
    weights: dict[str, float] | None = None,
    label: str = "Macro",
) -> tuple[RegimeResult, pd.DataFrame, pd.DataFrame]:
    score_table = build_score_table(df, module=module)
    cats = category_scores(score_table, weights=weights)
    if cats.empty:
        result = RegimeResult(0.0, "No Data", f"No {label.lower()} data available yet. Run the data update first.")
        return result, score_table, cats

    total = float(cats["weighted_score"].sum())
    regime = ai_regime_from_score(total) if label == "AI" else regime_from_score(total)
    result = RegimeResult(total, regime, summarize_regime(total, cats, label))
    return result, score_table, cats


def compute_macro_regime(df: pd.DataFrame) -> tuple[RegimeResult, pd.DataFrame, pd.DataFrame]:
    return compute_regime(df, module="Macro", weights=MACRO_CATEGORY_WEIGHTS, label="Macro")


def compute_ai_regime(df: pd.DataFrame) -> tuple[RegimeResult, pd.DataFrame, pd.DataFrame]:
    return compute_regime(df, module="AI", weights=AI_CATEGORY_WEIGHTS, label="AI")


def compute_internal_regime(df: pd.DataFrame) -> tuple[RegimeResult, pd.DataFrame, pd.DataFrame]:
    return compute_regime(df, module="Internal", weights=INTERNAL_CATEGORY_WEIGHTS, label="Internal")


def compute_global_regime(df: pd.DataFrame) -> tuple[RegimeResult, pd.DataFrame, pd.DataFrame]:
    return compute_regime(df, module="Global", weights=GLOBAL_CATEGORY_WEIGHTS, label="Global")


def generate_alerts(score_table: pd.DataFrame, cats: pd.DataFrame) -> list[str]:
    alerts: list[str] = []
    if score_table.empty:
        return ["No observations loaded yet."]

    def get_score(name: str) -> float | None:
        row = score_table[score_table["name"].eq(name)]
        if row.empty or pd.isna(row["score"].iloc[-1]):
            return None
        return float(row["score"].iloc[-1])

    dxy = get_score("Trade Weighted USD") or get_score("US Dollar ETF")
    spx = get_score("S&P 500")
    ten_y = get_score("US 10Y Yield")
    vix = get_score("VIX")
    gold = get_score("Gold Futures")
    oil = get_score("WTI Crude Oil")

    if dxy is not None and ten_y is not None and dxy < -35 and ten_y < -35:
        alerts.append("Dollar and 10Y yield pressure are both rising: liquidity pressure risk.")
    if spx is not None and vix is not None and spx < -25 and vix < -25:
        alerts.append("Equities are weakening while volatility pressure is rising: risk-off tape.")
    if gold is not None and dxy is not None and gold > 25 and dxy < -25:
        alerts.append("Gold is firm despite dollar pressure: possible safety/geopolitical bid.")
    if oil is not None and oil < -30:
        alerts.append("Oil pressure is rising: watch inflation impulse and bond reaction.")
    if not alerts:
        alerts.append("No major cross-market stress alert from current rules.")

    if not cats.empty:
        worst = cats.sort_values("score").iloc[0]
        if worst["score"] < -45:
            alerts.append(f"Heavy category pressure detected in {worst['category']}: {worst['score']:.1f}.")

    return alerts


def generate_ai_alerts(ai_table: pd.DataFrame, macro_table: pd.DataFrame | None = None) -> list[str]:
    alerts: list[str] = []
    if ai_table.empty:
        return ["No AI observations loaded yet."]

    def score(table: pd.DataFrame, name: str) -> float | None:
        row = table[table["name"].eq(name)]
        if row.empty or pd.isna(row["score"].iloc[-1]):
            return None
        return float(row["score"].iloc[-1])

    nvda = score(ai_table, "Nvidia")
    smh = score(ai_table, "VanEck Semiconductor ETF")
    qqq = score(macro_table, "QQQ") if macro_table is not None and not macro_table.empty else None
    ten_y = score(macro_table, "US 10Y Yield") if macro_table is not None and not macro_table.empty else None
    vix = score(macro_table, "VIX") if macro_table is not None and not macro_table.empty else None

    if nvda is not None and smh is not None and nvda > 35 and smh > 25:
        alerts.append("AI leadership is firm: Nvidia and semiconductors are confirming risk appetite.")
    if nvda is not None and smh is not None and nvda < -35 and smh < -25:
        alerts.append("AI leadership is under pressure: Nvidia and semiconductors are both weakening.")
    if nvda is not None and qqq is not None and nvda > 30 and qqq < -10:
        alerts.append("AI is outperforming broad tech: narrow AI leadership / rotation signal.")
    if smh is not None and ten_y is not None and smh < -25 and ten_y < -25:
        alerts.append("Semiconductors are weak while yields pressure growth: high-rate AI stress.")
    if vix is not None and vix < -25 and nvda is not None and nvda < -25:
        alerts.append("AI is falling with rising volatility pressure: tech unwind risk.")
    if not alerts:
        alerts.append("No major AI stress alert from current rules.")

    return alerts


def generate_internal_alerts(internal_table: pd.DataFrame, macro_table: pd.DataFrame | None = None) -> list[str]:
    alerts: list[str] = []
    if internal_table.empty:
        return ["No internal market observations loaded yet."]

    valid = internal_table.dropna(subset=["score"]).copy()
    if valid.empty:
        return ["Internal market data loaded, but not enough history to score yet."]

    breadth = valid[valid["category"].isin(["Breadth", "Index Components"])]
    credit = valid[valid["category"].eq("Credit")]
    vol = valid[valid["category"].eq("Volatility Internals")]
    sectors = valid[valid["category"].isin(["Sector Rotation", "Defensive Rotation", "Rate Sensitive"])]
    single = valid[valid["category"].eq("Single Stock Leadership")]

    if not breadth.empty:
        pct_pos = (breadth["score"] > 0).mean() * 100
        if pct_pos < 40:
            alerts.append(f"Internal breadth is weak: only {pct_pos:.0f}% of breadth proxies are supportive.")
        elif pct_pos > 65:
            alerts.append(f"Internal breadth is confirming: {pct_pos:.0f}% of breadth proxies are supportive.")

    if not credit.empty and credit["score"].mean() < -25:
        alerts.append("Credit proxies are weakening: watch HYG/JNK/LQD and bank stress confirmation.")
    if not vol.empty and vol["score"].mean() < -25:
        alerts.append("Volatility internals are pressuring risk: short-term/event hedge demand may be rising.")
    if not sectors.empty:
        defensive = valid[valid["category"].eq("Defensive Rotation")]["score"].mean() if not valid[valid["category"].eq("Defensive Rotation")].empty else 0
        cyclicals = sectors[sectors["category"].eq("Sector Rotation")]["score"].mean() if not sectors[sectors["category"].eq("Sector Rotation")].empty else 0
        if defensive < -20 and cyclicals < -10:
            alerts.append("Defensive rotation is rising while cyclicals are weak: hidden risk-off rotation.")
        elif cyclicals > 20 and defensive > -10:
            alerts.append("Sector rotation is broadening: cyclicals are supporting risk appetite.")

    if not single.empty:
        leaders = single.sort_values("score", ascending=False).head(3)["name"].tolist()
        laggards = single.sort_values("score", ascending=True).head(3)["name"].tolist()
        alerts.append(f"Internal leaders: {', '.join(leaders)}. Laggards: {', '.join(laggards)}.")

    if not alerts:
        alerts.append("No major internal market divergence from current rules.")
    return alerts


def generate_global_alerts(global_table: pd.DataFrame) -> list[str]:
    if global_table.empty:
        return ["No global market observations loaded yet."]
    valid = global_table.dropna(subset=["score"]).copy()
    if valid.empty:
        return ["Global market data loaded, but not enough history to score yet."]
    pct_pos = (valid["score"] > 0).mean() * 100
    weakest = valid.sort_values("score").head(3)["name"].tolist()
    strongest = valid.sort_values("score", ascending=False).head(3)["name"].tolist()
    if pct_pos < 40:
        return [f"Global confirmation is weak: only {pct_pos:.0f}% of global proxies are supportive. Weakest: {', '.join(weakest)}."]
    if pct_pos > 65:
        return [f"Global risk appetite is broad: {pct_pos:.0f}% of global proxies are supportive. Strongest: {', '.join(strongest)}."]
    return [f"Global markets are mixed. Strongest: {', '.join(strongest)}. Weakest: {', '.join(weakest)}."]
