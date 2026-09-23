"use client";

import { useEffect, useRef, useState } from 'react';
import { getSupabaseBrowserClient } from '../lib/supabaseClient';

type TelegramMessage = {
  chat_id: string;
  message_id: number;
  update_id?: number | null;
  sender: string;
  username?: string | null;
  body: string;
  sent_at: string;
};

type IntegrationStatus = {
  status: 'CONNECTED'|'DEGRADED'|'DISCONNECTED'|'SETUP_REQUIRED'|string;
  last_ok_at: string | null;
  last_error: string | null;
  updated_at: string;
};

export default function TelegramLiveChat({ compact = false }: { compact?: boolean }) {
  const [messages, setMessages] = useState<TelegramMessage[]>([]);
  const [integration, setIntegration] = useState<IntegrationStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let active = true;
    const supabase = getSupabaseBrowserClient();

    const load = async () => {
      try {
        const [messageResult, statusResult] = await Promise.all([
          supabase
            .from('telegram_public_messages')
            .select('chat_id,message_id,update_id,sender,username,body,sent_at')
            .order('sent_at', { ascending: false })
            .limit(40),
          supabase
            .from('integration_status')
            .select('status,last_ok_at,last_error,updated_at')
            .eq('integration', 'telegram_group')
            .maybeSingle(),
        ]);

        if (messageResult.error) throw messageResult.error;
        if (statusResult.error) throw statusResult.error;

        if (active) {
          setMessages(((messageResult.data || []) as TelegramMessage[]).slice().reverse());
          setIntegration((statusResult.data || null) as IntegrationStatus | null);
          setError(null);
        }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : 'Telegram bridge unavailable');
      }
    };

    void load();

    const messageChannel = supabase
      .channel('telegram-public-messages')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'telegram_public_messages' }, () => void load())
      .subscribe();

    const statusChannel = supabase
      .channel('telegram-integration-status')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'integration_status', filter: 'integration=eq.telegram_group' }, () => void load())
      .subscribe();

    return () => {
      active = false;
      try { supabase.removeChannel(messageChannel); } catch {}
      try { supabase.removeChannel(statusChannel); } catch {}
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages]);

  const lastOkMs = integration?.last_ok_at ? new Date(integration.last_ok_at).getTime() : 0;
  const heartbeatFresh = lastOkMs > 0 && Date.now() - lastOkMs < 120000;
  const connected = integration?.status === 'CONNECTED' && heartbeatFresh;
  const statusText = connected
    ? '● CONNECTED'
    : integration?.status === 'DEGRADED'
      ? '● DEGRADED'
      : integration
        ? '● OFFLINE'
        : '● WAITING FOR BRIDGE';

  return (
    <div className={`telegram-panel ${compact ? 'telegram-compact' : ''}`}>
      <div className="telegram-head">
        <div>
          <div className="label">Telegram Public Group</div>
          <strong>LIVE TRADER CHAT</strong>
        </div>
        <span className={`telegram-status ${connected ? 'telegram-live' : integration?.status === 'DEGRADED' ? 'telegram-error' : 'telegram-setup'}`}>
          {statusText}
        </span>
      </div>

      <div className="telegram-messages">
        {error && <div className="telegram-empty">Telegram bridge error: {error}</div>}
        {!error && messages.length === 0 && (
          <div className="telegram-empty">
            {connected
              ? 'Telegram bridge connected. Waiting for public group messages…'
              : 'Local Telegram bridge is not reporting a fresh heartbeat.'}
          </div>
        )}

        {messages.map((m) => {
          const time = new Date(m.sent_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          return (
            <div className="telegram-message" key={`${m.chat_id}-${m.message_id}`}>
              <div className="telegram-meta">
                <strong>{m.sender}</strong>
                {m.username && <span>@{m.username}</span>}
                <time>{time}</time>
              </div>
              <div className="telegram-text">{m.body}</div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      <div className="telegram-foot">
        PUBLIC GROUP • LOCAL BOT BRIDGE → SUPABASE • NO BOT TOKEN REQUIRED ON VERCEL
      </div>
    </div>
  );
}
