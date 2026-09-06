"use client";

import { getSupabaseBrowserClient } from './supabaseClient';

export type PublicSetupState = {
  symbol: string;
  timeframe: string;
  direction: 'BULLISH'|'NEUTRAL'|'BEARISH';
  status: string;
  grade: string;
  passedCount: number;
  totalCount: number;
  mandatoryPassed: number;
  mandatoryTotal: number;
  finalTrigger: string;
  marketState: string;
  executionSafety: string;
  updatedAt: number;
};

export type PerformanceState = {
  totalCalls: number;
  wins: number;
  losses: number;
  breakeven: number;
  winRate: number;
  netR: number;
  maxDrawdownR: number;
  demoBalance: number|null;
  demoEquity: number|null;
  asOf: number;
};

export const DEFAULT_PUBLIC_SETUP: PublicSetupState = {
  symbol:'XAUUSD', timeframe:'M5', direction:'NEUTRAL', status:'WATCHING', grade:'WATCH',
  passedCount:0, totalCount:0, mandatoryPassed:0, mandatoryTotal:0,
  finalTrigger:'WAITING', marketState:'NORMAL', executionSafety:'NORMAL', updatedAt:0
};

export const DEFAULT_PERFORMANCE: PerformanceState = {
  totalCalls:0, wins:0, losses:0, breakeven:0, winRate:0, netR:0,
  maxDrawdownR:0, demoBalance:null, demoEquity:null, asOf:0
};

function mapSetup(row:any):PublicSetupState {
  return {
    symbol: row?.symbol || 'XAUUSD', timeframe: row?.timeframe || 'M5',
    direction: row?.direction || 'NEUTRAL', status: row?.status || 'WATCHING',
    grade: row?.grade || 'WATCH', passedCount: Number(row?.passed_count || 0),
    totalCount: Number(row?.total_count || 0), mandatoryPassed: Number(row?.mandatory_passed || 0),
    mandatoryTotal: Number(row?.mandatory_total || 0), finalTrigger: row?.final_trigger || 'WAITING',
    marketState: row?.market_state || 'NORMAL', executionSafety: row?.execution_safety || 'NORMAL',
    updatedAt: row?.updated_at ? Date.parse(row.updated_at) : 0
  };
}

function mapPerformance(row:any):PerformanceState {
  const wins=Number(row?.wins||0), losses=Number(row?.losses||0), be=Number(row?.breakeven||0);
  const decided=wins+losses;
  return {
    totalCalls:Number(row?.total_calls||0), wins, losses, breakeven:be,
    winRate: decided ? (wins/decided)*100 : 0,
    netR:Number(row?.net_r||0), maxDrawdownR:Number(row?.max_drawdown_r||0),
    demoBalance: row?.demo_balance == null ? null : Number(row.demo_balance),
    demoEquity: row?.demo_equity == null ? null : Number(row.demo_equity),
    asOf: row?.as_of ? Date.parse(row.as_of) : 0
  };
}

export async function loadIntelligenceState(){
  try {
    const supabase=getSupabaseBrowserClient();
    const [setupRes, perfRes]=await Promise.all([
      supabase.from('public_setup_state').select('*').eq('id','global').maybeSingle(),
      supabase.from('performance_snapshots').select('*').order('as_of',{ascending:false}).limit(1).maybeSingle()
    ]);
    return {
      setup: setupRes.data ? mapSetup(setupRes.data) : DEFAULT_PUBLIC_SETUP,
      performance: perfRes.data ? mapPerformance(perfRes.data) : DEFAULT_PERFORMANCE
    };
  } catch {
    return {setup:DEFAULT_PUBLIC_SETUP,performance:DEFAULT_PERFORMANCE};
  }
}

export function subscribeIntelligenceState(
  onSetup:(v:PublicSetupState)=>void,
  onPerformance:(v:PerformanceState)=>void
){
  let supabase:ReturnType<typeof getSupabaseBrowserClient>;
  try { supabase=getSupabaseBrowserClient(); } catch { return ()=>{}; }

  const setupChannel=supabase.channel('public-setup-state')
    .on('postgres_changes',{event:'*',schema:'public',table:'public_setup_state',filter:'id=eq.global'},payload=>{
      if(payload.new) onSetup(mapSetup(payload.new));
    }).subscribe();

  const perfChannel=supabase.channel('public-performance-state')
    .on('postgres_changes',{event:'INSERT',schema:'public',table:'performance_snapshots'},payload=>{
      if(payload.new) onPerformance(mapPerformance(payload.new));
    }).subscribe();

  return ()=>{ supabase.removeChannel(setupChannel); supabase.removeChannel(perfChannel); };
}
