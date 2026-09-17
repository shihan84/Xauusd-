import csv
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(r"E:\xauusd")
BRIDGE_ENV = BASE_DIR / "bridge" / ".env"
STATE_FILE = BASE_DIR / "data" / "forward" / "vcpr_level_monitor_state.json"
REACTIONS_CSV = BASE_DIR / "data" / "forward" / "vcpr_level_reactions.csv"

SYMBOL = "XAUUSD"
POLL_SECONDS = 15
DEFAULT_APPROACH_DISTANCE = 3.0
DEFAULT_TOUCH_DISTANCE = 0.50
DEFAULT_RESET_DISTANCE = 8.0
TELEGRAM_TIMEOUT_SECONDS = 15

REACTION_FIELDS = [
    "reaction_id","symbol","origin_date","pivot","source","vcpr_status","approach_side",
    "touch_started_at_utc","touch_price","touch_count","min_price","max_price",
    "same_side_excursion","opposite_side_excursion","exit_time_utc","exit_price",
    "duration_seconds","outcome","touch_distance","reset_distance",
]

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()

def log(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)

def load_env_file(path):
    if not path.exists():
        raise FileNotFoundError(f"Bridge .env not found: {path}")
    with path.open("r", encoding="utf-8-sig") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")

def get_runtime_settings():
    load_env_file(BRIDGE_ENV)
    approach = float(os.getenv("VCPR_LEVEL_APPROACH_DISTANCE", str(DEFAULT_APPROACH_DISTANCE)))
    touch = float(os.getenv("VCPR_LEVEL_TOUCH_DISTANCE", str(DEFAULT_TOUCH_DISTANCE)))
    reset = float(os.getenv("VCPR_LEVEL_RESET_DISTANCE", str(DEFAULT_RESET_DISTANCE)))
    if touch <= 0 or approach <= 0 or reset <= 0:
        raise RuntimeError("VCPR level distances must be positive")
    if not (touch <= approach < reset):
        raise RuntimeError(f"Invalid VCPR thresholds: {touch:.2f} <= {approach:.2f} < {reset:.2f} required")
    return approach, touch, reset

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
    return supabase_url.rstrip("/"), supabase_key.strip(), telegram_token.strip(), telegram_chat_id.strip()

def supabase_get(table, params):
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

def telegram_send(message):
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

def load_state():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        return {"version": 2, "levels": {}}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        state["version"] = 2
        state.setdefault("levels", {})
        return state
    except Exception:
        return {"version": 2, "levels": {}}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    temp.replace(STATE_FILE)

def append_reaction(row):
    REACTIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
    exists = REACTIONS_CSV.exists() and REACTIONS_CSV.stat().st_size > 0
    with REACTIONS_CSV.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REACTION_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field) for field in REACTION_FIELDS})

def get_price():
    rows = supabase_get("market_latest", {"select":"bid,ask,received_at","symbol":f"eq.{SYMBOL}","limit":"1"})
    if not rows:
        raise RuntimeError("No market_latest row for XAUUSD")
    bid = float(rows[0]["bid"])
    if bid <= 0:
        raise RuntimeError("Invalid XAUUSD bid")
    return bid

def get_levels():
    rows = supabase_get(
        "vcpr_history",
        {
            "select":"origin_date,pivot,later_touched,first_later_touch,validation_status,virgin_on_day,source",
            "symbol":f"eq.{SYMBOL}",
            "virgin_on_day":"eq.true",
            "validation_status":"eq.M5_VALIDATED",
            "order":"origin_open_time.desc",
        },
    )
    levels = []
    for row in rows:
        try:
            pivot = float(row["pivot"])
        except (TypeError, ValueError, KeyError):
            continue
        source = str(row.get("source") or "UNKNOWN")
        levels.append({
            "origin_date": str(row.get("origin_date") or "unknown"),
            "pivot": pivot,
            "revisited": bool(row.get("later_touched")),
            "source": "ALPARI_MT4" if source == "MT4" else ("V3" if source == "V3_RESEARCH" else source),
        })
    return levels

def level_key(level):
    return f"{level['origin_date']}|{level['pivot']:.5f}"

def status_name(level):
    return "REVISITED" if level["revisited"] else "UNRESOLVED"

def price_side(price, pivot):
    return "BELOW" if price < pivot else "ABOVE"

def start_reaction(level, price, item, touch_distance):
    pivot = level["pivot"]
    prior_price = item.get("last_price")
    reference_price = float(prior_price) if prior_price is not None else price
    side = price_side(reference_price, pivot)
    item["reaction"] = {
        "reaction_id": uuid.uuid4().hex,
        "approach_side": side,
        "touch_started_at_utc": utc_now_iso(),
        "touch_started_epoch": time.time(),
        "touch_price": price,
        "touch_count": 1,
        "min_price": price,
        "max_price": price,
        "was_inside_touch": True,
        "touch_distance": touch_distance,
    }
    log(f"REACTION START | {level['origin_date']} | PP={pivot:.2f} | price={price:.2f} | from={side} | {status_name(level)} | {level['source']}")

