"use client";

import { useEffect, useMemo, useState } from 'react';

const vcprs = [
  { date: 'Sep 03', pivot: 4462.38, touched: false },
  { date: 'Aug 29', pivot: 4431.72, touched: true },
  { date: 'Aug 12', pivot: 4376.45, touched: true },
  { date: 'Jul 24', pivot: 4289.2, touched: false }
];

function PriceChart({ price }: { price: number }) {
  const points = useMemo(() => {
    const base = price - 14;
    return Array.from({ length: 70 }, (_, i) => {
      const drift = i * 0.18;
      const wave = Math.sin(i / 4.2) * 3.4 + Math.sin(i / 9) * 2.2;
      return base + drift + wave;
    });
  }, [Math.round(price)]);

  const levels = [...vcprs.map(v => v.pivot), ...points];
  const min = Math.min(...levels) - 5;
  const max = Math.max(...levels) + 5;
  const x = (i: number) => (i / (points.length - 1)) * 1000;
  const y = (v: number) => 420 - ((v - min) / (max - min)) * 380;
  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(p).toFixed(1)}`).join(' ');

  return (
    <div className="chart">
      <svg viewBox="0 0 1000 460" preserveAspectRatio="none">
        {Array.from({ length: 6 }, (_, i) => <line key={i} x1="0" x2="1000" y1={40 + i * 70} y2={40 + i * 70} stroke="#162231" strokeWidth="1" />)}
        {vcprs.map(v => (
          <g key={v.date}>
            <line x1="0" x2="1000" y1={y(v.pivot)} y2={y(v.pivot)} stroke={v.touched ? '#7c8798' : '#d4ad47'} strokeWidth="2" strokeDasharray={v.touched ? '8 8' : '0'} />
            <text x="12" y={y(v.pivot) - 7} fill={v.touched ? '#9aa6b6' : '#f4d26d'} fontSize="13">VCPR {v.date} • {v.pivot.toFixed(2)}</text>
          </g>
        ))}
        <path d={path} fill="none" stroke="#75d79a" strokeWidth="3" />
        <circle cx={x(points.length - 1)} cy={y(points[points.length - 1])} r="5" fill="#9af0b7" />
      </svg>
    </div>
  );
}

export default function MarketDashboard({ broadcast = false }: { broadcast?: boolean }) {
  const [price, setPrice] = useState(4447.6);
  const [bias, setBias] = useState<'BULLISH' | 'NEUTRAL' | 'BEARISH'>('BULLISH');
  const [headline, setHeadline] = useState('Waiting for MT4 live bridge • Demo feed active');

  useEffect(() => {
    const timer = setInterval(() => setPrice(p => Math.max(4200, p + (Math.random() - 0.48) * 0.9)), 900);
    return () => clearInterval(timer);
  }, []);

  return (
    <main className={broadcast ? 'broadcast' : 'shell'}>
      <div className="topbar">
        <div className="brand"><div className="brand-badge">AU</div><div><h1>XAU/USD GOLD INTELLIGENCE</h1><div className="muted">MT4-ready realtime analysis dashboard</div></div></div>
        <div className="live-pill">● DEMO DATA • MT4 BRIDGE PENDING</div>
      </div>

      <section className="grid">
        <div className="panel chart-panel">
          <div className="row"><div><div className="label">XAU/USD</div><div className="price">{price.toFixed(2)}</div></div><div style={{textAlign:'right'}}><div className="label">Market Bias</div><strong className={bias === 'BULLISH' ? 'positive' : bias === 'BEARISH' ? 'negative' : 'neutral'}>{bias}</strong><div className="muted">Confidence 72%</div></div></div>
          <div className="stat-grid"><div className="stat"><span className="label">DXY</span><strong>97.84</strong></div><div className="stat"><span className="label">US 10Y</span><strong>3.91%</strong></div><div className="stat"><span className="label">Spread</span><strong>0.26</strong></div></div>
          <PriceChart price={price} />
          <div className="legend"><span><i className="dot" style={{background:'#d4ad47'}}/>Untouched VCPR pivot</span><span><i className="dot" style={{background:'#7c8798'}}/>Later-touched historical VCPR</span><span><i className="dot" style={{background:'#75d79a'}}/>XAU/USD demo path</span></div>
        </div>

        <div className="side">
          <div className="panel card"><div className="label">Historic VCPR Pivots</div><div className="vcpr-table">{vcprs.map(v => <div className="vcpr-row" key={v.date}><span>{v.date}</span><strong>{v.pivot.toFixed(2)}</strong><span className={v.touched ? 'muted' : 'positive'}>{v.touched ? 'Revisited' : 'Untouched'}</span></div>)}</div></div>
          <div className="panel card"><div className="label">Next US Risk Event</div><h3 style={{marginBottom:6}}>Economic event feed pending</h3><div className="muted">Will show ET + IST countdown and 5-minute pre-event warning.</div></div>
          {!broadcast && <div className="panel card"><div className="label">Operator Demo</div><div style={{display:'flex',gap:8,marginTop:10,flexWrap:'wrap'}}><button className="btn btn-dark" onClick={()=>setBias('BULLISH')}>Bullish</button><button className="btn btn-dark" onClick={()=>setBias('NEUTRAL')}>Neutral</button><button className="btn btn-dark" onClick={()=>setBias('BEARISH')}>Bearish</button></div><input className="input" value={headline} onChange={e=>setHeadline(e.target.value)} /></div>}
        </div>
      </section>
      <div className="ticker"><span>⚡ {headline} &nbsp;&nbsp; • &nbsp;&nbsp; VCPR rule: virgin status is decided only on the originating day; center pivot carries forward permanently.</span></div>
    </main>
  );
}
