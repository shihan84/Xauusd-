import argparse
import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


BASE_DIR = Path(r"E:\xauusd")
DEFAULT_CSV = BASE_DIR / "data" / "historical" / "XAUUSD_VCPR_RESULTS_V3_FINAL.csv"
BRIDGE_ENV = BASE_DIR / "bridge" / ".env"

SYMBOL = "XAUUSD"
SOURCE = "V3_RESEARCH"
VALIDATION_STATUS = "M5_VALIDATED"
BATCH_SIZE = 100


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


def get_supabase_config() -> tuple[str, str]:
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


def headers(key: str, prefer: str | None = None) -> dict[str, str]:
    result = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        result["Prefer"] = prefer
    return result


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def parse_float(value: Any) -> float | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def parse_time_epoch(value: Any) -> int | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        # V3 timestamps already carry the broker UTC offset (+02:00/+03:00),
        # so converting the aware timestamp to epoch preserves the true instant.
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return None
        return int(dt.timestamp())
    except ValueError:
        return None


def synthetic_key(origin_date: str) -> int:
    # Keep imported research rows in a collision-free namespace. Native MT4 rows
    # use positive Unix timestamps; V3 research rows use negative YYYYMMDD keys.
    return -int(origin_date.replace("-", ""))


def fetch_authoritative_dates(url: str, key: str) -> set[str]:
    response = requests.get(
        f"{url}/rest/v1/vcpr_history",
        headers=headers(key),
        params={
            "select": "origin_date,source,validation_status",
            "symbol": f"eq.{SYMBOL}",
            "source": "eq.MT4",
            "validation_status": "eq.M5_VALIDATED",
            "limit": "1000",
        },
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(
            f"Could not read authoritative VCPRs: HTTP {response.status_code}: {response.text[:400]}"
        )
    return {str(row["origin_date"]) for row in response.json() if row.get("origin_date")}


def load_v3_rows(path: Path, authoritative_dates: set[str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not path.exists():
        raise FileNotFoundError(f"V3 CSV not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    payload: list[dict[str, Any]] = []
    stats = {
        "csv_rows": len(rows),
        "vcpr_rows": 0,
        "skipped_authoritative": 0,
        "revisited": 0,
        "unresolved": 0,
    }

    for index, row in enumerate(rows):
        if not parse_bool(row.get("is_vcpr")):
            continue

        stats["vcpr_rows"] += 1
        origin_date = str(row.get("broker_date") or "").strip()
        if not origin_date:
            continue

        # Alpari/MT4 broker-validated rows win for overlapping dates.
        if origin_date in authoritative_dates:
            stats["skipped_authoritative"] += 1
            continue

        pp = parse_float(row.get("pp"))
        cpr_low = parse_float(row.get("cpr_low"))
        cpr_high = parse_float(row.get("cpr_high"))
        if pp is None or cpr_low is None or cpr_high is None:
            continue

        revisited = parse_bool(row.get("revisited"))
        if revisited:
            stats["revisited"] += 1
        else:
            stats["unresolved"] += 1

        previous_date = origin_date
        if index > 0:
            previous_date = str(rows[index - 1].get("broker_date") or origin_date).strip()

        payload.append(
            {
                "symbol": SYMBOL,
                "origin_open_time": synthetic_key(origin_date),
                "origin_date": origin_date,
                "previous_open_time": synthetic_key(previous_date),
                "pivot": pp,
                "cpr_low": cpr_low,
                "cpr_high": cpr_high,
                "origin_day_touched": False,
                "virgin_on_day": True,
                "validation_status": VALIDATION_STATUS,
                "m5_first_time": parse_time_epoch(row.get("first_bar")),
                "m5_last_time": parse_time_epoch(row.get("last_bar")),
                "later_touched": revisited,
                "first_later_touch": parse_time_epoch(row.get("first_revisit_time")),
                "source": SOURCE,
                "scanned_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    return payload, stats


def upsert_rows(url: str, key: str, rows: list[dict[str, Any]]) -> None:
    endpoint = f"{url}/rest/v1/vcpr_history"
    total = len(rows)
    for start in range(0, total, BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        response = requests.post(
            endpoint,
            headers=headers(key, "resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "symbol,origin_open_time"},
            json=batch,
            timeout=45,
        )
        if not response.ok:
            raise RuntimeError(
                f"Upsert failed at rows {start + 1}-{start + len(batch)}: "
                f"HTTP {response.status_code}: {response.text[:600]}"
            )
        print(f"Imported {min(start + len(batch), total)}/{total}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import immutable V3-clean VCPR research levels into Supabase vcpr_history."
    )
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="Path to XAUUSD_VCPR_RESULTS_V3_FINAL.csv")
    parser.add_argument("--apply", action="store_true", help="Actually write rows. Without this flag the script is dry-run only.")
    args = parser.parse_args()

    url, key = get_supabase_config()
    authoritative_dates = fetch_authoritative_dates(url, key)
    rows, stats = load_v3_rows(Path(args.csv), authoritative_dates)

    print("XAUUSD V3 VCPR history import", flush=True)
    print(f"CSV rows: {stats['csv_rows']}", flush=True)
    print(f"VCPR rows in V3 baseline: {stats['vcpr_rows']}", flush=True)
    print(f"Existing MT4-authoritative dates: {len(authoritative_dates)}", flush=True)
    print(f"Skipped because MT4 authoritative exists: {stats['skipped_authoritative']}", flush=True)
    print(f"Research rows ready: {len(rows)}", flush=True)
    print(f"Research revisited: {stats['revisited']}", flush=True)
    print(f"Research unresolved: {stats['unresolved']}", flush=True)
    print(f"Source tag: {SOURCE}", flush=True)
    print(f"Validation tag: {VALIDATION_STATUS}", flush=True)

    if not args.apply:
        print("DRY RUN ONLY — no Supabase rows changed. Re-run with --apply after reviewing counts.", flush=True)
        return

    if not rows:
        print("Nothing to import.", flush=True)
        return

    upsert_rows(url, key, rows)
    print("IMPORT COMPLETE", flush=True)


if __name__ == "__main__":
    main()
