"use client";

import { FormEvent, useEffect, useState } from 'react';
import { getSupabaseBrowserClient } from '../../lib/supabaseClient';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState<'SIGN_IN'|'SIGN_UP'>('SIGN_IN');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    try {
      const supabase = getSupabaseBrowserClient();
      supabase.auth.getSession().then(({ data }) => {
        if (data.session) window.location.href = '/control';
      });
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Supabase is not configured');
    }
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setStatus('');
    try {
      const supabase = getSupabaseBrowserClient();
      if (mode === 'SIGN_IN') {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        window.location.href = '/control';
      } else {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: { data: { display_name: email.split('@')[0] } }
        });
        if (error) throw error;
        if (data.session) window.location.href = '/control';
        else setStatus('Account created. Check your email if confirmation is enabled, then sign in.');
      }
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Authentication failed');
    } finally {
      setBusy(false);
    }
  };

  return <main className="shell" style={{maxWidth:720}}>
    <div className="topbar"><div className="brand"><div className="brand-badge">AU</div><div><h1>Operator Login</h1><div className="muted">XAU/USD Gold Intelligence Control Room</div></div></div></div>
    <section className="panel card">
      <div className="label">{mode === 'SIGN_IN' ? 'SIGN IN' : 'CREATE ACCOUNT'}</div>
      <form onSubmit={submit} style={{display:'grid',gap:12,marginTop:14}}>
        <input className="input" type="email" required placeholder="Email" value={email} onChange={e=>setEmail(e.target.value)} />
        <input className="input" type="password" required minLength={8} placeholder="Password" value={password} onChange={e=>setPassword(e.target.value)} />
        <button className="btn btn-primary" disabled={busy}>{busy ? 'PLEASE WAIT…' : mode === 'SIGN_IN' ? 'Sign In' : 'Create Account'}</button>
      </form>
      {status && <p className="muted" style={{marginTop:12}}>{status}</p>}
      <button className="btn btn-dark" style={{marginTop:12}} onClick={()=>setMode(mode==='SIGN_IN'?'SIGN_UP':'SIGN_IN')}>
        {mode === 'SIGN_IN' ? 'Create operator account' : 'Back to sign in'}
      </button>
      <p className="muted" style={{marginTop:16}}>New accounts are not operators automatically. Operator permission must be explicitly granted in Supabase before broadcast controls can write shared state.</p>
    </section>
  </main>;
}
