# XAUUSD Gold Intelligence — Audited Gateway Strategy Playbook

Status: research specification; not a claim of profitability.

Purpose: convert the 16-strategy playbook into deterministic, backtestable gateway candidates for the existing Strategy Engine V1. No strategy is allowed to create a trade by itself. All thresholds below are parameters to validate, not assumed edge.

## Audit principles

1. Closed-candle data is the default for signal confirmation. Intrabar logic must be a separately tested execution variant.
2. Context, setup, trigger, veto, risk, execution, and management are separate layers.
3. Replace subjective phrases such as `strong candle`, `fresh zone`, `institutional candle`, `decisive bounce`, and `quickly reverses` with measurable definitions before backtesting.
4. Avoid look-ahead bias: swing points, divergence, zones, Fibonacci anchors, session levels and higher-timeframe values must only use information available at signal time.
5. Broker-native XAUUSD tick volume is not centralized global gold volume. Treat it as broker activity/tick intensity. If real traded volume is desired, use a separately timestamp-aligned exchange/futures feed and test it independently.
6. DXY and US10Y are confirmation/veto inputs, not automatic directional triggers. Correlation strength and lookback must be measured dynamically.
7. Every strategy is evaluated out-of-sample and walk-forward, including spread/slippage and session/news conditions.
8. Never promote an unverified published performance claim into gateway weighting. Win rate, profit factor and trade count must be reproduced on our own data.
9. Risk/exit policy is tested separately from entry edge. Fixed gold `pip` terminology is avoided internally; use price distance, ATR and R because broker conventions vary.
10. Strategies that describe the same market event are deduplicated into one candidate exposure.

## Shared deterministic primitives

Implement once and reuse across gateways:

- `ema(tf,n)`, `sma(tf,n)`, `atr(tf,n)`, `rsi(tf,n)`.
- `body = abs(close-open)`; `range = high-low`; upper/lower wick ratios.
- `bullish_engulf` / `bearish_engulf` using closed candles.
- `rejection(level,tolerance_atr,wick_ratio,close_location)`.
- `swing_high/low(left,right)` with confirmation delay explicitly recorded.
- `break(level,close_buffer_atr)`; `reclaim(level)`; `acceptance(level,n_closes,max_reentry_atr)`.
- `retest(level,tolerance_atr,max_bars)`.
- `BOS` and `CHoCH` based on confirmed swing structure, with pivot parameters stored in each result.
- `session_range(session_timezone,start,end)` using DST-aware IANA time zones.
- `PDH/PDL/PDC`, `PWH/PWL`, Asia/London/New York high/low.
- `volume_z = current_tick_volume / rolling_median_or_mean`; source always tagged.
- `distance_to_level / ATR` and `reward_space_R`.
- VCPR according to the canonical immutable classification in Strategy Engine V1.
- news state: `NORMAL`, `PRE_NEWS_LOCK`, `POST_NEWS_DISCOVERY`, `POST_NEWS_CONFIRMED`.

## Gateway contract

Each gateway returns evidence, never an order:

```text
strategy_id, profile, direction, state,
context_pass, setup_pass, trigger_pass,
primary_level, entry_reference, invalidation,
target_reference, expected_R,
confluences[], vetoes[],
parameter_version, data_source,
signal_bar_time, generated_at
```

Candidate state progression remains `WATCH -> FORMING -> READY -> ARMED`; only the execution/risk layer may progress to an order in demo mode.

---

# Part A — Intraday gateway audit

## P01 — EMA 9/15 Hybrid Rejection

Audit: viable as a trend-pullback candidate, but 9/15 alignment alone is too sensitive in chop. The published/open strategy concept itself warns that performance depends on market conditions and needs backtesting.

Gateway candidate:
- Context: M15 EMA9 > EMA15 for long, inverse for short; test optional H1 trend filter.
- Setup: M5 EMA9 > EMA15 and price pulls into an ATR-normalized distance of the EMA band.
- Trigger: closed M5 rejection candle. Parameterize minimum wick/body ratio, close location and maximum candle range in ATR.
- Veto: flat EMA slope/compression, insufficient target space, stale feed, excessive spread, news lock.
- Management: compare structural SL vs ATR SL; compare fixed partial + runner against pure-R exits.

Improvement: require pullback/rejection rather than accepting any EMA alignment. Test slope and regime filters independently.

## P02 — EMA 50/200 + Engulfing

Audit: deterministic after defining engulfing, but RSI 45–55 should not be assumed optimal and a fixed 20-pip target is not volatility invariant.

Gateway candidate:
- Context: EMA50/EMA200 ordering and slopes on M15/H1 variants.
- Setup: pullback toward EMA50 or validated structure.
- Trigger: closed engulfing candle plus close on trend side of EMA50.
- RSI neutral band is a parameter grid, not a fixed truth.
- Stops/targets expressed in ATR/R and structural distance; fixed-price target retained only as a comparison variant.

## P03 — VWAP + EMA + DXY

Audit: useful research family, but `institutional order flow` is too strong a description for spot XAUUSD VWAP/tick data. Spot XAUUSD is fragmented OTC; broker volume is not centralized traded volume.

