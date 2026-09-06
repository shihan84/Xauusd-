# XAUUSD Live Research Dashboard

Architecture:

MT4 EA -> local Node bridge -> secure realtime feed -> analysis/gateway engine -> Vercel dashboard / OBS browser source / Telegram / demo execution.

The frozen platform architecture and product rules are documented in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Current foundation

- MT4 live bid/ask and candle bridge
- MT4 historical D1 + M5/M1 export path
- CPR/VCPR backtest specification
- Historical VCPR definition: full CPR zone must remain untouched on its originating trading day
- Visible VCPR level: center Pivot only, carried forward permanently
- Realtime dashboard and OBS `/broadcast`
- Public Telegram chat integration
- Shared live broadcast state
- Core platform domain model in `lib/domain.ts`

## Planned implementation order

1. MT4 historical exporter (D1 + M5/M1)
2. CPR/VCPR backtest and validation against known chart examples
3. MT4 realtime bridge + stale-feed status
4. Persistence and account/auth foundation
5. Session engine: Sydney, Tokyo/Asia, London, New York and London/New York overlap
6. Supported indicator engine + MT4 custom-indicator registry
7. Technical interaction classifier: approach/touch/rejection/cross/confirmed cross/failed cross
8. Market-regime + proprietary gateway engine
9. Trade-plan engine: Entry, SL, TP1/TP2/TP3 and R:R
10. Shadow performance ledger
11. Demo MT4 executor + account/equity/margin telemetry
12. Public YouTube/OBS performance and gateway-count UI
13. Public/Premium Telegram routing
14. Premium terminal: interactive charts, presets, personal alerts and host-follow mode
15. Recovery/hedge research engine
16. Replay and similar-setup analytics

## Public vs Premium

The public YouTube dashboard may show setup state, setup grade/strength and aggregate gateway progress such as `7/9 passed`, but never the proprietary gateway names, formulas, weights, thresholds or custom-indicator internals.

Premium users may receive the detailed permitted gateway view, configurable supported indicators, saved layouts, personal alerts, premium Telegram trade plans and research/replay tools.

## Demo execution and performance

Official calls use immutable Call IDs. Initial Entry/SL/TP values are preserved and later management changes are append-only events. Demo performance must clearly display profit together with drawdown and be labeled as DEMO.

Auto-execution is not driven by a single signal. It must pass hard gates, weighted confirmation thresholds, veto gates and a final trigger. Rollout order is SHADOW -> APPROVAL_REQUIRED -> AUTO on demo.

## Security

Do not expose the MetaTrader terminal directly to the public Internet. The EA sends data to a bridge process. Expose only authenticated bridge endpoints, preferably behind TLS/WSS and a firewall/reverse proxy. Proprietary gateway logic and all secrets remain server-side.
