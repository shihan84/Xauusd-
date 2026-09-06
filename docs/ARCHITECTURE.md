# XAU/USD Intelligence Platform Architecture

Status: Architecture baseline v1

## Product model

The platform is split into three access levels:

- PUBLIC: YouTube/broadcast dashboard, public Telegram alerts, simplified setup strength, session status, market bias, selected technical events, and transparent demo performance statistics.
- MEMBER: account-based access to richer market views and community features.
- PREMIUM: interactive charts, personal layouts/presets, configurable supported indicators, detailed gateway breakdown, personal alerts, premium Telegram trade plans, historical/replay analytics, and host-follow mode.

Public users must never receive the proprietary gateway definitions. Public surfaces may show only counts/summary such as `7/9 gateways passed`, mandatory gate status, setup grade, and setup-strength state.

## Core data flow

MT4 market/account data -> local bridge -> market stream -> analysis engine -> gateway engine -> alert/trade-plan engine -> distribution + demo execution + performance ledger.

Distribution targets:

- Public web dashboard
- OBS `/broadcast` browser source -> YouTube Live
- Public Telegram
- Premium web terminal
- Premium Telegram
- Demo MT4 execution EA

## Market data

MT4 is the initial authoritative XAU/USD source.

The MT4 bridge should provide:

- Bid/Ask/spread and server timestamp
- OHLC candles for required timeframes
- Broker symbol metadata
- Account balance/equity/margin/free margin/margin level
- Open orders/positions and closed trade history
- Custom indicator buffer values exposed through `iCustom()` where available

Do not expose MT4 directly to the public internet. MT4 should send outbound data to a local authenticated bridge. Public/browser connections use authenticated HTTPS/WSS endpoints.

## Chart engine

Premium users can independently choose:

- Asset: XAU/USD initially; DXY, US yields and other confirmed feeds later
- Timeframes: M1, M5, M15, M30, H1, H4, D1
- Single/multi-chart layouts
- Supported indicators with user-configurable parameters
- Saved personal presets/layouts

Initial supported indicator families should include:

- SMA / EMA
- RSI
- MACD
- ATR
- Bollinger Bands
- VWAP / session VWAP when data supports it
- VCPR
- Previous day/week levels
- Session open/high/low/range
- Approved MT4 custom indicators

Do not allow arbitrary Pine Script, EX4/MQ4 upload, or arbitrary executable code in the browser/backend. Custom MT4 indicators are registered server-side and read through known buffers/configuration.

## VCPR canonical definition

For trading day D:

1. Calculate CPR from D-1:
   - PP = (High + Low + Close) / 3
   - BC = (High + Low) / 2
   - TC = 2 * PP - BC
   - CPR Low = min(BC, TC)
   - CPR High = max(BC, TC)
2. Examine only intraday candles belonging to day D.
3. A touch occurs when candle.high >= CPR Low AND candle.low <= CPR High.
4. If there is no touch on originating day D, that day is permanently classified as VCPR.
5. Later touches never declassify the VCPR.
6. Store full CPR internally, but display only the center Pivot/PP as a horizontal line extending right from the originating day.

Store later-touch metadata separately.

## Session engine

Track at minimum:

- Sydney
- Tokyo/Asia
- London
- New York
- London/New York overlap

Use real timezone rules and daylight-saving transitions; do not hard-code IST offsets for London/New York.

For each session expose:

- OPEN / CLOSED / OPENING SOON
- Time to open/close
- Open price
- High
- Low
- Range
- Previous completed session levels

Premium chart overlays may show session boxes/shading, open, high, low, and previous-session levels. Session events can feed the gateway engine, e.g. Asia high swept or London low broken.

## Gateway engine

No order is fired from a single indicator. A setup flows through explicit states:

`WATCH -> FORMING -> READY -> ARMED -> EXECUTED -> MANAGED -> CLOSED/INVALIDATED`

Three gateway classes:

1. Hard gates: must pass.
2. Weighted confirmation gates: contribute to setup score.
3. Veto gates: immediately block execution.

Typical hard gates:

- Fresh market feed
- Valid candle/price trigger
- Valid structural SL/invalidation
- Minimum configured risk/reward
- Acceptable spread/slippage
- No duplicate/conflicting order
- Account/margin/risk limits satisfied

