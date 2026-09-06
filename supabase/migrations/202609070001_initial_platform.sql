create extension if not exists pgcrypto;

create type public.user_tier as enum ('PUBLIC','MEMBER','PREMIUM');
create type public.call_status as enum ('WATCHING','SETUP_FORMING','CONFIRMED','INVALIDATED','CLOSED');
create type public.support_status as enum ('NEW','QUEUED','ASSIGNED','ACTIVE','RESOLVED','CLOSED');

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  tier public.user_tier not null default 'PUBLIC',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.trial_entitlements (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  trial_code text not null,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  used_at timestamptz,
  converted_at timestamptz,
  created_at timestamptz not null default now(),
  unique(user_id, trial_code)
);

create table public.broadcast_state (
  id text primary key default 'global',
  bias text not null default 'NEUTRAL',
  confidence integer not null default 50 check (confidence between 0 and 100),
  headline text not null default '',
  mode text not null default 'DASHBOARD',
  show_all_vcpr boolean not null default true,
  highlight_untouched boolean not null default true,
  show_revisited boolean not null default true,
  updated_by uuid references public.profiles(id),
  updated_at timestamptz not null default now()
);
insert into public.broadcast_state(id) values ('global') on conflict do nothing;

create table public.vcpr_records (
  id uuid primary key default gen_random_uuid(),
  trading_date date not null unique,
  pivot numeric not null,
  cpr_high numeric not null,
  cpr_low numeric not null,
  virgin_on_day boolean not null,
  later_touched boolean not null default false,
  first_later_touch timestamptz,
  source text not null default 'MT4',
  created_at timestamptz not null default now()
);

create table public.gateway_snapshots (
  id uuid primary key default gen_random_uuid(),
  symbol text not null default 'XAUUSD',
  timeframe text not null,
  setup_id text,
  passed_count integer not null default 0,
  total_count integer not null default 0,
  mandatory_passed integer not null default 0,
  mandatory_total integer not null default 0,
  final_trigger text not null default 'WAITING',
  market_state text,
  public_payload jsonb not null default '{}'::jsonb,
  premium_payload jsonb not null default '{}'::jsonb,
  internal_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.official_calls (
  id uuid primary key default gen_random_uuid(),
  call_ref text not null unique,
  symbol text not null default 'XAUUSD',
  timeframe text not null,
  direction text not null check (direction in ('BUY','SELL')),
  status public.call_status not null default 'WATCHING',
  entry numeric,
  original_sl numeric,
  original_tp1 numeric,
  original_tp2 numeric,
  original_tp3 numeric,
  gateway_passed integer,
  gateway_total integer,
  published_at timestamptz,
  closed_at timestamptz,
  realized_r numeric,
  realized_pl numeric,
  immutable_hash text,
  created_at timestamptz not null default now()
);

create table public.call_events (
  id uuid primary key default gen_random_uuid(),
  call_id uuid not null references public.official_calls(id) on delete cascade,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.performance_snapshots (
  id uuid primary key default gen_random_uuid(),
  total_calls integer not null default 0,
  wins integer not null default 0,
  losses integer not null default 0,
  breakeven integer not null default 0,
  net_r numeric not null default 0,
  max_drawdown_r numeric not null default 0,
  demo_balance numeric,
  demo_equity numeric,
  as_of timestamptz not null default now()
);

create table public.alert_rules (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  name text not null,
  symbol text not null default 'XAUUSD',
  timeframe text,
  rule jsonb not null,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.support_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  status public.support_status not null default 'NEW',
  subject text,
  assigned_to uuid references public.profiles(id),
  requested_at timestamptz not null default now(),
  active_at timestamptz,
  resolved_at timestamptz,
  closed_at timestamptz
);

alter table public.profiles enable row level security;
alter table public.trial_entitlements enable row level security;
alter table public.broadcast_state enable row level security;
alter table public.vcpr_records enable row level security;
alter table public.gateway_snapshots enable row level security;
alter table public.official_calls enable row level security;
alter table public.call_events enable row level security;
alter table public.performance_snapshots enable row level security;
alter table public.alert_rules enable row level security;
alter table public.support_requests enable row level security;

create policy "profiles own read" on public.profiles for select using (auth.uid() = id);
create policy "profiles own update" on public.profiles for update using (auth.uid() = id);
create policy "trials own read" on public.trial_entitlements for select using (auth.uid() = user_id);
create policy "broadcast public read" on public.broadcast_state for select using (true);
create policy "vcpr public read" on public.vcpr_records for select using (true);
create policy "gateway public read" on public.gateway_snapshots for select using (true);
create policy "official calls public read" on public.official_calls for select using (true);
create policy "call events public read" on public.call_events for select using (true);
create policy "performance public read" on public.performance_snapshots for select using (true);
create policy "alert rules own all" on public.alert_rules for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "support own read" on public.support_requests for select using (auth.uid() = user_id);
create policy "support own insert" on public.support_requests for insert with check (auth.uid() = user_id);

alter publication supabase_realtime add table public.broadcast_state;
alter publication supabase_realtime add table public.gateway_snapshots;
alter publication supabase_realtime add table public.official_calls;
alter publication supabase_realtime add table public.performance_snapshots;