def update_reaction(level, price, item, touch_distance, reset_distance):
    reaction = item.get("reaction")
    if not reaction:
        if abs(price - level["pivot"]) <= touch_distance:
            start_reaction(level, price, item, touch_distance)
        return

    pivot = level["pivot"]
    reaction["min_price"] = min(float(reaction.get("min_price", price)), price)
    reaction["max_price"] = max(float(reaction.get("max_price", price)), price)

    inside_touch = abs(price - pivot) <= touch_distance
    was_inside_touch = bool(reaction.get("was_inside_touch", False))
    if inside_touch and not was_inside_touch:
        reaction["touch_count"] = int(reaction.get("touch_count", 1)) + 1
        log(f"REACTION RETEST | {level['origin_date']} | PP={pivot:.2f} | price={price:.2f} | tests={reaction['touch_count']}")
    reaction["was_inside_touch"] = inside_touch

    if abs(price - pivot) < reset_distance:
        return

    approach_side = str(reaction.get("approach_side") or "BELOW")
    exit_side = price_side(price, pivot)
    outcome = "REJECTION" if exit_side == approach_side else "BREAKTHROUGH"

    min_price = float(reaction["min_price"])
    max_price = float(reaction["max_price"])
    if approach_side == "BELOW":
        same_side_excursion = max(0.0, pivot - min_price)
        opposite_side_excursion = max(0.0, max_price - pivot)
    else:
        same_side_excursion = max(0.0, max_price - pivot)
        opposite_side_excursion = max(0.0, pivot - min_price)

    start_epoch = float(reaction.get("touch_started_epoch") or time.time())
    duration_seconds = max(0, int(time.time() - start_epoch))

    row = {
        "reaction_id": reaction["reaction_id"],
        "symbol": SYMBOL,
        "origin_date": level["origin_date"],
        "pivot": f"{pivot:.5f}",
        "source": level["source"],
        "vcpr_status": status_name(level),
        "approach_side": approach_side,
        "touch_started_at_utc": reaction["touch_started_at_utc"],
        "touch_price": f"{float(reaction['touch_price']):.5f}",
        "touch_count": int(reaction.get("touch_count", 1)),
        "min_price": f"{min_price:.5f}",
        "max_price": f"{max_price:.5f}",
        "same_side_excursion": f"{same_side_excursion:.5f}",
        "opposite_side_excursion": f"{opposite_side_excursion:.5f}",
        "exit_time_utc": utc_now_iso(),
        "exit_price": f"{price:.5f}",
        "duration_seconds": duration_seconds,
        "outcome": outcome,
        "touch_distance": f"{touch_distance:.2f}",
        "reset_distance": f"{reset_distance:.2f}",
    }
    append_reaction(row)
    log(f"REACTION CLOSED | {level['origin_date']} | PP={pivot:.2f} | {outcome} | tests={row['touch_count']} | same={same_side_excursion:.2f} | opposite={opposite_side_excursion:.2f} | duration={duration_seconds}s")
    item["reaction"] = None

def process_level(level, price, state, approach_distance, touch_distance, reset_distance):
    key = level_key(level)
    item = state["levels"].setdefault(
        key,
        {"zone":"AWAY","last_price":None,"last_event":None,"last_event_at":None,"reaction":None},
    )
    item.setdefault("reaction", None)

    pivot = level["pivot"]
    distance = abs(price - pivot)
    previous_zone = item.get("zone", "AWAY")

    update_reaction(level, price, item, touch_distance, reset_distance)

    if distance <= touch_distance:
        zone = "TOUCH"
    elif distance <= approach_distance:
        zone = "APPROACH"
    elif distance >= reset_distance:
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
            f"Source: {level['source']}\n"
            f"Level is {side} current price\n"
            f"Distance: {distance:.2f}\n\n"
            f"Price is {direction} a permanent historical VCPR S/R reference.\n"
            "This is a level alert, not a fresh trade signal."
        )
        if telegram_send(message):
            log(f"{event} | {level['origin_date']} | PP={pivot:.2f} | price={price:.2f} | {status_name(level)} | {level['source']}")
            item["last_event"] = event
            item["last_event_at"] = utc_now_iso()

    item["zone"] = zone
    item["last_price"] = price

def main():
    approach_distance, touch_distance, reset_distance = get_runtime_settings()
    log("XAUUSD permanent VCPR level monitor starting")
    log(f"Approach={approach_distance:.2f} | Touch={touch_distance:.2f} | Reset={reset_distance:.2f} | Poll={POLL_SECONDS}s")
    log("Monitoring BOTH unresolved and previously revisited VCPR PP levels")
    log(f"Reaction tracking enabled -> {REACTIONS_CSV}")
    state = load_state()

    while True:
        try:
            price = get_price()
            levels = get_levels()
            active_reactions = 0
            for level in levels:
                process_level(level, price, state, approach_distance, touch_distance, reset_distance)
                item = state["levels"].get(level_key(level), {})
                if item.get("reaction"):
                    active_reactions += 1
            save_state(state)
            log(f"STATUS | price={price:.2f} | levels={len(levels)} | active_reactions={active_reactions}")
        except KeyboardInterrupt:
            save_state(state)
            log("Stopped by user")
            break
        except Exception as exc:
            log(f"ENGINE ERROR | {type(exc).__name__}: {exc}")
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
