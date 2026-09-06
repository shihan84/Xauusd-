"use client";

import { useEffect, useMemo, useState } from 'react';
import { DEFAULT_LIVE_STATE, LiveState, readLiveState, subscribeLiveState } from '../lib/liveState';
import TelegramLiveChat from './TelegramLiveChat';

type Candle = { t?:number; o:number; h:number; l:number; c:number };
type MarketPayload = {
  ok:boolean; source?:string; provisional?:boolean; note?:string; updatedAt?:number;
  gold?:{price:number|null; previousClose:number|null; candles:Candle[]};
  dxy?:{price:number|null}; us10y?:{price:number|null}; error?:string;
};

const demoVcprs = [
  { date: 'Sep 03', pivot: 4462.38, touched: false },
  { date: 'Aug 29', pivot: 4431.72, touched: true },
  { date: 'Aug 12', pivot: 4376.45, touched: true },
  { date: 'Jul 24', pivot: 4289.20, touched: false }
];

const fallbackCandles = (price:number):Candle[] => {
  const out:Candle[]=[]; let p=price-14;
  for(let i=0;i<62;i++){
    const o=p, c=o+Math.sin(i/4.8)*1.05+0.18, h=Math.max(o,c)+0.8+Math.abs(Math.sin(i))*0.55, l=Math.min(o,c)-0.8-Math.abs(Math.cos(i))*0.55;
    out.push({o,h,l,c}); p=c;
  }
  return out;
};

function sessionNow(label:string, tz:string, openHour:number, closeHour:number){
  const parts = new Intl.DateTimeFormat('en-US',{timeZone:tz,hour:'2-digit',minute:'2-digit',hourCycle:'h23',weekday:'short'}).formatToParts(new Date());
  const h=Number(parts.find(p=>p.type==='hour')?.value||0); const m=Number(parts.find(p=>p.type==='minute')?.value||0);
  const day=parts.find(p=>p.type==='weekday')?.value||''; const mins=h*60+m; const open=openHour*60, close=closeHour*60;
  const weekday=!['Sat','Sun'].includes(day); const isOpen=weekday && mins>=open && mins<close;
  let delta=isOpen?close-mins:(mins<open?open-mins:24*60-mins+open);
  return {label,isOpen,delta,text:`${Math.floor(delta/60)}h ${delta%60}m`};
}

function CandleChart({ candles, price, state }:{candles:Candle[];price:number;state:LiveState}){
  const shown = state.showAllVcpr ? demoVcprs.filter(v=>!v.touched||state.showRevisited) : [];
  const valid=candles.length?candles:fallbackCandles(price);
  const vals=[...valid.flatMap(c=>[c.h,c.l]),...shown.map(v=>v.pivot),price];
  const min=Math.min(...vals)-2, max=Math.max(...vals)+2, span=Math.max(1,max-min);
  const y=(v:number)=>430-((v-min)/span)*390; const step=1000/valid.length;
  return <div className="chart"><svg viewBox="0 0 1000 460" preserveAspectRatio="none">
    {Array.from({length:7},(_,i)=><line key={i} x1="0" x2="1000" y1={35+i*61} y2={35+i*61} stroke="#162231" strokeWidth="1" />)}
    {shown.map(v=><g key={v.date}><line x1="0" x2="1000" y1={y(v.pivot)} y2={y(v.pivot)} stroke={v.touched?'#667085':'#d9b54a'} strokeWidth={v.touched?1.3:2} strokeDasharray={v.touched?'8 7':'0'}/><text x="14" y={y(v.pivot)-7} fill={v.touched?'#8d99aa':'#f1d16c'} fontSize="12">VCPR* {v.date} · {v.pivot.toFixed(2)}</text></g>)}
    {valid.map((c,i)=>{const cx=i*step+step/2,up=c.c>=c.o,top=Math.min(y(c.o),y(c.c)),body=Math.max(2,Math.abs(y(c.o)-y(c.c)));return <g key={i}><line x1={cx} x2={cx} y1={y(c.h)} y2={y(c.l)} stroke={up?'#69d493':'#ff7d7d'} strokeWidth="1.1"/><rect x={cx-step*.28} y={top} width={step*.56} height={body} fill={up?'#69d493':'#ff7d7d'} rx="1"/></g>})}
    <line x1="0" x2="1000" y1={y(price)} y2={y(price)} stroke="#e5e7eb" strokeDasharray="3 5" opacity=".55"/><rect x="912" y={y(price)-11} width="80" height="22" rx="4" fill="#e5e7eb"/><text x="920" y={y(price)+5} fill="#111827" fontSize="13" fontWeight="800">{price.toFixed(2)}</text>
  </svg></div>;
}

