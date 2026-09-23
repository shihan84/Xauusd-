import os
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SYMBOL = "XAUUSD"
BROKER_TZ = ZoneInfo("Europe/Helsinki")
PERIODS = {"M5": 5, "M15": 15, "H1": 60, "H4": 240}


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


def find_hst(period_minutes: int, symbol: str = SYMBOL) -> Path:
    appdata = Path(os.environ.get("APPDATA", ""))
    root = appdata / "MetaQuotes" / "Terminal"
    pattern = f"*/history/*/{symbol}{period_minutes}.hst"
    candidates = [p for p in root.glob(pattern) if p.is_file()]
    if not candidates:
        raise FileNotFoundError(f"No MT4 HST found for {symbol} period={period_minutes} under {root}")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def parse_hst(path: Path, expected_period: int, max_rows: int | None = None):
    if not path.exists():
        raise FileNotFoundError(path)

    rec_fmt = "<qddddqiq"
    rec_size = struct.calcsize(rec_fmt)
    if rec_size != 60:
        raise RuntimeError(f"Unexpected MT4 HST record size {rec_size}")

    size = path.stat().st_size
    if size < 148:
        raise RuntimeError(f"Invalid HST file: {path}")

    total_records = (size - 148) // rec_size
    start_record = 0
    if max_rows is not None and total_records > max_rows:
        start_record = total_records - max_rows

    rows = []
    with path.open("rb") as handle:
        header = handle.read(148)
        version = struct.unpack_from("<i", header, 0)[0]
        symbol = header[68:80].split(b"\0")[0].decode(errors="ignore")
        period, digits = struct.unpack_from("<ii", header, 80)

        if version < 401:
            raise RuntimeError(f"Unsupported HST version {version}; expected 401+")
        if period != expected_period:
            raise RuntimeError(f"Expected period {expected_period}, got {period} in {path}")

        handle.seek(148 + start_record * rec_size)
        while True:
            data = handle.read(rec_size)
            if not data or len(data) != rec_size:
                break

            ts, opn, high, low, close, tick_volume, spread, real_volume = struct.unpack(rec_fmt, data)
            broker_naive = datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None)
            broker_dt = broker_naive.replace(tzinfo=BROKER_TZ)
            utc_dt = broker_dt.astimezone(timezone.utc)

            rows.append({
                "raw_ts": int(ts),
                "broker_dt": broker_dt,
                "utc_dt": utc_dt,
                "open": float(opn),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "tick_volume": int(tick_volume),
                "spread": int(spread),
            })

    if not rows:
        raise RuntimeError(f"No rows parsed from {path}")

    return {
        "version": version,
        "symbol": symbol,
        "period": period,
        "digits": digits,
        "path": str(path),
        "rows": rows,
    }


def closed_rows(parsed):
    rows = parsed["rows"]
    if len(rows) < 2:
        return []
    # MT4 HST normally keeps the currently-forming candle as the final record.
    return rows[:-1]


def _sma(values, period, index):
    if index + 1 < period:
        return None
    window = values[index - period + 1:index + 1]
    return sum(window) / period


def enrich_bars(bars):
    closes = [b["close"] for b in bars]
    trs = []
    for i, bar in enumerate(bars):
        if i == 0:
            tr = bar["high"] - bar["low"]
        else:
            prev_close = bars[i - 1]["close"]
            tr = max(
                bar["high"] - bar["low"],
                abs(bar["high"] - prev_close),
                abs(bar["low"] - prev_close),
            )
        trs.append(tr)

    ema99 = [None] * len(bars)
    atr14 = [None] * len(bars)

    if len(bars) >= 99:
        seed = sum(closes[:99]) / 99.0
        ema99[98] = seed
        alpha = 2.0 / 100.0
        for i in range(99, len(bars)):
            ema99[i] = alpha * closes[i] + (1.0 - alpha) * ema99[i - 1]

    if len(bars) >= 14:
        atr14[13] = sum(trs[:14]) / 14.0
        for i in range(14, len(bars)):
            atr14[i] = ((atr14[i - 1] * 13.0) + trs[i]) / 14.0

    enriched = []
    for i, bar in enumerate(bars):
        item = dict(bar)
        item["sma9"] = _sma(closes, 9, i)
        item["sma20"] = _sma(closes, 20, i)
        item["sma44"] = _sma(closes, 44, i)
        item["ema99"] = ema99[i]
        item["sma200"] = _sma(closes, 200, i)
        item["atr14"] = atr14[i]
        enriched.append(item)
    return enriched


