# Macro Regime Engine v8.2 — Full Universe + Clean Tile UI

## What changed
- Added real estate / housing: XLRE, VNQ, IYR, ITB, XHB, MBB, REM.
- Added all 11 sector coverage plus expanded sub-sector map: transports, retail, metals/mining, oil services, solar, airlines, biotech, aerospace/defense.
- Added currency map: EUR/USD, USD/JPY, GBP/USD, CAD/USD, AUD/USD, CHF/USD, EMFX.
- Added expanded commodities: natural gas, wheat, corn, soybeans, DBA, DBC.
- Added crypto-equity proxies: COIN, MSTR, MARA, RIOT.
- Added cleaner selectable live tiles: Symbol / price / % change / short state chip. No sentence tiles or text collision.
- Added Real Estate, Sub-Sectors, and Currencies pages.

## Run locally
```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python update_data.py
python update_events.py
streamlit run app.py
```
