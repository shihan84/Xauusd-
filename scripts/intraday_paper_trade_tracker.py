import argparse
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from intraday_mtf_core import BROKER_TZ, load_env_file

BASE_DIR = Path(r"E:\xauusd")
ENV_FILE = BASE_DIR / "bridge" / ".env"
TRACKED_STRATEGIES = (
    "INTRADAY_MTF_V1",
    "LIQUIDITY_SWEEP_REVERSAL_V1",
    "SESSION_BREAK_RETEST_V1",
    "COMPRESSION_EXPANSION_V1",
)
STRATEGY_NAMES = {
    "INTRADAY_MTF_V1": "Multi-Timeframe Trend Pullback V1",
    "LIQUIDITY_SWEEP_REVERSAL_V1": "Liquidity Sweep + Reversal V1",
    "SESSION_BREAK_RETEST_V1": "Asia Range Break + Retest V1",
    "COMPRESSION_EXPANSION_V1": "MA Compression → Expansion V1",
}
SYMBOL = "XAUUSD"
POLL_SECONDS = 15


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


def broker_raw_from_iso(value):
    dt = datetime.fromisoformat(value)
    naive = dt.replace(tzinfo=None)
    return int(naive.replace(tzinfo=timezone.utc).timestamp())


def raw_to_times(raw_ts):
    broker_naive = datetime.fromtimestamp(int(raw_ts), timezone.utc).replace(tzinfo=None)
    broker_dt = broker_naive.replace(tzinfo=BROKER_TZ)
    return broker_dt, broker_dt.astimezone(timezone.utc)


