"use client";

import { useEffect, useMemo, useState } from 'react';
import { getSupabaseBrowserClient } from '../lib/supabaseClient';

type ReactionRow = {
  reaction_id: string;
  origin_date: string;
  pivot: number | string;
  source: string;
  vcpr_status: string;
  approach_side: string;
  touch_started_at_utc: string;
  touch_price: number | string;
  touch_count: number | string;
  same_side_excursion: number | string;
  opposite_side_excursion: number | string;
  exit_time_utc: string;
  exit_price: number | string;
  duration_seconds: number | string;
  outcome: string;
};

function fmtDateTime(value: string) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value || '—';
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    timeZone: 'Asia/Kolkata'
  }).format(d);
}

function fmtDuration(seconds: number) {
  if (!Number.isFinite(seconds)) return '—';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

export default function VcprReactionAnalytics() {
  const [rows, setRows] = useState<ReactionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const supabase = getSupabaseBrowserClient();

    const load = async () => {
      try {
        const { data, error: queryError } = await supabase
          .from('vcpr_level_reactions')
          .select('reaction_id,origin_date,pivot,source,vcpr_status,approach_side,touch_started_at_utc,touch_price,touch_count,same_side_excursion,opposite_side_excursion,exit_time_utc,exit_price,duration_seconds,outcome')
          .eq('symbol', 'XAUUSD')
          .order('exit_time_utc', { ascending: false })
          .limit(200);
        if (queryError) throw queryError;
        if (active) {
          setRows((data || []) as ReactionRow[]);
          setError(null);
        }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : 'Reaction analytics unavailable');
      } finally {
        if (active) setLoading(false);
      }
    };

    void load();
    const channel = supabase
      .channel('vcpr-reaction-analytics')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'vcpr_level_reactions' }, () => { void load(); })
      .subscribe();

    return () => {
      active = false;
      supabase.removeChannel(channel);
    };
  }, []);

  const stats = useMemo(() => {
    const total = rows.length;
    const rejection = rows.filter(r => r.outcome === 'REJECTION').length;
    const breakthrough = rows.filter(r => r.outcome === 'BREAKTHROUGH').length;
    const alpari = rows.filter(r => r.source === 'ALPARI_MT4').length;
    const v3 = rows.filter(r => r.source === 'V3').length;
    const avgSame = total ? rows.reduce((a, r) => a + Number(r.same_side_excursion || 0), 0) / total : 0;
    const avgOpposite = total ? rows.reduce((a, r) => a + Number(r.opposite_side_excursion || 0), 0) / total : 0;
    return { total, rejection, breakthrough, alpari, v3, avgSame, avgOpposite };
  }, [rows]);

  const card: React.CSSProperties = {
    background: '#0d151f', border: '1px solid #1f2d3d', borderRadius: 12, padding: 14, minHeight: 88
  };

  return (
    <section style={{ maxWidth: 1500, margin: '0 auto', padding: '0 22px 90px' }}>
      <div className="panel" style={{ padding: 18 }}>
        <div className="label">FORWARD OBSERVATION</div>
        <h2 style={{ margin: '5px 0 4px', fontSize: 21 }}>VCPR Level Reaction Analytics</h2>
        <div className="muted" style={{ maxWidth: 900 }}>
          Completed live touch episodes only. Rejection/breakthrough describe where price first reached the configured reset distance after a touch; they are not trade signals or probability claims.
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(165px,1fr))', gap: 10, marginTop: 16 }}>
          <div style={card}><div className="label">Completed episodes</div><strong style={{ fontSize: 25 }}>{stats.total}</strong></div>
          <div style={card}><div className="label">Rejections</div><strong style={{ fontSize: 25 }}>{stats.rejection}</strong></div>
          <div style={card}><div className="label">Breakthroughs</div><strong style={{ fontSize: 25 }}>{stats.breakthrough}</strong></div>
          <div style={card}><div className="label">ALPARI MT4</div><strong style={{ fontSize: 25 }}>{stats.alpari}</strong></div>
          <div style={card}><div className="label">V3</div><strong style={{ fontSize: 25 }}>{stats.v3}</strong></div>
          <div style={card}><div className="label">Avg same-side excursion</div><strong style={{ fontSize: 21 }}>{stats.avgSame.toFixed(2)}</strong></div>
          <div style={card}><div className="label">Avg opposite excursion</div><strong style={{ fontSize: 21 }}>{stats.avgOpposite.toFixed(2)}</strong></div>
        </div>

        {loading && <div className="muted" style={{ marginTop: 16 }}>Loading live reaction evidence…</div>}
        {error && <div className="negative" style={{ marginTop: 16 }}>Reaction analytics: {error}</div>}

        {!loading && !error && (
          <div style={{ overflowX: 'auto', border: '1px solid #1f2d3d', borderRadius: 10, marginTop: 16 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1120 }}>
              <thead>
                <tr style={{ background: '#0b1118', textAlign: 'left' }}>
                  {['Exit (IST)','Origin','PP','Source','Status','From','Outcome','Tests','Same-side','Opposite','Duration'].map(label => (
                    <th key={label} style={{ padding: '11px 12px', fontSize: 12, color: '#8d99aa', borderBottom: '1px solid #1f2d3d' }}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 30).map(r => (
                  <tr key={r.reaction_id} style={{ borderBottom: '1px solid #172331' }}>
                    <td style={{ padding: '10px 12px' }}>{fmtDateTime(r.exit_time_utc)}</td>
                    <td style={{ padding: '10px 12px' }}>{r.origin_date}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 800 }}>{Number(r.pivot).toFixed(2)}</td>
                    <td style={{ padding: '10px 12px' }}>{r.source}</td>
                    <td style={{ padding: '10px 12px' }}>{r.vcpr_status}</td>
                    <td style={{ padding: '10px 12px' }}>{r.approach_side}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 800 }}>{r.outcome}</td>
                    <td style={{ padding: '10px 12px' }}>{Number(r.touch_count)}</td>
                    <td style={{ padding: '10px 12px' }}>{Number(r.same_side_excursion).toFixed(2)}</td>
                    <td style={{ padding: '10px 12px' }}>{Number(r.opposite_side_excursion).toFixed(2)}</td>
                    <td style={{ padding: '10px 12px' }}>{fmtDuration(Number(r.duration_seconds))}</td>
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan={11} className="muted" style={{ padding: 18 }}>No completed live reaction episodes yet. Active touches are intentionally not counted until they resolve to the reset distance.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
