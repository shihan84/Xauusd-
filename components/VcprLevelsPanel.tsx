"use client";

import { useEffect, useMemo, useState } from 'react';
import { getSupabaseBrowserClient } from '../lib/supabaseClient';

type VcprRow = {
  origin_date: string;
  pivot: number | string;
  later_touched: boolean;
  first_later_touch: number | string | null;
  validation_status: string;
  virgin_on_day: boolean;
  source: string | null;
};

type VcprLevel = {
  date: string;
  pivot: number;
  touched: boolean;
  firstLaterTouch: number | string | null;
  source: string;
};

type PriceRow = {
  bid: number | string | null;
  ask: number | string | null;
  received_at: number | string | null;
};

type Filter = 'ALL' | 'UNRESOLVED' | 'REVISITED';

function formatOriginDate(value: string) {
  const d = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC'
  }).format(d);
}

function formatTouchTime(value: number | string | null) {
  if (value == null) return '—';

  let d: Date;
  if (typeof value === 'number' || /^\d+(\.\d+)?$/.test(String(value))) {
    const n = Number(value);
    const ms = Math.abs(n) < 1e12 ? n * 1000 : n;
    d = new Date(ms);
  } else {
    d = new Date(String(value));
  }

  if (Number.isNaN(d.getTime())) return '—';

  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Kolkata'
  }).format(d);
}

function distanceLabel(pivot: number, price: number | null) {
  if (!price) return '—';
  const distance = pivot - price;
  return `${distance >= 0 ? '+' : ''}${distance.toFixed(2)}`;
}

function sourceLabel(source: string) {
  if (source === 'MT4') return 'ALPARI MT4';
  if (source === 'V3_RESEARCH') return 'V3';
  return source || 'UNKNOWN';
}