Possible weighted gates:

- SMA/EMA interaction
- VCPR alignment
- Higher-timeframe bias
- Session structure
- DXY confirmation
- US Treasury yield confirmation
- Momentum/volatility conditions
- Approved custom MT4 indicator signals

Possible veto gates:

- Stale/disconnected feed
- Daily risk stop reached
- Extreme spread/slippage
- Invalid margin safety
- Major-news lock when enabled
- Explicit operator pause

Public surfaces expose only aggregate information, never proprietary conditions.

## Technical interaction classifier

For supported levels/indicators, distinguish:

- APPROACH
- TOUCH
- REJECTION
- CROSS
- CONFIRMED CROSS
- FAILED CROSS

Example for SMA44:

- TOUCH: wick intersects SMA, close remains on original side.
- CROSS: candle closes on opposite side.
- CONFIRMED CROSS: configured close-distance/ATR threshold and/or confirmation candle holds beyond the SMA.
- FAILED CROSS: initial close crosses but subsequent confirmation returns through the SMA.

Thresholds are configurable and can be saved in premium presets.

## Market regime

Classify market state before evaluating setups:

- NORMAL
- TRENDING
- RANGING
- HIGH_VOLATILITY
- LOW_VOLATILITY
- PRE_NEWS
- NEWS_LIVE
- POST_NEWS
- RECOVERY_HEDGE

Gateway thresholds and allowed strategies may vary by regime.

## News state machine

Use scheduled high-impact events and breaking-news inputs to support:

`NORMAL -> PRE_NEWS_LOCK -> NEWS_LIVE -> POST_NEWS_VOLATILITY -> NORMAL`

For U.S. events, display both U.S. Eastern Time and IST with DST handled correctly.

## Alerts

Two major classes:

### Official intelligence alerts

Generated centrally and eligible for public/premium/broadcast distribution.

Examples:

- VCPR approach/rejection/touch
- SMA44 cross/rejection/failed cross
- Session high/low sweep
- High-impact news countdown
- Setup-forming / setup-confirmed / invalidated

### Personal premium alerts

User-configured and private.

Examples:

- Price reaches level
- Price within distance of VCPR
- SMA/EMA cross/rejection
- RSI threshold/cross
- Session breakout
- Multi-condition alert

## Trade-plan engine

A confirmed setup can generate:

- Direction
- Entry zone
- Initial SL/invalidation
- TP1 / TP2 / TP3
- Risk/reward per target
- Setup grade
- Gateway count
- Timestamp
- Call ID

Entry/SL/targets should be derived from structure and configured risk policy, not arbitrary fixed distances.

Typical inputs include swing structure, VCPR, session levels, ATR, liquidity/technical levels, and minimum risk/reward.

## Telegram distribution

### Public Telegram

Publish broad intelligence and selected official events without exposing proprietary gateway details or full premium trade logic.

### Premium Telegram

May receive confirmed trade plans including entry zone, SL, TP1/TP2/TP3, risk/reward, setup status, management updates, and detailed gateway information permitted for premium members.

Every message links to the same immutable Call ID used by the dashboard/demo executor.

## Demo execution

Demo MT4 execution supports modes:

- SHADOW: calculate and record, no order sent
- APPROVAL_REQUIRED: operator approval before execution
- AUTO: order allowed only after all execution gates pass
- PAUSED

Start validation in SHADOW, then APPROVAL_REQUIRED, then AUTO on demo only after sufficient evidence.

Execution safety checks include:

- Spread/slippage
- Feed freshness
- Duplicate order prevention
- Lot/risk cap
- Maximum open exposure
- Daily loss limit
- Consecutive-loss limit
- Margin safety
- News state
- Setup still valid at execution time

## Trade management

Support structured events rather than silently changing a trade:

- ENTRY_FILLED
- TP1_HIT
- TP2_HIT
- TP3_HIT
- SL_MOVED_TO_BE
- PARTIAL_CLOSE
- TRAILING_UPDATE
- INVALIDATED
- STOPPED
- MANUAL_CLOSE
- CLOSED

Partial-exit allocation and break-even policy must be fixed/configured before performance statistics are calculated.