Gateway candidate:
- Define VWAP source explicitly. Broker-tick VWAP and exchange/futures VWAP are separate variants.
- Context: price side of VWAP + EMA9/20/50 ordering.
- Trigger: measurable displacement/rejection near VWAP/EMA cluster.
- DXY: use synchronized return/slope and optional rolling correlation regime; do not require inverse movement when measured correlation is weak.
- Volume: optional confirmation only, source-tagged.

Improvement: never let DXY or volume alone create a signal.

## P04 — Five-Filter Supply/Demand

Audit: currently under-specified because `fresh H1 supply/demand zone` is subjective.

Before activation define zone algorithm, e.g. displacement-origin/base candles, minimum departure in ATR, maximum base bars, and touch count. `Fresh` must mean a machine-readable number of prior penetrations/touches.

Gateway:
H1 zone -> H1 EMA50 context -> RSI regime -> closed M15 directional confirmation -> closed M5 breakout/engulf trigger. All five conditions can form a strict research variant, but weighting must come from tests rather than calling it Grade A in advance.

## P05 — RSI + EMA Momentum Reversal

Audit: RSI <30/>70 can remain extreme in strong gold trends. This should not be a standalone reversal gateway.

Improvement:
- Require trend-side EMA context as proposed.
- Add actual reversal/reclaim trigger after RSI excursion instead of entering merely because threshold is crossed.
- Test RSI crossing back through threshold, divergence, structure reclaim, and distance-from-EMA variants separately.
- Disable during high-impact expansion unless a dedicated post-news model validates it.

---

# Part B — Swing / extended gateway audit

Keep these statistics completely separate from intraday.

## P06 — Horizon Trend Rider

Strongly specified candidate. Test D1 EMA50/200 regime, H4 EMA21 pullback tolerance, RSI threshold, resumption candle definition, ATR stop, time stop and Chandelier management independently. Use only completed D1/H4 candles. Do not assume 2.5 ATR / 3 ATR are optimal.

## P07 — Volatility-Adjusted Mean Reversion

Audit warning: the supplied `73% win rate`, `PF ~2.1`, `1,200 trades` is unverified and must not be stored as expected performance or gateway weight.

Need exact formula for volatility threshold and IBS before implementation. Candidate definition:
`IBS=(close-low)/(high-low)` with zero-range protection; 10-period high, 25-period average-range formula and MA50 regime must be explicitly versioned. Research-only until independently reproduced.

## P08 — Coil Breakout

Improve by defining compression without mixing 5-day and D1 units ambiguously. Candidate: rolling 5-day high-low divided by D1 ATR14; threshold is optimized only in training folds. Require closed breakout or separately test stop-entry execution. Include gap/slippage and overnight financing/execution assumptions.

## P09 — MA Confluence Zone

Currently descriptive, not executable. Define normalized dispersion, e.g. `(max(MA20,50,100,200)-min(...))/ATR`. A cluster is valid only below a tested threshold. Direction must come from approach + rejection/acceptance + HTF regime; the cluster itself is not directional.

## P10 — Fibonacci + Price Action

Main risk is hindsight selection of swing anchors. Use only confirmed algorithmic swing pivots. Store anchor timestamps and pivot-confirmation time. Test 38.2/50/61.8 as independent zones with ATR tolerance; do not assume one level has superior probability. Require closed rejection/reclaim/continuation trigger.

---

# Part C — S&R / fake-breakout / sniper audit

These six strategies share primitives and should not become six duplicate positions.

## P11 — Asian Range False Breakout

High-value candidate for our existing Session Liquidity Sweep strategy.
- Define Asia session with one canonical DST-safe timezone/session policy; do not hard-code Beijing clock as the engine's universal session definition.
- Range high/low must be frozen at session completion.
- Sweep = wick/price exceeds boundary by tested minimum; reclaim = closed M5/M15 back inside.
- Test maximum sweep depth, reclaim time, session opening window and target policy.

## P12 — Liquidity Sweep + Volume Confirmation

Use confirmed rolling 20-bar high/low without accidentally including the signal candle in the reference range. Volume 1.5x is only a candidate threshold. Broker XAUUSD volume is tick activity, so record source and test with/without it. A volume spike without follow-through can be evidence, not proof of institutional activity.

## P13 — Failed Breakout / Failed Retest

Maps closely to Strategy C/B. Improve with explicit states:
`BREAK -> RETEST -> FAILED_ACCEPTANCE -> RECLAIM -> TRIGGER`.
Set maximum bars between states and ATR-normalized level tolerance. Enter only after closed trigger. This is different from a valid breakout-retest continuation and must be labeled accordingly.

## P14 — Pin-Bar Rejection at Key Level

Define pin bar mathematically: wick/body ratio, close location, minimum/maximum range in ATR, and distance to level. Round-number spacing must be instrument/digits aware. RSI/Stochastic is optional evidence, not mandatory until tested. Avoid entering when opposing target space is inadequate.

## P15 — MTF Structure + Divergence

