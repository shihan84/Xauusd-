"use client";

import { getSupabaseBrowserClient } from './supabaseClient';

export type Bias = 'BULLISH' | 'NEUTRAL' | 'BEARISH';
export type BroadcastMode = 'DASHBOARD' | 'CHART FOCUS' | 'NEWS' | 'BREAKING' | 'DATA RELEASE' | 'COMMENTARY';

export type LiveState = {
  bias: Bias;
  confidence: number;
  headline: string;
  mode: BroadcastMode;
  showAllVcpr: boolean;
  highlightUntouched: boolean;
  showRevisited: boolean;
  updatedAt: number;
};

export const DEFAULT_LIVE_STATE: LiveState = {
  bias: 'BULLISH',
  confidence: 72,
  headline: 'Waiting for MT4 live bridge • Demo feed active',
  mode: 'DASHBOARD',
  showAllVcpr: true,
  highlightUntouched: true,
  showRevisited: true,
  updatedAt: Date.now()
};

const STORAGE_KEY = 'xauusd-live-state-v1';
const CHANNEL_KEY = 'xauusd-broadcast-state';

type BroadcastRow = {
  id: string;
  bias: string;
  confidence: number;
  headline: string;
  mode: string;
  show_all_vcpr: boolean;
  highlight_untouched: boolean;
  show_revisited: boolean;
  updated_at: string;
};

function normalize(row: Partial<BroadcastRow> | null | undefined): LiveState {
  if (!row) return DEFAULT_LIVE_STATE;
  return {
    bias: (row.bias as Bias) || DEFAULT_LIVE_STATE.bias,
    confidence: typeof row.confidence === 'number' ? row.confidence : DEFAULT_LIVE_STATE.confidence,
    headline: row.headline ?? DEFAULT_LIVE_STATE.headline,
    mode: (row.mode as BroadcastMode) || DEFAULT_LIVE_STATE.mode,
    showAllVcpr: row.show_all_vcpr ?? DEFAULT_LIVE_STATE.showAllVcpr,
    highlightUntouched: row.highlight_untouched ?? DEFAULT_LIVE_STATE.highlightUntouched,
    showRevisited: row.show_revisited ?? DEFAULT_LIVE_STATE.showRevisited,
    updatedAt: row.updated_at ? new Date(row.updated_at).getTime() : Date.now()
  };
}

function cacheLocal(next: LiveState) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  try {
    const channel = new BroadcastChannel(CHANNEL_KEY);
    channel.postMessage(next);
    channel.close();
  } catch {}
  window.dispatchEvent(new CustomEvent('xauusd-live-state', { detail: next }));
}

export function readLiveState(): LiveState {
  if (typeof window === 'undefined') return DEFAULT_LIVE_STATE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULT_LIVE_STATE, ...JSON.parse(raw) } : DEFAULT_LIVE_STATE;
  } catch {
    return DEFAULT_LIVE_STATE;
  }
}

export async function loadLiveState(): Promise<LiveState> {
  try {
    const supabase = getSupabaseBrowserClient();
    const { data, error } = await supabase
      .from('broadcast_state')
      .select('id,bias,confidence,headline,mode,show_all_vcpr,highlight_untouched,show_revisited,updated_at')
      .eq('id', 'global')
      .single();
    if (error) throw error;
    const next = normalize(data as BroadcastRow);
    cacheLocal(next);
    return next;
  } catch {
    return readLiveState();
  }
}

export async function publishLiveState(next: LiveState): Promise<{ ok: boolean; error?: string }> {
  cacheLocal(next);
  try {
    const supabase = getSupabaseBrowserClient();
    const { error } = await supabase
      .from('broadcast_state')
      .update({
        bias: next.bias,
        confidence: next.confidence,
        headline: next.headline,
        mode: next.mode,
        show_all_vcpr: next.showAllVcpr,
        highlight_untouched: next.highlightUntouched,
        show_revisited: next.showRevisited,
        updated_at: new Date(next.updatedAt).toISOString()
      })
      .eq('id', 'global');
    if (error) return { ok: false, error: error.message };
    return { ok: true };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : 'Supabase update failed' };
  }
}

export function subscribeLiveState(listener: (state: LiveState) => void) {
  if (typeof window === 'undefined') return () => {};

  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY && event.newValue) {
      try { listener({ ...DEFAULT_LIVE_STATE, ...JSON.parse(event.newValue) }); } catch {}
    }
  };
  const onCustom = (event: Event) => listener((event as CustomEvent<LiveState>).detail);
  let localChannel: BroadcastChannel | null = null;
  let realtimeChannel: ReturnType<ReturnType<typeof getSupabaseBrowserClient>['channel']> | null = null;

  try {
    localChannel = new BroadcastChannel(CHANNEL_KEY);
    localChannel.onmessage = event => listener(event.data as LiveState);
  } catch {}

  try {
    const supabase = getSupabaseBrowserClient();
    realtimeChannel = supabase
      .channel('broadcast-state-global')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'broadcast_state', filter: 'id=eq.global' },
        payload => {
          const next = normalize(payload.new as BroadcastRow);
          cacheLocal(next);
          listener(next);
        }
      )
      .subscribe();
  } catch {}

  window.addEventListener('storage', onStorage);
  window.addEventListener('xauusd-live-state', onCustom);

  return () => {
    window.removeEventListener('storage', onStorage);
    window.removeEventListener('xauusd-live-state', onCustom);
    localChannel?.close();
    if (realtimeChannel) {
      try { getSupabaseBrowserClient().removeChannel(realtimeChannel); } catch {}
    }
  };
}
