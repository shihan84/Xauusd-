"use client";

import { useEffect, useMemo, useState } from 'react';
import { DEFAULT_LIVE_STATE, LiveState, readLiveState, subscribeLiveState } from '../lib/liveState';
import TelegramLiveChat from './TelegramLiveChat';

const vcprs = [
  { date: 'Sep 03', pivot: 4462.38, touched: false },
  { date: 'Aug 29', pivot: 4431.72, touched: true },
  { date: 'Aug 12', pivot: 4376.45, touched: true },
  { date: 'Jul 24', pivot: 4289.20, touched: false }
];

type Candle = { o:number; h:number; l:number; c:number };

function buildCandles(price:number): Candle[] {
  const out:Candle[] = [];
  let prev = price - 17;
  for (let i=0;i<54;i++) {
    const drift = Math.sin(i/5.2)*1.3 + 0.28;
    const open = prev;
    const close = open + drift + Math.sin(i/2.7)*0.55;
    const high = Math.max(open, close) + 0.7 + Math.abs(Math.sin(i))*0.8;
    const low = Math.min(open, close) - 0.7 - Math.abs(Math.cos(i))*0.8;
    out.push({o:open,h:high,l:low,c:close});
    prev = close;
  }
  return out.map((c,i)=> i===out.length-1 ? {...c,c:price,h:Math.max(c.h,price),l:Math.min(c.l,price)} : c);
}

function CandleChart({ price, state }: { price:number; state:LiveState }) {
  const candles = useMemo(()=>buildCandles(price), [Math.round(price*2)]);
  const shownVcpr = state.showAllVcpr ? vcprs.filter(v => !v.touched || state.showRevisited) : [];
  const levels = [...shownVcpr.map(v=>v.pivot), ...candles.flatMap(c=>[c.h,c.l])];
  const min = Math.min(...levels)-3;
  const max = Math.max(...levels)+3;
  const y = (v:number)=>430-((v-min)/(max-min))*390;
  const step = 1000/candles.length;

  return <div className="chart">
    <svg viewBox="0 0 1000 460" preserveAspectRatio="none">
      {Array.from({length:7},(_,i)=><line key={i} x1="0" x2="1000" y1={35+i*61} y2={35+i*61} stroke="#162231" strokeWidth="1" />)}
      {shownVcpr.map(v=><g key={v.date}>
        <line x1="0" x2="1000" y1={y(v.pivot)} y2={y(v.pivot)} stroke={v.touched ? '#6f7b8e' : (state.highlightUntouched ? '#d9b54a' : '#9f8a4d')} strokeWidth={v.touched?1.5:2.2} strokeDasharray={v.touched?'8 7':'0'} />
        <rect x="8" y={y(v.pivot)-22} width="150" height="18" rx="4" fill="#0a1019" opacity="0.9" />
        <text x="15" y={y(v.pivot)-9} fill={v.touched?'#9ba6b5':'#f3d46f'} fontSize="12">VCPR {v.date} · {v.pivot.toFixed(2)}</text>
      </g>)}
      {candles.map((c,i)=>{
        const cx = i*step+step/2;
        const up = c.c>=c.o;
        const top = Math.min(y(c.o),y(c.c));
        const bodyH = Math.max(2,Math.abs(y(c.o)-y(c.c)));
        return <g key={i}>
          <line x1={cx} x2={cx} y1={y(c.h)} y2={y(c.l)} stroke={up?'#69d493':'#ff7d7d'} strokeWidth="1.2" />
          <rect x={cx-step*0.28} y={top} width={step*0.56} height={bodyH} fill={up?'#69d493':'#ff7d7d'} rx="1" />
        </g>
      })}
      <line x1="0" x2="1000" y1={y(price)} y2={y(price)} stroke="#dce4ef" strokeWidth="1" strokeDasharray="3 5" opacity="0.5" />
      <rect x="916" y={y(price)-11} width="76" height="22" rx="4" fill="#e5e7eb" />
      <text x="924" y={y(price)+5} fill="#111827" fontSize="13" fontWeight="700">{price.toFixed(2)}</text>
    </svg>
  </div>;
}

export default function MarketDashboard({ broadcast=false }: { broadcast?:boolean }) {
  const [price,setPrice] = useState(4447.60);
  const [state,setState] = useState<LiveState>(DEFAULT_LIVE_STATE);

  useEffect(()=>{
    setState(readLiveState());
    return subscribeLiveState(setState);
  },[]);

  useEffect(()=>{
    const timer = setInterval(()=>setPrice(p=>Math.max(4200,p+(Math.random()-0.49)*0.85)),850);
    return ()=>clearInterval(timer);
  },[]);

  const biasClass = state.bias==='BULLISH'?'positive':state.bias==='BEARISH'?'negative':'neutral';
  const compact = broadcast && state.mode==='CHART FOCUS';

  return <main className={broadcast?'broadcast':'shell'}>
    <div className="topbar">
      <div className="brand"><div className="brand-badge">AU</div><div><h1>XAU/USD GOLD INTELLIGENCE</h1><div className="muted">MT4-ready realtime analysis dashboard</div></div></div>
      <div className="live-pill">● DEMO FEED • {state.mode}</div>
    </div>

    <section className={compact?'grid compact-grid':'grid'}>
      <div className="panel chart-panel">
        <div className="row"><div><div className="label">XAU/USD</div><div className="price">{price.toFixed(2)}</div></div><div style={{textAlign:'right'}}><div className="label">Market Bias</div><strong className={biasClass}>{state.bias}</strong><div className="muted">Confidence {state.confidence}%</div></div></div>
        <div className="stat-grid"><div className="stat"><span className="label">DXY</span><strong>97.84</strong></div><div className="stat"><span className="label">US 10Y</span><strong>3.91%</strong></div><div className="stat"><span className="label">MT4 Spread</span><strong>0.26</strong></div></div>
        <CandleChart price={price} state={state} />
        <div className="legend"><span><i className="dot" style={{background:'#d9b54a'}}/>Never-revisited VCPR pivot</span><span><i className="dot" style={{background:'#6f7b8e'}}/>Later-revisited historical VCPR</span><span><i className="dot" style={{background:'#69d493'}}/>Demo candles</span></div>
      </div>

      {!compact && <div className="side">
        <TelegramLiveChat compact={broadcast} />
        <div className="panel card"><div className="label">Historic VCPR Pivots</div><div className="vcpr-table">{vcprs.filter(v=>state.showAllVcpr && (!v.touched||state.showRevisited)).map(v=><div className="vcpr-row" key={v.date}><span>{v.date}</span><strong>{v.pivot.toFixed(2)}</strong><span className={v.touched?'muted':'positive'}>{v.touched?'Revisited':'Untouched'}</span></div>)}</div></div>
        {!broadcast && <div className="panel card"><div className="label">Next US Risk Event</div><h3 style={{marginBottom:6}}>Economic calendar connection pending</h3><div className="muted">Final version will show ET + IST and the 5-minute pre-event alert.</div></div>}
      </div>}
    </section>
    <div className="ticker"><span>⚡ {state.headline || 'Gold Intelligence dashboard online'} &nbsp;&nbsp; • &nbsp;&nbsp; Telegram public group chat is displayed live on the broadcast panel.</span></div>
  </main>;
}
