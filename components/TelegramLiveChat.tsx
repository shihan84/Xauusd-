"use client";

import { useEffect, useRef, useState } from 'react';

type TelegramMessage = {
  id: number;
  updateId?: number;
  chatId: string;
  sender: string;
  username?: string;
  text: string;
  date: number;
};

export default function TelegramLiveChat({ compact = false }: { compact?: boolean }) {
  const [messages, setMessages] = useState<TelegramMessage[]>([]);
  const [status, setStatus] = useState<'connecting'|'live'|'setup'|'error'>('connecting');
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let stopped = false;

    async function load() {
      try {
        const res = await fetch('/api/telegram/messages', { cache: 'no-store' });
        if (!res.ok) {
          setStatus(res.status === 503 ? 'setup' : 'error');
          return;
        }
        const data = await res.json();
        if (!stopped) {
          setMessages(Array.isArray(data.messages) ? data.messages : []);
          setStatus('live');
        }
      } catch {
        if (!stopped) setStatus('error');
      }
    }

    load();
    const timer = window.setInterval(load, 2500);
    return () => { stopped = true; window.clearInterval(timer); };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages]);

  const statusText = status === 'live' ? '● LIVE' : status === 'setup' ? 'SETUP REQUIRED' : status === 'error' ? 'CONNECTION ERROR' : 'CONNECTING';

  return (
    <div className={`telegram-panel ${compact ? 'telegram-compact' : ''}`}>
      <div className="telegram-head">
        <div>
          <div className="label">Telegram Public Group</div>
          <strong>LIVE TRADER CHAT</strong>
        </div>
        <span className={`telegram-status telegram-${status}`}>{statusText}</span>
      </div>

      <div className="telegram-messages">
        {messages.length === 0 && (
          <div className="telegram-empty">
            {status === 'setup' ? 'Connect the Telegram bot and group to start the live public chat.' : 'Waiting for public group messages…'}
          </div>
        )}
        {messages.map((m) => {
          const time = new Date(m.date * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          return (
            <div className="telegram-message" key={`${m.id}-${m.date}`}>
              <div className="telegram-meta">
                <strong>{m.sender}</strong>
                {m.username && <span>@{m.username}</span>}
                <time>{time}</time>
              </div>
              <div className="telegram-text">{m.text}</div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      <div className="telegram-foot">PUBLIC GROUP • MESSAGES MAY APPEAR ON YOUTUBE LIVE</div>
    </div>
  );
}
