"use client";

import { useEffect, useMemo, useState } from 'react';
import { DEFAULT_LIVE_STATE, LiveState, loadLiveState, subscribeLiveState } from '../lib/liveState';
import { DEFAULT_PERFORMANCE, DEFAULT_PUBLIC_SETUP, PerformanceState, PublicSetupState, loadIntelligenceState, subscribeIntelligenceState } from '../lib/intelligenceState';
import { getSupabaseBrowserClient } from '../lib/supabaseClient';
import TelegramLiveChat from './TelegramLiveChat';

type Candle = { t?:number; o:number; h:number; l:number; c:number };
type MarketPayload = {
  ok:boolean; source?:string; provisional?:boolean; note?:string; updatedAt?:number; timeframe?:string;
  gold?:{price:number|null; previousClose:number|null; candles:Candle[]};
  dxy?:{price:number|null}; us10y?:{price:number|null}; error?:string;
};
type Timeframe = 'M1'|'M5'|'M15'|'M30'|'H1'|'H4'|'D1';
type Mt4Latest = { bid:number|null; ask:number|null; spread_points:number|null; received_at:number|null; source?:string };

type CandleRow = {
  symbol:string; timeframe:string; open_time:number|string; open:number|string; high:number|string; low:number|string; close:number|string; is_closed:boolean;
};

const TIMEFRAMES:{key:Timeframe;label:string}[] = [
  {key:'M1',label:'1m'}, {key:'M5',label:'5m'}, {key:'M15',label:'15m'}, {key:'M30',label:'30m'},
  {key:'H1',label:'1H'}, {key:'H4',label:'4H'}, {key:'D1',label:'D1'}
];

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

const rowToCandle=(row:CandleRow):Candle=>({
  t:Number(row.open_time), o:Number(row.open), h:Number(row.high), l:Number(row.low), c:Number(row.close)
});

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
    {valid.map((c,i)=>{const cx=i*step+step/2,up=c.c>=c.o,top=Math.min(y(c.o),y(c.c)),body=Math.max(2,Math.abs(y(c.o)-y(c.c)));return <g key={`${c.t||i}-${i}`}><line x1={cx} x2={cx} y1={y(c.h)} y2={y(c.l)} stroke={up?'#69d493':'#ff7d7d'} strokeWidth="1.1"/><rect x={cx-step*.28} y={top} width={step*.56} height={body} fill={up?'#69d493':'#ff7d7d'} rx="1"/></g>})}
    <line x1="0" x2="1000" y1={y(price)} y2={y(price)} stroke="#e5e7eb" strokeDasharray="3 5" opacity=".55"/><rect x="912" y={y(price)-11} width="80" height="22" rx="4" fill="#e5e7eb"/><text x="920" y={y(price)+5} fill="#111827" fontSize="13" fontWeight="800">{price.toFixed(2)}</text>
  </svg></div>;
}

