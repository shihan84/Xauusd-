# XAUUSD Live Research Dashboard

Architecture:

MT4 EA -> local Node bridge -> secure realtime feed -> Vercel dashboard / OBS browser source.

## Phase 1

- MT4 live bid/ask and candle feed
- MT4 historical D1 + M5 export
- CPR backtest
- Identify VCPR days: CPR zone must remain untouched on its originating trading day
- Persist only the center Pivot as the visible VCPR horizontal line
- VCPR line carries forward permanently; later touches do not remove VCPR status
- Realtime dashboard integration

## Security

Do not expose the MetaTrader terminal directly to the public Internet. The EA sends data to a bridge process. Expose only the authenticated bridge endpoint, preferably behind TLS/WSS and a firewall/reverse proxy.
