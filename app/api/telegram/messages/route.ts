import { NextResponse } from 'next/server';

type TgUpdate = {
  update_id: number;
  message?: {
    message_id: number;
    date: number;
    chat: { id: number; title?: string; type: string };
    from?: { first_name?: string; last_name?: string; username?: string; is_bot?: boolean };
    text?: string;
    caption?: string;
  };
};

export const dynamic = 'force-dynamic';

export async function GET() {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;

  if (!token || !chatId) {
    return NextResponse.json({
      configured: false,
      messages: [],
      error: 'Telegram environment variables are not configured.'
    }, { status: 503 });
  }

  try {
    const url = `https://api.telegram.org/bot${token}/getUpdates?limit=100&allowed_updates=%5B%22message%22%5D`;
    const response = await fetch(url, { cache: 'no-store' });
    const payload = await response.json();

    if (!response.ok || !payload?.ok) {
      return NextResponse.json({ configured: true, messages: [], error: payload?.description || 'Telegram API error' }, { status: 502 });
    }

    const updates: TgUpdate[] = Array.isArray(payload.result) ? payload.result : [];
    const messages = updates
      .filter((u) => u.message && String(u.message.chat.id) === String(chatId) && !u.message.from?.is_bot)
      .map((u) => {
        const m = u.message!;
        const first = m.from?.first_name || 'Telegram User';
        const last = m.from?.last_name ? ` ${m.from.last_name}` : '';
        return {
          id: m.message_id,
          updateId: u.update_id,
          chatId: String(m.chat.id),
          sender: `${first}${last}`,
          username: m.from?.username,
          text: m.text || m.caption || '[Media message]',
          date: m.date
        };
      })
      .slice(-40);

    return NextResponse.json({ configured: true, messages }, {
      headers: { 'Cache-Control': 'no-store, max-age=0' }
    });
  } catch (error) {
    return NextResponse.json({ configured: true, messages: [], error: error instanceof Error ? error.message : 'Unknown error' }, { status: 500 });
  }
}
