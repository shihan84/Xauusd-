-- Public-safe realtime setup state and operator-only writes.
-- Proprietary gateway details remain in gateway_snapshots.

create table if not exists public.public_setup_state (
  id text primary key default 'global',
  symbol text not null default 'XAUUSD',
  timeframe text not null default 'M5',
  direction text not null default 'NEUTRAL' check (direction in ('BULLISH','NEUTRAL','BEARISH')),
  status text not null default 'WATCHING',
  grade text not null default 'WATCH',
  passed_count integer not null default 0 check (passed_count >= 0),
  total_count integer not null default 0 check (total_count >= 0),
  mandatory_passed integer not null default 0 check (mandatory_passed >= 0),
  mandatory_total integer not null default 0 check (mandatory_total >= 0),
  final_trigger text not null default 'WAITING',
  market_state text not null default 'NORMAL',
  execution_safety text not null default 'NORMAL',
  updated_at timestamptz not null default now(),
  updated_by uuid references public.profiles(id)
);

insert into public.public_setup_state (
  id, symbol, timeframe, direction, status, grade,
  passed_count, total_count, mandatory_passed, mandatory_total,
  final_trigger, market_state, execution_safety
) values (
  'global','XAUUSD','M5','NEUTRAL','WATCHING','WATCH',
  0,0,0,0,'WAITING','NORMAL','NORMAL'
) on conflict (id) do nothing;

alter table public.public_setup_state enable row level security;

create policy "public setup read" on public.public_setup_state
for select using (true);

create policy "operator setup insert" on public.public_setup_state
for insert with check (
  exists (select 1 from public.profiles p where p.id = auth.uid() and p.is_operator = true)
);

create policy "operator setup update" on public.public_setup_state
for update using (
  exists (select 1 from public.profiles p where p.id = auth.uid() and p.is_operator = true)
) with check (
  exists (select 1 from public.profiles p where p.id = auth.uid() and p.is_operator = true)
);

create policy "operator performance insert" on public.performance_snapshots
for insert with check (
  exists (select 1 from public.profiles p where p.id = auth.uid() and p.is_operator = true)
);

create policy "operator performance update" on public.performance_snapshots
for update using (
  exists (select 1 from public.profiles p where p.id = auth.uid() and p.is_operator = true)
) with check (
  exists (select 1 from public.profiles p where p.id = auth.uid() and p.is_operator = true)
);

alter publication supabase_realtime add table public.public_setup_state;

comment on table public.public_setup_state is
'Public realtime projection of aggregate setup/gateway state only. No proprietary gateway names, weights, thresholds or internal conditions.';
