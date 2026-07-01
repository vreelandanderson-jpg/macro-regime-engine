# Macro Regime Engine v8 — Action Console

v8 rebuilds the dashboard from a bulletin-board style dashboard into an action-first console.

## Main changes

- Action Console home screen
- NOW / DRIVER / PRESSURE / SUPPORT / NEXT RISK tiles
- Target Board with pressure targets and cancel levels
- Outcome Board with ranked scenarios
- Confirm / Invalidate / Avoid board
- Gauge row kept central: Macro, AI Growth, Internals, Liquidity, Risk
- Search results now start with an action read before raw relationship tables
- Raw data/detail pages remain available from the sidebar
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
