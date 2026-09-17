import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


BASE_DIR = Path(r"E:\xauusd")
BRIDGE_ENV = BASE_DIR / "bridge" / ".env"
STATE_FILE = BASE_DIR / "data" / "forward" / "vcpr_level_monitor_state.json"

SYMBOL = "XAUUSD"
POLL_SECONDS = 15
APPROACH_DISTANCE = float(os.getenv("VCPR_LEVEL_APPROACH_DISTANCE", "3.0"))
TOUCH_DISTANCE = float(os.getenv("VCPR_LEVEL_TOUCH_DISTANCE", "0.50"))
RESET_DISTANCE = float(os.getenv("VCPR_LEVEL_RESET_DISTANCE", "8.0"))
TELEGRAM_TIMEOUT_SECONDS = 15


def log(message: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}", flush=True)


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Bridge .env not found: {path}")

    with path.open("r", encoding="utf-8-sig") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def get_config():
    load_env_file(BRIDGE_ENV)

    supabase_url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not supabase_url or not supabase_key:
        raise RuntimeError("Supabase URL/key missing")
    if not telegram_token or not telegram_chat_id:
        raise RuntimeError("Telegram token/chat id missing")

    return (
        supabase_url.rstrip("/"),
        supabase_key.strip(),
        telegram_token.strip(),
        telegram_chat_id.strip(),
    )


def supabase_get(table: str, params: dict):
    url, key, _, _ = get_config()
    response = requests.get(
        f"{url}/rest/v1/{table}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        params=params,
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Supabase {table} HTTP {response.status_code}: {response.text[:300]}")
    return response.json()


def telegram_send(message: str) -> bool:
    try:
        _, _, token, chat_id = get_config()
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": message},
            timeout=TELEGRAM_TIMEOUT_SECONDS,
        )
        if not response.ok:
            log(f"TELEGRAM ERROR HTTP {response.status_code}: {response.text[:250]}")
            return False
        return True
    except Exception as exc:
        log(f"TELEGRAM ERROR {type(exc).__name__}: {exc}")
        return False


def load_state() -> dict:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        return {"version": 1, "levels": {}}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        state.setdefault("version", 1)
        state.setdefault("levels", {})
        return state
    except Exception:
        return {"version": 1, "levels": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    temp.replace(STATE_FILE)


def get_price() -> float:
    rows = supabase_get(
        "market_latest",
        {
            "select": "bid,ask,received_at",
            "symbol": f"eq.{SYMBOL}",
            "limit": "1",
        },
    )
    if not rows:
        raise RuntimeError("No market_latest row for XAUUSD")
    bid = float(rows[0]["bid"])
    if bid <= 0:
        raise RuntimeError("Invalid XAUUSD bid")
    return bid


def get_levels() -> list[dict]:
    rows = supabase_get(
        "vcpr_history",
        {
            "select": "origin_date,pivot,later_touched,first_later_touch,validation_status,virgin_on_day",
            "symbol": f"eq.{SYMBOL}",
            "virgin_on_day": "eq.true",
            "validation_status": "eq.M5_VALIDATED",
            "order": "origin_open_time.desc",
        },
    )

    levels = []
    for row in rows:
        try:
            pivot = float(row["pivot"])
        except (TypeError, ValueError, KeyError):
            continue
        levels.append(
            {
                "origin_date": str(row.get("origin_date") or "unknown"),
                "pivot": pivot,
                "revisited": bool(row.get("later_touched")),
            }
        )
    return levels


def level_key(level: dict) -> str:
    return f"{level['origin_date']}|{level['pivot']:.5f}"


def status_name(level: dict) -> str:
    return "REVISITED" if level["revisited"] else "UNRESOLVED"


def process_level(level: dict, price: float, state: dict) -> None:
    key = level_key(level)
    item = state["levels"].setdefault(
        key,
        {
            "zone": "AWAY",
            "last_price": None,
            "last_event": None,
            "last_event_at": None,
        },
    )

    pivot = level["pivot"]
    distance = abs(price - pivot)
    previous_zone = item.get("zone", "AWAY")

    if distance <= TOUCH_DISTANCE:
        zone = "TOUCH"
    elif distance <= APPROACH_DISTANCE:
        zone = "APPROACH"
    elif distance >= RESET_DISTANCE:
        zone = "AWAY"
    else:
        zone = previous_zone

    event = None
    if zone == "TOUCH" and previous_zone != "TOUCH":
        event = "TOUCH"
    elif zone == "APPROACH" and previous_zone == "AWAY":
        event = "APPROACH"

    if event:
        side = "ABOVE" if pivot >= price else "BELOW"
        direction = "approaching" if event == "APPROACH" else "testing"
        message = (
            f"{'🔵' if level['revisited'] else '🟡'} XAUUSD VCPR LEVEL {event}\n\n"
            f"Price: {price:.2f}\n"
            f"VCPR PP: {pivot:.2f}\n"
            f"Origin: {level['origin_date']}\n"
            f"Status: {status_name(level)}\n"
            f"Level is {side} current price\n"
            f"Distance: {distance:.2f}\n\n"
            f"Price is {direction} a permanent historical VCPR S/R reference.\n"
            "This is a level alert, not a fresh trade signal."
        )
        if telegram_send(message):
            log(
                f"{event} | {level['origin_date']} | PP={pivot:.2f} | "
                f"price={price:.2f} | {status_name(level)}"
            )
            item["last_event"] = event
            item["last_event_at"] = datetime.now(timezone.utc).isoformat()

    item["zone"] = zone
    item["last_price"] = price


def main() -> None:
    log("XAUUSD permanent VCPR level monitor starting")
    log(
        f"Approach={APPROACH_DISTANCE:.2f} | Touch={TOUCH_DISTANCE:.2f} | "
        f"Reset={RESET_DISTANCE:.2f} | Poll={POLL_SECONDS}s"
    )
    log("Monitoring BOTH unresolved and previously revisited VCPR PP levels")

    state = load_state()

    while True:
        try:
            price = get_price()
            levels = get_levels()
            for level in levels:
                process_level(level, price, state)
            save_state(state)
            log(f"STATUS | price={price:.2f} | levels={len(levels)}")
        except KeyboardInterrupt:
            save_state(state)
            log("Stopped by user")
            break
        except Exception as exc:
            log(f"ENGINE ERROR | {type(exc).__name__}: {exc}")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