## Recovery / hedge mode

Recovery logic is isolated from the normal signal engine.

Possible states:

`NORMAL -> DRAWDOWN -> HEDGE_LOCK -> WAITING -> RECOVERY_READY -> PARTIAL_UNHEDGE/ADD -> RECOVERY -> PROFIT_LOCK -> NORMAL`

Track:

- Gross BUY lots
- Gross SELL lots
- Net exposure
- Locked/hedged exposure
- Basket breakeven
- Floating P/L
- Equity drawdown
- Margin safety
- Required recovery amount

Do not use a fixed `2x lot` rule. Recovery exposure must be calculated from basket state, invalidation distance, target distance, margin, equity, and maximum permitted drawdown.

Recovery mode remains demo-only until independently validated.

## Performance ledger

Every official call has a unique immutable Call ID.

Original publication data is never overwritten:

- Direction
- Entry/entry zone
- Initial SL
- Initial targets
- Timestamp
- Setup grade
- Public gateway count

All later modifications are append-only events.

Track at minimum:

- Total completed calls
- Win/loss/breakeven counts
- TP1/TP2/TP3 hit rates
- Net points
- Net R
- Average R
- Gross profit/loss
- Net account P/L
- Maximum drawdown
- Consecutive wins/losses
- Setup-grade performance
- Theoretical vs actual demo execution result

The YouTube dashboard must clearly label account execution as DEMO and show drawdown alongside profit.

## Gateway research and accuracy

Do not optimize only for win rate. Evaluate:

- Expectancy
- Average/median R
- Maximum drawdown
- Trade frequency/sample size
- Session/timeframe performance
- Regime performance
- Recovery characteristics

Store a setup fingerprint at entry containing the state of each allowed gateway/context feature. This enables later analysis of which combinations improve expectancy and which gates reduce opportunity without adding value.

Maintain a gateway performance matrix and test changes using historical backtest plus forward demo evidence.

## Public broadcast dashboard

The OBS `/broadcast` page may show:

- XAU/USD chart
- Current session(s)
- Market regime
- Setup status
- `passed / total` gateway count only
- Mandatory-gate summary without details
- Setup grade/strength
- Selected public technical alerts
- News countdowns (ET + IST)
- Demo performance ledger
- Current demo balance/equity/floating P/L
- Public Telegram chat where enabled

Never expose proprietary gateway names, formulas, thresholds, custom-indicator internals, or weighting on the public broadcast.

## Premium terminal

Premium features include:

- Interactive independent charts/timeframes
- User-configurable supported indicators
- Saved layouts/presets
- Session overlays
- Detailed permitted gateway view
- Personal alerts
- Premium Telegram
- Historical VCPR analytics
- Replay/backtest mode
- Similar historical setup statistics
- Host-follow mode

### Host-follow mode

During live commentary the operator can publish a focus context such as:

`XAU/USD | M5 | VCPR 4462.38`

Premium users see `Host is discussing XAU/USD M5` and may click to switch their terminal to that context. This never forces a viewer to leave their own layout.

## Access/security

Roles:

- PUBLIC
- MEMBER
- PREMIUM
- OPERATOR/ADMIN

Rules:

- `/broadcast` is read-only.
- `/control` requires authentication.
- Premium settings/alerts/layouts belong to each account.
- Secrets stay server-side/environment only.
- Market feed endpoints require authentication and stale-data detection.
- MT4 is never directly exposed.
- Proprietary gateway definitions are server-side only.

## Build order

1. MT4 historical exporter (D1 + M5/M1)
2. CPR/VCPR backtest and validation against known chart examples
3. MT4 realtime bridge + stale-feed status
4. Core domain model + persistence
5. Session engine
6. Supported indicator engine + MT4 custom-indicator registry
7. Interaction classifier (approach/touch/rejection/cross/failed cross)
8. Gateway/regime engine
9. Trade-plan engine
10. Shadow performance ledger
11. Demo executor + account telemetry
12. Public broadcast performance/setup UI
13. Telegram public/premium routing
14. Premium auth/terminal/presets/personal alerts
15. Recovery/hedge research engine
16. Replay/similar-setup analytics

All strategy/gateway changes should be versioned so historical results remain attributable to the exact rules used at that time.
