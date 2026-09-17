create table if not exists public.vcpr_level_reactions (
  reaction_id uuid primary key,
  symbol text not null default 'XAUUSD',
  origin_date date not null,
  pivot numeric not null,
  source text not null,
  vcpr_status text not null,
  approach_side text not null,
  touch_started_at_utc timestamptz not null,
  touch_price numeric not null,
  touch_count integer not null default 1,
  min_price numeric not null,
  max_price numeric not null,
  same_side_excursion numeric not null,
  opposite_side_excursion numeric not null,
  exit_time_utc timestamptz not null,
  exit_price numeric not null,
  duration_seconds integer not null,
  outcome text not null,
  touch_distance numeric not null,
  reset_distance numeric not null,
  created_at timestamptz not null default now(),
  constraint vcpr_level_reactions_outcome_chk check (outcome in ('REJECTION','BREAKTHROUGH')),
  constraint vcpr_level_reactions_side_chk check (approach_side in ('ABOVE','BELOW')),
  constraint vcpr_level_reactions_status_chk check (vcpr_status in ('REVISITED','UNRESOLVED'))
);

create index if not exists vcpr_level_reactions_exit_idx
  on public.vcpr_level_reactions(symbol, exit_time_utc desc);

create index if not exists vcpr_level_reactions_level_idx
  on public.vcpr_level_reactions(symbol, origin_date, pivot);

alter table public.vcpr_level_reactions enable row level security;

do $$ begin
  create policy "vcpr reactions public read"
    on public.vcpr_level_reactions for select
    using (true);
exception when duplicate_object then null;
end $$;

alter table public.vcpr_level_reactions replica identity full;

do $$ begin
  alter publication supabase_realtime add table public.vcpr_level_reactions;
exception when duplicate_object then null;
end $$;

comment on table public.vcpr_level_reactions is
'Forward observational VCPR touch episodes. REJECTION/BREAKTHROUGH are descriptive exit classifications, not trade signals or probability claims.';
