import csv
import os
import struct
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BASE_DIR = Path(r"E:\xauusd")
BRIDGE_ENV = BASE_DIR / "bridge" / ".env"
DEFAULT_HST = Path(r"C:\Users\LIVE PC\AppData\Roaming\MetaQuotes\Terminal\287469DEA9630EA94D0715D755974F1B\history\Alpari-Pro.ECN-Demo\XAUUSD1.hst")
DEFAULT_OUT = BASE_DIR / "data" / "historical" / "XAUUSD_ALPARI_M1_VCPR_REACTIONS_V1.csv"

SYMBOL = "XAUUSD"
BROKER_TZ = ZoneInfo("Europe/Helsinki")
TOUCH_DISTANCE = 0.50
RESET_DISTANCE = 8.00

FIELDS = [
    "episode_id","origin_date","pivot","source","vcpr_status","approach_side",
    "touch_time_broker","touch_time_utc","touch_price_proxy","touch_count",
    "min_price","max_price","same_side_excursion","opposite_side_excursion",
    "exit_time_broker","exit_time_utc","exit_price_proxy","duration_seconds",
    "outcome","ambiguous_reason","touch_distance","reset_distance",
]


def load_env_file(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Missing env file: {path}")
    with path.open("r", encoding="utf-8-sig") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def supabase_get_levels():
    load_env_file(BRIDGE_ENV)
    url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or ""
    ).strip()
    if not url or not key:
        raise RuntimeError("Supabase URL/key missing from bridge .env")

    response = requests.get(
        f"{url}/rest/v1/vcpr_history",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        params={
            "select": "origin_date,pivot,later_touched,source,validation_status,virgin_on_day",
            "symbol": f"eq.{SYMBOL}",
            "source": "eq.MT4",
            "validation_status": "eq.M5_VALIDATED",
            "virgin_on_day": "eq.true",
            "order": "origin_date.asc",
        },
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Supabase HTTP {response.status_code}: {response.text[:300]}")

    levels = []
    for row in response.json():
        levels.append({
            "origin_date": str(row["origin_date"]),
            "pivot": float(row["pivot"]),
            "vcpr_status": "REVISITED" if bool(row.get("later_touched")) else "UNRESOLVED",
        })
    return levels


def parse_hst_m1(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)

    rows = []
    with path.open("rb") as handle:
        header = handle.read(148)
        if len(header) != 148:
            raise RuntimeError("Invalid HST header")
        version = struct.unpack_from("<i", header, 0)[0]
        symbol = header[68:80].split(b"\0")[0].decode(errors="ignore")
        period, digits = struct.unpack_from("<ii", header, 80)

        if version < 401:
            raise RuntimeError(f"Unsupported HST version {version}; expected 401+")
        if period != 1:
            raise RuntimeError(f"Expected M1 HST period=1, got {period}")

        rec_fmt = "<qddddqiq"
        rec_size = struct.calcsize(rec_fmt)
        if rec_size != 60:
            raise RuntimeError(f"Unexpected HST record size {rec_size}")

        while True:
            data = handle.read(rec_size)
            if not data:
                break
            if len(data) != rec_size:
                break
            ts, opn, high, low, close, tick_volume, spread, real_volume = struct.unpack(rec_fmt, data)

            # MT4 HST stores broker/server wall-clock seconds in its datetime field.
            # Decode as a naive wall-clock first, then localize with the broker DST zone.
            broker_naive = datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None)
            broker_dt = broker_naive.replace(tzinfo=BROKER_TZ)
            utc_dt = broker_dt.astimezone(timezone.utc)

            rows.append({
                "raw_ts": ts,
                "broker_dt": broker_dt,
                "utc_dt": utc_dt,
                "broker_date": broker_dt.date().isoformat(),
                "open": float(opn),
                "high": float(high),
                "low": float(low),
                "close": float(close),
            })

    if not rows:
        raise RuntimeError("No M1 rows parsed")

    print(f"HST version: {version}")
    print(f"Symbol/period/digits: {symbol} / M{period} / {digits}")
    print(f"M1 rows: {len(rows)}")
    print(f"Broker coverage: {rows[0]['broker_dt'].isoformat()} -> {rows[-1]['broker_dt'].isoformat()}")
    print(f"UTC coverage: {rows[0]['utc_dt'].isoformat()} -> {rows[-1]['utc_dt'].isoformat()}")
    return rows


def touched(bar, pivot):
    return bar["high"] >= pivot - TOUCH_DISTANCE and bar["low"] <= pivot + TOUCH_DISTANCE


def finalize(level, active, bar, outcome, reason=""):
    pivot = level["pivot"]
    if active["approach_side"] == "ABOVE":
        same_exc = max(0.0, active["max_price"] - pivot)
        opp_exc = max(0.0, pivot - active["min_price"])
    else:
        same_exc = max(0.0, pivot - active["min_price"])
        opp_exc = max(0.0, active["max_price"] - pivot)

    return {
        "episode_id": active["episode_id"],
        "origin_date": level["origin_date"],
        "pivot": f"{pivot:.5f}",
        "source": "ALPARI_MT4_M1",
        "vcpr_status": level["vcpr_status"],
        "approach_side": active["approach_side"],
        "touch_time_broker": active["touch_bar"]["broker_dt"].isoformat(),
        "touch_time_utc": active["touch_bar"]["utc_dt"].isoformat(),
        "touch_price_proxy": f"{active['touch_bar']['close']:.5f}",
        "touch_count": active["touch_count"],
        "min_price": f"{active['min_price']:.5f}",
        "max_price": f"{active['max_price']:.5f}",
        "same_side_excursion": f"{same_exc:.5f}",
        "opposite_side_excursion": f"{opp_exc:.5f}",
        "exit_time_broker": bar["broker_dt"].isoformat(),
        "exit_time_utc": bar["utc_dt"].isoformat(),
        "exit_price_proxy": f"{bar['close']:.5f}",
        "duration_seconds": int((bar["utc_dt"] - active["touch_bar"]["utc_dt"]).total_seconds()),
        "outcome": outcome,
        "ambiguous_reason": reason,
        "touch_distance": f"{TOUCH_DISTANCE:.2f}",
        "reset_distance": f"{RESET_DISTANCE:.2f}",
    }


