import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from intraday_mtf_engine import config, headers, load_timeframes, load_vcpr_levels
from intraday_strategy_suite_core import (
    STRATEGY_IDS,
    evaluate_compression_expansion,
    evaluate_liquidity_sweep,
    evaluate_session_break_retest,
)

BASE_DIR = Path(r"E:\xauusd")
SYMBOL = "XAUUSD"
STATE_FILE = BASE_DIR / "data" / "forward" / "intraday_strategy_suite_notify_state.json"


def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(payload):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def fmt(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def telegram_post(token, chat_id, text):
    if not token or not chat_id:
        return False
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text},
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Telegram HTTP {response.status_code}: {response.text[:300]}")
    return True


def patch_runtime(url, key, strategy_id, result, source_meta):
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        **result,
        "source": "ALPARI_MT4_HST+SUPABASE_LIVE",
        "source_meta": source_meta,
        "paper_only": True,
    }
    response = requests.patch(
        f"{url}/rest/v1/strategy_registry",
        headers=headers(key, "return=minimal"),
        params={"strategy_id": f"eq.{strategy_id}"},
        json={
            "runtime_status": result.get("state") or "UNKNOWN",
            "runtime_payload": payload,
            "runtime_updated_at": now,
            "updated_at": now,
        },
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(
            f"Runtime PATCH {strategy_id} HTTP {response.status_code}: {response.text[:300]}"
        )


def insert_signal(url, key, strategy_id, result):
    if result.get("state") != "SIGNAL" or not result.get("direction"):
        return None

    plan = result.get("risk_plan") or {}
    vcpr = result.get("vcpr") or {}
    signal_time = result.get("signal_time_utc")
    event_key = f"{strategy_id}|{result['direction']}|{signal_time}"

    row = {
        "event_key": event_key,
        "strategy_id": strategy_id,
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
            "strategy_name": result.get("strategy_name"),
            "reason": result.get("reason"),
            "vcpr": vcpr,
            "checks": result.get("checks"),
            "risk": plan.get("risk"),
            "paper_only": True,
            "source": "ALPARI_MT4_HST+SUPABASE_LIVE",
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
        raise RuntimeError(
            f"Signal insert {strategy_id} HTTP {response.status_code}: {response.text[:300]}"
        )

    created = response.json()
    return created[0] if created else None


def setup_message(result):
    checks = result.get("checks") or {}
    name = result.get("strategy_name") or "XAUUSD Strategy"
    lines = [
        "XAUUSD SETUP FORMING",
        "",
        f"Strategy: {name}",
        f"Direction: {result.get('direction') or 'WAIT'}",
        f"Setup score: {result.get('score', 0)}/10",
        f"Price: {fmt(result.get('price'))}",
        f"Reason: {result.get('reason') or 'Setup conditions are forming.'}",
    ]

    if "sweep_found" in checks:
        lines.extend([
            f"Sweep/reclaim: {'READY' if checks.get('sweep_found') else 'WAITING'}",
            f"M5 confirmation: {'READY' if checks.get('m5_confirmation') else 'WAITING'}",
        ])
    if "breakout_found" in checks:
        lines.extend([
            f"Asia breakout: {'READY' if checks.get('breakout_found') else 'WAITING'}",
            f"Retest: {'READY' if checks.get('retest') else 'WAITING'}",
        ])
    if "compressed" in checks:
        lines.extend([
            f"M15 compression: {'READY' if checks.get('compressed') else 'WAITING'}",
            f"M5 expansion: {'READY' if checks.get('m5_expansion') else 'WAITING'}",
        ])

    lines.extend(["", "Paper/demo research only. No trade has been placed."])
    return "\n".join(lines)


def signal_message(result):
    plan = result.get("risk_plan") or {}
    return "\n".join([
        "XAUUSD PAPER TEST SIGNAL",
        "",
        f"Strategy: {result.get('strategy_name')}",
        f"Direction: {result.get('direction')}",
        f"Score: {result.get('score')}/10",
        f"Entry: {fmt(plan.get('entry'))}",
        f"Stop: {fmt(plan.get('stop'))}",
        f"T1: {fmt(plan.get('target1'))}",
        f"T2: {fmt(plan.get('target2'))}",
        f"Reason: {result.get('reason')}",
        "",
        "Paper/demo research only. No live order was placed.",
    ])


def ended_message(name, previous_direction, result):
    return "\n".join([
        "XAUUSD SETUP ENDED - NO TRADE",
        "",
        f"Strategy: {name}",
        f"Previous direction: {previous_direction or '—'}",
        f"Current state: {str(result.get('state') or 'WAITING').replace('_', ' ')}",
        f"Reason: {result.get('reason') or 'Setup conditions are no longer complete.'}",
        "",
        "No paper trade was recorded.",
    ])


def notify_state_change(token, chat_id, strategy_id, result, enabled=True):
    state = load_state()
    prev = state.get(strategy_id, {})
    previous_state = prev.get("state")
    previous_direction = prev.get("direction")
    current_state = str(result.get("state") or "UNKNOWN")
    current_direction = result.get("direction")
    sent = None

    if enabled:
        if current_state == "SETUP" and previous_state != "SETUP":
            if telegram_post(token, chat_id, setup_message(result)):
                sent = "SETUP"
        elif previous_state == "SETUP" and current_state not in ("SETUP", "SIGNAL"):
            if telegram_post(
                token, chat_id,
                ended_message(result.get("strategy_name") or strategy_id, previous_direction, result),
            ):
                sent = "ENDED"

    state[strategy_id] = {
        "state": current_state,
        "direction": current_direction,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_state(state)
    return sent


def one_cycle(url, key, token, chat_id, telegram_enabled=True):
    series, source_meta = load_timeframes(url, key, max_rows=800)
    levels = load_vcpr_levels(url, key)

    latest_m5 = series["M5"][-1]
    latest_close_utc = latest_m5["utc_dt"] + timedelta(minutes=5)
    feed_age = (datetime.now(timezone.utc) - latest_close_utc).total_seconds() / 60.0

    if feed_age > 20:
        stale = {
            "strategy_name": "Data Safety",
            "state": "DATA_STALE",
            "direction": None,
            "score": 0,
            "reason": f"Latest closed M5 feed is {feed_age:.1f} minutes old; signals suppressed.",
            "price": latest_m5.get("close"),
        }
        results = {strategy_id: dict(stale) for strategy_id in STRATEGY_IDS.values()}
    else:
        results = {
            STRATEGY_IDS["liquidity"]: evaluate_liquidity_sweep(
                series["M5"], series["H1"], levels
            ),
            STRATEGY_IDS["session"]: evaluate_session_break_retest(
                series["M5"], series["H1"], levels
            ),
            STRATEGY_IDS["compression"]: evaluate_compression_expansion(
                series["M5"], series["M15"], series["H1"], series["H4"], levels
            ),
        }

    source_meta["feed_age_minutes"] = round(feed_age, 2)
    source_meta["latest_m5_close_utc"] = latest_close_utc.isoformat()

    summaries = []
    for strategy_id, result in results.items():
        patch_runtime(url, key, strategy_id, result, source_meta)
        setup_tg = notify_state_change(
            token, chat_id, strategy_id, result, enabled=telegram_enabled
        )
        created = insert_signal(url, key, strategy_id, result)
        signal_tg = False
        if created and telegram_enabled:
            signal_tg = telegram_post(token, chat_id, signal_message(result))

        summaries.append(
            f"{strategy_id}={result.get('state')} "
            f"{result.get('direction') or '-'} score={result.get('score', 0)} "
            f"signal={'YES' if created else 'NO'} "
            f"tg={setup_tg or ('SIGNAL' if signal_tg else 'NO')}"
        )

    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] SUITE OK | "
        + " | ".join(summaries),
        flush=True,
    )
    return results


def main():
    parser = argparse.ArgumentParser(description="XAUUSD additional intraday paper strategy suite")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll", type=int, default=15)
    parser.add_argument("--no-telegram", action="store_true")
    args = parser.parse_args()

    url, key, token, chat_id = config()
    print(
        "Intraday strategy suite starting | "
        "Liquidity Sweep + Session Break/Retest + Compression Expansion | PAPER",
        flush=True,
    )

    while True:
        try:
            one_cycle(
                url, key, token, chat_id,
                telegram_enabled=not args.no_telegram,
            )
        except Exception as exc:
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"SUITE ERROR | {type(exc).__name__}: {exc}",
                flush=True,
            )
            if args.once:
                raise

        if args.once:
            break
        time.sleep(max(5, args.poll))


if __name__ == "__main__":
    main()
