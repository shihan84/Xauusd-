import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

type Candle = { t:number; o:number; h:number; l:number; c:number };
type YahooChart = {
  chart?: { result?: Array<{
    meta?: { regularMarketPrice?: number; chartPreviousClose?: number; symbol?: string; currency?: string };
    timestamp?: number[];
    indicators?: { quote?: Array<{ open?: Array<number|null>; high?: Array<number|null>; low?: Array<number|null>; close?: Array<number|null> }> };
  }> };
};

type GoldSpot = { name?:string; price?:number; symbol?:string; updatedAt?:string; updated_at?:string; timestamp?:number };

type Timeframe = 'M1'|'M5'|'M15'|'M30'|'H1'|'H4'|'D1';

const timeframeConfig:Record<Timeframe,{interval:string;range:string}> = {
  M1:{interval:'1m',range:'1d'},
  M5:{interval:'5m',range:'5d'},
  M15:{interval:'15m',range:'5d'},
  M30:{interval:'30m',range:'5d'},
  H1:{interval:'60m',range:'1mo'},
  H4:{interval:'60m',range:'1mo'},
  D1:{interval:'1d',range:'6mo'}
};

function normalizeTimeframe(value:string|null):Timeframe {
  const tf=(value||'M5').toUpperCase() as Timeframe;
  return tf in timeframeConfig ? tf : 'M5';
}

function aggregateFourHour(candles:Candle[]) {
  const buckets = new Map<number,Candle[]>();
  for (const candle of candles) {
    const d = new Date(candle.t*1000);
    const utcHour = d.getUTCHours();
    const bucketHour = Math.floor(utcHour/4)*4;
    const bucket = Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate(),bucketHour,0,0)/1000;
    const list=buckets.get(bucket)||[];
    list.push(candle);
    buckets.set(bucket,list);
  }
  return [...buckets.entries()].sort((a,b)=>a[0]-b[0]).map(([t,list])=>({
    t,
    o:list[0].o,
    h:Math.max(...list.map(v=>v.h)),
    l:Math.min(...list.map(v=>v.l)),
    c:list[list.length-1].c
  }));
}

async function yahoo(symbol: string, interval = '5m', range = '1d', aggregateH4=false) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=${interval}&range=${range}&includePrePost=true`;
  const res = await fetch(url, { cache: 'no-store', headers: { 'User-Agent': 'Mozilla/5.0 XAUUSD-Dashboard/1.0' } });
  if (!res.ok) throw new Error(`Yahoo ${symbol} ${res.status}`);
  const data = await res.json() as YahooChart;
  const result = data.chart?.result?.[0];
  if (!result) throw new Error(`No chart result for ${symbol}`);
  const q = result.indicators?.quote?.[0];
  let candles = (result.timestamp || []).map((t, i) => ({ t, o:q?.open?.[i], h:q?.high?.[i], l:q?.low?.[i], c:q?.close?.[i] }))
    .filter((c):c is Candle => [c.o,c.h,c.l,c.c].every(v => typeof v === 'number'));
  if (aggregateH4) candles=aggregateFourHour(candles);
  return { symbol:result.meta?.symbol||symbol, price:result.meta?.regularMarketPrice??candles.at(-1)?.c??null, previousClose:result.meta?.chartPreviousClose??null, candles:candles.slice(-120) };
}

async function spotGold() {
  const res = await fetch('https://api.gold-api.com/price/XAU', { cache:'no-store' });
  if (!res.ok) throw new Error(`Gold API ${res.status}`);
  const data = await res.json() as GoldSpot;
  if (typeof data.price !== 'number') throw new Error('Gold API returned no price');
  return data;
}

export async function GET(request:NextRequest) {
  const timeframe=normalizeTimeframe(request.nextUrl.searchParams.get('timeframe'));
  const cfg=timeframeConfig[timeframe];
  try {
    const [spot, goldProxy, dxy, us10y] = await Promise.all([
      spotGold(),
      yahoo('GC=F',cfg.interval,cfg.range,timeframe==='H4'),
      yahoo('DX-Y.NYB'),
      yahoo('^TNX')
    ]);
    return NextResponse.json({
      ok:true,
      source:'Gold-API spot + Yahoo Finance market proxies',
      provisional:true,
      timeframe,
      note:`Spot price is live XAU; ${timeframe} chart candles use a temporary GC futures proxy only when MT4 history is unavailable.`,
      updatedAt:Date.now(),
      gold:{ price:spot.price, previousClose:null, candles:goldProxy.candles },
      dxy,
      us10y
    }, { headers:{'Cache-Control':'no-store, max-age=0'} });
  } catch (error) {
    return NextResponse.json({ ok:false, source:'online feed unavailable', error:error instanceof Error?error.message:'Unknown market data error' }, { status:502 });
  }
}
