# XAUUSD Gold Intelligence — Strategy Engine V1

## Goal
Build a deterministic, backtestable strategy engine for XAUUSD using broker-native MT4 candles. The engine must separate context, setup, trigger, risk and execution so indicators do not independently create trades.

## Operating principle
A trade is allowed only when:
1. Mandatory safety gates pass.
2. A strategy setup is valid.
3. A trigger confirms the setup.
4. No veto condition is active.
5. Risk and execution checks pass.

Initial rollout: visualisation -> signal classification -> historical backtest -> shadow signals -> demo execution -> optional full-auto demo.

## Core inputs
- Broker-native XAUUSD candles: M1, M5, M15, M30, H1, H4, D1.
- SMA 44.
- EMA 99.
- SMA 200.
- VCPR records.
- Previous Day High / Low / Close.
- Previous Week High / Low.
- Session High / Low for Asia, London and New York.
- DXY.
- US 10Y yield.
- High-impact economic-news lock.
- Spread, feed freshness and broker execution state.

## Moving-average interpretation
Moving averages are context/gateway tools, not standalone signals.

### Bullish alignment
- Price above SMA44.
- SMA44 above EMA99.
- EMA99 above SMA200.

### Bearish alignment
- Price below SMA44.
- SMA44 below EMA99.
- EMA99 below SMA200.

### Transition
Any mixed ordering is classified as TRANSITION and receives lower confidence until backtesting proves otherwise.

### Events to classify
For SMA44, EMA99 and SMA200:
- approach
- touch
- rejection
- close above / close below
- cross
- confirmed cross
- failed cross

A confirmed cross should require closed-candle confirmation. Exact confirmation count and tolerance are backtest parameters, not hard-coded assumptions.

## Higher-timeframe bias
Primary context:
- H4 = structural bias.
- H1 = working trend.
- M15 = setup timeframe.
- M5 = entry/trigger timeframe.
- M1 = optional execution refinement only.

D1 is used for major directional context and previous-day levels, not as a mandatory entry trigger.

## Strategy A — Trend Pullback
Purpose: participate in an established H1/H4 trend after a controlled retracement.

### Long setup context
- H4 is bullish or bullish-neutral.
- H1 trend is bullish.
- Price is not directly underneath a major resistance level.
- No hard veto is active.

### Long pullback zone
At least one valid confluence area:
- SMA44,
- EMA99,
- VCPR pivot/zone,
- previous-day structural level,
- session breakout level retest.

More than one confluence may increase setup quality after backtesting.

### Long trigger
On M5 or M15, require a closed-candle bullish reaction from the pullback zone. Candidate trigger families for backtest:
- rejection candle,
- reclaim after temporary close below,
- break of local lower-high after pullback,
- bullish engulf / strong body close,
- failed bearish continuation.

Do not choose the winning trigger family before backtesting.

### Long invalidation
The setup is invalid if:
- price closes through the structural invalidation level,
- H1 trend flips bearish,
- feed/news/spread veto activates before entry,
- risk distance becomes unacceptable.

Short rules are the mirror image.

## Strategy B — Breakout + Retest
Purpose: avoid chasing first breakout candles and trade confirmed acceptance beyond a key level.

Key levels:
- Previous Day High / Low.
- Previous Week High / Low.
- Asia High / Low.
- London High / Low.
- VCPR pivot.
- major MA clusters when backtest supports them.

### Long sequence
1. Price breaks above a key level.
2. A candle closes above the level.
3. Price retests the breakout area.
4. Retest holds or briefly sweeps and reclaims.
5. M5/M15 trigger confirms continuation.
6. No major opposing level is too close.

### Fake-breakout protection
Do not classify a breakout as confirmed solely because the wick crossed the level.

Backtest variables:
- required close distance beyond level,
- number of confirming closes,
- maximum retest depth,
- maximum time/bars allowed for retest.

Short rules are mirrored.

