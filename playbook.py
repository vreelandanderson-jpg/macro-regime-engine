"""Knowledge base for Macro Regime Engine v4.

This file is intentionally plain Python data so the dashboard can display a
large amount of market intelligence without needing a separate spreadsheet.
Use it as the built-in brain of the engine: rows are displayed in the dashboard,
and the event calendar is now generated automatically by auto_events.py.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_events import build_auto_event_calendar


CAUSE_EFFECT_ROWS: list[dict[str, str]] = [

    {
        "area": "Real Estate / Housing",
        "condition": "XLRE/VNQ/ITB weakening while 10Y yield rises",
        "can_cause": "Rate-sensitive real estate pressure, mortgage-rate stress, homebuilder weakness, REIT repricing.",
        "watch_for": "XLRE, VNQ, IYR, ITB, XHB, MBB versus 10Y/TLT and bank/credit proxies.",
        "confirmation": "Real estate ETFs fail bounces while 10Y holds bid and MBB/credit softens.",
        "trading_read": "Treat housing and REIT strength as suspect until yields cool or MBB stabilizes.",
        "danger": "Real estate can bounce from defensive yield rotation if rates fall from growth scare.",
    },
    {
        "area": "Currencies",
        "condition": "Dollar strength broad against EUR/AUD/CAD/EMFX",
        "can_cause": "Global liquidity pressure, commodity FX weakness, foreign-market stress, pressure on risk assets.",
        "watch_for": "UUP/DXY up while EURUSD, AUDUSD, CADUSD, CEW weaken and global equities lag.",
        "confirmation": "Dollar holds highs and non-US equities/commodities fail to confirm risk-on.",
        "trading_read": "Risk-on needs more proof. Watch for QQQ/BTC/commodities to fade if dollar remains bid.",
        "danger": "USDJPY can rise from carry/rate differential without broad dollar risk-off pressure.",
    },
    {
        "area": "Sub-Sectors",
        "condition": "Sub-sector rotation diverges from headline index",
        "can_cause": "Hidden leadership shift, narrow index support, early sector stress or stealth accumulation.",
        "watch_for": "IYT, XRT, XME, XBI, ITA, XOP, OIH, TAN versus SPY/QQQ/RSP.",
        "confirmation": "Several sub-sectors lead/lag together while the headline index remains flat or misleading.",
        "trading_read": "Do not trust broad index read alone. Use sub-sectors to identify where the real pressure is building.",
        "danger": "Sub-sector ETFs can be thin or theme-driven; confirm with main sector and credit/volatility.",
    },

    {
        "area": "US Dollar",
        "condition": "Dollar rising hard",
        "can_cause": "Liquidity pressure, weaker commodities, weaker risk assets, stress in foreign USD debt.",
        "watch_for": "DXY/UUP strength together with weak equities, weak gold, weak BTC, or rising yields.",
        "confirmation": "Dollar holds pullbacks and closes near highs while risk assets fail rebounds.",
        "trading_read": "Continuation risk is lower for high-beta longs. Shorts/retests can work better until dollar stalls.",
        "danger": "Gold can still rise with dollar if fear/geopolitical bid is stronger than normal dollar pressure.",
    },
    {
        "area": "US Dollar",
        "condition": "Dollar falling cleanly",
        "can_cause": "Easier financial conditions, support for stocks, gold, crypto, and foreign markets.",
        "watch_for": "DXY lower highs, QQQ/SPX firm, BTC firm, gold firm, yields stable/down.",
        "confirmation": "Dollar loses reclaim attempts while risk assets hold higher lows.",
        "trading_read": "Risk-on continuation has more support; dips in growth/AI can be cleaner if yields are not rising.",
        "danger": "Dollar down because US growth is collapsing can still become risk-off if equities reject.",
    },
    {
        "area": "Rates",
        "condition": "2Y yield rising faster than 10Y",
        "can_cause": "Fed policy pressure, higher rate-cut repricing, growth stock pressure, bank/credit stress.",
        "watch_for": "DGS2 up, curve flattening/inverting, QQQ/NVDA pressure, VIX rising.",
        "confirmation": "Front-end yields hold bid after inflation/Fed/labor data.",
        "trading_read": "High-beta longs need more confirmation. AI/tech pullbacks become more likely.",
        "danger": "If equities ignore 2Y pressure, market may be pricing stronger growth rather than pure stress.",
    },
    {
        "area": "Rates",
        "condition": "10Y yield rising hard",
        "can_cause": "Discount-rate pressure, mortgage/housing pressure, long-duration tech/AI pressure.",
        "watch_for": "DGS10 up with TLT down, QQQ weak, homebuilders weak, gold reaction mixed.",
        "confirmation": "10Y closes above prior swing/yield resistance and TLT fails reclaim.",
        "trading_read": "Growth names need stronger location and confirmation. Watch for AI compression/breakdown.",
        "danger": "10Y up with copper/oil/equities up can mean growth expansion, not immediate risk-off.",
    },
    {
        "area": "Rates",
        "condition": "Yields falling cleanly",
        "can_cause": "Bond bid, easing expectations, tech support, gold support, possible growth scare.",
        "watch_for": "TLT up, DGS10/DGS2 down, QQQ reaction, gold reaction, VIX direction.",
        "confirmation": "Yields fail rebounds while equities or gold hold higher lows.",
        "trading_read": "If VIX is calm, growth/AI can rally. If VIX rises, falling yields may be recession fear.",
        "danger": "Falling yields are bullish only when not paired with heavy equity/credit stress.",
    },
    {
        "area": "Yield Curve",
        "condition": "Curve steepening after deep inversion",
        "can_cause": "Growth scare, recession repricing, Fed cut expectations, bank pressure.",
        "watch_for": "T10Y2Y/T10Y3M rising from deeply negative while equities weaken and unemployment/claims rise.",
        "confirmation": "Steepening persists while front-end yields fall faster than long-end yields.",
        "trading_read": "Do not treat every steepening as bullish. Check whether it is bull steepening or bear steepening.",
        "danger": "Bear steepening from inflation/fiscal supply can pressure stocks and bonds together.",
    },
    {
        "area": "Volatility",
        "condition": "VIX rising while SPX/QQQ falling",
        "can_cause": "Risk-off tape, hedging demand, liquidation, faster intraday moves.",
        "watch_for": "VIX expansion, weak breadth, failed equity bounces, dollar/yield confirmation.",
        "confirmation": "VIX holds above previous range and equities close near lows.",
        "trading_read": "Expect faster tap-go reactions, wider ranges, and less patience for slow setups.",
        "danger": "VIX spikes can mark exhaustion if they occur into strong HTF support/location.",
    },
    {
        "area": "Volatility",
        "condition": "VIX falling while equities rising",
        "can_cause": "Risk appetite, easier tape, dip buying, compression-to-expansion in growth names.",
        "watch_for": "SPX/QQQ higher lows, VIX lower highs, credit calm, yields not spiking.",
        "confirmation": "Equities hold retests while VIX fails to reclaim prior highs.",
        "trading_read": "Continuation setups have better backing. Shorts need stronger location/sweep evidence.",
        "danger": "Low VIX can also mean complacency if market is extended into major event risk.",
    },
    {
        "area": "Gold",
        "condition": "Gold rising with yields falling",
        "can_cause": "Real-yield relief, Fed cut pricing, safety bid, dollar weakness.",
        "watch_for": "GC up, real yield down, DXY down or flat, TLT up.",
        "confirmation": "Gold holds pullbacks while real yields fail rebounds.",
        "trading_read": "Gold longs have macro support when location/structure confirms.",
        "danger": "Gold can overextend fast around CPI/FOMC/NFP and reverse after the event.",
    },
    {
        "area": "Gold",
        "condition": "Gold rising with dollar and yields rising",
        "can_cause": "Fear/geopolitical/safety demand overpowering normal macro pressure.",
        "watch_for": "Gold firm despite DXY/DGS10 strength, oil up, VIX firm, news risk elevated.",
        "confirmation": "Gold refuses to break down after dollar/yield spikes.",
        "trading_read": "Gold may be trading as fear asset. Avoid assuming normal inverse relationship.",
        "danger": "If fear premium fades, gold can unwind sharply back toward normal rate/dollar logic.",
    },
    {
        "area": "Oil",
        "condition": "Oil rising sharply",
        "can_cause": "Inflation impulse, consumer pressure, bond yield pressure, sector rotation into energy.",
        "watch_for": "CL up, inflation breakeven proxies, yields reaction, airlines/transports weakness.",
        "confirmation": "Oil holds breakout/retest and energy equities confirm.",
        "trading_read": "Inflation-sensitive markets can get choppy; bond/yield reaction matters more.",
        "danger": "Oil up from growth demand is less bearish than oil up from supply/geopolitical shock.",
    },
    {
        "area": "Oil",
        "condition": "Oil falling sharply",
        "can_cause": "Lower inflation pressure, possible growth weakness, energy sector pressure.",
        "watch_for": "CL down with copper down and equities weak = growth scare; CL down with equities firm = inflation relief.",
        "confirmation": "Oil fails reclaim while inflation/rate proxies soften.",
        "trading_read": "Read through the cause: inflation relief can help risk, demand collapse can hurt risk.",
        "danger": "Do not assume oil down is bullish if copper, equities, and credit are also breaking down.",
    },
    {
        "area": "Copper",
        "condition": "Copper rising with equities",
        "can_cause": "Growth expansion signal, infrastructure/industrial demand, global risk-on confirmation.",
        "watch_for": "HG up, Russell/Dow firm, industrials firm, dollar not too strong.",
        "confirmation": "Copper holds higher lows while equities broaden beyond mega-cap tech.",
        "trading_read": "Risk-on has better breadth. Pullbacks can be continuation, not just squeeze.",
        "danger": "Copper can rise from supply issues; confirm with industrial/equity breadth.",
    },
    {
        "area": "Equities",
        "condition": "SPX/QQQ rising with falling dollar/yields",
        "can_cause": "Clean risk-on, easier liquidity, growth/AI support.",
        "watch_for": "QQQ/SMH/NVDA confirmation, VIX lower, DXY lower, yields stable/down.",
        "confirmation": "Equity dips hold and leadership expands beyond one ticker.",
        "trading_read": "Continuation bias improves. Pullbacks to clean location can work well.",
        "danger": "Narrow leadership only can fail if the rest of the market does not confirm.",
    },
    {
        "area": "Equities",
        "condition": "SPX rising but small caps weak",
        "can_cause": "Narrow leadership, mega-cap hiding place, late-cycle or fragile risk appetite.",
        "watch_for": "SPX/QQQ up while RUT weak, breadth weak, credit not confirming.",
        "confirmation": "Rallies concentrated in a small group; pullbacks hit broad names harder.",
        "trading_read": "Be selective. AI leaders may work while broad market internals weaken.",
        "danger": "Index strength can hide underlying rotation risk.",
    },
    {
        "area": "Crypto",
        "condition": "Bitcoin rising with Nasdaq and dollar down",
        "can_cause": "High-beta liquidity expansion, risk appetite, speculative flow.",
        "watch_for": "BTC up, QQQ up, DXY down, real yields down, VIX calm.",
        "confirmation": "BTC holds retests while tech/growth confirms.",
        "trading_read": "Risk appetite likely supportive. Watch for spillover to high beta assets.",
        "danger": "Crypto can detach around crypto-specific news/flows.",
    },
    {
        "area": "Credit",
        "condition": "Credit stress rising",
        "can_cause": "Risk-off, equity drawdown pressure, bank stress, lower liquidity.",
        "watch_for": "HYG/JNK weakness, VIX up, banks weak, yields down from safety if severe.",
        "confirmation": "Credit ETFs fail bounces while equities lose support.",
        "trading_read": "Risk-on setups need stronger proof. Avoid overconfidence in index bounces.",
        "danger": "Credit data may lag intraday. Use it as regime confirmation, not tick trigger.",
    },
    {
        "area": "AI",
        "condition": "NVDA + SMH + QQQ all rising",
        "can_cause": "AI leadership expansion, growth risk appetite, semiconductor confirmation.",
        "watch_for": "NVDA holding highs, SMH/SOXX confirmation, yields not spiking, VIX calm.",
        "confirmation": "AI leaders hold pullbacks and infrastructure names confirm.",
        "trading_read": "AI risk-on regime. Dips in AI/growth can be continuation if macro does not fight it.",
        "danger": "If AI rises alone while breadth is weak, the rally may be narrow and fragile.",
    },
    {
        "area": "AI",
        "condition": "NVDA weak while QQQ still firm",
        "can_cause": "AI leadership rotation, chip-specific pressure, possible warning before tech weakens.",
        "watch_for": "NVDA/SMH underperforming, MSFT/GOOGL/META holding, yields reaction.",
        "confirmation": "Semis fail retests while software/cloud names rotate higher.",
        "trading_read": "AI leadership is changing. Avoid treating QQQ strength as full AI strength.",
        "danger": "NVDA can shake out and reclaim quickly; wait for hold/fail around key location.",
    },
    {
        "area": "AI",
        "condition": "Semiconductors falling with yields rising",
        "can_cause": "High-rate pressure on growth, AI multiple compression, risk-off in long-duration assets.",
        "watch_for": "SMH/SOXX down, DGS10/DGS2 up, QQQ weak, VIX up.",
        "confirmation": "Semis fail bounces while yields hold above breakout levels.",
        "trading_read": "AI longs need stronger location and faster proof. Pullbacks can deepen.",
        "danger": "Strong earnings/guidance can override macro pressure temporarily.",
    },
    {
        "area": "AI Infrastructure",
        "condition": "Data center / power names leading",
        "can_cause": "AI infrastructure cycle strength, energy/power demand theme, capex expansion.",
        "watch_for": "VRT, ETN, EQIX, DLR, CCJ, URA confirmation with semis/cloud.",
        "confirmation": "Infrastructure group holds while mega-cap AI names pause.",
        "trading_read": "AI trade may be rotating from chips into power/cooling/data-center buildout.",
        "danger": "REIT/data-center names can be rate sensitive; check 10Y pressure.",
    },
    {
        "area": "Geopolitics",
        "condition": "Middle East/shipping/energy shock",
        "can_cause": "Oil spike, gold bid, inflation fear, risk-off, dollar safety demand.",
        "watch_for": "CL up, GC up, DXY firm, VIX firm, airlines/transports weak.",
        "confirmation": "Oil/gold hold after initial headline spike instead of fading immediately.",
        "trading_read": "Gold/oil can detach from normal technicals; wait for acceptance/hold after headline move.",
        "danger": "Headline spikes often reverse if there is no follow-through in oil/gold/VIX.",
    },
    {
        "area": "Geopolitics",
        "condition": "Sanctions/trade restrictions/chip export controls",
        "can_cause": "Semiconductor volatility, China-sensitive risk, supply-chain repricing.",
        "watch_for": "SMH/SOXX, NVDA/AMD/TSM/ASML reaction, China ETFs, dollar risk.",
        "confirmation": "Affected names fail bounces while broad AI basket diverges.",
        "trading_read": "AI may split: domestic software/cloud can hold while chip supply chain weakens.",
        "danger": "Policy headlines can be clarified or walked back; avoid chasing first headline candle.",
    },
    {
        "area": "Economic Data",
        "condition": "Hot inflation print",
        "can_cause": "Yields up, dollar up, stocks/AI pressure, gold mixed, rate cuts priced out.",
        "watch_for": "DGS2/DGS10 up, DXY up, QQQ/SMH down, Fed-sensitive names weak.",
        "confirmation": "Initial reaction holds after 30-90 minutes and does not fully reclaim pre-release levels.",
        "trading_read": "Do not force risk-on immediately. Let the post-news range choose direction.",
        "danger": "Hot CPI can reverse if the details are less bad or positioning was crowded.",
    },
    {
        "area": "Economic Data",
        "condition": "Soft inflation print",
        "can_cause": "Yields down, dollar down, growth/AI support, gold support, rate-cut pricing.",
        "watch_for": "DGS2/DGS10 down, QQQ/SMH up, VIX down, DXY down.",
        "confirmation": "Risk assets hold pullbacks and yields fail to reclaim the release spike.",
        "trading_read": "Risk-on continuation can be cleaner if growth data is not collapsing.",
        "danger": "Soft inflation plus weak growth can become recession fear, not clean risk-on.",
    },
    {
        "area": "Economic Data",
        "condition": "Strong jobs / strong wage pressure",
        "can_cause": "Higher yields, stronger dollar, less rate-cut hope, tech/AI pressure if too hot.",
        "watch_for": "NFP, unemployment, average hourly earnings, 2Y yield, dollar, QQQ/SMH.",
        "confirmation": "2Y yield and dollar hold bid after the release.",
        "trading_read": "Good news can become bad news when it delays easing.",
        "danger": "Strong jobs can support equities if inflation/rates do not respond badly.",
    },
    {
        "area": "Economic Data",
        "condition": "Weak jobs / rising claims",
        "can_cause": "Cut pricing, yields down, possible gold support, possible equity stress if growth scare.",
        "watch_for": "Claims up, unemployment up, payrolls weak, VIX, credit, Russell.",
        "confirmation": "Equities either hold rate-cut relief or reject as growth fear rises.",
        "trading_read": "Read the market reaction, not only the data headline.",
        "danger": "Weak data can first pump stocks then reverse if recession concern dominates.",
    },
    {
        "area": "Central Bank",
        "condition": "Hawkish Fed / higher-for-longer tone",
        "can_cause": "2Y up, dollar up, risk pressure, AI/growth multiple pressure.",
        "watch_for": "Fed statement, dot plot, Powell Q&A, 2Y yield, QQQ/NVDA reaction.",
        "confirmation": "Market continues in the same direction after Powell starts speaking.",
        "trading_read": "FOMC has two reactions: statement reaction, then press-conference reaction.",
        "danger": "First FOMC move is often trap; wait for second acceptance if possible.",
    },
    {
        "area": "Central Bank",
        "condition": "Dovish Fed / cuts closer",
        "can_cause": "Yields down, dollar down, equities/gold support, AI support if growth stable.",
        "watch_for": "2Y down, QQQ/SMH up, gold up, VIX down.",
        "confirmation": "Risk assets hold after press conference and yields fail reclaim.",
        "trading_read": "Risk-on can expand if recession fear is not the reason for cuts.",
        "danger": "Dovish because economy is breaking is not the same as healthy risk-on.",
    },
]


EVENT_WATCH_ROWS: list[dict[str, str]] = [
    {
        "event": "CPI Inflation",
        "typical_time_et": "08:30",
        "frequency": "Monthly",
        "why_it_matters": "Major inflation input for yields, dollar, Fed expectations, gold, AI/growth pressure.",
        "watch_before": "Check DXY, 2Y, 10Y, QQQ, gold, VIX; mark pre-release high/low.",
        "watch_after": "Does the first move hold, reverse, or create a two-sided sweep? Wait for acceptance.",
    },
    {
        "event": "PCE Inflation",
        "typical_time_et": "08:30",
        "frequency": "Monthly",
        "why_it_matters": "Fed-preferred inflation family; can reprice rate expectations.",
        "watch_before": "Check 2Y yield and Fed funds expectations proxies.",
        "watch_after": "Compare QQQ/SMH reaction against yields and dollar.",
    },
    {
        "event": "Nonfarm Payrolls / Jobs Friday",
        "typical_time_et": "08:30",
        "frequency": "Monthly",
        "why_it_matters": "Labor strength/weakness drives Fed and growth repricing.",
        "watch_before": "Check unemployment trend, claims trend, 2Y yield, dollar.",
        "watch_after": "Separate headline payrolls from wages/unemployment; watch the second move.",
    },
    {
        "event": "Initial Jobless Claims",
        "typical_time_et": "08:30",
        "frequency": "Weekly",
        "why_it_matters": "Fast labor stress clue; matters more when growth/recession risk is active.",
        "watch_before": "Check whether market is sensitive to labor weakness.",
        "watch_after": "If claims jump and equities fail, growth scare risk rises.",
    },
    {
        "event": "FOMC Statement",
        "typical_time_et": "14:00",
        "frequency": "Scheduled meetings",
        "why_it_matters": "Direct policy-rate and guidance catalyst.",
        "watch_before": "Flatten risk, know current regime, mark pre-FOMC range.",
        "watch_after": "First move may trap. Wait for statement acceptance and Powell reaction.",
    },
    {
        "event": "FOMC Press Conference",
        "typical_time_et": "14:30",
        "frequency": "Scheduled meetings",
        "why_it_matters": "Powell Q&A often reverses or confirms the statement reaction.",
        "watch_before": "Do not overtrust the 14:00 move if 14:30 is pending.",
        "watch_after": "Watch 2Y, dollar, QQQ, gold, and VIX for real acceptance.",
    },
    {
        "event": "ISM Manufacturing",
        "typical_time_et": "10:00",
        "frequency": "Monthly",
        "why_it_matters": "Growth/inflation mix; new orders and prices paid matter.",
        "watch_before": "Check copper, oil, industrials, rates.",
        "watch_after": "Hot prices paid can hit bonds; weak new orders can hit growth view.",
    },
    {
        "event": "ISM Services",
        "typical_time_et": "10:00",
        "frequency": "Monthly",
        "why_it_matters": "Services inflation and growth signal; often market-moving.",
        "watch_before": "Check 2Y/10Y, dollar, QQQ/SPX.",
        "watch_after": "Services prices/employment can matter more than headline.",
    },
    {
        "event": "Retail Sales",
        "typical_time_et": "08:30",
        "frequency": "Monthly",
        "why_it_matters": "Consumer demand and growth signal.",
        "watch_before": "Check consumer discretionary, yields, dollar.",
        "watch_after": "Strong sales can be growth-on or inflation/rates pressure depending on yield reaction.",
    },
    {
        "event": "GDP",
        "typical_time_et": "08:30",
        "frequency": "Quarterly releases/revisions",
        "why_it_matters": "Broad growth pulse; revisions can shift recession/soft-landing narrative.",
        "watch_before": "Check growth-sensitive assets like copper, Russell, Dow, credit.",
        "watch_after": "Strong growth with calm inflation = risk support; strong growth with yields spike = mixed.",
    },
    {
        "event": "Treasury Auctions",
        "typical_time_et": "13:00",
        "frequency": "Frequent scheduled auctions",
        "why_it_matters": "Weak demand can push yields up and pressure equities/gold.",
        "watch_before": "Check 10Y/30Y, TLT, dollar, equities near auction time.",
        "watch_after": "Tail/weak demand = yields up pressure; strong demand = bond relief.",
    },
    {
        "event": "EIA Crude Oil Inventories",
        "typical_time_et": "10:30",
        "frequency": "Weekly",
        "why_it_matters": "Can move oil and inflation/energy-sensitive trades.",
        "watch_before": "Check CL structure and energy equities.",
        "watch_after": "Inventory shock only matters broadly if oil move holds and yields/inflation react.",
    },
    {
        "event": "Fed Speakers",
        "typical_time_et": "Varies",
        "frequency": "Frequent",
        "why_it_matters": "Can shift rate-cut/hike expectations between official meetings.",
        "watch_before": "Know whether speaker is voting/non-voting and topic is policy relevant.",
        "watch_after": "2Y yield and dollar response tells if market cared.",
    },
    {
        "event": "Mega-cap AI Earnings",
        "typical_time_et": "Before open / after close",
        "frequency": "Quarterly",
        "why_it_matters": "NVDA, MSFT, GOOGL, AMZN, META can move AI regime and Nasdaq sentiment.",
        "watch_before": "Check AI score, semis score, QQQ, yields, option-implied move if available.",
        "watch_after": "Guidance/capex comments matter more than headline EPS in AI cycle.",
    },
]


SCENARIO_ROWS: list[dict[str, str]] = [
    {
        "scenario": "Clean Risk-On",
        "ingredients": "SPX/QQQ up, VIX down, dollar down, yields stable/down, AI confirming.",
        "likely_cause": "Liquidity easing, soft inflation, dovish Fed, strong earnings, calm geopolitics.",
        "look_out_for": "Dip holds, breadth improves, semis confirm, BTC/copper participate.",
        "invalidates_when": "Dollar/yields spike and equities fail to hold pullbacks.",
    },
    {
        "scenario": "Liquidity Pressure",
        "ingredients": "Dollar up, 2Y/10Y up, QQQ weak, VIX firm, TLT down.",
        "likely_cause": "Hot inflation, hawkish Fed, weak Treasury demand, rate-cut repricing.",
        "look_out_for": "Growth/AI underperformance and failed equity bounces.",
        "invalidates_when": "Yields/dollar reverse lower and QQQ/SMH reclaim quickly.",
    },
    {
        "scenario": "Geopolitical Fear Bid",
        "ingredients": "Gold up, oil up, dollar firm, VIX firm, equities mixed/weak.",
        "likely_cause": "War escalation, supply shock, sanctions, shipping disruption.",
        "look_out_for": "Gold/oil hold after headline, risk assets fail bounce.",
        "invalidates_when": "Oil/gold headline spike fades and VIX falls.",
    },
    {
        "scenario": "Growth Scare",
        "ingredients": "Yields down, equities down, VIX up, dollar firm, copper/oil weak.",
        "likely_cause": "Weak jobs, weak ISM, recession fear, credit stress.",
        "look_out_for": "Credit weakness, small caps/banks underperform, curve steepens.",
        "invalidates_when": "Equities respond positively to lower yields and credit holds.",
    },
    {
        "scenario": "Inflation Relief Rally",
        "ingredients": "Yields down, dollar down, QQQ/AI up, gold firm, VIX down.",
        "likely_cause": "Soft CPI/PCE/wage data, dovish Fed guidance.",
        "look_out_for": "AI/semis leading and pullbacks holding after the event.",
        "invalidates_when": "Weak growth details cause VIX/credit stress to rise.",
    },
    {
        "scenario": "AI Leadership Expansion",
        "ingredients": "NVDA/SMH/SOXX up, QQQ up, VIX calm, yields not fighting.",
        "likely_cause": "Strong AI earnings/guidance, capex cycle, chip demand, data-center buildout.",
        "look_out_for": "Infrastructure names confirm and leadership broadens.",
        "invalidates_when": "NVDA/SMH fail retests while QQQ holds only by non-AI names.",
    },
    {
        "scenario": "AI Rotation / Narrow Market",
        "ingredients": "QQQ/SPX up but RUT/SMH/NVDA weak or mixed.",
        "likely_cause": "Crowded leadership, post-earnings rotation, rate pressure, valuation stress.",
        "look_out_for": "Divergences between mega-cap, semis, software, and infrastructure.",
        "invalidates_when": "Semis reclaim and breadth improves.",
    },
    {
        "scenario": "Bond Market Stress",
        "ingredients": "Yields up, TLT down, dollar firm, equities weak, gold mixed.",
        "likely_cause": "Hot data, weak auction, fiscal/supply concern, hawkish Fed.",
        "look_out_for": "10Y/30Y pressure and equity multiple compression.",
        "invalidates_when": "Bond bid returns and yields lose the breakout.",
    },
]


GEOPOLITICAL_ROWS: list[dict[str, str]] = [
    {
        "risk": "Energy supply shock",
        "first_markets": "Oil, gold, dollar, VIX, energy equities",
        "second_order_effects": "Inflation expectations, yields, consumer pressure, transport weakness.",
        "watch_trigger": "Oil and gold hold gains after headline instead of reversing.",
    },
    {
        "risk": "Shipping route disruption",
        "first_markets": "Oil, freight-sensitive equities, gold, dollar",
        "second_order_effects": "Supply-chain inflation, delivery delays, margin pressure.",
        "watch_trigger": "Oil/freight-sensitive assets confirm for more than one session.",
    },
    {
        "risk": "Chip export restrictions",
        "first_markets": "NVDA, AMD, TSM, ASML, SMH/SOXX",
        "second_order_effects": "AI supply chain repricing and China-sensitive weakness.",
        "watch_trigger": "Semis break while software/cloud AI holds or diverges.",
    },
    {
        "risk": "Banking/credit stress",
        "first_markets": "Banks, HYG/JNK, VIX, yields, dollar",
        "second_order_effects": "Liquidity tightening, risk-off, Fed-cut pricing.",
        "watch_trigger": "Credit fails bounces and VIX expands with equity downside.",
    },
    {
        "risk": "Election/policy shock",
        "first_markets": "Dollar, yields, sector ETFs, volatility",
        "second_order_effects": "Tax/regulation/trade repricing, sector rotation.",
        "watch_trigger": "Market reaction persists beyond first headline cycle.",
    },
]


CHECKLIST_ROWS: list[dict[str, str]] = [
    {"step": "1", "question": "What is the current macro regime?", "why": "Defines whether risk-on or risk-off setups have background support."},
    {"step": "2", "question": "Is the dollar helping or fighting risk?", "why": "Dollar pressure often controls liquidity feel."},
    {"step": "3", "question": "Are yields rising from growth or inflation/stress?", "why": "Same yield move can have opposite meanings depending on equities/copper/VIX."},
    {"step": "4", "question": "Is AI leading, rotating, or breaking?", "why": "AI can pull Nasdaq and risk sentiment."},
    {"step": "5", "question": "What event/time is next?", "why": "CPI, NFP, FOMC, ISM, auctions, and earnings can flip the tape."},
    {"step": "6", "question": "Is gold acting normal or fear-driven?", "why": "Gold rising with dollar/yields can signal safety/geopolitical bid."},
    {"step": "7", "question": "Is oil creating inflation pressure or showing demand weakness?", "why": "Oil up/down has different meaning depending on cause."},
    {"step": "8", "question": "Are VIX and credit calm or warning?", "why": "VIX/credit tell if risk appetite is real or fragile."},
]


CATEGORY_DIAGNOSTICS: dict[str, dict[str, str]] = {
    "Equities": {
        "positive": "Equity risk appetite is supportive. Look for dip holds and breadth/AI confirmation.",
        "negative": "Equities are pressuring the regime. Watch for failed bounces, VIX confirmation, and liquidity stress.",
    },
    "Volatility": {
        "positive": "Volatility pressure is easing. That usually supports cleaner continuation if other categories confirm.",
        "negative": "Volatility pressure is rising. Expect faster moves, wider ranges, and higher reversal risk.",
    },
    "Dollar": {
        "positive": "Dollar pressure is easing. This can support risk assets, gold, commodities, and crypto.",
        "negative": "Dollar pressure is rising. Watch liquidity stress and weak high-beta assets.",
    },
    "Rates": {
        "positive": "Rates are supportive or easing. Growth/AI can respond well if this is not recession fear.",
        "negative": "Rates are pressuring the tape. Watch 2Y/10Y, TLT, QQQ, semis, and gold reaction.",
    },
    "Commodities": {
        "positive": "Commodity action is growth-supportive. Confirm with copper and equity breadth.",
        "negative": "Commodity/inflation pressure is negative. Separate oil inflation shock from demand weakness.",
    },
    "Crypto": {
        "positive": "Crypto is confirming high-beta liquidity appetite.",
        "negative": "Crypto is not confirming risk appetite. Watch for high-beta weakness.",
    },
    "Economy": {
        "positive": "Economic data is supportive. Watch whether yields stay calm.",
        "negative": "Economic data is pressuring the regime. Separate inflation pressure from growth weakness.",
    },
    "AI Leaders": {
        "positive": "AI leaders are supportive. Watch NVDA/MSFT/GOOGL/META and whether leadership broadens.",
        "negative": "AI leaders are under pressure. Watch for rotation, earnings risk, or rate pressure.",
    },
    "Semiconductors": {
        "positive": "Semiconductors confirm AI risk appetite.",
        "negative": "Semiconductors are pressuring AI. Watch NVDA/SMH/SOXX and yield pressure.",
    },
    "AI Infrastructure": {
        "positive": "Infrastructure confirms AI buildout demand. Watch VRT/ETN/data centers/power names.",
        "negative": "Infrastructure is not confirming AI demand or may be rate-sensitive.",
    },
    "AI ETFs": {
        "positive": "AI basket breadth is supportive.",
        "negative": "AI ETF basket is weakening. Watch if weakness spreads beyond one ticker.",
    },
}


def cause_effect_df() -> pd.DataFrame:
    return pd.DataFrame(CAUSE_EFFECT_ROWS)


def event_watch_df() -> pd.DataFrame:
    return pd.DataFrame(EVENT_WATCH_ROWS)


def scenario_df() -> pd.DataFrame:
    return pd.DataFrame(SCENARIO_ROWS)


def geopolitical_df() -> pd.DataFrame:
    return pd.DataFrame(GEOPOLITICAL_ROWS)


def checklist_df() -> pd.DataFrame:
    return pd.DataFrame(CHECKLIST_ROWS)


def auto_event_calendar_df(months_ahead: int = 6, include_live_sources: bool = True) -> pd.DataFrame:
    """Automatic event calendar. No manual CSV editing needed."""
    return build_auto_event_calendar(months_ahead=months_ahead, include_live_sources=include_live_sources)


def load_manual_events(path: str | Path = "manual_events.csv") -> pd.DataFrame:
    """Backward-compatible alias for v3. v4 now returns the auto calendar."""
    return auto_event_calendar_df()


def diagnostics_for_categories(category_scores: pd.DataFrame, threshold: float = 20.0) -> list[str]:
    if category_scores.empty:
        return ["No category scores loaded yet."]
    diagnostics: list[str] = []
    ranked = category_scores.copy()
    ranked["score"] = pd.to_numeric(ranked["score"], errors="coerce")
    ranked = ranked.dropna(subset=["score"])
    for row in ranked.sort_values("score").itertuples(index=False):
        category = getattr(row, "category")
        score = float(getattr(row, "score"))
        if abs(score) < threshold:
            continue
        guide = CATEGORY_DIAGNOSTICS.get(category, {})
        tone = "positive" if score > 0 else "negative"
        text = guide.get(tone)
        if text:
            diagnostics.append(f"{category} ({score:.1f}): {text}")
    if not diagnostics:
        diagnostics.append("No category is beyond the diagnostic threshold yet. Regime is mixed or quiet.")
    return diagnostics
