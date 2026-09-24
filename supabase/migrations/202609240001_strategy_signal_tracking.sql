alter table public.strategy_signals
  add column if not exists paper_status text not null default 'ACTIVE',
  add column if not exists outcome_1r text,
  add column if not exists outcome_2r text,
  add column if not exists t1_hit_at timestamptz,
  add column if not exists t2_hit_at timestamptz,
  add column if not exists stop_hit_at timestamptz,
  add column if not exists closed_at timestamptz,
  add column if not exists mfe_r numeric,
  add column if not exists mae_r numeric,
  add column if not exists last_evaluated_at timestamptz;

comment on column public.strategy_signals.paper_status is
  'Paper-trade lifecycle state such as ACTIVE, T1_HIT, T2_HIT, STOPPED, T1_HIT_THEN_STOP, EXPIRED or AMBIGUOUS.';

comment on column public.strategy_signals.outcome_1r is
  'Independent first-hit test for the 1R target: WIN, STOP, EXPIRED or AMBIGUOUS.';

comment on column public.strategy_signals.outcome_2r is
  'Independent first-hit test for the 2R target: WIN, STOP, EXPIRED or AMBIGUOUS.';
