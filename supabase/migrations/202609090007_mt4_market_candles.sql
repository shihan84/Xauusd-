create table if not exists public.market_candles (
  symbol text not null,
  timeframe text not null,
  open_time bigint not null,
  open numeric not null,
  high numeric not null,
  low numeric not null,
  close numeric not null,
  is_closed boolean not null default true,
  source text not null default 'MT4',
  updated_at timestamptz not null default now(),
  primary key (symbol, timeframe, open_time)
);

create index if not exists market_candles_lookup_idx
  on public.market_candles (symbol, timeframe, open_time desc);

alter table public.market_candles enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'market_candles'
      and policyname = 'market candles public read'
  ) then
    create policy "market candles public read"
      on public.market_candles
      for select
      using (true);
  end if;
end $$;

-- Writes stay private. The local bridge uses a Supabase secret/service-role key.
do $$
begin
  alter publication supabase_realtime add table public.market_candles;
exception
  when duplicate_object then null;
end $$;
