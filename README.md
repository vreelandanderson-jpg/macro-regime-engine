# Macro Regime Engine v8.1 — Global Live Action Engine

v8.1 upgrades the Action Console so live data powers the whole engine, not only the tiles.

## Main changes

- Selectable Live Market Pulse tiles
- Tile category filters: All, Indexes, AI/Tech, Bonds, Dollar, Commodities, Crypto, Internals, Credit, Volatility, Global
- Selected asset Action Panel with NOW / TARGET / INVALIDATION / DRIVER / RELATED / EVENT RISK
- Confirm / Invalidate / Avoid panel for the selected tile
- Global Live State strip showing Action Console, Gauges, Targets, Alerts, and Data recalculation
- Live updates now visually connect to gauges, target board, outcome board, alerts, search, and selected asset read
- Action Console home screen retained
- Target Board retained
- Outcome Board retained
- Confirm / Invalidate / Avoid board retained
- Gauge row retained: Macro, AI Growth, Internals, Liquidity, Risk
- Live-only setup preserved
- Eastern/Toronto 12-hour time preserved
- Auto re-run and background updater preserved

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python update_data.py
python update_events.py
streamlit run app.py
```

## Live updater

Start/stop the background updater from the dashboard, or use:

```powershell
python live_updater.py --interval 15
```

## Feed tests

```powershell
python update_data.py --prices-only
python update_data.py --econ-only
python update_data.py --internal-only
python update_data.py --global-only
```

## Notes

The Action Console target levels are directional pressure levels calculated from live prices and score strength. They are not trade orders.