export default function MarketDashboard({broadcast=false}:{broadcast?:boolean}){
  const [state,setState]=useState<LiveState>(DEFAULT_LIVE_STATE);
  const [setup,setSetup]=useState<PublicSetupState>(DEFAULT_PUBLIC_SETUP);
  const [performance,setPerformance]=useState<PerformanceState>(DEFAULT_PERFORMANCE);
  const [market,setMarket]=useState<MarketPayload|null>(null);
  const [timeframe,setTimeframe]=useState<Timeframe>('M15');
  const [mt4Latest,setMt4Latest]=useState<Mt4Latest|null>(null);
  const [mt4Candles,setMt4Candles]=useState<Candle[]>([]);
  const [mt4CandleReady,setMt4CandleReady]=useState(false);
  const [now,setNow]=useState(Date.now());

  useEffect(()=>{let active=true;loadLiveState().then(s=>{if(active)setState(s)});const off=subscribeLiveState(setState);return()=>{active=false;off()}},[]);
  useEffect(()=>{let active=true;loadIntelligenceState().then(v=>{if(active){setSetup(v.setup);setPerformance(v.performance)}});const off=subscribeIntelligenceState(setSetup,setPerformance);return()=>{active=false;off()}},[]);

  useEffect(()=>{
    let active=true;
    let channel:ReturnType<ReturnType<typeof getSupabaseBrowserClient>['channel']>|null=null;
    try {
      const supabase=getSupabaseBrowserClient();
      supabase.from('market_latest').select('bid,ask,spread_points,received_at,source').eq('symbol','XAUUSD').maybeSingle().then(({data})=>{
        if(active&&data)setMt4Latest({bid:Number(data.bid),ask:Number(data.ask),spread_points:Number(data.spread_points),received_at:Number(data.received_at),source:data.source});
      });
      channel=supabase.channel('dashboard-market-latest').on('postgres_changes',{event:'*',schema:'public',table:'market_latest',filter:'symbol=eq.XAUUSD'},payload=>{
        const row=payload.new as Record<string,unknown>;
        if(!row||row.symbol!=='XAUUSD')return;
        setMt4Latest({bid:Number(row.bid),ask:Number(row.ask),spread_points:Number(row.spread_points),received_at:Number(row.received_at),source:String(row.source||'MT4')});
      }).subscribe();
    } catch {
      setMt4Latest(null);
    }
    return()=>{active=false;if(channel){try{getSupabaseBrowserClient().removeChannel(channel)}catch{}}};
  },[]);

  useEffect(()=>{
    let active=true;
    setMt4CandleReady(false);
    setMt4Candles([]);
    let channel:ReturnType<ReturnType<typeof getSupabaseBrowserClient>['channel']>|null=null;
    try {
      const supabase=getSupabaseBrowserClient();
      supabase.from('market_candles').select('symbol,timeframe,open_time,open,high,low,close,is_closed').eq('symbol','XAUUSD').eq('timeframe',timeframe).order('open_time',{ascending:false}).limit(120).then(({data,error})=>{
        if(!active)return;
        if(!error&&data){
          const rows=(data as CandleRow[]).slice().reverse().map(rowToCandle);
          setMt4Candles(rows);
          setMt4CandleReady(rows.length>0);
        }
      });
      channel=supabase.channel(`dashboard-candles-${timeframe}`).on('postgres_changes',{event:'*',schema:'public',table:'market_candles',filter:'symbol=eq.XAUUSD'},payload=>{
        const row=payload.new as CandleRow;
        if(!row||row.symbol!=='XAUUSD'||row.timeframe!==timeframe)return;
        const candle=rowToCandle(row);
        setMt4Candles(prev=>{
          const next=prev.filter(v=>v.t!==candle.t);
          next.push(candle);
          next.sort((a,b)=>(a.t||0)-(b.t||0));
          return next.slice(-120);
        });
        setMt4CandleReady(true);
      }).subscribe();
    } catch {
      setMt4Candles([]);
      setMt4CandleReady(false);
    }
    return()=>{active=false;if(channel){try{getSupabaseBrowserClient().removeChannel(channel)}catch{}}};
  },[timeframe]);

  useEffect(()=>{let stop=false;const load=async()=>{try{const r=await fetch(`/api/market?timeframe=${timeframe}`,{cache:'no-store'});const j=await r.json();if(!stop)setMarket(j)}catch{if(!stop)setMarket({ok:false,error:'Feed connection failed'})}};load();const t=setInterval(load,15000);return()=>{stop=true;clearInterval(t)}},[timeframe]);
  useEffect(()=>{const t=setInterval(()=>setNow(Date.now()),30000);return()=>clearInterval(t)},[]);

  const mt4Live=Boolean(mt4Latest?.bid&&mt4Latest.received_at&&Date.now()-mt4Latest.received_at<120000);
  const fallbackPrice=market?.gold?.price||4419.09;
  const price=mt4Live&&mt4Latest?.bid?mt4Latest.bid:fallbackPrice;
  const candles=mt4CandleReady&&mt4Candles.length?mt4Candles:(market?.gold?.candles||fallbackCandles(price));
  const previousClose=market?.gold?.previousClose;
  const change=previousClose?price-previousClose:0;
  const sessions=useMemo(()=>[
    sessionNow('SYDNEY','Australia/Sydney',8,17),
    sessionNow('ASIA / TOKYO','Asia/Tokyo',9,18),
    sessionNow('LONDON','Europe/London',8,17),
    sessionNow('NEW YORK','America/New_York',8,17)
  ],[now]);
  const openSessions=sessions.filter(s=>s.isOpen).map(s=>s.label);
  const compact=broadcast&&state.mode==='CHART FOCUS'; const biasClass=state.bias==='BULLISH'?'positive':state.bias==='BEARISH'?'negative':'neutral';
  const online=mt4Live||market?.ok===true;
  const setupPct=setup.totalCount>0?Math.min(100,(setup.passedCount/setup.totalCount)*100):0;
  const setupLive=setup.totalCount>0 || setup.updatedAt>0;
  const performanceLive=performance.totalCalls>0 || performance.asOf>0;
  const chartSource=mt4CandleReady?'ALPARI MT4':'TEMP PROXY';

  return <main className={broadcast?'broadcast':'shell'}>
    <div className="topbar"><div className="brand"><div className="brand-badge">AU</div><div><h1>XAU/USD GOLD INTELLIGENCE</h1><div className="muted">Live research terminal • {mt4Live?'Alpari MT4 connected':'MT4 reconnecting / backup feed'}</div></div></div><div className={`live-pill ${online?'feed-live':'feed-warn'}`}>● {mt4Live?'MT4 LIVE':online?'BACKUP ONLINE':'BACKUP DATA'} • {state.mode}</div></div>

    <section className="session-strip">{sessions.map(s=><div className={`session-chip ${s.isOpen?'session-open':''}`} key={s.label}><span>{s.label}</span><strong>{s.isOpen?'● OPEN':'○ CLOSED'}</strong><small>{s.isOpen?`closes ${s.text}`:`next open ${s.text}`}</small></div>)}</section>

    <section className={compact?'grid compact-grid':'grid'}>
      <div className="panel chart-panel">
        <div className="row"><div><div className="label">{mt4Live?'ALPARI MT4 XAUUSD':'TEMP ONLINE GOLD FEED'}</div><div className="price">{price.toFixed(2)}</div><div className={change>=0?'positive':'negative'}>{previousClose?`${change>=0?'+':''}${change.toFixed(2)} vs prev close`:`Bid ${mt4Latest?.bid?.toFixed(2)||'--'} • Ask ${mt4Latest?.ask?.toFixed(2)||'--'}`}</div></div><div style={{textAlign:'right'}}><div className="label">Market Bias</div><strong className={biasClass}>{state.bias}</strong><div className="muted">Setup strength {state.confidence}%</div></div></div>
        <div className="stat-grid"><div className="stat"><span className="label">DXY</span><strong>{market?.dxy?.price?.toFixed(2)||'--'}</strong></div><div className="stat"><span className="label">US 10Y</span><strong>{market?.us10y?.price?`${market.us10y.price.toFixed(2)}%`:'--'}</strong></div><div className="stat"><span className="label">Active Sessions</span><strong>{openSessions.length?openSessions.join(' + '):'Transition'}</strong></div></div>
        <div className="timeframe-row"><div><div className="label">Candle timeframe</div><div className="timeframe-bar">{TIMEFRAMES.map(tf=><button key={tf.key} className={`timeframe-btn ${timeframe===tf.key?'active':''}`} onClick={()=>setTimeframe(tf.key)}>{tf.label}</button>)}</div></div><div className={`timeframe-source ${mt4CandleReady?'feed-live':'feed-warn'}`}>● {chartSource}</div></div>
        <CandleChart candles={candles} price={price} state={state}/>
        <div className="legend"><span><i className="dot" style={{background:'#69d493'}}/>{mt4CandleReady?`MT4 ${timeframe} candles`:`Temporary ${timeframe} candles`}</span><span><i className="dot" style={{background:'#d9b54a'}}/>VCPR preview*</span><span className="muted">*VCPR levels remain placeholders until the MT4 history backtest is completed.</span></div>
      </div>

      {!compact&&<div className="side">
        <TelegramLiveChat compact={broadcast}/>
        <div className="panel card setup-card"><div className="row"><div><div className="label">Official Setup Engine • {setup.symbol} {setup.timeframe}</div><h3 className="setup-title">{setup.direction} {setup.status.replaceAll('_',' ')}</h3></div><span className="grade">{setup.grade}</span></div><div className="gateway-number">{setup.passedCount} <span>/ {setup.totalCount || '—'} gateways</span></div><div className="progress"><i style={{width:`${setupPct}%`}}/></div><div className="mini-grid"><div><span>Mandatory</span><strong className={setup.mandatoryTotal>0&&setup.mandatoryPassed===setup.mandatoryTotal?'positive':'neutral'}>{setup.mandatoryPassed}/{setup.mandatoryTotal || '—'} {setup.mandatoryTotal>0&&setup.mandatoryPassed===setup.mandatoryTotal?'PASS':'WAIT'}</strong></div><div><span>Final Trigger</span><strong className="neutral">{setup.finalTrigger}</strong></div></div><div className="mini-grid"><div><span>Market State</span><strong>{setup.marketState}</strong></div><div><span>Execution Safety</span><strong>{setup.executionSafety}</strong></div></div><div className="locked">🔒 Proprietary gateway details hidden on public dashboard</div>{!setupLive&&<small className="muted">Realtime setup feed ready. Waiting for the strategy engine/MT4 integration.</small>}</div>
        <div className="panel card"><div className="label">Official Calls Performance — Demo Account</div><div className="performance-grid"><div><span>Calls</span><strong>{performance.totalCalls}</strong></div><div><span>Win rate</span><strong>{performanceLive?`${performance.winRate.toFixed(1)}%`:'—'}</strong></div><div><span>Net R</span><strong className={performance.netR>=0?'positive':'negative'}>{performanceLive?`${performance.netR>=0?'+':''}${performance.netR.toFixed(1)}R`:'—'}</strong></div><div><span>Max DD</span><strong className="negative">{performanceLive?`${performance.maxDrawdownR.toFixed(1)}R`:'—'}</strong></div></div>{performance.demoBalance!=null&&<div className="mini-grid"><div><span>Demo Balance</span><strong>${performance.demoBalance.toFixed(2)}</strong></div><div><span>Demo Equity</span><strong>${(performance.demoEquity??performance.demoBalance).toFixed(2)}</strong></div></div>}<small className="muted">{performanceLive?'Realtime immutable-call performance snapshot.':'Ledger connected. Statistics begin only after official demo calls are recorded.'}</small></div>
      </div>}
    </section>
    <div className="source-note">SOURCE: {mt4Live?'Alpari MT4 realtime price':'temporary price fallback'} • CHART: {mt4CandleReady?`Alpari MT4 ${timeframe}`:`temporary ${timeframe} proxy`} • DXY/US10Y remain temporary market proxies.</div>
    <div className="ticker"><span>⚡ {state.headline||'Gold Intelligence dashboard online'} &nbsp;&nbsp; • &nbsp;&nbsp; {openSessions.length?`${openSessions.join(' + ')} session active`:'Session transition'} &nbsp;&nbsp; • &nbsp;&nbsp; {setup.totalCount?`${setup.passedCount}/${setup.totalCount} gateways passed`:'Gateway engine waiting'} &nbsp;&nbsp; • &nbsp;&nbsp; Public shows aggregate gateway state only.</span></div>
  </main>;
}
