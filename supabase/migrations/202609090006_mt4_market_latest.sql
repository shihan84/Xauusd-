create table if not exists public.market_latest (
  symbol text primary key,
  source text not null default 'MT4',
  server_time bigint,
  digits integer,
  bid numeric,
  ask numeric,
  spread_points numeric,
  m1 jsonb not null default '{}'::jsonb,
  indicators jsonb not null default '{}'::jsonb,
  received_at bigint,
  updated_at timestamptz not null default now()
);

alter table public.market_latest enable row level security;

create policy "market latest public read"
on public.market_latest
for select
using (true);

-- Writes are intentionally not granted to public/authenticated users.
-- The local MT4 bridge writes with the Supabase service-role key only.

do $$
begin
  alter publication supabase_realtime add table public.market_latest;
exception
  when duplicate_object then null;
end $$;
