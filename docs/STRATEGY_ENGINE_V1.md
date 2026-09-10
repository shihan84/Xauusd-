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

## Strategy D — VCPR Reaction
Purpose: trade statistically validated reactions around confirmed historical VCPR pivots without assuming every VCPR is support/resistance.

### Eligible levels
Only confirmed historical VCPR records may participate. The original classification remains immutable even if the level was revisited later.

### Reaction families
Backtest these separately:
- first later touch,
- rejection from pivot,
- sweep through pivot then reclaim,
- close through pivot followed by retest,
- unresolved VCPR first-touch reaction,
- revisited VCPR reaction.

### Long candidate
1. Price approaches a VCPR pivot from above or below according to the tested setup family.
2. M5/M15 produces the required reaction pattern.
3. There is enough space to the next opposing structural level.
4. H1/H4 context is supportive or at least not a hard veto.
5. News/spread/feed gates pass.

### Critical rule
Do not assign a positive edge to VCPR merely because it is virgin. First-touch, revisited and breakout-through behavior must be measured independently.

## Strategy E — Session Liquidity Sweep
Purpose: trade false breaks of session extremes after liquidity is taken and price re-enters the prior range.

Primary levels:
- Asia High / Low,
- London High / Low,
- previous New York High / Low where available.

### Long candidate
1. Price trades below a defined session low.
2. The move fails to gain acceptance below the level.
3. Price reclaims the session low on a closed M5/M15 candle.
4. A local bullish structure shift or continuation trigger follows.
5. Entry is not directly into major resistance/VCPR/PDH.

### Short candidate
Mirror the sequence above a session high.

### Backtest dimensions
- session producing the sweep,
- minutes after session open,
- sweep depth in ATR or points,
- reclaim speed,
- trend-aligned vs counter-trend,
- first sweep vs repeated sweep,
- overlap with PDH/PDL or VCPR.

## Strategy F — MA Compression → Expansion
Purpose: detect transition from low directional separation to a directional expansion move while avoiding blind MA crossover trading.

### Compression context
Candidate compression exists when:
- SMA44, EMA99 and SMA200 are within a configurable distance band,
- recent ATR/realized range is compressed relative to its lookback,
- price is not already extended far from the MA cluster.

### Bullish expansion candidate
1. Compression is established.
2. Price closes above the cluster or tested range boundary.
3. SMA44 begins separating upward from EMA99.
4. Follow-through or retest confirms acceptance.
5. H1/H4 context is not strongly bearish.

### Bearish expansion candidate
Mirror the bullish conditions.

### Critical rule
A crossover alone is never enough. The strategy requires volatility/range expansion and acceptance beyond structure.

## Strategy G — Previous Day Level Reclaim
Purpose: trade PDH/PDL false breaks and reclaims as a distinct setup from generic failed breakouts so their expectancy can be measured independently.

### Long PDL reclaim
1. Price trades below Previous Day Low.
2. Price closes back above PDL.
3. M5/M15 confirms local bullish structure or strong reclaim momentum.
4. No hard macro/news veto.
5. Target space exists toward previous close, intraday midpoint, PDH, VCPR or another validated structure.

### Short PDH reclaim
Mirror above Previous Day High.

### Test separately
- same-session reclaim,
- London reclaim,
- New York reclaim,
- trend-aligned reclaim,
- counter-trend reclaim,
- reclaim coincident with VCPR or session sweep.

## Strategy H — Trend Continuation After Session Break
Purpose: capture continuation when an established trend breaks a session boundary and never offers a deep pullback to the primary MAs.

### Long candidate
1. H4/H1 trend is bullish.
2. Asia or London high is broken with a closed candle.
3. Price remains accepted above the broken level.
4. A shallow M5 pullback or inside consolidation occurs above the level.
5. Continuation trigger breaks the local consolidation high.
6. Price is not excessively extended relative to ATR or the nearest structural target.

### Short candidate
Mirror below session low in a bearish H4/H1 trend.

This must be kept separate from Strategy B because Strategy B requires a meaningful retest of the broken level, while Strategy H allows shallow continuation structures that never return to the level.

## Strategy I — Exhaustion / Mean Reversion (Research Only)
Purpose: research extreme intraday extensions that may revert toward a validated mean. This strategy is disabled for execution until it proves robust because fading strong gold trends is high risk.

Candidate research context:
- price extended by a configurable ATR multiple from SMA44/EMA99,
- major structural target or session extreme reached,
- momentum fails to continue,
- M5/M15 reversal structure confirms,
- no high-impact event is actively driving price.

Possible mean targets:
- SMA44,
- EMA99,
- session midpoint,
- previous close,
- validated VCPR pivot.

This strategy must have stricter risk limits and its own acceptance threshold. It must never be merged into the trend strategies during evaluation.

## Strategy conflict policy
Multiple strategies may detect the same market event. The engine must not open duplicate positions for overlapping setups.

Each candidate signal should carry:
- strategy_id,
- direction,
- setup timeframe,
- trigger timeframe,
- primary level,
- confluences,
- invalidation,
- target structure,
- timestamp,
- confidence components,
- veto state.

Conflict resolution should be deterministic:
1. Hard veto always wins.
2. Existing position/duplicate exposure gate wins.
3. Higher validated expectancy strategy has priority once enough backtest samples exist.
4. Until enough samples exist, overlapping setups are merged into one shadow candidate rather than counted as separate trades.
5. Opposite-direction simultaneous strategies produce NO TRADE unless a later, explicitly tested arbitration rule resolves the conflict.

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

Also compare:
- first occurrence vs repeated occurrence at a level,
- trend-aligned vs counter-trend,
- first half vs second half of session,
- high/normal/low volatility,
- unresolved vs revisited VCPR,
- isolated level vs multi-level confluence.

Use out-of-sample validation and avoid selecting parameters solely because they maximize historical profit.

## Strategy acceptance gates
A strategy is not promoted because of win rate alone. Promotion from research to shadow/demo requires minimum sample count plus acceptable:
- expectancy,
- profit factor,
- drawdown,
- stability across months/regimes,
- long/short balance or an explainable directional asymmetry,
- out-of-sample behavior.

Exact thresholds remain configurable until we have enough broker-native history.

## Implementation order
1. Complete live indicator/level calculation: SMA44, EMA99, SMA200, PDH/PDL, PWH/PWL and session highs/lows.
2. Add MA relationship/event classification.
3. Add reusable level-event classifiers: breakout, reclaim, rejection, sweep, retest and acceptance.
4. Build Strategy A Trend Pullback in shadow mode.
5. Build Strategy B Breakout + Retest.
6. Build Strategy C Failed Breakout / Reversal.
7. Build Strategy D VCPR Reaction.
8. Build Strategy E Session Liquidity Sweep.
9. Build Strategy F MA Compression -> Expansion.
10. Build Strategy G Previous Day Level Reclaim.
11. Build Strategy H Trend Continuation After Session Break.
12. Keep Strategy I Mean Reversion research-only until independently validated.
13. Add historical backtest runner shared by all strategies.
14. Add strategy conflict/arbitration layer.
15. Add macro confirmation and news veto.
16. Promote only validated strategies to demo execution.

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
