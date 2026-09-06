"use client";

import { useState } from 'react';

export default function ControlPage() {
  const [bias, setBias] = useState('BULLISH');
  const [confidence, setConfidence] = useState(72);
  const [headline, setHeadline] = useState('Watching XAU/USD structure and historic VCPR pivots');

  return (
    <main className="shell">
      <div className="topbar"><div className="brand"><div className="brand-badge">AU</div><div><h1>Broadcast Control</h1><div className="muted">Local demo controls — realtime shared state comes next</div></div></div><div className="live-pill">CONTROL PREVIEW</div></div>
      <section className="control-grid">
        <div className="panel card">
          <div className="label">Market Bias</div>
          <div style={{display:'flex',gap:8,margin:'12px 0',flexWrap:'wrap'}}>
            {['BULLISH','NEUTRAL','BEARISH'].map(v => <button key={v} className={bias===v?'btn btn-primary':'btn btn-dark'} onClick={()=>setBias(v)}>{v}</button>)}
          </div>
          <label className="label">Confidence %</label>
          <input className="input" type="number" min="0" max="100" value={confidence} onChange={e=>setConfidence(Number(e.target.value))}/>
        </div>
        <div className="panel card">
          <div className="label">Breaking / Commentary</div>
          <textarea className="input" rows={5} value={headline} onChange={e=>setHeadline(e.target.value)} />
          <div style={{display:'flex',gap:8,marginTop:10,flexWrap:'wrap'}}><button className="btn btn-primary">Publish</button><button className="btn btn-dark">Clear</button></div>
        </div>
        <div className="panel card">
          <div className="label">VCPR Display</div>
          <p><input type="checkbox" defaultChecked /> Show all historical VCPR pivots</p>
          <p><input type="checkbox" defaultChecked /> Highlight never-revisited pivots</p>
          <p><input type="checkbox" defaultChecked /> Keep later-touched pivots visible</p>
          <p className="muted">Only center Pivot is rendered. CPR top/bottom remain internal to the backtest logic.</p>
        </div>
        <div className="panel card">
          <div className="label">Broadcast Mode</div>
          <div style={{display:'flex',gap:8,marginTop:12,flexWrap:'wrap'}}>{['DASHBOARD','CHART FOCUS','NEWS','BREAKING','DATA RELEASE','COMMENTARY'].map(v=><button className="btn btn-dark" key={v}>{v}</button>)}</div>
        </div>
      </section>
      <div className="ticker"><span>Preview state: {bias} • Confidence {confidence}% • {headline}</span></div>
    </main>
  );
}