export default function VcprLevelsPanel() {
  const [levels, setLevels] = useState<VcprLevel[]>([]);
  const [price, setPrice] = useState<number | null>(null);
  const [filter, setFilter] = useState<Filter>('ALL');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let priceChannel: ReturnType<ReturnType<typeof getSupabaseBrowserClient>['channel']> | null = null;
    let vcprChannel: ReturnType<ReturnType<typeof getSupabaseBrowserClient>['channel']> | null = null;

    const loadLevels = async () => {
      try {
        const supabase = getSupabaseBrowserClient();
        const { data, error: queryError } = await supabase
          .from('vcpr_history')
          .select('origin_date,pivot,later_touched,first_later_touch,validation_status,virgin_on_day,source')
          .eq('symbol', 'XAUUSD')
          .eq('virgin_on_day', true)
          .eq('validation_status', 'M5_VALIDATED')
          .order('origin_open_time', { ascending: false });

        if (queryError) throw queryError;
        if (!active) return;

        const next = ((data || []) as VcprRow[])
          .map(row => ({
            date: row.origin_date,
            pivot: Number(row.pivot),
            touched: Boolean(row.later_touched),
            firstLaterTouch: row.first_later_touch,
            source: String(row.source || 'UNKNOWN')
          }))
          .filter(row => Number.isFinite(row.pivot));

        setLevels(next);
        setError(null);
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : 'VCPR history unavailable');
      } finally {
        if (active) setLoading(false);
      }
    };

    const start = async () => {
      const supabase = getSupabaseBrowserClient();

      const { data } = await supabase
        .from('market_latest')
        .select('bid,ask,received_at')
        .eq('symbol', 'XAUUSD')
        .maybeSingle();

      if (active && data) {
        const row = data as PriceRow;
        const bid = Number(row.bid);
        if (Number.isFinite(bid)) setPrice(bid);
      }

      await loadLevels();

      priceChannel = supabase
        .channel('vcpr-level-panel-price')
        .on(
          'postgres_changes',
          { event: '*', schema: 'public', table: 'market_latest', filter: 'symbol=eq.XAUUSD' },
          payload => {
            const row = payload.new as Record<string, unknown>;
            const bid = Number(row?.bid);
            if (Number.isFinite(bid)) setPrice(bid);
          }
        )
        .subscribe();

      vcprChannel = supabase
        .channel('vcpr-level-panel-history')
        .on(
          'postgres_changes',
          { event: '*', schema: 'public', table: 'vcpr_history', filter: 'symbol=eq.XAUUSD' },
          () => { void loadLevels(); }
        )
        .subscribe();
    };

    void start();

    return () => {
      active = false;
      try {
        const supabase = getSupabaseBrowserClient();
        if (priceChannel) supabase.removeChannel(priceChannel);
        if (vcprChannel) supabase.removeChannel(vcprChannel);
      } catch {}
    };
  }, []);

  const unresolved = useMemo(() => levels.filter(level => !level.touched), [levels]);
  const revisited = useMemo(() => levels.filter(level => level.touched), [levels]);
  const alpari = useMemo(() => levels.filter(level => level.source === 'MT4'), [levels]);
  const v3 = useMemo(() => levels.filter(level => level.source === 'V3_RESEARCH'), [levels]);

  const nearestAbove = useMemo(() => {
    if (!price) return null;
    return levels
      .filter(level => level.pivot >= price)
      .sort((a, b) => a.pivot - b.pivot)[0] || null;
  }, [levels, price]);

  const nearestBelow = useMemo(() => {
    if (!price) return null;
    return levels
      .filter(level => level.pivot < price)
      .sort((a, b) => b.pivot - a.pivot)[0] || null;
  }, [levels, price]);

  const visibleLevels = useMemo(() => {
    const filtered = levels.filter(level => {
      if (filter === 'UNRESOLVED') return !level.touched;
      if (filter === 'REVISITED') return level.touched;
      return true;
    });

    if (!price) return filtered.slice(0, 30);

    return filtered
      .slice()
      .sort((a, b) => Math.abs(a.pivot - price) - Math.abs(b.pivot - price))
      .slice(0, 30);
  }, [filter, levels, price]);

  const cardStyle: React.CSSProperties = {
    background: '#0d151f',
    border: '1px solid #1f2d3d',
    borderRadius: 12,
    padding: 14,
    minHeight: 92
  };

  return (
    <section style={{ maxWidth: 1500, margin: '0 auto', padding: '0 22px 90px' }}>
      <div className="panel" style={{ padding: 18 }}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap' }}>
          <div>
            <div className="label">PERMANENT VCPR S/R MAP</div>
            <h2 style={{ margin: '5px 0 4px', fontSize: 21 }}>Historical VCPR Pivot Levels</h2>
            <div className="muted" style={{ maxWidth: 760 }}>
              A confirmed VCPR remains a structural reference after its first revisit. Revisited levels stay visible; they are not treated as fresh strategy entries. Alpari MT4 rows are broker-authoritative; V3 rows are the validated historical research map.
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className="label">Live XAUUSD</div>
            <strong style={{ fontSize: 24 }}>{price ? price.toFixed(2) : '—'}</strong>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 10, marginTop: 16 }}>
          <div style={cardStyle}>
            <div className="label">All permanent levels</div>
            <strong style={{ fontSize: 26 }}>{levels.length}</strong>
            <div className="muted">M5 validated</div>
          </div>
          <div style={cardStyle}>
            <div className="label">Unresolved</div>
            <strong style={{ fontSize: 26, color: '#f1d16c' }}>{unresolved.length}</strong>
            <div className="muted">Never revisited yet</div>
          </div>
          <div style={cardStyle}>
            <div className="label">Revisited</div>
            <strong style={{ fontSize: 26, color: '#8fb6e8' }}>{revisited.length}</strong>
            <div className="muted">Still monitored as S/R</div>
          </div>
          <div style={cardStyle}>
            <div className="label">Alpari MT4</div>
            <strong style={{ fontSize: 26, color: '#69d493' }}>{alpari.length}</strong>
            <div className="muted">Broker-authoritative</div>
          </div>
          <div style={cardStyle}>
            <div className="label">V3</div>
            <strong style={{ fontSize: 26, color: '#b8a7ff' }}>{v3.length}</strong>
            <div className="muted">Historical research levels</div>
          </div>
          <div style={cardStyle}>
            <div className="label">Nearest VCPR above</div>
            <strong style={{ fontSize: 22 }}>{nearestAbove ? nearestAbove.pivot.toFixed(2) : '—'}</strong>
            <div className="muted">
              {nearestAbove ? `${nearestAbove.touched ? 'REVISITED' : 'UNRESOLVED'} • ${sourceLabel(nearestAbove.source)} • ${distanceLabel(nearestAbove.pivot, price)}` : 'No level above'}
            </div>
          </div>
          <div style={cardStyle}>
            <div className="label">Nearest VCPR below</div>
            <strong style={{ fontSize: 22 }}>{nearestBelow ? nearestBelow.pivot.toFixed(2) : '—'}</strong>
            <div className="muted">
              {nearestBelow ? `${nearestBelow.touched ? 'REVISITED' : 'UNRESOLVED'} • ${sourceLabel(nearestBelow.source)} • ${distanceLabel(nearestBelow.pivot, price)}` : 'No level below'}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 18, marginBottom: 10 }}>
          {(['ALL', 'UNRESOLVED', 'REVISITED'] as Filter[]).map(value => (
            <button
              key={value}
              className={`timeframe-btn ${filter === value ? 'active' : ''}`}
              onClick={() => setFilter(value)}
            >
              {value}
            </button>
          ))}
          <span className="muted" style={{ marginLeft: 4 }}>
            Chart above: mouse wheel = zoom • drag = pan • LIVE / RESET returns to current price.
          </span>
        </div>

        {loading && <div className="muted">Loading VCPR levels…</div>}
        {error && <div className="negative">VCPR level feed: {error}</div>}

        {!loading && !error && (
          <div style={{ overflowX: 'auto', border: '1px solid #1f2d3d', borderRadius: 10 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 930 }}>
              <thead>
                <tr style={{ background: '#0b1118', textAlign: 'left' }}>
                  {['Origin', 'PP level', 'Status', 'Source', 'Position vs price', 'Distance', 'First revisit (IST)'].map(label => (
                    <th key={label} style={{ padding: '11px 12px', fontSize: 12, color: '#8d99aa', borderBottom: '1px solid #1f2d3d' }}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleLevels.map(level => {
                  const above = price != null ? level.pivot >= price : null;
                  const isMt4 = level.source === 'MT4';
                  return (
                    <tr key={`${level.date}-${level.pivot}-${level.source}`} style={{ borderBottom: '1px solid #172331' }}>
                      <td style={{ padding: '11px 12px' }}>{formatOriginDate(level.date)}</td>
                      <td style={{ padding: '11px 12px', fontWeight: 800 }}>{level.pivot.toFixed(2)}</td>
                      <td style={{ padding: '11px 12px' }}>
                        <span style={{
                          display: 'inline-block',
                          padding: '4px 8px',
                          borderRadius: 999,
                          fontSize: 11,
                          fontWeight: 800,
                          color: level.touched ? '#b8d7ff' : '#f4d978',
                          background: level.touched ? 'rgba(70,120,180,.16)' : 'rgba(217,181,74,.13)',
                          border: `1px solid ${level.touched ? '#355a82' : '#6d5a25'}`
                        }}>
                          {level.touched ? 'REVISITED' : 'UNRESOLVED'}
                        </span>
                      </td>
                      <td style={{ padding: '11px 12px' }}>
                        <span style={{
                          display: 'inline-block',
                          padding: '4px 8px',
                          borderRadius: 999,
                          fontSize: 11,
                          fontWeight: 800,
                          color: isMt4 ? '#8ff0b4' : '#c9bdff',
                          background: isMt4 ? 'rgba(65,180,110,.12)' : 'rgba(130,105,210,.13)',
                          border: `1px solid ${isMt4 ? '#2e6c49' : '#54458b'}`
                        }}>
                          {sourceLabel(level.source)}
                        </span>
                      </td>
                      <td style={{ padding: '11px 12px' }}>{above == null ? '—' : above ? 'ABOVE PRICE' : 'BELOW PRICE'}</td>
                      <td style={{ padding: '11px 12px', fontVariantNumeric: 'tabular-nums' }}>{distanceLabel(level.pivot, price)}</td>
                      <td style={{ padding: '11px 12px' }}>{level.touched ? formatTouchTime(level.firstLaterTouch) : '—'}</td>
                    </tr>
                  );
                })}
                {visibleLevels.length === 0 && (
                  <tr><td colSpan={7} className="muted" style={{ padding: 18 }}>No VCPR levels in this filter.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        <div className="muted" style={{ marginTop: 10, fontSize: 12 }}>
          The table is sorted by distance from live price and shows the nearest 30 levels. “Revisited” is a historical status only; it does not imply a new trade signal. Alpari MT4 is authoritative where it overlaps V3.
        </div>
      </div>
    </section>
  );
}
