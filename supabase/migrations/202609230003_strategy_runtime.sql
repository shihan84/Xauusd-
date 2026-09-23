alter table public.strategy_registry
  add column if not exists runtime_status text,
  add column if not exists runtime_payload jsonb not null default '{}'::jsonb,
  add column if not exists runtime_updated_at timestamptz;

comment on column public.strategy_registry.runtime_status is
  'Current live/paper engine state reported by the local strategy runtime.';

comment on column public.strategy_registry.runtime_payload is
  'Current non-secret strategy runtime snapshot for dashboard display.';

comment on column public.strategy_registry.runtime_updated_at is
  'Heartbeat timestamp of the strategy runtime sync.';
