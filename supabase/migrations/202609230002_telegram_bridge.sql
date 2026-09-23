create table if not exists public.integration_status (
  integration text primary key,
  status text not null check (status in ('CONNECTED','DEGRADED','DISCONNECTED','SETUP_REQUIRED')),
  last_ok_at timestamptz,
  last_error text,
  metadata jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.telegram_public_messages (
  chat_id text not null,
  message_id bigint not null,
  update_id bigint,
  sender text not null,
  username text,
  body text not null,
  sent_at timestamptz not null,
  created_at timestamptz not null default now(),
  primary key (chat_id, message_id)
);

create index if not exists telegram_public_messages_sent_at_idx
  on public.telegram_public_messages (sent_at desc);

alter table public.integration_status enable row level security;
alter table public.telegram_public_messages enable row level security;

drop policy if exists "Public can read integration status" on public.integration_status;
create policy "Public can read integration status"
  on public.integration_status for select using (true);

drop policy if exists "Public can read telegram public messages" on public.telegram_public_messages;
create policy "Public can read telegram public messages"
  on public.telegram_public_messages for select using (true);

do $$
begin
  alter publication supabase_realtime add table public.integration_status;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.telegram_public_messages;
exception when duplicate_object then null;
end $$;
