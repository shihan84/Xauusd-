"use client";

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

export function readLiveState(): LiveState {
  if (typeof window === 'undefined') return DEFAULT_LIVE_STATE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULT_LIVE_STATE, ...JSON.parse(raw) } : DEFAULT_LIVE_STATE;
  } catch {
    return DEFAULT_LIVE_STATE;
  }
}

export function publishLiveState(next: LiveState) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  try {
    const channel = new BroadcastChannel(CHANNEL_KEY);
    channel.postMessage(next);
    channel.close();
  } catch {}
  window.dispatchEvent(new CustomEvent('xauusd-live-state', { detail: next }));
}

export function subscribeLiveState(listener: (state: LiveState) => void) {
  if (typeof window === 'undefined') return () => {};

  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY && event.newValue) {
      try { listener({ ...DEFAULT_LIVE_STATE, ...JSON.parse(event.newValue) }); } catch {}
    }
  };
  const onCustom = (event: Event) => listener((event as CustomEvent<LiveState>).detail);
  let channel: BroadcastChannel | null = null;

  try {
    channel = new BroadcastChannel(CHANNEL_KEY);
    channel.onmessage = event => listener(event.data as LiveState);
  } catch {}

  window.addEventListener('storage', onStorage);
  window.addEventListener('xauusd-live-state', onCustom);

  return () => {
    window.removeEventListener('storage', onStorage);
    window.removeEventListener('xauusd-live-state', onCustom);
    channel?.close();
  };
}