def ready(series):
    if len(series) < 204:
        return False
    last = series[-1]
    required = ("sma9", "sma20", "sma44", "ema99", "sma200", "atr14")
    return all(last.get(k) is not None for k in required)


def _slope(series, key, lookback=3):
    if len(series) <= lookback:
        return 0.0
    now = series[-1].get(key)
    old = series[-1 - lookback].get(key)
    if now is None or old is None:
        return 0.0
    return float(now) - float(old)


def _nearest_vcpr(levels, price, broker_date):
    usable = []
    for level in levels:
        try:
            if str(level.get("origin_date")) > broker_date:
                continue
            pivot = float(level["pivot"])
            low = float(level.get("cpr_low") if level.get("cpr_low") is not None else pivot)
            high = float(level.get("cpr_high") if level.get("cpr_high") is not None else pivot)
        except (TypeError, ValueError, KeyError):
            continue
        usable.append({**level, "pivot": pivot, "cpr_low": min(low, high), "cpr_high": max(low, high)})

    if not usable:
        return {"nearest": None, "below": None, "above": None, "inside": None}

    nearest = min(usable, key=lambda x: abs(x["pivot"] - price))
    below_candidates = [x for x in usable if x["pivot"] <= price]
    above_candidates = [x for x in usable if x["pivot"] > price]
    below = max(below_candidates, key=lambda x: x["pivot"]) if below_candidates else None
    above = min(above_candidates, key=lambda x: x["pivot"]) if above_candidates else None
    inside_candidates = [x for x in usable if x["cpr_low"] <= price <= x["cpr_high"]]
    inside = min(inside_candidates, key=lambda x: abs(x["pivot"] - price)) if inside_candidates else None
    return {"nearest": nearest, "below": below, "above": above, "inside": inside}


def _risk_plan(direction, m5, atr):
    entry = float(m5[-1]["close"])
    if direction == "BUY":
        swing = min(float(x["low"]) for x in m5[-5:])
        stop = swing - 0.15 * atr
        risk = entry - stop
        if risk < 0.60 * atr:
            risk = 0.60 * atr
            stop = entry - risk
    else:
        swing = max(float(x["high"]) for x in m5[-5:])
        stop = swing + 0.15 * atr
        risk = stop - entry
        if risk < 0.60 * atr:
            risk = 0.60 * atr
            stop = entry + risk

    risk_too_wide = risk > 1.50 * atr
    if direction == "BUY":
        t1 = entry + risk
        t2 = entry + 2.0 * risk
    else:
        t1 = entry - risk
        t2 = entry - 2.0 * risk

    return {
        "entry": entry,
        "stop": stop,
        "risk": risk,
        "target1": t1,
        "target2": t2,
        "risk_too_wide": risk_too_wide,
    }


