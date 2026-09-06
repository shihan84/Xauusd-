-- Protect proprietary gateway details. Public users only receive aggregate fields through gateway_public.

drop policy if exists "gateway public read" on public.gateway_snapshots;

create policy "gateway premium read" on public.gateway_snapshots
for select
using (
  exists (
    select 1
    from public.profiles p
    where p.id = auth.uid()
      and p.tier = 'PREMIUM'
  )
);

create or replace view public.gateway_public
with (security_invoker = false)
as
select
  id,
  symbol,
  timeframe,
  setup_id,
  passed_count,
  total_count,
  mandatory_passed,
  mandatory_total,
  final_trigger,
  market_state,
  public_payload,
  created_at
from public.gateway_snapshots;

grant select on public.gateway_public to anon, authenticated;

comment on view public.gateway_public is
'Public-safe aggregate gateway state. Never expose premium_payload or internal_payload through public dashboard APIs.';
