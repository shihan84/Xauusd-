import csv
import os
import time
from pathlib import Path

import requests

BASE_DIR = Path(r"E:\xauusd")
BRIDGE_ENV = BASE_DIR / "bridge" / ".env"
REACTIONS_CSV = BASE_DIR / "data" / "forward" / "vcpr_level_reactions.csv"
POLL_SECONDS = 30

FIELDS = [
    "reaction_id","symbol","origin_date","pivot","source","vcpr_status","approach_side",
    "touch_started_at_utc","touch_price","touch_count","min_price","max_price",
    "same_side_excursion","opposite_side_excursion","exit_time_utc","exit_price",
    "duration_seconds","outcome","touch_distance","reset_distance",
]


def log(message):
    from datetime import datetime
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


def get_config():
    load_env_file(BRIDGE_ENV)
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )
    if not url or not key:
        raise RuntimeError("Supabase URL/key missing")
    return url.rstrip("/"), key.strip()


def read_rows():
    if not REACTIONS_CSV.exists() or REACTIONS_CSV.stat().st_size == 0:
        return []
    with REACTIONS_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        out = []
        for row in csv.DictReader(handle):
            if not row.get("reaction_id"):
                continue
            out.append({field: row.get(field) for field in FIELDS})
        return out


def normalize(row):
    numeric = {
        "pivot": float,
        "touch_price": float,
        "touch_count": int,
        "min_price": float,
        "max_price": float,
        "same_side_excursion": float,
        "opposite_side_excursion": float,
        "exit_price": float,
        "duration_seconds": int,
        "touch_distance": float,
        "reset_distance": float,
    }
    result = dict(row)
    for key, cast in numeric.items():
        value = result.get(key)
        if value not in (None, ""):
            result[key] = cast(float(value)) if cast is int else cast(value)
    return result


def upsert(rows):
    if not rows:
        return 0
    url, key = get_config()
    response = requests.post(
        f"{url}/rest/v1/vcpr_level_reactions",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        params={"on_conflict": "reaction_id"},
        json=[normalize(row) for row in rows],
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"Supabase sync HTTP {response.status_code}: {response.text[:500]}")
    return len(rows)


def sync_once():
    rows = read_rows()
    count = upsert(rows)
    log(f"SYNC OK | local_reactions={len(rows)} | upserted={count}")
    return count


def main():
    log(f"VCPR reaction sync starting | poll={POLL_SECONDS}s | source={REACTIONS_CSV}")
    while True:
        try:
            sync_once()
        except KeyboardInterrupt:
            log("Stopped by user")
            break
        except Exception as exc:
            log(f"SYNC ERROR | {type(exc).__name__}: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