def fetch_candidates(url, key):
    response = requests.get(
        f"{url}/rest/v1/strategy_signals",
        headers=headers(key),
        params={
            "select": (
                "id,event_key,strategy_id,direction,signal_time,broker_time,entry_price,stop_price,"
                "target1_price,target2_price,paper_status,outcome_1r,outcome_2r,"
                "t1_hit_at,t2_hit_at,stop_hit_at,mfe_r,mae_r,payload"
            ),
            "strategy_id": "in.(" + ",".join(TRACKED_STRATEGIES) + ")",
            "order": "signal_time.desc",
            "limit": "100",
        },
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Signal fetch HTTP {response.status_code}: {response.text[:300]}")
    return response.json()


def fetch_m5(url, key, start_raw):
    response = requests.get(
        f"{url}/rest/v1/market_candles",
        headers=headers(key),
        params={
            "select": "open_time,open,high,low,close",
            "symbol": f"eq.{SYMBOL}",
            "timeframe": "eq.M5",
            "is_closed": "eq.true",
            "open_time": f"gte.{start_raw}",
            "order": "open_time.asc",
            "limit": "1000",
        },
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"M5 fetch HTTP {response.status_code}: {response.text[:300]}")

    rows = []
    for row in response.json():
        broker_dt, utc_dt = raw_to_times(row["open_time"])
        rows.append({
            "broker_dt": broker_dt,
            "utc_dt": utc_dt,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        })
    return rows


def first_hit(direction, bars, stop, target):
    for bar in bars:
        if direction == "BUY":
            stop_hit = bar["low"] <= stop
            target_hit = bar["high"] >= target
        else:
            stop_hit = bar["high"] >= stop
            target_hit = bar["low"] <= target

        close_time = bar["utc_dt"]
        if stop_hit and target_hit:
            return "AMBIGUOUS", close_time
        if target_hit:
            return "WIN", close_time
        if stop_hit:
            return "STOP", close_time

    return None, None


def lifecycle_status(out1, out2):
    if out1 == "AMBIGUOUS" or out2 == "AMBIGUOUS":
        return "AMBIGUOUS"
    if out2 == "WIN":
        return "T2_HIT"
    if out1 == "STOP":
        return "STOPPED"
    if out1 == "WIN" and out2 == "STOP":
        return "T1_HIT_THEN_STOP"
    if out1 == "WIN":
        return "T1_HIT"
    if out1 == "EXPIRED":
        return "EXPIRED"
    return "ACTIVE"


def is_terminal(status, out1, out2):
    if status in ("T2_HIT", "STOPPED", "T1_HIT_THEN_STOP", "EXPIRED", "AMBIGUOUS"):
        return True
    return out1 is not None and out2 is not None


def fmt(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def patch_signal(url, key, signal_id, payload):
    response = requests.patch(
        f"{url}/rest/v1/strategy_signals",
        headers=headers(key, "return=minimal"),
        params={"id": f"eq.{signal_id}"},
        json=payload,
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Signal update HTTP {response.status_code}: {response.text[:300]}")


def send_telegram(token, chat_id, signal, new_status, out1, out2, mfe_r, mae_r):
    if not token or not chat_id or new_status == "ACTIVE":
        return False

    lines = [
        "XAUUSD PAPER TRADE UPDATE",
        "",
        f"Strategy: {STRATEGY_NAMES.get(signal.get('strategy_id'), signal.get('strategy_id') or 'XAUUSD Paper Strategy')}",
        f"Direction: {signal['direction']}",
        f"Status: {new_status.replace('_', ' ')}",
        f"Entry: {fmt(signal['entry_price'])}",
        f"Stop: {fmt(signal['stop_price'])}",
        f"T1: {fmt(signal['target1_price'])}",
        f"T2: {fmt(signal['target2_price'])}",
        f"1R outcome: {out1 or 'OPEN'}",
        f"2R outcome: {out2 or 'OPEN'}",
        f"MFE: {mfe_r:.2f}R | MAE: {mae_r:.2f}R",
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


def evaluate_signal(url, key, token, chat_id, signal, telegram_enabled=True):
    old_status = signal.get("paper_status") or "ACTIVE"
    old1 = signal.get("outcome_1r")
    old2 = signal.get("outcome_2r")

    if is_terminal(old_status, old1, old2):
        return False, old_status

    broker_time = signal.get("broker_time")
    if not broker_time:
        raise RuntimeError(f"Signal {signal['id']} missing broker_time")

    start_raw = broker_raw_from_iso(broker_time)
    bars = fetch_m5(url, key, start_raw)

    signal_broker = datetime.fromisoformat(broker_time)
    signal_date = signal_broker.date()
    same_day = [b for b in bars if b["broker_dt"].date() == signal_date]

    direction = signal["direction"]
    entry = float(signal["entry_price"])
    stop = float(signal["stop_price"])
    t1 = float(signal["target1_price"])
    t2 = float(signal["target2_price"])
    risk = abs(entry - stop)
    if risk <= 0:
        raise RuntimeError(f"Signal {signal['id']} has invalid risk")

    mfe = 0.0
    mae = 0.0
    for bar in same_day:
        if direction == "BUY":
            mfe = max(mfe, bar["high"] - entry)
            mae = max(mae, entry - bar["low"])
        else:
            mfe = max(mfe, entry - bar["low"])
            mae = max(mae, bar["high"] - entry)

    mfe_r = max(float(signal.get("mfe_r") or 0.0), mfe / risk)
    mae_r = max(float(signal.get("mae_r") or 0.0), mae / risk)

    out1, t1_event = (old1, None)
    out2, t2_event = (old2, None)

    if old1 is None:
        out1, t1_event = first_hit(direction, same_day, stop, t1)
    if old2 is None:
        out2, t2_event = first_hit(direction, same_day, stop, t2)

    now_broker = datetime.now(timezone.utc).astimezone(BROKER_TZ)
    if now_broker.date() > signal_date:
        if out1 is None:
            out1 = "EXPIRED"
        if out2 is None:
            out2 = "EXPIRED"

    new_status = lifecycle_status(out1, out2)
    now_iso = datetime.now(timezone.utc).isoformat()

    stop_event = None
    if out1 == "STOP" and t1_event:
        stop_event = t1_event
    elif out2 == "STOP" and t2_event:
        stop_event = t2_event

    payload = {
        "paper_status": new_status,
        "outcome_1r": out1,
        "outcome_2r": out2,
        "mfe_r": round(mfe_r, 6),
        "mae_r": round(mae_r, 6),
        "last_evaluated_at": now_iso,
    }

    if out1 == "WIN" and t1_event and not signal.get("t1_hit_at"):
        payload["t1_hit_at"] = t1_event.isoformat()
    if out2 == "WIN" and t2_event and not signal.get("t2_hit_at"):
        payload["t2_hit_at"] = t2_event.isoformat()
    if stop_event and not signal.get("stop_hit_at"):
        payload["stop_hit_at"] = stop_event.isoformat()

    if is_terminal(new_status, out1, out2):
        terminal_times = [x for x in (t1_event, t2_event, stop_event) if x is not None]
        payload["closed_at"] = (
            max(terminal_times).isoformat() if terminal_times else now_iso
        )

    changed = new_status != old_status or out1 != old1 or out2 != old2
    patch_signal(url, key, signal["id"], payload)

    telegram_sent = False
    if changed and telegram_enabled and new_status != old_status:
        telegram_sent = send_telegram(
            token, chat_id, signal, new_status, out1, out2, mfe_r, mae_r
        )

    return changed, new_status, telegram_sent


def one_cycle(url, key, token, chat_id, telegram_enabled=True):
    signals = fetch_candidates(url, key)
    active = 0
    changed = 0
    sent = 0

    for signal in reversed(signals):
        if is_terminal(
            signal.get("paper_status") or "ACTIVE",
            signal.get("outcome_1r"),
            signal.get("outcome_2r"),
        ):
            continue

        active += 1
        result = evaluate_signal(
            url, key, token, chat_id, signal, telegram_enabled=telegram_enabled
        )
        if result[0]:
            changed += 1
        if len(result) > 2 and result[2]:
            sent += 1

    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
        f"TRACK OK | active={active} | changed={changed} | telegram={sent}",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description="Track paper outcomes for INTRADAY_MTF_V1 signals")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll", type=int, default=POLL_SECONDS)
    parser.add_argument("--no-telegram", action="store_true")
    args = parser.parse_args()

    url, key, token, chat_id = config()
    print(
        f"Intraday paper trade tracker starting | strategies={len(TRACKED_STRATEGIES)} | "
        f"poll={max(5, args.poll)}s",
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
                f"TRACK ERROR | {type(exc).__name__}: {exc}",
                flush=True,
            )
            if args.once:
                raise

        if args.once:
            break
        time.sleep(max(5, args.poll))


if __name__ == "__main__":
    main()
