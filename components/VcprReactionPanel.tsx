"use client";

import { useEffect, useMemo, useState } from 'react';
import { getSupabaseBrowserClient } from '../lib/supabaseClient';

type ReactionRow = {
  reaction_id: string;
  origin_date: string;
  pivot: number | string;
  source: string;
  vcpr_status: 'REVISITED' | 'UNRESOLVED' | string;
  approach_side: 'ABOVE' | 'BELOW' | string;
  touch_started_at_utc: string;
  touch_price: number | string;
  touch_count: number | string;
  min_price: number | string;
  max_price: number | string;
  same_side_excursion: number | string;
  opposite_side_excursion: number | string;
  exit_time_utc: string;
  exit_price: number | string;
  duration_seconds: number | string;
  outcome: 'REJECTION' | 'BREAKTHROUGH' | string;
};

type SourceFilter = 'ALL' | 'V3' | 'ALPARI_MT4';

function n(value: number | string | null | undefined) {
  const valueNumber = Number(value);
  return Number.isFinite(valueNumber) ? valueNumber : 0;
}

function fmtDateTime(value: string) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    timeZone: 'Asia/Kolkata'
  }).format(d);
}

function fmtDuration(seconds: number) {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

export default function VcprReactionPanel() {
  const [rows, setRows] = useState<ReactionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('ALL');

  useEffect(() => {
    let active = true;
    const supabase = getSupabaseBrowserClient();

    const load = async () => {
      try {
        const { data, error: queryError } = await supabase
          .from('vcpr_level_reactions')
          .select('reaction_id,origin_date,pivot,source,vcpr_status,approach_side,touch_started_at_utc,touch_price,touch_count,min_price,max_price,same_side_excursion,opposite_side_excursion,exit_time_utc,exit_price,duration_seconds,outcome')
          .eq('symbol', 'XAUUSD')
          .order('exit_time_utc', { ascending: false })
          .limit(500);
        if (queryError) throw queryError;
        if (!active) return;
        setRows((data || []) as ReactionRow[]);
        setError(null);
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : 'Reaction analytics unavailable');
      } finally {
        if (active) setLoading(false);
      }
    };

    void load();
    const channel = supabase
      .channel('vcpr-reaction-panel')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'vcpr_level_reactions', filter: 'symbol=eq.XAUUSD' }, () => { void load(); })
      .subscribe();

    return () => {
      active = false;
      try { supabase.removeChannel(channel); } catch {}
    };
  }, []);

  const filtered = useMemo(() => rows.filter(row => sourceFilter === 'ALL' || row.source === sourceFilter), [rows, sourceFilter]);
  const rejections = useMemo(() => filtered.filter(row => row.outcome === 'REJECTION'), [filtered]);
  const breakthroughs = useMemo(() => filtered.filter(row => row.outcome === 'BREAKTHROUGH'), [filtered]);
  const avgTouches = useMemo(() => filtered.length ? filtered.reduce((s, row) => s + n(row.touch_count), 0) / filtered.length : 0, [filtered]);
  const avgDuration = useMemo(() => filtered.length ? filtered.reduce((s, row) => s + n(row.duration_seconds), 0) / filtered.length : 0, [filtered]);
  const avgSame = useMemo(() => filtered.length ? filtered.reduce((s, row) => s + n(row.same_side_excursion), 0) / filtered.length : 0, [filtered]);
  const avgOpposite = useMemo(() => filtered.length ? filtered.reduce((s, row) => s + n(row.opposite_side_excursion), 0) / filtered.length : 0, [filtered]);

  const cardStyle: React.CSSProperties = {
    background: '#0d151f', border: '1px solid #1f2d3d', borderRadius: 12, padding: 14, minHeight: 92
  };

  return (
    <section style={{ maxWidth: 1500, margin: '0 auto', padding: '0 22px 90px' }}>
      <div className="panel" style={{ padding: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div>
            <div className="label">VCPR FORWARD REACTION LAB</div>
            <h2 style={{ margin: '5px 0 4px', fontSize: 21 }}>Live Touch Reaction Evidence</h2>
            <div className="muted" style={{ maxWidth: 850 }}>
              Completed live VCPR touch episodes only. Rejection/breakthrough is a descriptive 8-point exit classification, not a trade signal or forecast.
            </div>
          </div>
          <div style={{ display: 'flex', gap: 7, alignItems: 'flex-start', flexWrap: 'wrap' }}>
            {(['ALL','V3','ALPARI_MT4'] as SourceFilter[]).map(value => (
              <button key={value} className={`timeframe-btn ${sourceFilter === value ? 'active' : ''}`} onClick={() => setSourceFilter(value)}>
                {value === 'ALPARI_MT4' ? 'ALPARI MT4' : value}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(170px,1fr))', gap: 10, marginTop: 16 }}>
          <div style={cardStyle}><div className="label">Completed episodes</div><strong style={{ fontSize: 26 }}>{filtered.length}</strong><div className="muted">Forward observations</div></div>
          <div style={cardStyle}><div className="label">Rejections</div><strong style={{ fontSize: 26, color: '#8fd4a8' }}>{rejections.length}</strong><div className="muted">Returned to approach side</div></div>
          <div style={cardStyle}><div className="label">Breakthroughs</div><strong style={{ fontSize: 26, color: '#f0a0a0' }}>{breakthroughs.length}</strong><div className="muted">Exited opposite side</div></div>
          <div style={cardStyle}><div className="label">Avg tests / episode</div><strong style={{ fontSize: 24 }}>{avgTouches.toFixed(2)}</strong><div className="muted">Repeated touch-zone entries</div></div>
          <div style={cardStyle}><div className="label">Avg duration</div><strong style={{ fontSize: 22 }}>{fmtDuration(Math.round(avgDuration))}</strong><div className="muted">First touch to ±8 exit</div></div>
          <div style={cardStyle}><div className="label">Avg same-side excursion</div><strong style={{ fontSize: 22 }}>{avgSame.toFixed(2)}</strong><div className="muted">Observed price units</div></div>
          <div style={cardStyle}><div className="label">Avg opposite excursion</div><strong style={{ fontSize: 22 }}>{avgOpposite.toFixed(2)}</strong><div className="muted">Observed price units</div></div>
        </div>

        {loading && <div className="muted" style={{ marginTop: 14 }}>Loading forward reaction evidence…</div>}
        {error && <div className="negative" style={{ marginTop: 14 }}>Reaction feed: {error}</div>}

        {!loading && !error && (
          <div style={{ overflowX: 'auto', border: '1px solid #1f2d3d', borderRadius: 10, marginTop: 16 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1100 }}>
              <thead>
                <tr style={{ background: '#0b1118', textAlign: 'left' }}>
                  {['Exit (IST)','Origin','PP','Source','Status','From','Outcome','Tests','Duration','Same excursion','Opposite excursion'].map(label => (
                    <th key={label} style={{ padding: '11px 12px', fontSize: 12, color: '#8d99aa', borderBottom: '1px solid #1f2d3d' }}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 40).map(row => (
                  <tr key={row.reaction_id} style={{ borderBottom: '1px solid #172331' }}>
                    <td style={{ padding: '10px 12px' }}>{fmtDateTime(row.exit_time_utc)}</td>
                    <td style={{ padding: '10px 12px' }}>{row.origin_date}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 800 }}>{n(row.pivot).toFixed(2)}</td>
                    <td style={{ padding: '10px 12px' }}>{row.source === 'ALPARI_MT4' ? 'ALPARI MT4' : row.source}</td>
                    <td style={{ padding: '10px 12px' }}>{row.vcpr_status}</td>
                    <td style={{ padding: '10px 12px' }}>{row.approach_side}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 800, color: row.outcome === 'REJECTION' ? '#8fd4a8' : '#f0a0a0' }}>{row.outcome}</td>
                    <td style={{ padding: '10px 12px' }}>{n(row.touch_count)}</td>
                    <td style={{ padding: '10px 12px' }}>{fmtDuration(Math.round(n(row.duration_seconds)))}</td>
                    <td style={{ padding: '10px 12px' }}>{n(row.same_side_excursion).toFixed(2)}</td>
                    <td style={{ padding: '10px 12px' }}>{n(row.opposite_side_excursion).toFixed(2)}</td>
                  </tr>
                ))}
                {filtered.length === 0 && <tr><td colSpan={11} className="muted" style={{ padding: 18 }}>No completed forward reaction episodes yet.</td></tr>}
              </tbody>
            </table>
          </div>
        )}

        <div className="muted" style={{ marginTop: 10, fontSize: 12 }}>
          Do not interpret early percentages or counts as probabilities. This panel is for accumulating out-of-sample evidence before any strategy change.
        </div>
      </div>
    </section>
  );
}
