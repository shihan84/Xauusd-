import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(r"E:\xauusd")
ENV_FILE = BASE_DIR / "bridge" / ".env"
FORWARD_STATE_FILE = BASE_DIR / "data" / "forward" / "vcpr_above_forward_state.json"
LOCAL_STATE_FILE = BASE_DIR / "data" / "forward" / "strategy_runtime_sync_state.json"

STRATEGY_ID = "VCPR_ABOVE_V1"
POLL_SECONDS = 15


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
    return url, key, token, chat_id


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp.replace(path)


def latest_candidate(state):
    candidates = state.get("candidates") or {}
    if not isinstance(candidates, dict) or not candidates:
        return None
    key = sorted(candidates.keys())[-1]
    value = candidates.get(key) or {}
    if not isinstance(value, dict):
        return None
    result = dict(value)
    result.setdefault("origin_date", key)
    return result


def runtime_snapshot(state):
    candidate = latest_candidate(state)
    signals = state.get("signals") or {}

    if candidate:
        status = str(candidate.get("status") or "WATCHING")
        payload = {
            "engine_version": state.get("version"),
            "forward_start_time": state.get("forward_start_time"),
            "last_completed_d1_date": state.get("last_completed_d1_date"),
            "candidate_origin_date": candidate.get("origin_date"),
            "pp": candidate.get("pp"),
            "cpr_low": candidate.get("cpr_low"),
            "cpr_high": candidate.get("cpr_high"),
            "origin_close": candidate.get("origin_close"),
            "atr14": candidate.get("atr14"),
            "arm_level": candidate.get("arm_level"),
            "monitor_from": candidate.get("monitor_from"),
            "arm_time": candidate.get("arm_time"),
            "trigger_time": candidate.get("trigger_time"),
            "entry_price": candidate.get("entry_price"),
            "stop_price": candidate.get("stop_price"),
            "target_price": candidate.get("target_price"),
            "exit_time": candidate.get("exit_time"),
            "exit_price": candidate.get("exit_price"),
            "result": candidate.get("result"),
            "result_atr": candidate.get("result_atr"),
            "signals_count": len(signals) if isinstance(signals, dict) else 0,
        }
    else:
        status = "WATCHING_NO_CANDIDATE"
        payload = {
            "engine_version": state.get("version"),
            "forward_start_time": state.get("forward_start_time"),
            "last_completed_d1_date": state.get("last_completed_d1_date"),
            "signals_count": len(signals) if isinstance(signals, dict) else 0,
        }

    return status, payload


def supabase_upsert(url, key, status, payload):
    now = datetime.now(timezone.utc).isoformat()
    response = requests.patch(
        f"{url}/rest/v1/strategy_registry",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        params={"strategy_id": f"eq.{STRATEGY_ID}"},
        json={
            "runtime_status": status,
            "runtime_payload": payload,
            "runtime_updated_at": now,
            "updated_at": now,
        },
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Supabase strategy_registry HTTP {response.status_code}: {response.text[:300]}")


def state_hash(status, payload):
    meaningful = {
        "status": status,
        "candidate_origin_date": payload.get("candidate_origin_date"),
        "pp": payload.get("pp"),
        "arm_level": payload.get("arm_level"),
        "arm_time": payload.get("arm_time"),
        "trigger_time": payload.get("trigger_time"),
        "entry_price": payload.get("entry_price"),
        "stop_price": payload.get("stop_price"),
        "target_price": payload.get("target_price"),
        "exit_time": payload.get("exit_time"),
        "exit_price": payload.get("exit_price"),
        "result": payload.get("result"),
        "result_atr": payload.get("result_atr"),
        "signals_count": payload.get("signals_count"),
    }
    encoded = json.dumps(meaningful, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def fmt_number(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def telegram_message(status, payload):
    pretty_status = status.replace("_", " ")
    lines = [
        "XAUUSD STRATEGY STATE CHANGE",
        "",
        "VCPR ABOVE Continuation V1",
        f"State: {pretty_status}",
    ]
    if payload.get("candidate_origin_date"):
        lines.append(f"Origin: {payload.get('candidate_origin_date')}")
    if payload.get("pp") is not None:
        lines.append(f"VCPR PP: {fmt_number(payload.get('pp'))}")
    if payload.get("arm_level") is not None:
        lines.append(f"Arm level: {fmt_number(payload.get('arm_level'))}")
    if payload.get("entry_price") is not None:
        lines.append(f"Paper entry: {fmt_number(payload.get('entry_price'))}")
    if payload.get("stop_price") is not None:
        lines.append(f"Stop: {fmt_number(payload.get('stop_price'))}")
    if payload.get("target_price") is not None:
        lines.append(f"Target: {fmt_number(payload.get('target_price'))}")
    if payload.get("result") is not None:
        lines.append(f"Result: {payload.get('result')}")
    lines.extend([
        "",
        "Mode: MONITOR ONLY / PAPER RESEARCH",
        "No live-money order is executed by this status bridge.",
    ])
    return "\n".join(lines)


def telegram_send(token, chat_id, message):
    if not token or not chat_id:
        return False
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": message},
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Telegram HTTP {response.status_code}: {response.text[:300]}")
    return True


def main():
    url, key, token, chat_id = config()
    local_state = load_json(LOCAL_STATE_FILE)
    print(f"Strategy runtime sync starting | strategy={STRATEGY_ID} | poll={POLL_SECONDS}s", flush=True)

    while True:
        try:
            forward_state = load_json(FORWARD_STATE_FILE)
            if not forward_state:
                raise RuntimeError(f"Forward state unavailable: {FORWARD_STATE_FILE}")

            status, payload = runtime_snapshot(forward_state)
            supabase_upsert(url, key, status, payload)

            new_hash = state_hash(status, payload)
            old_hash = local_state.get("last_notified_hash")
            notified = False

            if new_hash != old_hash:
                if telegram_send(token, chat_id, telegram_message(status, payload)):
                    local_state["last_notified_hash"] = new_hash
                    local_state["last_notified_at"] = datetime.now(timezone.utc).isoformat()
                    save_json(LOCAL_STATE_FILE, local_state)
                    notified = True

            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"SYNC OK | runtime={status} | candidate={payload.get('candidate_origin_date') or '-'} | "
                f"telegram={'SENT' if notified else 'UNCHANGED'}",
                flush=True,
            )
        except Exception as exc:
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"SYNC ERROR | {type(exc).__name__}: {exc}",
                flush=True,
            )

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
