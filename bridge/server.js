import express from 'express';
import http from 'http';
import { WebSocketServer } from 'ws';

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: '/ws' });

const PORT = Number(process.env.PORT || 8787);
const API_TOKEN = process.env.MT4_BRIDGE_TOKEN || 'CHANGE_ME';

let latestTick = null;

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

app.get('/health', (_req, res) => {
  res.json({ ok: true, service: 'xauusd-mt4-bridge', latestTickAt: latestTick?.received_at ?? null });
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
  res.status(202).json({ ok: true });
});

wss.on('connection', (socket) => {
  if (latestTick) socket.send(JSON.stringify(latestTick));
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`XAUUSD MT4 bridge listening on port ${PORT}`);
  console.log('Keep this service behind TLS/authentication before exposing it publicly.');
});