## Strategy C — Failed Breakout / Reversal
Purpose: identify liquidity sweeps and failed continuation at important levels.

Candidate long reversal:
1. Price trades below a major support/liquidity level.
2. It fails to maintain acceptance below.
3. It closes/reclaims back above the level.
4. M5/M15 structure turns bullish.
5. Higher-timeframe context does not strongly veto the reversal.

Candidate short reversal is mirrored above resistance.

This strategy must be scored separately from Trend Pullback because reversal trades have different risk and expectancy.

## VCPR rules
Canonical VCPR classification:
- CPR is calculated from D-1.
- A day is VCPR only if its full CPR zone is untouched during that same trading day.
- Wick touch counts.
- Once classified VCPR, it remains historically VCPR forever even if visited later.
- Visible chart may show the center Pivot only.
- Later touch is metadata and must not declassify the original VCPR.

VCPR may act as:
- pullback confluence,
- breakout/retest level,
- reversal/liquidity level,
- target obstacle.

Its actual weight must come from historical testing.

## Macro confirmation
DXY and US10Y are confirmation/veto inputs, not primary entry signals.

Candidate bullish-gold confirmation:
- DXY weakening,
- US10Y falling/stable,
- no conflicting high-impact macro shock.

Candidate bearish-gold confirmation is the inverse.

Do not hard-code a directional score until historical validation is complete.

## Mandatory hard gates
Before any entry:
- MT4 feed fresh.
- Candle data fresh.
- spread within configured threshold.
- valid bid/ask.
- no duplicate position/order.
- max open positions not exceeded.
- max daily loss not exceeded.
- stop-loss valid for broker rules.
- sufficient margin.
- no active emergency/news veto.

## News lock
High-impact events should block new entries around release time. Initial window is configurable and must be tested. Existing positions are managed under a separate policy; do not automatically close simply because a news lock begins.

## Engine states
WATCH -> FORMING -> READY -> ARMED -> EXECUTED -> MANAGED -> CLOSED

Alternative exits:
- INVALIDATED
- CANCELLED

Definitions:
- WATCH: context exists but no setup.
- FORMING: setup is developing.
- READY: setup conditions complete, waiting for trigger.
- ARMED: trigger confirmed and execution gates are being checked.
- EXECUTED: demo order opened.
- MANAGED: SL/TP/breakeven/trailing logic active.
- CLOSED: trade completed and immutable performance event recorded.

## Backtest requirements
Do not optimize on one timeframe or a short sample.

For each strategy record:
- sample count,
- win rate,
- expectancy in R,
- profit factor,
- average win/loss,
- max drawdown,
- MAE/MFE,
- session,
- direction,
- timeframe,
- volatility regime,
- news proximity,
- VCPR relationship,
- MA relationship,
- DXY/US10Y context where historical data is available.

Use out-of-sample validation and avoid selecting parameters solely because they maximize historical profit.

## Initial implementation order
1. Calculate SMA44, EMA99 and SMA200 from `market_candles` in application code.
2. Render the three averages on the dashboard chart.
3. Add MA relationship/event classification.
4. Build Strategy A classifier in shadow mode.
5. Build historical backtest runner for Strategy A.
6. Validate and freeze parameters.
7. Add Strategy B and backtest.
8. Add Strategy C and backtest.
9. Add macro confirmation and news veto.
10. Add demo execution only after shadow/backtest acceptance.

## Database policy
No Supabase schema change is required merely to calculate moving averages or classify live setups. Use existing `market_candles` and `market_latest` as source data.

Add new schema only when persistence is required, for example:
- strategy_signals,
- backtest_runs,
- backtest_trades,
- gateway snapshots,
- official-call events.

Avoid storing every derived indicator value unless later analysis demonstrates a need.

## V1 safety rule
No strategy in V1 is permitted to send a live-money order. Automatic execution is demo-only after backtest and shadow-mode validation.