def evaluate_strategy(m5, m15, h1, h4, vcpr_levels):
    series_map = {"M5": m5, "M15": m15, "H1": h1, "H4": h4}
    missing = [name for name, series in series_map.items() if not ready(series)]
    if missing:
        return {
            "state": "WARMING_UP",
            "direction": None,
            "score": 0,
            "reason": f"Need >=204 closed bars with indicators for: {', '.join(missing)}",
            "timeframes_ready": {k: k not in missing for k in series_map},
        }

    c5, p5 = m5[-1], m5[-2]
    c15 = m15[-1]
    c1 = h1[-1]
    c4 = h4[-1]

    h4_bull = (
        c4["close"] > c4["ema99"]
        and c4["close"] > c4["sma200"]
        and c4["sma44"] > c4["ema99"]
        and _slope(h4, "sma44", 3) > 0
    )
    h4_bear = (
        c4["close"] < c4["ema99"]
        and c4["close"] < c4["sma200"]
        and c4["sma44"] < c4["ema99"]
        and _slope(h4, "sma44", 3) < 0
    )

    h1_bull = (
        c1["close"] > c1["ema99"]
        and c1["close"] > c1["sma200"]
        and c1["sma20"] > c1["sma44"]
        and _slope(h1, "sma44", 3) > 0
    )
    h1_bear = (
        c1["close"] < c1["ema99"]
        and c1["close"] < c1["sma200"]
        and c1["sma20"] < c1["sma44"]
        and _slope(h1, "sma44", 3) < 0
    )

    direction = None
    if h4_bull and h1_bull:
        direction = "BUY"
    elif h4_bear and h1_bear:
        direction = "SELL"

    atr15 = float(c15["atr14"])
    ma_zone_low = min(float(c15["sma20"]), float(c15["sma44"]))
    ma_zone_high = max(float(c15["sma20"]), float(c15["sma44"]))
    touched_ma_zone = (
        float(c15["low"]) <= ma_zone_high + 0.10 * atr15
        and float(c15["high"]) >= ma_zone_low - 0.10 * atr15
    )

    if direction == "BUY":
        m15_setup = touched_ma_zone and float(c15["close"]) >= float(c15["sma44"]) - 0.25 * atr15
        m15_momentum = float(c15["sma9"]) >= float(c15["sma20"])
    elif direction == "SELL":
        m15_setup = touched_ma_zone and float(c15["close"]) <= float(c15["sma44"]) + 0.25 * atr15
        m15_momentum = float(c15["sma9"]) <= float(c15["sma20"])
    else:
        m15_setup = False
        m15_momentum = False

    atr5 = float(c5["atr14"])
    if direction == "BUY":
        m5_trigger = (
            float(c5["close"]) > float(c5["sma9"])
            and float(c5["close"]) > float(c5["sma20"])
            and float(c5["sma9"]) >= float(c5["sma20"])
            and (float(p5["close"]) <= float(p5["sma9"]) or float(p5["close"]) <= float(p5["sma20"]))
            and float(c5["close"]) > float(p5["high"])
            and float(c5["close"]) > float(c5["open"])
            and abs(float(c5["close"]) - float(c5["sma20"])) <= 1.0 * atr5
        )
        m5_stack = float(c5["sma9"]) > float(c5["sma20"]) > float(c5["sma44"])
    elif direction == "SELL":
        m5_trigger = (
            float(c5["close"]) < float(c5["sma9"])
            and float(c5["close"]) < float(c5["sma20"])
            and float(c5["sma9"]) <= float(c5["sma20"])
            and (float(p5["close"]) >= float(p5["sma9"]) or float(p5["close"]) >= float(p5["sma20"]))
            and float(c5["close"]) < float(p5["low"])
            and float(c5["close"]) < float(c5["open"])
            and abs(float(c5["close"]) - float(c5["sma20"])) <= 1.0 * atr5
        )
        m5_stack = float(c5["sma9"]) < float(c5["sma20"]) < float(c5["sma44"])
    else:
        m5_trigger = False
        m5_stack = False

    broker_date = c5["broker_dt"].date().isoformat()
    vcpr = _nearest_vcpr(vcpr_levels, float(c5["close"]), broker_date)
    risk_plan = _risk_plan(direction, m5, atr5) if direction else None

    vcpr_supportive = False
    vcpr_blocker = False
    vcpr_context = "NO_LEVEL"

    if direction and risk_plan:
        price = float(c5["close"])
        risk = float(risk_plan["risk"])
        if vcpr["inside"] is not None:
            vcpr_context = "AT_VCPR"
            vcpr_supportive = True
        elif direction == "BUY":
            below = vcpr["below"]
            above = vcpr["above"]
            if below and price - float(below["pivot"]) <= 0.50 * atr15:
                vcpr_supportive = True
                vcpr_context = "VCPR_SUPPORT"
            if above and float(above["pivot"]) - price < 0.80 * risk:
                vcpr_blocker = True
                vcpr_context = "VCPR_AHEAD_BLOCKER"
        else:
            above = vcpr["above"]
            below = vcpr["below"]
            if above and float(above["pivot"]) - price <= 0.50 * atr15:
                vcpr_supportive = True
                vcpr_context = "VCPR_RESISTANCE"
            if below and price - float(below["pivot"]) < 0.80 * risk:
                vcpr_blocker = True
                vcpr_context = "VCPR_AHEAD_BLOCKER"

    score = 0
    if direction:
        score += 4
    if m15_setup:
        score += 2
    if m5_trigger:
        score += 2
    if vcpr_supportive:
        score += 1
    if m5_stack:
        score += 1

    state = "SCANNING"
    reason = "H4/H1 are not aligned."
    if direction:
        state = "BIAS_FOUND"
        reason = f"{direction} higher-timeframe bias found."
    if direction and m15_setup:
        state = "SETUP"
        reason = f"{direction} bias with M15 pullback context; waiting for M5 trigger."
    if direction and m15_setup and m5_trigger:
        state = "ARMED"
        reason = "M5 trigger present; checking score, VCPR blocker and paper-risk guardrails."

    if risk_plan and risk_plan["risk_too_wide"]:
        state = "BLOCKED_RISK"
        reason = "Paper stop would exceed 1.50 x M5 ATR."
    elif vcpr_blocker:
        state = "BLOCKED_VCPR"
        reason = "A VCPR pivot is too close in front of the proposed trade."
    elif direction and m15_setup and m5_trigger and score >= 8:
        state = "SIGNAL"
        reason = "Paper-test signal: H4/H1 aligned, M15 pullback and M5 confirmation passed."

    nearest = vcpr["nearest"]
    signal_open_utc = c5["utc_dt"]
    signal_close_utc = signal_open_utc + timedelta(minutes=5)
    signal_close_broker = c5["broker_dt"] + timedelta(minutes=5)

    return {
        "state": state,
        "direction": direction,
        "score": score,
        "reason": reason,
        "signal_time_utc": signal_close_utc.isoformat(),
        "signal_time_broker": signal_close_broker.isoformat(),
        "m5_open_time_raw": c5["raw_ts"],
        "price": float(c5["close"]),
        "risk_plan": risk_plan,
        "vcpr": {
            "context": vcpr_context,
            "supportive": vcpr_supportive,
            "blocker": vcpr_blocker,
            "nearest_pivot": float(nearest["pivot"]) if nearest else None,
            "nearest_origin_date": str(nearest.get("origin_date")) if nearest else None,
            "nearest_source": str(nearest.get("source")) if nearest else None,
        },
        "checks": {
            "h4_bull": h4_bull,
            "h4_bear": h4_bear,
            "h1_bull": h1_bull,
            "h1_bear": h1_bear,
            "m15_setup": m15_setup,
            "m15_momentum": m15_momentum,
            "m5_trigger": m5_trigger,
            "m5_stack": m5_stack,
        },
        "ma": {
            "M5": {k: float(c5[k]) for k in ("sma9","sma20","sma44","ema99","sma200","atr14")},
            "M15": {k: float(c15[k]) for k in ("sma9","sma20","sma44","ema99","sma200","atr14")},
            "H1": {k: float(c1[k]) for k in ("sma9","sma20","sma44","ema99","sma200","atr14")},
            "H4": {k: float(c4[k]) for k in ("sma9","sma20","sma44","ema99","sma200","atr14")},
        },
        "bars": {
            "M5": c5["broker_dt"].isoformat(),
            "M15": c15["broker_dt"].isoformat(),
            "H1": c1["broker_dt"].isoformat(),
            "H4": c4["broker_dt"].isoformat(),
        },
    }
