import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(r"E:\xauusd")
ENV_FILE = BASE_DIR / "bridge" / ".env"
STATE_FILE = BASE_DIR / "data" / "forward" / "telegram_group_sync_state.json"
POLL_SECONDS = 5


def load_env(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def config():
    load_env(ENV_FILE)
    url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or ""
    ).strip()
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not url or not key:
        raise RuntimeError("Supabase URL/key missing")
    if not token or not chat_id:
        raise RuntimeError("Telegram token/chat id missing")
    return url, key, token, chat_id


def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temp.replace(STATE_FILE)


def supabase_headers(key):
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }


def update_status(url, key, status, chat_id, error=None):
    now = datetime.now(timezone.utc).isoformat()
    payload = [{
        "integration": "telegram_group",
        "status": status,
        "last_ok_at": now if status == "CONNECTED" else None,
        "last_error": error,
        "metadata": {"chat_id": chat_id, "source": "LOCAL_BOT_BRIDGE"},
        "updated_at": now,
    }]
    response = requests.post(
        f"{url}/rest/v1/integration_status?on_conflict=integration",
        headers=supabase_headers(key),
        json=payload,
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Supabase integration_status HTTP {response.status_code}: {response.text[:300]}")


def upsert_messages(url, key, rows):
    if not rows:
        return
    response = requests.post(
        f"{url}/rest/v1/telegram_public_messages?on_conflict=chat_id,message_id",
        headers=supabase_headers(key),
        json=rows,
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Supabase telegram_public_messages HTTP {response.status_code}: {response.text[:300]}")


def fetch_updates(token, offset=None):
    params = {
        "timeout": 0,
        "limit": 100,
        "allowed_updates": json.dumps(["message"]),
    }
    if offset is not None:
        params["offset"] = offset
    else:
        params["offset"] = -50
    response = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params=params,
        timeout=25,
    )
    payload = response.json()
    if not response.ok or not payload.get("ok"):
        raise RuntimeError(payload.get("description") or f"Telegram HTTP {response.status_code}")
    return payload.get("result") or []


def normalize_updates(updates, chat_id):
    rows = []
    max_update_id = None
    for update in updates:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            max_update_id = update_id if max_update_id is None else max(max_update_id, update_id)

        message = update.get("message") or {}
        chat = message.get("chat") or {}
        if str(chat.get("id")) != str(chat_id):
            continue

        sender_obj = message.get("from") or {}
        first = sender_obj.get("first_name") or "Telegram User"
        last = sender_obj.get("last_name") or ""
        sender = f"{first} {last}".strip()
        body = message.get("text") or message.get("caption") or "[Media message]"
        message_id = message.get("message_id")
        date_epoch = message.get("date")
        if message_id is None or date_epoch is None:
            continue

        rows.append({
            "chat_id": str(chat_id),
            "message_id": int(message_id),
            "update_id": update_id,
            "sender": sender,
            "username": sender_obj.get("username"),
            "body": body,
            "sent_at": datetime.fromtimestamp(int(date_epoch), timezone.utc).isoformat(),
        })
    return rows, max_update_id


def main():
    url, key, token, chat_id = config()
    state = load_state()
    offset = state.get("offset")
    print(f"Telegram group sync starting | chat_id={chat_id} | poll={POLL_SECONDS}s", flush=True)

    while True:
        try:
            updates = fetch_updates(token, offset)
            rows, max_update_id = normalize_updates(updates, chat_id)
            upsert_messages(url, key, rows)
            update_status(url, key, "CONNECTED", chat_id, None)

            if max_update_id is not None:
                offset = max_update_id + 1
                state["offset"] = offset
                save_state(state)

            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] SYNC OK | updates={len(updates)} | group_messages={len(rows)} | offset={offset}",
                flush=True,
            )
        except Exception as exc:
            try:
                update_status(url, key, "DEGRADED", chat_id, f"{type(exc).__name__}: {exc}")
            except Exception:
                pass
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] SYNC ERROR | {type(exc).__name__}: {exc}",
                flush=True,
            )

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