Audit: divergence is especially vulnerable to hindsight/repainting if pivots are not confirmed. Define oscillator, pivot width, maximum separation in bars and confirmation delay. Never compare a current unconfirmed swing with a future-confirmed pivot. Require level reclaim plus closed structure trigger. Test MACD and Stochastic variants separately rather than mixing them.

## P16 — Post-News Fake Breakout

Keep separate from ordinary liquidity sweeps.
- Hard pre-news lock blocks new entries.
- At release, record pre-news PDH/PDL/session/swing levels and spike extremes.
- No entry during configurable discovery window (candidate 5/10/15 minutes; test each).
- Require closed reclaim plus algorithmic BOS/CHoCH after the release.
- Spread must normalize below threshold before ARMED.
- Model slippage explicitly; news backtests using only OHLC can materially understate execution risk.

---

# Breakout classifier — improved

Do not use a binary narrative table alone. Record measurable evidence:

Real-breakout evidence candidates:
- closed distance beyond level / ATR,
- N closes accepted beyond level,
- retest holds,
- follow-through MFE within N bars,
- structure continuation,
- normalized activity/volume where reliable.

Failed-breakout evidence candidates:
- excursion beyond level followed by close back inside,
- wick/body rejection,
- reclaim speed,
- failed retest,
- opposing CHoCH/BOS,
- divergence only when confirmed without look-ahead.

The classifier must output features and state. It must not assign a probability until calibrated out-of-sample.

# Risk and execution improvements

- Default research risk cap may be 1% or lower, but actual demo risk is configurable and evaluated by drawdown, losing streak and tail behavior.
- Structural invalidation is primary; ATR provides volatility normalization and maximum/minimum stop sanity checks.
- Reject trades when stop distance is too small for spread/noise or too large for risk budget.
- Minimum target space is expressed in R after spread/slippage.
- Daily loss, max exposure, stale feed, abnormal spread, margin and news locks are hard gates.
- No martingale, loss-chasing, or automatic averaging down.
- Intraday and swing exposure budgets remain separate.

# Gateway grouping to avoid double counting

Instead of treating all 16 as independent votes, group correlated strategies:

- Trend/Pullback family: P01, P02, P04, P06.
- Dynamic-value/correlation family: P03, P09, P10.
- Mean-reversion family: P05, P07.
- Breakout/expansion family: P08 plus existing Strategy B/F/H/J.
- Liquidity/fakeout family: P11, P12, P13, P14, P15, P16 plus existing Strategy C/E/G.

Multiple strategies from the same family increase evidence metadata but do not count as independent gateways. This prevents `five similar fake-breakout rules` from appearing as five independent confirmations.

# Promotion standard for a gateway

Lifecycle:
`SPEC -> IMPLEMENTED -> UNIT_TESTED -> BACKTESTED -> OOS_VALIDATED -> SHADOW -> DEMO_ELIGIBLE`.

Minimum research record per strategy/version:
- exact parameter JSON + code/data version,
- train/test date ranges and broker/timezone/session policy,
- trade count,
- win/loss/BE,
- expectancy in R,
- profit factor,
- median R,
- max drawdown in R and %, if account simulation is used,
- MFE/MAE,
- average/median holding time,
- long/short split,
- session split,
- volatility-regime split,
- news/non-news split,
- spread/slippage assumptions,
- out-of-sample metrics,
- walk-forward fold metrics,
- parameter-stability/sensitivity results.

Do not promote on win rate alone. Prefer stable expectancy across regimes and parameter neighborhoods over the best in-sample result.

# Backtest anti-bias requirements

1. Chronological train/validation/test splits; never random shuffle time series.
2. Walk-forward validation.
3. No future-confirmed pivots at signal time.
4. Higher-timeframe candle values only after their close unless explicitly testing an intrabar variant.
5. Session/DST alignment versioned.
6. Spread and slippage included; use conservative news assumptions.
7. Deduplicate overlapping setups before counting trades.
8. Report all tested variants, including failures, to reduce selection bias.
9. Freeze a strategy version before final out-of-sample evaluation.
10. Paper/shadow forward validation before demo eligibility.

# Data plan

Primary/live truth remains Alpari MT4 broker-native candles. Long external M5 history may be used for research only after session/timezone calibration against overlapping Alpari D1/M5 data. VCPR history must preserve the canonical D-1 CPR/full-zone origin-day untouched rule.

For volume-sensitive strategies, store `volume_source` (`ALPARI_TICK`, `COMEX_GC`, etc.) and never silently substitute one for another.

# Implementation priority

Phase 1 — shared primitives + strategies with least subjective interpretation:
P01, P02, P11, P12 (without mandatory volume), P13, P14, P16.

Phase 2 — algorithmic zone/structure definitions:
P04, P08, P09, P10, P15.

Phase 3 — external/synchronized data or special research:
P03, P05, P06, P07 and alternative real-volume variants.

This priority is about implementation determinism, not predicted profitability.

# Relationship to Strategy Engine V1

This document extends `docs/STRATEGY_ENGINE_V1.md`; it does not replace it. The existing hard gates, conflict policy, VCPR definition, public/private gateway separation, state machine and demo-first execution policy remain authoritative.
