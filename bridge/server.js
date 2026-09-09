import express from 'express';
import http from 'http';
import { WebSocketServer } from 'ws';

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: '/ws' });

const PORT = Number(process.env.PORT || 8787);
const API_TOKEN = process.env.MT4_BRIDGE_TOKEN || 'CHANGE_ME';
const SUPABASE_URL = (process.env.SUPABASE_URL || '').replace(/\/$/, '');
const SUPABASE_KEY = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || '';

let latestTick = null;
let lastCandlesAt = null;
let lastHistoryAt = null;
let historyRowsAccepted = 0;
let lastSupabaseOkAt = null;
let lastSupabaseError = null;
let lastCandleSupabaseOkAt = null;
let lastCandleSupabaseError = null;
let lastHistorySupabaseOkAt = null;
let lastHistorySupabaseError = null;
let cloudPublishInFlight = false;
let pendingCloudTick = null;

app.use(express.json({ limit: '8mb' }));

function authorized(req) {
  const auth = req.headers.authorization || '';
  return auth === `Bearer ${API_TOKEN}`;
}

function broadcast(payload) {
  const text = JSON.stringify(payload);
  for (const client of wss.clients) {
    if (client.readyState === 1) client.send(text);
  }
}

function cloudConfigured() {
  return Boolean(SUPABASE_URL && SUPABASE_KEY);
}

function supabaseHeaders(prefer = 'resolution=merge-duplicates,return=minimal') {
  const headers = { apikey: SUPABASE_KEY, 'Content-Type': 'application/json', Prefer: prefer };
  if (!SUPABASE_KEY.startsWith('sb_secret_')) headers.Authorization = `Bearer ${SUPABASE_KEY}`;
  return headers;
}

async function upsertRows(rows) {
  if (!cloudConfigured() || !rows.length) return;
  const response = await fetch(`${SUPABASE_URL}/rest/v1/market_candles?on_conflict=symbol,timeframe,open_time`, {
    method: 'POST', headers: supabaseHeaders(), body: JSON.stringify(rows)
  });
  if (!response.ok) throw new Error(`Supabase HTTP ${response.status}: ${await response.text()}`);
}

function candleRows(payload, forcedTimeframe = null) {
  return Array.isArray(payload?.candles) ? payload.candles
    .filter(c => c && Number.isFinite(Number(c.time)) && (forcedTimeframe || typeof c.timeframe === 'string'))
    .map(c => ({
      symbol: payload.symbol,
      timeframe: forcedTimeframe || c.timeframe,
      open_time: Number(c.time), open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close),
      is_closed: c.is_closed !== false, source: 'MT4', updated_at: new Date().toISOString()
    })) : [];
}

async function upsertSupabaseTick(tick) {
  if (!cloudConfigured()) return;
  pendingCloudTick = tick;
  if (cloudPublishInFlight) return;
  cloudPublishInFlight = true;
  try {
    while (pendingCloudTick) {
      const current = pendingCloudTick; pendingCloudTick = null;
      const response = await fetch(`${SUPABASE_URL}/rest/v1/market_latest?on_conflict=symbol`, {
        method: 'POST', headers: supabaseHeaders(), body: JSON.stringify({
          symbol: current.symbol, source: 'MT4', server_time: current.server_time ?? null, digits: current.digits ?? null,
          bid: current.bid ?? null, ask: current.ask ?? null, spread_points: current.spread_points ?? null,
          m1: current.m1 ?? {}, indicators: current.indicators ?? {}, received_at: current.received_at ?? Date.now(), updated_at: new Date().toISOString()
        })
      });
      if (!response.ok) throw new Error(`Supabase HTTP ${response.status}: ${await response.text()}`);
      lastSupabaseOkAt = Date.now(); lastSupabaseError = null;
    }
  } catch (error) {
    lastSupabaseError = error instanceof Error ? error.message : String(error);
    console.error('Supabase tick publish failed:', lastSupabaseError);
  } finally {
    cloudPublishInFlight = false;
    if (pendingCloudTick) void upsertSupabaseTick(pendingCloudTick);
  }
}

async function upsertSupabaseCandles(payload) {
  const rows = candleRows(payload);
  if (!rows.length) return;
  try { await upsertRows(rows); lastCandleSupabaseOkAt = Date.now(); lastCandleSupabaseError = null; }
  catch (error) { lastCandleSupabaseError = error instanceof Error ? error.message : String(error); console.error('Supabase candle publish failed:', lastCandleSupabaseError); }
}

async function upsertSupabaseHistory(payload) {
  const rows = candleRows(payload, payload.timeframe);
  if (!rows.length) return;
  try { await upsertRows(rows); historyRowsAccepted += rows.length; lastHistorySupabaseOkAt = Date.now(); lastHistorySupabaseError = null; }
  catch (error) { lastHistorySupabaseError = error instanceof Error ? error.message : String(error); console.error('Supabase history publish failed:', lastHistorySupabaseError); }
}

app.get('/health', (_req, res) => res.json({
  ok: true, service: 'xauusd-mt4-bridge', latestTickAt: latestTick?.received_at ?? null, latestCandlesAt: lastCandlesAt,
  history: { lastReceivedAt: lastHistoryAt, rowsAccepted: historyRowsAccepted },
  cloud: { configured: cloudConfigured(), lastOkAt: lastSupabaseOkAt, lastError: lastSupabaseError,
    lastCandleOkAt: lastCandleSupabaseOkAt, lastCandleError: lastCandleSupabaseError,
    lastHistoryOkAt: lastHistorySupabaseOkAt, lastHistoryError: lastHistorySupabaseError }
}));

app.get('/latest', (_req, res) => {
  if (!latestTick) return res.status(404).json({ error: 'No MT4 tick received yet' });
  res.json(latestTick);
});

app.post('/ingest/tick', (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });
  const body = req.body;
  if (!body || body.type !== 'tick' || typeof body.symbol !== 'string') return res.status(400).json({ error: 'Invalid tick payload' });
  latestTick = { ...body, received_at: Date.now() };
  broadcast(latestTick); void upsertSupabaseTick(latestTick); res.status(202).json({ ok: true });
});

app.post('/ingest/candles', (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });
  const body = req.body;
  if (!body || body.type !== 'candles' || typeof body.symbol !== 'string' || !Array.isArray(body.candles)) return res.status(400).json({ error: 'Invalid candle payload' });
  lastCandlesAt = Date.now(); void upsertSupabaseCandles(body); res.status(202).json({ ok: true, rows: body.candles.length });
});

app.post('/ingest/history', (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });
  const body = req.body;
  const allowed = new Set(['M1','M5','D1']);
  if (!body || body.type !== 'history' || typeof body.symbol !== 'string' || !allowed.has(body.timeframe) || !Array.isArray(body.candles)) return res.status(400).json({ error: 'Invalid history payload' });
  lastHistoryAt = Date.now(); void upsertSupabaseHistory(body); res.status(202).json({ ok: true, timeframe: body.timeframe, rows: body.candles.length });
});

wss.on('connection', socket => { if (latestTick) socket.send(JSON.stringify(latestTick)); });

server.listen(PORT, '0.0.0.0', () => {
  console.log(`XAUUSD MT4 bridge listening on port ${PORT}`);
  console.log(cloudConfigured() ? 'Supabase cloud forwarding enabled.' : 'Supabase cloud forwarding disabled: set SUPABASE_URL and SUPABASE_SECRET_KEY/SUPABASE_SERVICE_ROLE_KEY.');
  console.log('Historical backfill endpoint ready at /ingest/history.');
  console.log('Keep this service behind TLS/authentication before exposing it publicly.');
});
