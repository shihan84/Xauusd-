create table if not exists public.vcpr_history (
  symbol text not null,
  origin_open_time bigint not null,
  origin_date date not null,
  previous_open_time bigint not null,
  pivot numeric not null,
  cpr_low numeric not null,
  cpr_high numeric not null,
  origin_day_touched boolean,
  virgin_on_day boolean,
  validation_status text not null default 'UNVALIDATED',
  m5_first_time bigint,
  m5_last_time bigint,
  later_touched boolean,
  first_later_touch bigint,
  source text not null default 'MT4',
  scanned_at timestamptz not null default now(),
  primary key (symbol, origin_open_time)
);

create index if not exists vcpr_history_symbol_date_idx
  on public.vcpr_history(symbol, origin_open_time desc);

alter table public.vcpr_history enable row level security;

do $$ begin
  create policy "vcpr history public read"
    on public.vcpr_history for select
    using (true);
exception when duplicate_object then null;
end $$;

alter table public.vcpr_history replica identity full;

do $$ begin
  alter publication supabase_realtime add table public.vcpr_history;
exception when duplicate_object then null;
end $$;

create or replace function public.refresh_vcpr_history(p_symbol text default 'XAUUSD')
returns table(
  scanned_rows integer,
  validated_rows integer,
  virgin_rows integer,
  m5_coverage_start bigint,
  m5_coverage_end bigint
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_m5_min bigint;
  v_m5_max bigint;
  v_count integer;
  v_validated integer;
  v_virgin integer;
begin
  select min(open_time), max(open_time)
    into v_m5_min, v_m5_max
  from public.market_candles
  where symbol = p_symbol and timeframe = 'M5';

  with d1 as (
    select
      open_time,
      open,
      high,
      low,
      close,
      lag(open_time) over (order by open_time) as previous_open_time,
      lag(high) over (order by open_time) as previous_high,
      lag(low) over (order by open_time) as previous_low,
      lag(close) over (order by open_time) as previous_close,
      lead(open_time) over (order by open_time) as next_open_time
    from public.market_candles
    where symbol = p_symbol and timeframe = 'D1'
  ),
  base as (
    select
      open_time as origin_open_time,
      previous_open_time,
      next_open_time,
      (previous_high + previous_low + previous_close) / 3.0 as pivot,
      least(
        (previous_high + previous_low) / 2.0,
        2.0 * ((previous_high + previous_low + previous_close) / 3.0) - ((previous_high + previous_low) / 2.0)
      ) as cpr_low,
      greatest(
        (previous_high + previous_low) / 2.0,
        2.0 * ((previous_high + previous_low + previous_close) / 3.0) - ((previous_high + previous_low) / 2.0)
      ) as cpr_high
    from d1
    where previous_open_time is not null
  ),
  classified as (
    select
      b.*,
      case
        when b.next_open_time is not null
         and v_m5_min is not null
         and v_m5_max is not null
         and b.origin_open_time >= v_m5_min
         and b.next_open_time <= v_m5_max + 300
        then 'M5_VALIDATED'
        else 'UNVALIDATED'
      end as validation_status,
      exists (
        select 1
        from public.market_candles m
        where m.symbol = p_symbol
          and m.timeframe = 'M5'
          and b.next_open_time is not null
          and m.open_time >= b.origin_open_time
          and m.open_time < b.next_open_time
          and m.high >= b.cpr_low
          and m.low <= b.cpr_high
      ) as origin_touch,
      (
        select min(m.open_time)
        from public.market_candles m
        where m.symbol = p_symbol
          and m.timeframe = 'M5'
          and b.next_open_time is not null
          and m.open_time >= b.next_open_time
          and m.high >= b.cpr_low
          and m.low <= b.cpr_high
      ) as first_later_touch
    from base b
  )
  insert into public.vcpr_history (
    symbol,
    origin_open_time,
    origin_date,
    previous_open_time,
    pivot,
    cpr_low,
    cpr_high,
    origin_day_touched,
    virgin_on_day,
    validation_status,
    m5_first_time,
    m5_last_time,
    later_touched,
    first_later_touch,
    source,
    scanned_at
  )
  select
    p_symbol,
    c.origin_open_time,
    to_timestamp(c.origin_open_time)::date,
    c.previous_open_time,
    c.pivot,
    c.cpr_low,
    c.cpr_high,
    case when c.validation_status = 'M5_VALIDATED' then c.origin_touch else null end,
    case when c.validation_status = 'M5_VALIDATED' then not c.origin_touch else null end,
    c.validation_status,
    v_m5_min,
    v_m5_max,
    case when c.first_later_touch is not null then true else false end,
    c.first_later_touch,
    'MT4',
    now()
  from classified c
  on conflict (symbol, origin_open_time) do update set
    origin_date = excluded.origin_date,
    previous_open_time = excluded.previous_open_time,
    pivot = excluded.pivot,
    cpr_low = excluded.cpr_low,
    cpr_high = excluded.cpr_high,
    origin_day_touched = excluded.origin_day_touched,
    virgin_on_day = excluded.virgin_on_day,
    validation_status = excluded.validation_status,
    m5_first_time = excluded.m5_first_time,
    m5_last_time = excluded.m5_last_time,
    later_touched = excluded.later_touched,
    first_later_touch = excluded.first_later_touch,
    source = excluded.source,
    scanned_at = excluded.scanned_at;

  get diagnostics v_count = row_count;

  select count(*) into v_validated
  from public.vcpr_history
  where symbol = p_symbol and validation_status = 'M5_VALIDATED';

  select count(*) into v_virgin
  from public.vcpr_history
  where symbol = p_symbol and validation_status = 'M5_VALIDATED' and virgin_on_day is true;

  return query select v_count, v_validated, v_virgin, v_m5_min, v_m5_max;
end;
$$;

comment on function public.refresh_vcpr_history(text) is
'Computes CPR from D-1 D1 OHLC and classifies the origin day as VCPR only when full M5 coverage exists. Historical VCPR status is immutable conceptually: later touches are metadata and never declassify virgin_on_day.';