export default function MarketDashboard({broadcast=false}:{broadcast?:boolean}){
  const [state,setState]=useState<LiveState>(DEFAULT_LIVE_STATE);
  const [market,setMarket]=useState<MarketPayload|null>(null);
  const [now,setNow]=useState(Date.now());

  useEffect(()=>{setState(readLiveState());return subscribeLiveState(setState)},[]);
  useEffect(()=>{let stop=false;const load=async()=>{try{const r=await fetch('/api/market',{cache:'no-store'});const j=await r.json();if(!stop)setMarket(j)}catch{if(!stop)setMarket({ok:false,error:'Feed connection failed'})}};load();const t=setInterval(load,15000);return()=>{stop=true;clearInterval(t)}},[]);
  useEffect(()=>{const t=setInterval(()=>setNow(Date.now()),30000);return()=>clearInterval(t)},[]);

  const price=market?.gold?.price||4419.09;
  const candles=market?.gold?.candles||fallbackCandles(price);
  const change=market?.gold?.previousClose?price-market.gold.previousClose:0;
  const sessions=useMemo(()=>[
    sessionNow('SYDNEY','Australia/Sydney',8,17),
    sessionNow('ASIA / TOKYO','Asia/Tokyo',9,18),
    sessionNow('LONDON','Europe/London',8,17),
    sessionNow('NEW YORK','America/New_York',8,17)
  ],[now]);
  const openSessions=sessions.filter(s=>s.isOpen).map(s=>s.label);
  const compact=broadcast&&state.mode==='CHART FOCUS'; const biasClass=state.bias==='BULLISH'?'positive':state.bias==='BEARISH'?'negative':'neutral';
  const online=market?.ok===true;

  return <main className={broadcast?'broadcast':'shell'}>
    <div className="topbar"><div className="brand"><div className="brand-badge">AU</div><div><h1>XAU/USD GOLD INTELLIGENCE</h1><div className="muted">Live research terminal • MT4 integration pending</div></div></div><div className={`live-pill ${online?'feed-live':'feed-warn'}`}>● {online?'ONLINE DATA':'BACKUP DATA'} • {state.mode}</div></div>

    <section className="session-strip">{sessions.map(s=><div className={`session-chip ${s.isOpen?'session-open':''}`} key={s.label}><span>{s.label}</span><strong>{s.isOpen?'● OPEN':'○ CLOSED'}</strong><small>{s.isOpen?`closes ${s.text}`:`next open ${s.text}`}</small></div>)}</section>

    <section className={compact?'grid compact-grid':'grid'}>
      <div className="panel chart-panel">
        <div className="row"><div><div className="label">TEMP ONLINE GOLD FEED</div><div className="price">{price.toFixed(2)}</div><div className={change>=0?'positive':'negative'}>{change>=0?'+':''}{change.toFixed(2)} vs prev close</div></div><div style={{textAlign:'right'}}><div className="label">Market Bias</div><strong className={biasClass}>{state.bias}</strong><div className="muted">Setup strength {state.confidence}%</div></div></div>
        <div className="stat-grid"><div className="stat"><span className="label">DXY</span><strong>{market?.dxy?.price?.toFixed(2)||'--'}</strong></div><div className="stat"><span className="label">US 10Y</span><strong>{market?.us10y?.price?`${market.us10y.price.toFixed(2)}%`:'--'}</strong></div><div className="stat"><span className="label">Active Sessions</span><strong>{openSessions.length?openSessions.join(' + '):'Transition'}</strong></div></div>
        <CandleChart candles={candles} price={price} state={state}/>
        <div className="legend"><span><i className="dot" style={{background:'#69d493'}}/>Online 5m candles</span><span><i className="dot" style={{background:'#d9b54a'}}/>VCPR preview*</span><span className="muted">*VCPR levels are placeholders until MT4 history backtest.</span></div>
      </div>

      {!compact&&<div className="side">
        <TelegramLiveChat compact={broadcast}/>
        <div className="panel card setup-card"><div className="row"><div><div className="label">Official Setup Engine</div><h3 className="setup-title">BULLISH SETUP FORMING</h3></div><span className="grade">A</span></div><div className="gateway-number">7 <span>/ 9 gateways</span></div><div className="progress"><i style={{width:'77.8%'}}/></div><div className="mini-grid"><div><span>Mandatory</span><strong className="positive">4/4 PASS</strong></div><div><span>Final Trigger</span><strong className="neutral">WAITING</strong></div></div><div className="locked">🔒 Proprietary gateway details hidden on public dashboard</div></div>
        <div className="panel card"><div className="label">Demo Performance Preview</div><div className="performance-grid"><div><span>Calls</span><strong>24</strong></div><div><span>Win rate</span><strong>70.8%</strong></div><div><span>Net R</span><strong className="positive">+14.6R</strong></div><div><span>Max DD</span><strong className="negative">-4.2R</strong></div></div><small className="muted">Preview layout only. Real statistics start with immutable official calls + MT4 demo execution.</small></div>
      </div>}
    </section>
    <div className="source-note">SOURCE: {market?.source||'temporary fallback'} • {market?.note||'MT4 XAU/USD will replace the provisional feed.'}</div>
    <div className="ticker"><span>⚡ {state.headline||'Gold Intelligence dashboard online'} &nbsp;&nbsp; • &nbsp;&nbsp; {openSessions.length?`${openSessions.join(' + ')} session active`:'Session transition'} &nbsp;&nbsp; • &nbsp;&nbsp; Public shows gateway count only — premium reveals permitted conditions.</span></div>
  </main>;
}
