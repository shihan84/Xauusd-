import express from 'express';
import http from 'http';
import { WebSocketServer } from 'ws';

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: '/ws' });

const PORT = Number(process.env.PORT || 8787);
const API_TOKEN = process.env.MT4_BRIDGE_TOKEN || 'CHANGE_ME';
const SUPABASE_URL = (process.env.SUPABASE_URL || '').replace(/\/$/, '');
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || '';

let latestTick = null;
let lastSupabaseOkAt = null;
let lastSupabaseError = null;
let cloudPublishInFlight = false;
let pendingCloudTick = null;

app.use(express.json({ limit: '2mb' }));

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
  return Boolean(SUPABASE_URL && SUPABASE_SERVICE_ROLE_KEY);
}

function supabaseHeaders() {
  const headers = {
    apikey: SUPABASE_SERVICE_ROLE_KEY,
    'Content-Type': 'application/json',
    Prefer: 'resolution=merge-duplicates,return=minimal'
  };

  // New Supabase sb_secret_* keys are API keys, not JWTs. Sending them as
  // Authorization: Bearer causes PostgREST to treat the request as a user-token
  // request and RLS can be enforced. Legacy service_role JWTs still need the
  // Authorization header, so retain it only for JWT-shaped keys.
  if (!SUPABASE_SERVICE_ROLE_KEY.startsWith('sb_secret_')) {
    headers.Authorization = `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`;
  }

  return headers;
}

async function upsertSupabaseTick(tick) {
  if (!cloudConfigured()) return;

  pendingCloudTick = tick;
  if (cloudPublishInFlight) return;

  cloudPublishInFlight = true;
  try {
    while (pendingCloudTick) {
      const current = pendingCloudTick;
      pendingCloudTick = null;

      const response = await fetch(`${SUPABASE_URL}/rest/v1/market_latest?on_conflict=symbol`, {
        method: 'POST',
        headers: supabaseHeaders(),
        body: JSON.stringify({
          symbol: current.symbol,
          source: 'MT4',
          server_time: current.server_time ?? null,
          digits: current.digits ?? null,
          bid: current.bid ?? null,
          ask: current.ask ?? null,
          spread_points: current.spread_points ?? null,
          m1: current.m1 ?? {},
          indicators: current.indicators ?? {},
          received_at: current.received_at ?? Date.now(),
          updated_at: new Date().toISOString()
        })
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`Supabase HTTP ${response.status}: ${detail}`);
      }

      lastSupabaseOkAt = Date.now();
      lastSupabaseError = null;
    }
  } catch (error) {
    lastSupabaseError = error instanceof Error ? error.message : String(error);
    console.error('Supabase publish failed:', lastSupabaseError);
  } finally {
    cloudPublishInFlight = false;

    // If a newer tick arrived after the final loop check, send it now.
    if (pendingCloudTick) void upsertSupabaseTick(pendingCloudTick);
  }
}

app.get('/health', (_req, res) => {
  res.json({
    ok: true,
    service: 'xauusd-mt4-bridge',
    latestTickAt: latestTick?.received_at ?? null,
    cloud: {
      configured: cloudConfigured(),
      lastOkAt: lastSupabaseOkAt,
      lastError: lastSupabaseError
    }
  });
});

app.get('/latest', (_req, res) => {
  if (!latestTick) return res.status(404).json({ error: 'No MT4 tick received yet' });
  res.json(latestTick);
});

app.post('/ingest/tick', (req, res) => {
  if (!authorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  const body = req.body;
  if (!body || body.type !== 'tick' || typeof body.symbol !== 'string') {
    return res.status(400).json({ error: 'Invalid tick payload' });
  }

  latestTick = {
    ...body,
    received_at: Date.now()
  };

  broadcast(latestTick);
  void upsertSupabaseTick(latestTick);
  res.status(202).json({ ok: true });
});

wss.on('connection', (socket) => {
  if (latestTick) socket.send(JSON.stringify(latestTick));
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`XAUUSD MT4 bridge listening on port ${PORT}`);
  console.log(
    cloudConfigured()
      ? 'Supabase cloud forwarding enabled.'
      : 'Supabase cloud forwarding disabled: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.'
  );
  console.log('Keep this service behind TLS/authentication before exposing it publicly.');
});
