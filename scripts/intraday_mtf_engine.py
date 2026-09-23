import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from intraday_mtf_core import PERIODS, closed_rows, enrich_bars, evaluate_strategy, find_hst, load_env_file, parse_hst

BASE_DIR = Path(r"E:\xauusd")
ENV_FILE = BASE_DIR / "bridge" / ".env"
STRATEGY_ID = "INTRADAY_MTF_V1"
SYMBOL = "XAUUSD"


def config():
    load_env_file(ENV_FILE)
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
        raise RuntimeError("Supabase URL/key missing from bridge .env")
    return url, key, token, chat_id


def headers(key, prefer=None):
    out = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        out["Prefer"] = prefer
    return out


def load_vcpr_levels(url, key):
    response = requests.get(
        f"{url}/rest/v1/vcpr_history",
        headers=headers(key),
        params={
            "select": "origin_date,pivot,cpr_low,cpr_high,source,later_touched,validation_status,virgin_on_day",
            "symbol": f"eq.{SYMBOL}",
            "virgin_on_day": "eq.true",
            "order": "origin_date.asc",
            "limit": "500",
        },
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"VCPR fetch HTTP {response.status_code}: {response.text[:300]}")
    return response.json()


def load_timeframes(max_rows=420):
    result = {}
    meta = {}
    for name, period in PERIODS.items():
        path = find_hst(period, SYMBOL)
        parsed = parse_hst(path, period, max_rows=max_rows)
        rows = closed_rows(parsed)
        result[name] = enrich_bars(rows)
        meta[name] = {
            "path": parsed["path"],
            "rows": len(rows),
            "last_closed_open_broker": rows[-1]["broker_dt"].isoformat() if rows else None,
        }
    return result, meta


def patch_runtime(url, key, result, source_meta):
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "state": result.get("state"),
        "direction": result.get("direction"),
        "score": result.get("score"),
        "reason": result.get("reason"),
        "signal_time_utc": result.get("signal_time_utc"),
        "signal_time_broker": result.get("signal_time_broker"),
        "price": result.get("price"),
        "risk_plan": result.get("risk_plan"),
        "vcpr": result.get("vcpr"),
        "checks": result.get("checks"),
        "ma": result.get("ma"),
        "bars": result.get("bars"),
        "timeframes_ready": result.get("timeframes_ready"),
        "source": "ALPARI_MT4_HST",
        "source_meta": source_meta,
        "paper_only": True,
    }

    response = requests.patch(
        f"{url}/rest/v1/strategy_registry",
        headers=headers(key, "return=minimal"),
        params={"strategy_id": f"eq.{STRATEGY_ID}"},
        json={
            "runtime_status": result.get("state") or "UNKNOWN",
            "runtime_payload": payload,
            "runtime_updated_at": now,
            "updated_at": now,
        },
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Runtime PATCH HTTP {response.status_code}: {response.text[:300]}")


def insert_signal(url, key, result):
    if result.get("state") != "SIGNAL" or not result.get("direction"):
        return None

    plan = result.get("risk_plan") or {}
    vcpr = result.get("vcpr") or {}
    signal_time = result.get("signal_time_utc")
    event_key = f"{STRATEGY_ID}|{result['direction']}|{signal_time}"

    row = {
        "event_key": event_key,
        "strategy_id": STRATEGY_ID,
        "symbol": SYMBOL,
        "direction": result["direction"],
        "state": "SIGNAL",
        "signal_time": signal_time,
        "broker_time": result.get("signal_time_broker"),
        "entry_price": plan.get("entry"),
        "stop_price": plan.get("stop"),
        "target1_price": plan.get("target1"),
        "target2_price": plan.get("target2"),
        "score": result.get("score"),
        "vcpr_pivot": vcpr.get("nearest_pivot"),
        "payload": {
            "reason": result.get("reason"),
            "vcpr": vcpr,
            "checks": result.get("checks"),
            "ma": result.get("ma"),
            "bars": result.get("bars"),
            "risk": plan.get("risk"),
            "paper_only": True,
            "source": "ALPARI_MT4_HST",
        },
    }

    response = requests.post(
        f"{url}/rest/v1/strategy_signals",
        headers=headers(key, "resolution=ignore-duplicates,return=representation"),
        params={"on_conflict": "event_key"},
        json=row,
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Signal insert HTTP {response.status_code}: {response.text[:300]}")

    created = response.json()
    return created[0] if created else None


def fmt(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def send_telegram(token, chat_id, result):
    if not token or not chat_id:
        return False

    plan = result.get("risk_plan") or {}
    vcpr = result.get("vcpr") or {}
    direction = result.get("direction")
    lines = [
        "XAUUSD PAPER TEST SIGNAL",
        "",
        f"Strategy: Multi-Timeframe Trend Pullback V1",
        f"Direction: {direction}",
        f"Score: {result.get('score')}/10",
        f"Entry: {fmt(plan.get('entry'))}",
        f"Stop: {fmt(plan.get('stop'))}",
        f"T1: {fmt(plan.get('target1'))}",
        f"T2: {fmt(plan.get('target2'))}",
        f"VCPR: {vcpr.get('context', '—')} @ {fmt(vcpr.get('nearest_pivot'))}",
        f"Broker time: {result.get('signal_time_broker')}",
        "",
        "Paper/demo research only. No live order was placed.",
    ]

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": "\n".join(lines)},
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Telegram HTTP {response.status_code}: {response.text[:300]}")
    return True


def one_cycle(url, key, token, chat_id, telegram_enabled=True):
    series, source_meta = load_timeframes()
    levels = load_vcpr_levels(url, key)

    result = evaluate_strategy(
        series["M5"],
        series["M15"],
        series["H1"],
        series["H4"],
        levels,
    )

    patch_runtime(url, key, result, source_meta)
    created = insert_signal(url, key, result)
    telegram_sent = False
    if created and telegram_enabled:
        telegram_sent = send_telegram(token, chat_id, result)

    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
        f"STATE={result.get('state')} | DIR={result.get('direction') or '-'} | "
        f"SCORE={result.get('score', 0)} | PRICE={fmt(result.get('price'))} | "
        f"VCPR={(result.get('vcpr') or {}).get('context', '-')} | "
        f"NEW_SIGNAL={'YES' if created else 'NO'} | TG={'SENT' if telegram_sent else 'NO'}",
        flush=True,
    )
    print(f"REASON | {result.get('reason')}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description="XAUUSD MTF intraday paper signal engine")
    parser.add_argument("--once", action="store_true", help="Run one evaluation and exit")
    parser.add_argument("--poll", type=int, default=15, help="Loop interval in seconds")
    parser.add_argument("--no-telegram", action="store_true", help="Do not publish new paper signals to Telegram")
    args = parser.parse_args()

    url, key, token, chat_id = config()
    print(
        f"Intraday MTF engine starting | strategy={STRATEGY_ID} | "
        f"mode=PAPER | poll={max(5, args.poll)}s",
        flush=True,
    )

    while True:
        try:
            one_cycle(url, key, token, chat_id, telegram_enabled=not args.no_telegram)
        except Exception as exc:
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"ERROR | {type(exc).__name__}: {exc}",
                flush=True,
            )
            if args.once:
                raise

        if args.once:
            break
        time.sleep(max(5, args.poll))


if __name__ == "__main__":
    main()
