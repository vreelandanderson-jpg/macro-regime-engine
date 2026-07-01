"""Configuration for Macro Regime Engine v8.2.

v7 is live-first and removes FRED/demo dependency.
Primary live sources:
- yfinance for markets, AI, ETFs, commodities, crypto, rates proxies
- BLS public API for CPI, unemployment, payrolls, PPI, wages
- computed curves from live yield proxies
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DataSource = Literal["yfinance", "bls", "computed"]
ModuleName = Literal["Macro", "AI", "Internal", "Global"]


@dataclass(frozen=True)
class SeriesConfig:
    symbol: str
    name: str
    source: DataSource
    category: str
    direction: Literal["risk_on", "risk_off", "neutral"]
    description: str = ""
    module: ModuleName = "Macro"


# Direction means how a rising value should be interpreted for the score:
# risk_on  = rising value supports liquidity / growth / risk appetite
# risk_off = rising value creates pressure / stress / inflation / fear
# neutral  = rising/falling is context-dependent; score impact is reduced
SERIES: list[SeriesConfig] = [
    # Broad market risk appetite
    SeriesConfig("^GSPC", "S&P 500", "yfinance", "Equities", "risk_on", "Broad US equity risk appetite"),
    SeriesConfig("^NDX", "Nasdaq 100", "yfinance", "Equities", "risk_on", "Growth/tech risk appetite"),
    SeriesConfig("^DJI", "Dow Jones", "yfinance", "Equities", "risk_on", "Large-cap industrial risk appetite"),
    SeriesConfig("^RUT", "Russell 2000", "yfinance", "Equities", "risk_on", "Small-cap risk appetite"),
    SeriesConfig("QQQ", "QQQ", "yfinance", "Equities", "risk_on", "Liquid Nasdaq proxy"),
    SeriesConfig("SPY", "SPY", "yfinance", "Equities", "risk_on", "Liquid S&P 500 ETF proxy"),

    # Fear / volatility
    SeriesConfig("^VIX", "VIX", "yfinance", "Volatility", "risk_off", "Equity fear/hedging pressure"),

    # Dollar / liquidity pressure
    SeriesConfig("DX-Y.NYB", "US Dollar Index", "yfinance", "Dollar", "risk_off", "DXY dollar pressure"),
    SeriesConfig("UUP", "US Dollar ETF", "yfinance", "Dollar", "risk_off", "Tradable dollar proxy"),

    # Rates / bonds — no FRED. Use exchange-traded/yfinance proxies and computed curves.
    SeriesConfig("^IRX", "13W T-Bill Yield", "yfinance", "Rates", "risk_off", "Front-end bill yield pressure"),
    SeriesConfig("^FVX", "US 5Y Yield", "yfinance", "Rates", "risk_off", "Mid-curve yield pressure"),
    SeriesConfig("^TNX", "US 10Y Yield", "yfinance", "Rates", "risk_off", "Long-end yield pressure"),
    SeriesConfig("^TYX", "US 30Y Yield", "yfinance", "Rates", "risk_off", "Long bond yield pressure"),
    SeriesConfig("SHY", "Short Treasury ETF", "yfinance", "Rates", "risk_on", "Short bond bid / yield relief proxy"),
    SeriesConfig("IEF", "7-10Y Treasury ETF", "yfinance", "Rates", "risk_on", "Intermediate bond bid / yield relief proxy"),
    SeriesConfig("TLT", "Long Treasury Bond ETF", "yfinance", "Rates", "risk_on", "Long bond bid / easing pressure proxy"),
    SeriesConfig("TIP", "TIPS Bond ETF", "yfinance", "Rates", "risk_on", "Inflation-protected bond bid / real-rate relief proxy"),
    SeriesConfig("CURVE_10Y_5Y", "10Y-5Y Curve Proxy", "computed", "Rates", "neutral", "Computed from ^TNX minus ^FVX"),
    SeriesConfig("CURVE_10Y_13W", "10Y-13W Curve Proxy", "computed", "Rates", "neutral", "Computed from ^TNX minus ^IRX"),

    # Commodities / inflation impulse
    SeriesConfig("GC=F", "Gold Futures", "yfinance", "Commodities", "neutral", "Safety/inflation hedge"),
    SeriesConfig("SI=F", "Silver Futures", "yfinance", "Commodities", "neutral", "Precious/industrial metals proxy"),
    SeriesConfig("CL=F", "WTI Crude Oil", "yfinance", "Commodities", "risk_off", "Energy/inflation pressure"),
    SeriesConfig("BZ=F", "Brent Crude Oil", "yfinance", "Commodities", "risk_off", "Global energy/inflation pressure"),
    SeriesConfig("HG=F", "Copper Futures", "yfinance", "Commodities", "risk_on", "Growth-sensitive commodity"),
    SeriesConfig("URA", "Uranium ETF", "yfinance", "Commodities", "risk_on", "Nuclear/energy infrastructure proxy"),

    # Crypto liquidity proxy
    SeriesConfig("BTC-USD", "Bitcoin", "yfinance", "Crypto", "risk_on", "High-beta liquidity proxy"),
    SeriesConfig("ETH-USD", "Ethereum", "yfinance", "Crypto", "risk_on", "High-beta crypto liquidity proxy"),

    # Economy — BLS live public API, no FRED.
    SeriesConfig("CUSR0000SA0", "CPI", "bls", "Economy", "risk_off", "BLS CPI all urban consumers, seasonally adjusted"),
    SeriesConfig("LNS14000000", "Unemployment Rate", "bls", "Economy", "risk_off", "BLS unemployment rate"),
    SeriesConfig("CES0000000001", "Nonfarm Payrolls", "bls", "Economy", "risk_on", "BLS all employees, total nonfarm"),
    SeriesConfig("WPUFD4", "PPI Final Demand", "bls", "Economy", "risk_off", "BLS Producer Price Index final demand"),
    SeriesConfig("CES0500000003", "Average Hourly Earnings", "bls", "Economy", "neutral", "BLS average hourly earnings"),

    # AI leaders
    SeriesConfig("NVDA", "Nvidia", "yfinance", "AI Leaders", "risk_on", "Primary AI accelerator leadership", "AI"),
    SeriesConfig("MSFT", "Microsoft", "yfinance", "AI Leaders", "risk_on", "Cloud and enterprise AI leader", "AI"),
    SeriesConfig("GOOGL", "Alphabet", "yfinance", "AI Leaders", "risk_on", "AI/search/cloud leader", "AI"),
    SeriesConfig("META", "Meta", "yfinance", "AI Leaders", "risk_on", "AI platform/ad model leader", "AI"),
    SeriesConfig("AMZN", "Amazon", "yfinance", "AI Leaders", "risk_on", "AWS/cloud AI leader", "AI"),
    SeriesConfig("AMD", "AMD", "yfinance", "AI Leaders", "risk_on", "AI GPU competitor", "AI"),
    SeriesConfig("AVGO", "Broadcom", "yfinance", "AI Leaders", "risk_on", "Networking/custom silicon AI proxy", "AI"),
    SeriesConfig("PLTR", "Palantir", "yfinance", "AI Leaders", "risk_on", "AI software/data platform proxy", "AI"),

    # Semiconductors
    SeriesConfig("SMH", "VanEck Semiconductor ETF", "yfinance", "Semiconductors", "risk_on", "Semiconductor leadership basket", "AI"),
    SeriesConfig("SOXX", "iShares Semiconductor ETF", "yfinance", "Semiconductors", "risk_on", "Semiconductor confirmation basket", "AI"),
    SeriesConfig("TSM", "TSMC", "yfinance", "Semiconductors", "risk_on", "AI foundry supply chain proxy", "AI"),
    SeriesConfig("ASML", "ASML", "yfinance", "Semiconductors", "risk_on", "Lithography/capex supply chain proxy", "AI"),
    SeriesConfig("MU", "Micron", "yfinance", "Semiconductors", "risk_on", "AI memory cycle proxy", "AI"),

    # Cloud / data center / infrastructure
    SeriesConfig("ORCL", "Oracle", "yfinance", "AI Infrastructure", "risk_on", "Cloud/database AI infrastructure", "AI"),
    SeriesConfig("EQIX", "Equinix", "yfinance", "AI Infrastructure", "risk_on", "Data-center infrastructure", "AI"),
    SeriesConfig("DLR", "Digital Realty", "yfinance", "AI Infrastructure", "risk_on", "Data-center infrastructure", "AI"),
    SeriesConfig("VRT", "Vertiv", "yfinance", "AI Infrastructure", "risk_on", "Data-center power/cooling proxy", "AI"),
    SeriesConfig("ETN", "Eaton", "yfinance", "AI Infrastructure", "risk_on", "Electrical infrastructure proxy", "AI"),
    SeriesConfig("CCJ", "Cameco", "yfinance", "AI Infrastructure", "risk_on", "Nuclear power demand proxy", "AI"),

    # AI ETF basket
    SeriesConfig("AIQ", "Global X AI & Tech ETF", "yfinance", "AI ETFs", "risk_on", "AI thematic basket", "AI"),
    SeriesConfig("BOTZ", "Global X Robotics & AI ETF", "yfinance", "AI ETFs", "risk_on", "Robotics/AI thematic basket", "AI"),
    SeriesConfig("ROBO", "ROBO Global Robotics & Automation ETF", "yfinance", "AI ETFs", "risk_on", "Automation/AI basket", "AI"),
    SeriesConfig("ARKQ", "ARK Autonomous Tech & Robotics ETF", "yfinance", "AI ETFs", "risk_on", "High-beta AI/robotics proxy", "AI"),

    # Market internals / breadth proxies — live-only using ETFs and index components.
    SeriesConfig("RSP", "Equal Weight S&P 500", "yfinance", "Breadth", "risk_on", "Equal-weight S&P breadth proxy", "Internal"),
    SeriesConfig("QQQE", "Equal Weight Nasdaq 100", "yfinance", "Breadth", "risk_on", "Equal-weight Nasdaq breadth proxy", "Internal"),
    SeriesConfig("IWM", "Russell 2000 ETF", "yfinance", "Breadth", "risk_on", "Small-cap breadth/risk proxy", "Internal"),
    SeriesConfig("MDY", "S&P MidCap 400 ETF", "yfinance", "Breadth", "risk_on", "Mid-cap breadth proxy", "Internal"),
    SeriesConfig("DIA", "Dow 30 ETF", "yfinance", "Index Components", "risk_on", "Dow 30 tradable proxy", "Internal"),
    SeriesConfig("OEF", "S&P 100 ETF", "yfinance", "Index Components", "risk_on", "Large-cap component breadth proxy", "Internal"),

    # Sector rotation proxies.
    SeriesConfig("XLK", "Technology Sector", "yfinance", "Sector Rotation", "risk_on", "Technology sector leadership", "Internal"),
    SeriesConfig("XLF", "Financials Sector", "yfinance", "Sector Rotation", "risk_on", "Financials / bank risk appetite", "Internal"),
    SeriesConfig("XLE", "Energy Sector", "yfinance", "Sector Rotation", "neutral", "Energy/inflation rotation", "Internal"),
    SeriesConfig("XLV", "Healthcare Sector", "yfinance", "Sector Rotation", "neutral", "Healthcare defensive/growth mix", "Internal"),
    SeriesConfig("XLI", "Industrials Sector", "yfinance", "Sector Rotation", "risk_on", "Cyclical industrial leadership", "Internal"),
    SeriesConfig("XLY", "Consumer Discretionary Sector", "yfinance", "Sector Rotation", "risk_on", "Consumer risk appetite", "Internal"),
    SeriesConfig("XLP", "Consumer Staples Sector", "yfinance", "Defensive Rotation", "risk_off", "Defensive staples rotation", "Internal"),
    SeriesConfig("XLU", "Utilities Sector", "yfinance", "Defensive Rotation", "risk_off", "Defensive / yield-sensitive rotation", "Internal"),
    SeriesConfig("XLB", "Materials Sector", "yfinance", "Sector Rotation", "risk_on", "Materials / global growth proxy", "Internal"),
    SeriesConfig("XLRE", "Real Estate Sector", "yfinance", "Rate Sensitive", "risk_on", "Rate-sensitive real estate proxy", "Internal"),
    SeriesConfig("XLC", "Communication Services Sector", "yfinance", "Sector Rotation", "risk_on", "Mega-cap communications / ad cycle proxy", "Internal"),

    # Credit and financial stress proxies.
    SeriesConfig("HYG", "High Yield Credit ETF", "yfinance", "Credit", "risk_on", "High-yield credit risk appetite", "Internal"),
    SeriesConfig("JNK", "Junk Bond ETF", "yfinance", "Credit", "risk_on", "Junk credit confirmation proxy", "Internal"),
    SeriesConfig("LQD", "Investment Grade Credit ETF", "yfinance", "Credit", "risk_on", "Investment-grade credit stability", "Internal"),
    SeriesConfig("KRE", "Regional Banks ETF", "yfinance", "Credit", "risk_on", "Regional banking stress proxy", "Internal"),
    SeriesConfig("KBE", "Bank ETF", "yfinance", "Credit", "risk_on", "Banking sector confirmation proxy", "Internal"),

    # Volatility structure proxies.
    SeriesConfig("^VIX9D", "VIX 9-Day", "yfinance", "Volatility Internals", "risk_off", "Short-term event volatility pressure", "Internal"),
    SeriesConfig("^VIX3M", "VIX 3-Month", "yfinance", "Volatility Internals", "risk_off", "Medium-term volatility pressure", "Internal"),
    SeriesConfig("^VVIX", "VVIX", "yfinance", "Volatility Internals", "risk_off", "Volatility-of-volatility pressure", "Internal"),
    SeriesConfig("^SKEW", "SKEW Index", "yfinance", "Volatility Internals", "risk_off", "Tail-risk demand proxy", "Internal"),

    # Major internal single-stock leadership. Used to detect narrow vs broad index strength.
    SeriesConfig("AAPL", "Apple", "yfinance", "Single Stock Leadership", "risk_on", "Mega-cap index leadership", "Internal"),
    SeriesConfig("TSLA", "Tesla", "yfinance", "Single Stock Leadership", "risk_on", "High-beta growth leadership", "Internal"),
    SeriesConfig("JPM", "JPMorgan", "yfinance", "Single Stock Leadership", "risk_on", "Bank/credit leadership", "Internal"),
    SeriesConfig("UNH", "UnitedHealth", "yfinance", "Single Stock Leadership", "neutral", "Defensive healthcare heavyweight", "Internal"),
    SeriesConfig("HD", "Home Depot", "yfinance", "Single Stock Leadership", "risk_on", "Housing/consumer cyclical proxy", "Internal"),
    SeriesConfig("CAT", "Caterpillar", "yfinance", "Single Stock Leadership", "risk_on", "Industrial/global growth proxy", "Internal"),
    SeriesConfig("BA", "Boeing", "yfinance", "Single Stock Leadership", "risk_on", "Industrial risk proxy", "Internal"),
    SeriesConfig("GS", "Goldman Sachs", "yfinance", "Single Stock Leadership", "risk_on", "Financial risk appetite proxy", "Internal"),


    # v8.2 Full Universe Expansion — real estate / housing / rate-sensitive assets.
    SeriesConfig("VNQ", "Vanguard Real Estate ETF", "yfinance", "Real Estate / Housing", "risk_on", "Broad REIT / real estate risk proxy", "Internal"),
    SeriesConfig("IYR", "iShares US Real Estate ETF", "yfinance", "Real Estate / Housing", "risk_on", "US real estate ETF confirmation", "Internal"),
    SeriesConfig("ITB", "US Home Construction ETF", "yfinance", "Real Estate / Housing", "risk_on", "Homebuilders / housing cycle proxy", "Internal"),
    SeriesConfig("XHB", "Homebuilders ETF", "yfinance", "Real Estate / Housing", "risk_on", "Homebuilders and housing suppliers proxy", "Internal"),
    SeriesConfig("MBB", "Mortgage-Backed Securities ETF", "yfinance", "Real Estate / Housing", "risk_on", "Mortgage-backed security stability proxy", "Internal"),
    SeriesConfig("REM", "Mortgage REIT ETF", "yfinance", "Real Estate / Housing", "risk_on", "Mortgage REIT / rate-sensitive real estate proxy", "Internal"),

    # v8.2 Sub-sector rotation map.
    SeriesConfig("IYT", "Transportation ETF", "yfinance", "Sub-Sectors", "risk_on", "Transports / economic flow proxy", "Internal"),
    SeriesConfig("XRT", "Retail ETF", "yfinance", "Sub-Sectors", "risk_on", "Retail / consumer demand proxy", "Internal"),
    SeriesConfig("XME", "Metals & Mining ETF", "yfinance", "Sub-Sectors", "risk_on", "Metals/mining cyclicals and inflation rotation", "Internal"),
    SeriesConfig("XOP", "Oil Exploration ETF", "yfinance", "Sub-Sectors", "neutral", "Oil exploration and production rotation", "Internal"),
    SeriesConfig("OIH", "Oil Services ETF", "yfinance", "Sub-Sectors", "neutral", "Oil services / energy capex proxy", "Internal"),
    SeriesConfig("TAN", "Solar ETF", "yfinance", "Sub-Sectors", "risk_on", "Solar / clean energy growth proxy", "Internal"),
    SeriesConfig("JETS", "Airlines ETF", "yfinance", "Sub-Sectors", "risk_on", "Airlines / travel demand proxy", "Internal"),
    SeriesConfig("IBB", "Biotech ETF", "yfinance", "Sub-Sectors", "risk_on", "Large-cap biotech risk appetite", "Internal"),
    SeriesConfig("XBI", "Biotech Equal Weight ETF", "yfinance", "Sub-Sectors", "risk_on", "High-beta biotech breadth", "Internal"),
    SeriesConfig("ITA", "Aerospace & Defense ETF", "yfinance", "Sub-Sectors", "neutral", "Aerospace/defense/geopolitical proxy", "Internal"),
    SeriesConfig("XAR", "Aerospace & Defense Equal Weight ETF", "yfinance", "Sub-Sectors", "neutral", "Defense breadth / geopolitical proxy", "Internal"),

    # v8.2 Currency map — confirms dollar liquidity and global risk pressure.
    SeriesConfig("EURUSD=X", "EUR/USD", "yfinance", "Currencies", "risk_on", "Euro vs dollar liquidity proxy", "Global"),
    SeriesConfig("USDJPY=X", "USD/JPY", "yfinance", "Currencies", "neutral", "Japan/rate differential and carry proxy", "Global"),
    SeriesConfig("GBPUSD=X", "GBP/USD", "yfinance", "Currencies", "risk_on", "Sterling vs dollar risk proxy", "Global"),
    SeriesConfig("CADUSD=X", "CAD/USD", "yfinance", "Currencies", "risk_on", "Canada/commodity FX proxy", "Global"),
    SeriesConfig("AUDUSD=X", "AUD/USD", "yfinance", "Currencies", "risk_on", "China/global growth FX proxy", "Global"),
    SeriesConfig("CHFUSD=X", "CHF/USD", "yfinance", "Currencies", "neutral", "Swiss franc safety/FX proxy", "Global"),
    SeriesConfig("CEW", "Emerging Market Currency ETF", "yfinance", "Currencies", "risk_on", "Emerging-market FX risk appetite", "Global"),

    # v8.2 Expanded commodity map.
    SeriesConfig("NG=F", "Natural Gas Futures", "yfinance", "Commodities", "risk_off", "Natural gas / energy inflation pressure"),
    SeriesConfig("ZW=F", "Wheat Futures", "yfinance", "Commodities", "risk_off", "Wheat / food inflation pressure"),
    SeriesConfig("ZC=F", "Corn Futures", "yfinance", "Commodities", "risk_off", "Corn / food inflation pressure"),
    SeriesConfig("ZS=F", "Soybean Futures", "yfinance", "Commodities", "risk_off", "Soybean / food inflation pressure"),
    SeriesConfig("DBA", "Agriculture ETF", "yfinance", "Commodities", "risk_off", "Agriculture basket / food inflation proxy"),
    SeriesConfig("DBC", "Commodity Basket ETF", "yfinance", "Commodities", "risk_off", "Broad commodity inflation proxy"),

    # v8.2 Crypto liquidity and crypto-equity proxies.
    SeriesConfig("SOL-USD", "Solana", "yfinance", "Crypto", "risk_on", "High-beta crypto risk proxy"),
    SeriesConfig("COIN", "Coinbase", "yfinance", "Crypto Equity", "risk_on", "Crypto exchange / risk appetite proxy", "Internal"),
    SeriesConfig("MSTR", "MicroStrategy", "yfinance", "Crypto Equity", "risk_on", "Bitcoin-equity beta proxy", "Internal"),
    SeriesConfig("MARA", "Marathon Digital", "yfinance", "Crypto Equity", "risk_on", "Bitcoin miner beta proxy", "Internal"),
    SeriesConfig("RIOT", "Riot Platforms", "yfinance", "Crypto Equity", "risk_on", "Bitcoin miner beta proxy", "Internal"),

    # Global market confirmation.
    SeriesConfig("EWC", "Canada ETF", "yfinance", "Global Markets", "risk_on", "Canada equity risk appetite", "Global"),
    SeriesConfig("EWU", "UK ETF", "yfinance", "Global Markets", "risk_on", "UK equity risk appetite", "Global"),
    SeriesConfig("EWG", "Germany ETF", "yfinance", "Global Markets", "risk_on", "Germany/Europe cyclical proxy", "Global"),
    SeriesConfig("EWQ", "France ETF", "yfinance", "Global Markets", "risk_on", "France/Europe equity proxy", "Global"),
    SeriesConfig("EWJ", "Japan ETF", "yfinance", "Global Markets", "risk_on", "Japan equity risk appetite", "Global"),
    SeriesConfig("FXI", "China Large-Cap ETF", "yfinance", "Global Markets", "risk_on", "China large-cap risk proxy", "Global"),
    SeriesConfig("EWH", "Hong Kong ETF", "yfinance", "Global Markets", "risk_on", "Hong Kong/China liquidity proxy", "Global"),
    SeriesConfig("INDA", "India ETF", "yfinance", "Global Markets", "risk_on", "India equity risk appetite", "Global"),
    SeriesConfig("EEM", "Emerging Markets ETF", "yfinance", "Global Markets", "risk_on", "Emerging market risk appetite", "Global"),
    SeriesConfig("ACWI", "Global ACWI ETF", "yfinance", "Global Markets", "risk_on", "Global equity breadth proxy", "Global"),

]

MACRO_CATEGORY_WEIGHTS: dict[str, float] = {
    "Equities": 0.20,
    "Volatility": 0.10,
    "Dollar": 0.17,
    "Rates": 0.23,
    "Commodities": 0.15,
    "Crypto": 0.05,
    "Economy": 0.10,
}

AI_CATEGORY_WEIGHTS: dict[str, float] = {
    "AI Leaders": 0.35,
    "Semiconductors": 0.30,
    "AI Infrastructure": 0.20,
    "AI ETFs": 0.15,
}

INTERNAL_CATEGORY_WEIGHTS: dict[str, float] = {
    "Breadth": 0.22,
    "Index Components": 0.10,
    "Sector Rotation": 0.17,
    "Defensive Rotation": 0.10,
    "Rate Sensitive": 0.06,
    "Real Estate / Housing": 0.08,
    "Sub-Sectors": 0.08,
    "Credit": 0.13,
    "Volatility Internals": 0.09,
    "Single Stock Leadership": 0.07,
    "Crypto Equity": 0.04,
}

GLOBAL_CATEGORY_WEIGHTS: dict[str, float] = {
    "Global Markets": 0.70,
    "Currencies": 0.30,
}

CATEGORY_WEIGHTS: dict[str, float] = {
    **MACRO_CATEGORY_WEIGHTS,
    **AI_CATEGORY_WEIGHTS,
    **INTERNAL_CATEGORY_WEIGHTS,
    **GLOBAL_CATEGORY_WEIGHTS,
}
DATABASE_PATH = "macro_engine.sqlite"
