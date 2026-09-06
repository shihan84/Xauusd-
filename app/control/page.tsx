"use client";

import { useEffect, useState } from 'react';
import { BroadcastMode, DEFAULT_LIVE_STATE, LiveState, publishLiveState, readLiveState } from '../../lib/liveState';

const modes: BroadcastMode[] = ['DASHBOARD','CHART FOCUS','NEWS','BREAKING','DATA RELEASE','COMMENTARY'];

export default function ControlPage() {
  const [state, setState] = useState<LiveState>(DEFAULT_LIVE_STATE);
  const [saved, setSaved] = useState(false);

  useEffect(() => setState(readLiveState()), []);

  const update = <K extends keyof LiveState>(key: K, value: LiveState[K]) => setState(s => ({ ...s, [key]: value }));
  const publish = () => {
    const next = { ...state, updatedAt: Date.now() };
    setState(next);
    publishLiveState(next);
    setSaved(true);
    setTimeout(() => setSaved(false), 1200);
  };

  return (
    <main className="shell">
      <div className="topbar"><div className="brand"><div className="brand-badge">AU</div><div><h1>Broadcast Control</h1><div className="muted">Controls the open dashboard/broadcast tabs in this browser</div></div></div><div className="live-pill">{saved ? '✓ PUBLISHED' : 'CONTROL READY'}</div></div>
      <section className="control-grid">
        <div className="panel card">
          <div className="label">Market Bias</div>
          <div style={{display:'flex',gap:8,margin:'12px 0',flexWrap:'wrap'}}>
            {(['BULLISH','NEUTRAL','BEARISH'] as const).map(v => <button key={v} className={state.bias===v?'btn btn-primary':'btn btn-dark'} onClick={()=>update('bias',v)}>{v}</button>)}
          </div>
          <label className="label">Confidence %</label>
          <input className="input" type="number" min="0" max="100" value={state.confidence} onChange={e=>update('confidence',Math.max(0,Math.min(100,Number(e.target.value))))}/>
        </div>
        <div className="panel card">
          <div className="label">Breaking / Commentary</div>
          <textarea className="input" rows={5} value={state.headline} onChange={e=>update('headline',e.target.value)} />
          <div style={{display:'flex',gap:8,marginTop:10,flexWrap:'wrap'}}><button className="btn btn-primary" onClick={publish}>Publish</button><button className="btn btn-dark" onClick={()=>update('headline','')}>Clear</button></div>
        </div>
        <div className="panel card">
          <div className="label">VCPR Display</div>
          <p><input type="checkbox" checked={state.showAllVcpr} onChange={e=>update('showAllVcpr',e.target.checked)} /> Show historical VCPR pivots</p>
          <p><input type="checkbox" checked={state.highlightUntouched} onChange={e=>update('highlightUntouched',e.target.checked)} /> Highlight never-revisited pivots</p>
          <p><input type="checkbox" checked={state.showRevisited} onChange={e=>update('showRevisited',e.target.checked)} /> Keep later-touched pivots visible</p>
          <p className="muted">Only center Pivot is rendered. CPR top/bottom remain internal to backtest logic.</p>
        </div>
        <div className="panel card">
          <div className="label">Broadcast Mode</div>
          <div style={{display:'flex',gap:8,marginTop:12,flexWrap:'wrap'}}>{modes.map(v=><button className={state.mode===v?'btn btn-primary':'btn btn-dark'} key={v} onClick={()=>update('mode',v)}>{v}</button>)}</div>
          <button className="btn btn-primary" style={{marginTop:14,width:'100%'}} onClick={publish}>Publish All Changes</button>
        </div>
      </section>
      <div className="ticker"><span>Preview: {state.mode} • {state.bias} • Confidence {state.confidence}% • {state.headline || 'No headline'}</span></div>
    </main>
  );
}