def replay_level(level, bars):
    pivot = level["pivot"]
    usable = [b for b in bars if b["broker_date"] > level["origin_date"]]
    if not usable:
        return []

    episodes = []
    active = None
    prev_close = None
    was_inside = False
    seq = 0

    for bar in usable:
        inside = touched(bar, pivot)

        if active is None:
            if inside:
                reference = prev_close if prev_close is not None else bar["open"]
                side = "ABOVE" if reference >= pivot else "BELOW"
                seq += 1
                active = {
                    "episode_id": f"{level['origin_date']}|{pivot:.5f}|{seq}",
                    "approach_side": side,
                    "touch_bar": bar,
                    "touch_count": 1,
                    "min_price": bar["low"],
                    "max_price": bar["high"],
                }

                same_hit = bar["high"] >= pivot + RESET_DISTANCE if side == "ABOVE" else bar["low"] <= pivot - RESET_DISTANCE
                opp_hit = bar["low"] <= pivot - RESET_DISTANCE if side == "ABOVE" else bar["high"] >= pivot + RESET_DISTANCE

                if same_hit or opp_hit:
                    reason = "INITIAL_TOUCH_AND_RESET_SAME_M1"
                    if same_hit and opp_hit:
                        reason = "BOTH_RESET_SIDES_SAME_M1"
                    episodes.append(finalize(level, active, bar, "AMBIGUOUS", reason))
                    active = None

            was_inside = inside
            prev_close = bar["close"]
            continue

        active["min_price"] = min(active["min_price"], bar["low"])
        active["max_price"] = max(active["max_price"], bar["high"])
        if inside and not was_inside:
            active["touch_count"] += 1

        side = active["approach_side"]
        same_hit = bar["high"] >= pivot + RESET_DISTANCE if side == "ABOVE" else bar["low"] <= pivot - RESET_DISTANCE
        opp_hit = bar["low"] <= pivot - RESET_DISTANCE if side == "ABOVE" else bar["high"] >= pivot + RESET_DISTANCE

        if same_hit or opp_hit:
            if same_hit and opp_hit:
                episodes.append(finalize(level, active, bar, "AMBIGUOUS", "BOTH_RESET_SIDES_SAME_M1"))
            elif same_hit:
                episodes.append(finalize(level, active, bar, "REJECTION"))
            else:
                episodes.append(finalize(level, active, bar, "BREAKTHROUGH"))
            active = None

        was_inside = inside
        prev_close = bar["close"]

    return episodes


def main():
    levels = supabase_get_levels()
    bars = parse_hst_m1(DEFAULT_HST)

    first_date = bars[0]["broker_date"]
    last_date = bars[-1]["broker_date"]
    eligible = [lvl for lvl in levels if lvl["origin_date"] < last_date]

    print(f"MT4 VCPRs from Supabase: {len(levels)}")
    print(f"Eligible within M1 cache horizon: {len(eligible)}")
    for level in eligible:
        print(f"  {level['origin_date']} | PP={level['pivot']:.5f} | {level['vcpr_status']}")

    all_rows = []
    for level in eligible:
        rows = replay_level(level, bars)
        all_rows.extend(rows)
        resolved = sum(r["outcome"] != "AMBIGUOUS" for r in rows)
        ambiguous = sum(r["outcome"] == "AMBIGUOUS" for r in rows)
        print(
            f"Replay {level['origin_date']} PP={level['pivot']:.2f}: "
            f"episodes={len(rows)} resolved={resolved} ambiguous={ambiguous}"
        )

    DEFAULT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    resolved_rows = [r for r in all_rows if r["outcome"] in {"REJECTION", "BREAKTHROUGH"}]
    ambiguous_rows = [r for r in all_rows if r["outcome"] == "AMBIGUOUS"]
    rejections = sum(r["outcome"] == "REJECTION" for r in resolved_rows)
    breakthroughs = sum(r["outcome"] == "BREAKTHROUGH" for r in resolved_rows)

    print()
    print("=== ALPARI M1 SUMMARY ===")
    print(f"Total episodes: {len(all_rows)}")
    print(f"Resolved: {len(resolved_rows)}")
    print(f"Ambiguous M1: {len(ambiguous_rows)}")
    print(f"Rejections: {rejections}")
    print(f"Breakthroughs: {breakthroughs}")
    if resolved_rows:
        print(f"Rejection share among resolved: {rejections / len(resolved_rows):.2%}")
    print(f"Output: {DEFAULT_OUT}")
    print("Guardrail: this is an Alpari-only M1 validation sample. Do not merge it numerically with the external V3 replay.")


if __name__ == "__main__":
    main()
