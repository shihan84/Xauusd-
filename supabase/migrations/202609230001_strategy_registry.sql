create table if not exists public.strategy_registry (
  strategy_id text primary key,
  name text not null,
  strategy_group text not null default 'VCPR',
  timeframe text not null,
  status text not null check (status in ('PAPER_READY','FORWARD_TEST','RESEARCH','PAUSED','RETIRED')),
  mode text not null check (mode in ('MONITOR_ONLY','PAPER','OBSERVE_ONLY','DISABLED')),
  enabled boolean not null default true,
  dashboard_visible boolean not null default true,
  telegram_enabled boolean not null default false,
  description text not null default '',
  rules jsonb not null default '{}'::jsonb,
  evidence jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.strategy_registry enable row level security;

drop policy if exists "Public can read strategy registry" on public.strategy_registry;
create policy "Public can read strategy registry"
  on public.strategy_registry
  for select
  using (dashboard_visible = true);

insert into public.strategy_registry (
  strategy_id,name,strategy_group,timeframe,status,mode,enabled,dashboard_visible,telegram_enabled,description,rules,evidence
) values
(
  'VCPR_ABOVE_V1',
  'VCPR ABOVE Continuation V1',
  'VCPR',
  'M5',
  'PAPER_READY',
  'MONITOR_ONLY',
  true,true,true,
  'Frozen historical candidate. Keep rules unchanged while collecting independent forward evidence.',
  jsonb_build_object(
    'location','ABOVE VCPR',
    'arm_distance_atr',0.50,
    'confirmation','prior 6 continuous closed M5 bullish break + trigger close',
    'stop','2 ATR',
    'target','VCPR PP'
  ),
  jsonb_build_object(
    'historical_n',25,
    'fixed_stop_wins',21,
    'gross_expectancy_atr',1.161,
    'warning','Small historical sample; before costs; not proof of future performance.'
  )
),
(
  'VCPR_FIRST_TOUCH_REJECTION',
  'VCPR First-Touch Rejection',
  'VCPR',
  'M1/M5',
  'RESEARCH',
  'OBSERVE_ONLY',
  true,true,true,
  'First-touch rejection research. M1 is preferred because M5 intrabar ambiguity is high in the 2026 sample.',
  jsonb_build_object(
    'touch_distance',0.50,
    'reaction_reset_distance',8.0,
    'entry_rules','NOT FROZEN',
    'risk_rules','NOT FROZEN'
  ),
  jsonb_build_object(
    'alpari_m1_first_touch_resolved',3,
    'alpari_m1_first_touch_rejections',2,
    'alpari_m1_first_touch_breakthroughs',1,
    'warning','Too few independent VCPR levels to claim an edge.'
  )
),
(
  'VCPR_BREAKTHROUGH_RESEARCH',
  'VCPR Breakthrough / Continuation',
  'VCPR',
  'M1/M5',
  'RESEARCH',
  'OBSERVE_ONLY',
  true,true,true,
  'Breakthrough behavior is being measured separately from rejection behavior so opposite outcomes are not mixed.',
  jsonb_build_object(
    'touch_distance',0.50,
    'reaction_reset_distance',8.0,
    'entry_rules','NOT FROZEN',
    'risk_rules','NOT FROZEN'
  ),
  jsonb_build_object(
    'warning','Research-only until exact rules are frozen and forward-tested.'
  )
)
on conflict (strategy_id) do update set
  name=excluded.name,
  strategy_group=excluded.strategy_group,
  timeframe=excluded.timeframe,
  status=excluded.status,
  mode=excluded.mode,
  enabled=excluded.enabled,
  dashboard_visible=excluded.dashboard_visible,
  telegram_enabled=excluded.telegram_enabled,
  description=excluded.description,
  rules=excluded.rules,
  evidence=excluded.evidence,
  updated_at=now();

do $$
begin
  alter publication supabase_realtime add table public.strategy_registry;
exception
  when duplicate_object then null;
end $$;
