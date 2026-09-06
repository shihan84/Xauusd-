"use client";

import { useEffect, useState } from 'react';
import { BroadcastMode, DEFAULT_LIVE_STATE, LiveState, loadLiveState, publishLiveState } from '../../lib/liveState';
import { getSupabaseBrowserClient } from '../../lib/supabaseClient';

const modes: BroadcastMode[] = ['DASHBOARD','CHART FOCUS','NEWS','BREAKING','DATA RELEASE','COMMENTARY'];

type AuthState = 'CHECKING'|'SIGNED_OUT'|'NO_PERMISSION'|'OPERATOR';

export default function ControlPage() {
  const [state, setState] = useState<LiveState>(DEFAULT_LIVE_STATE);
  const [status, setStatus] = useState<'READY'|'SAVING'|'SAVED'|'ERROR'>('READY');
  const [authState, setAuthState] = useState<AuthState>('CHECKING');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    loadLiveState().then(setState);
    const check = async () => {
      try {
        const supabase = getSupabaseBrowserClient();
        const { data: sessionData } = await supabase.auth.getSession();
        const user = sessionData.session?.user;
        if (!user) { setAuthState('SIGNED_OUT'); return; }
        setEmail(user.email || '');
        const { data, error: profileError } = await supabase.from('profiles').select('is_operator').eq('id', user.id).single();
        if (profileError || !data?.is_operator) { setAuthState('NO_PERMISSION'); return; }
        setAuthState('OPERATOR');
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Authentication check failed');
        setAuthState('SIGNED_OUT');
      }
    };
    check();
  }, []);

  const update = <K extends keyof LiveState>(key: K, value: LiveState[K]) => setState(s => ({ ...s, [key]: value }));
  const publish = async () => {
    if (authState !== 'OPERATOR') return;
    const next = { ...state, updatedAt: Date.now() };
    setState(next);
    setStatus('SAVING');
    setError('');
    const result = await publishLiveState(next);
    if (result.ok) {
      setStatus('SAVED');
      setTimeout(() => setStatus('READY'), 1600);
    } else {
      setStatus('ERROR');
      setError(result.error || 'Supabase publish failed');
    }
  };

  const signOut = async () => {
    try { await getSupabaseBrowserClient().auth.signOut(); } catch {}
    window.location.href = '/login';
  };

  if (authState === 'CHECKING') return <main className="shell"><div className="panel card"><strong>Checking operator access…</strong></div></main>;

  if (authState === 'SIGNED_OUT') return <main className="shell" style={{maxWidth:760}}>
    <div className="topbar"><div className="brand"><div className="brand-badge">AU</div><div><h1>Broadcast Control</h1><div className="muted">Protected operator area</div></div></div></div>
    <div className="panel card"><h2>Sign in required</h2><p className="muted">The public dashboard remains readable, but shared broadcast controls require an authenticated operator.</p><button className="btn btn-primary" onClick={()=>window.location.href='/login'}>Open Operator Login</button>{error&&<p className="negative">{error}</p>}</div>
  </main>;

  if (authState === 'NO_PERMISSION') return <main className="shell" style={{maxWidth:760}}>
    <div className="topbar"><div className="brand"><div className="brand-badge">AU</div><div><h1>Broadcast Control</h1><div className="muted">Signed in as {email}</div></div></div></div>
    <div className="panel card"><h2>Operator permission required</h2><p className="muted">Your account is authenticated, but it has not been granted operator permission yet. In Supabase, set <strong>profiles.is_operator</strong> to <strong>true</strong> for this account. This is intentionally manual so new public/member accounts can never take over the broadcast.</p><button className="btn btn-dark" onClick={signOut}>Sign Out</button></div>
  </main>;

  return (
    <main className="shell">
      <div className="topbar"><div className="brand"><div className="brand-badge">AU</div><div><h1>Broadcast Control</h1><div className="muted">Supabase Realtime control • Operator: {email}</div></div></div><div style={{display:'flex',gap:8,alignItems:'center'}}><div className={`live-pill ${status==='ERROR'?'feed-warn':'feed-live'}`}>{status==='SAVING'?'SYNCING…':status==='SAVED'?'✓ SYNCED':status==='ERROR'?'SYNC ERROR':'REALTIME READY'}</div><button className="btn btn-dark" onClick={signOut}>Sign Out</button></div></div>
      {error && <div className="panel card" style={{marginBottom:14}}><strong className="negative">Supabase write blocked:</strong> <span className="muted">{error}</span></div>}
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
