import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

type YahooChart = {
  chart?: { result?: Array<{
    meta?: { regularMarketPrice?: number; chartPreviousClose?: number; symbol?: string; currency?: string };
    timestamp?: number[];
    indicators?: { quote?: Array<{ open?: Array<number|null>; high?: Array<number|null>; low?: Array<number|null>; close?: Array<number|null> }> };
  }> };
};

type GoldSpot = { name?:string; price?:number; symbol?:string; updatedAt?:string; updated_at?:string; timestamp?:number };

async function yahoo(symbol: string, interval = '5m', range = '1d') {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=${interval}&range=${range}&includePrePost=true`;
  const res = await fetch(url, { cache: 'no-store', headers: { 'User-Agent': 'Mozilla/5.0 XAUUSD-Dashboard/1.0' } });
  if (!res.ok) throw new Error(`Yahoo ${symbol} ${res.status}`);
  const data = await res.json() as YahooChart;
  const result = data.chart?.result?.[0];
  if (!result) throw new Error(`No chart result for ${symbol}`);
  const q = result.indicators?.quote?.[0];
  const candles = (result.timestamp || []).map((t, i) => ({ t, o:q?.open?.[i], h:q?.high?.[i], l:q?.low?.[i], c:q?.close?.[i] }))
    .filter(c => [c.o,c.h,c.l,c.c].every(v => typeof v === 'number'));
  return { symbol:result.meta?.symbol||symbol, price:result.meta?.regularMarketPrice??candles.at(-1)?.c??null, previousClose:result.meta?.chartPreviousClose??null, candles:candles.slice(-90) };
}

async function spotGold() {
  const res = await fetch('https://api.gold-api.com/price/XAU', { cache:'no-store' });
  if (!res.ok) throw new Error(`Gold API ${res.status}`);
  const data = await res.json() as GoldSpot;
  if (typeof data.price !== 'number') throw new Error('Gold API returned no price');
  return data;
}

export async function GET() {
  try {
    const [spot, goldProxy, dxy, us10y] = await Promise.all([spotGold(), yahoo('GC=F'), yahoo('DX-Y.NYB'), yahoo('^TNX')]);
    return NextResponse.json({
      ok:true,
      source:'Gold-API spot + Yahoo Finance market proxies',
      provisional:true,
      note:'Spot price is live XAU; 5m chart candles temporarily use GC futures shape until MT4 XAU/USD candles are connected.',
      updatedAt:Date.now(),
      gold:{ price:spot.price, previousClose:null, candles:goldProxy.candles },
      dxy,
      us10y
    }, { headers:{'Cache-Control':'no-store, max-age=0'} });
  } catch (error) {
    return NextResponse.json({ ok:false, source:'online feed unavailable', error:error instanceof Error?error.message:'Unknown market data error' }, { status:502 });
  }
}
