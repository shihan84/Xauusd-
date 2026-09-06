-- Protect the original published trade plan and keep call_events append-only.

create or replace function public.protect_published_call_originals()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if old.published_at is not null then
    if new.call_ref is distinct from old.call_ref
       or new.symbol is distinct from old.symbol
       or new.timeframe is distinct from old.timeframe
       or new.direction is distinct from old.direction
       or new.entry is distinct from old.entry
       or new.original_sl is distinct from old.original_sl
       or new.original_tp1 is distinct from old.original_tp1
       or new.original_tp2 is distinct from old.original_tp2
       or new.original_tp3 is distinct from old.original_tp3
       or new.gateway_passed is distinct from old.gateway_passed
       or new.gateway_total is distinct from old.gateway_total
       or new.published_at is distinct from old.published_at then
      raise exception 'Published official call original fields are immutable. Record changes in call_events.';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists trg_protect_published_call_originals on public.official_calls;
create trigger trg_protect_published_call_originals
before update on public.official_calls
for each row execute function public.protect_published_call_originals();

create or replace function public.compute_official_call_hash()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.published_at is not null and (old.published_at is null or new.immutable_hash is null) then
    new.immutable_hash := encode(digest(concat_ws('|',
      new.call_ref,
      new.symbol,
      new.timeframe,
      new.direction,
      coalesce(new.entry::text,''),
      coalesce(new.original_sl::text,''),
      coalesce(new.original_tp1::text,''),
      coalesce(new.original_tp2::text,''),
      coalesce(new.original_tp3::text,''),
      coalesce(new.gateway_passed::text,''),
      coalesce(new.gateway_total::text,''),
      new.published_at::text
    ), 'sha256'), 'hex');
  end if;
  return new;
end;
$$;

drop trigger if exists trg_compute_official_call_hash on public.official_calls;
create trigger trg_compute_official_call_hash
before insert or update on public.official_calls
for each row execute function public.compute_official_call_hash();

-- Only operators can create or manage official calls and append events.
create policy "operator official calls insert" on public.official_calls
for insert with check (
  exists (select 1 from public.profiles p where p.id = auth.uid() and p.is_operator = true)
);

create policy "operator official calls update" on public.official_calls
for update using (
  exists (select 1 from public.profiles p where p.id = auth.uid() and p.is_operator = true)
) with check (
  exists (select 1 from public.profiles p where p.id = auth.uid() and p.is_operator = true)
);

create policy "operator call events insert" on public.call_events
for insert with check (
  exists (select 1 from public.profiles p where p.id = auth.uid() and p.is_operator = true)
);

-- No UPDATE or DELETE policies are granted on call_events: event history is append-only through RLS.

comment on function public.protect_published_call_originals() is
'Locks original entry/SL/targets/gateway count and publication timestamp after an official call is published.';
