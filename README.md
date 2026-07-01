# Macro Regime Engine v7.4 — Unified Command Center UI

Live-only global/internal market surveillance dashboard. No demo logic and no FRED dependency.

## v7.4 UI fixes

- Search bar moved into one unified command-center row.
- Streamlit Deploy/menu/header elements are hidden so they cannot block search.
- Search, local 12-hour time, live pulse, data health, Start/Stop/Now controls are integrated into one compact command bar.
- Meter gauges restored on the dashboard without removing regime cards, internals, events, alerts, search intelligence, or live updater.
- Background live updater remains: press **Start** to refresh data in the background without forcing full browser auto-refresh.

## Existing surveillance scope

- Macro
- AI / Tech
- Bonds / rates
- Dollar
- Commodities
- Crypto
- Economic/event calendar
- Geopolitics
- Market internals
- Sector rotation
- Breadth proxies
- Index components / single-stock leadership
- Credit / bank stress
- Volatility internals
- Global markets
- Relationship search

## Live sources

- `yfinance`: market prices, AI, sectors, index components, credit ETFs, volatility proxies, global ETFs, commodities, crypto, rates proxies
- `BLS public API`: CPI, unemployment, payrolls, PPI, wages
- `computed`: curve proxies generated from live yield proxies

## Run in VS Code

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python update_data.py
python update_events.py
streamlit run app.py
```

Inside the dashboard, press **Start** to keep live prices updating in the background.

## Isolate feeds

```powershell
python update_data.py --prices-only
python update_data.py --econ-only
python update_data.py --ai-only
python update_data.py --macro-only
python update_data.py --internal-only
python update_data.py --global-only
```

## Search examples

Try:

```text
NDX
QQQ
AI
NVDA
internals
breadth
credit
global
gold
dollar
yields
CPI
FOMC
oil
```

Search should return related markets, drivers, events, alerts, playbook matches, scenario matches, and direct data rows.

## VPS Deployment

This package includes `deploy/install_ubuntu.sh`, which installs the engine as always-on Ubuntu systemd services.

On the server:

```bash
cd /root/macro_regime_engine
sudo bash deploy/install_ubuntu.sh
```

Then open:

```text
http://YOUR_SERVER_IP:8501
```
