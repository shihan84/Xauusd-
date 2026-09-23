import argparse
import hashlib
import json
import os
from pathlib import Path

import requests

BASE_DIR = Path(r"E:\xauusd")
ENV_FILE = BASE_DIR / "bridge" / ".env"
STATE_FILE = BASE_DIR / "data" / "forward" / "strategy_telegram_status_state.json"


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


def get_strategies(url, key):
    response = requests.get(
        f"{url}/rest/v1/strategy_registry",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        params={
            "select": "strategy_id,name,timeframe,status,mode,telegram_enabled,description",
            "enabled": "eq.true",
            "telegram_enabled": "eq.true",
            "order": "strategy_id.asc",
        },
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Supabase strategy_registry HTTP {response.status_code}: {response.text[:300]}")
    return response.json()


def get_setup_state(url, key):
    response = requests.get(
        f"{url}/rest/v1/public_setup_state",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        params={"select": "direction,status,grade,passed_count,total_count,final_trigger,market_state,updated_at", "id": "eq.global", "limit": "1"},
        timeout=20,
    )
    if not response.ok:
        return None
    rows = response.json()
    return rows[0] if rows else None


def render(strategies, setup):
    lines = [
        "XAUUSD STRATEGY ENGINE STATUS",
        "",
    ]
    if not strategies:
        lines.append("No Telegram-enabled strategies are registered.")
    else:
        for row in strategies:
            status = str(row.get("status") or "UNKNOWN").replace("_", " ")
            mode = str(row.get("mode") or "UNKNOWN").replace("_", " ")
            lines.append(f"• {row.get('name')} [{row.get('timeframe')}]")
            lines.append(f"  Status: {status} | Mode: {mode}")
    lines.extend([
        "",
        "Current setup state:",
    ])
    if setup:
        lines.append(
            f"{setup.get('direction','NEUTRAL')} | {setup.get('status','WATCHING')} | "
            f"Trigger: {setup.get('final_trigger','WAITING')}"
        )
        lines.append(
            f"Gateway: {setup.get('passed_count',0)}/{setup.get('total_count',0)} | "
            f"Market: {setup.get('market_state','NORMAL')}"
        )
    else:
        lines.append("No public setup-state row available.")

    lines.extend([
        "",
        "Research/demo monitoring only. No live-money execution is implied.",
    ])
    return "\n".join(lines)


def load_last_hash():
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8")).get("message_hash")
    except Exception:
        return None


def save_hash(value):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"message_hash": value}, indent=2), encoding="utf-8")


def send(token, chat_id, message):
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": message},
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Telegram HTTP {response.status_code}: {response.text[:300]}")


def main():
    parser = argparse.ArgumentParser(description="Send a non-flooding XAUUSD strategy status message to Telegram.")
    parser.add_argument("--force", action="store_true", help="Send even if the status text is unchanged.")
    args = parser.parse_args()

    url, key, token, chat_id = config()
    strategies = get_strategies(url, key)
    setup = get_setup_state(url, key)
    message = render(strategies, setup)
    message_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()

    if not args.force and load_last_hash() == message_hash:
        print("SKIP | strategy status unchanged")
        return

    send(token, chat_id, message)
    save_hash(message_hash)
    print(f"SENT | strategies={len(strategies)} | chat_id={chat_id}")


if __name__ == "__main__":
    main()
