from __future__ import annotations

from datetime import timedelta
from statistics import median

from intraday_mtf_core import _nearest_vcpr

STRATEGY_IDS = {
    "liquidity": "LIQUIDITY_SWEEP_REVERSAL_V1",
    "session": "SESSION_BREAK_RETEST_V1",
    "compression": "COMPRESSION_EXPANSION_V1",
}


def _risk(direction, entry, anchor, atr):
    if direction == "BUY":
        stop = anchor - 0.15 * atr
        risk = entry - stop
    else:
        stop = anchor + 0.15 * atr
        risk = stop - entry

    if risk <= 0:
        return None

    return {
        "entry": entry,
        "stop": stop,
        "risk": risk,
        "target1": entry + risk if direction == "BUY" else entry - risk,
        "target2": entry + 2 * risk if direction == "BUY" else entry - 2 * risk,
        "risk_too_wide": risk > 1.50 * atr,
    }


def _previous_day_levels(m5):
    today = m5[-1]["broker_dt"].date()
    previous_dates = sorted({b["broker_dt"].date() for b in m5 if b["broker_dt"].date() < today})
    if not previous_dates:
        return None
    prev_date = previous_dates[-1]
    bars = [b for b in m5 if b["broker_dt"].date() == prev_date]
    if not bars:
        return None
    return {
        "date": prev_date.isoformat(),
        "high": max(b["high"] for b in bars),
        "low": min(b["low"] for b in bars),
    }


def _asia_range(m5):
    today = m5[-1]["broker_dt"].date()
    bars = [
        b for b in m5
        if b["broker_dt"].date() == today and 0 <= b["broker_dt"].hour < 8
    ]
    if not bars:
        return None
    return {
        "date": today.isoformat(),
        "high": max(b["high"] for b in bars),
        "low": min(b["low"] for b in bars),
        "bars": len(bars),
    }


def _common_payload(state, direction, score, reason, c5, plan, vcpr, checks, strategy_name):
    close_utc = c5["utc_dt"] + timedelta(minutes=5)
    close_broker = c5["broker_dt"] + timedelta(minutes=5)
    return {
        "strategy_name": strategy_name,
        "state": state,
        "direction": direction,
        "score": score,
        "reason": reason,
        "price": float(c5["close"]),
        "signal_time_utc": close_utc.isoformat(),
        "signal_time_broker": close_broker.isoformat(),
        "m5_open_time_raw": c5["raw_ts"],
        "risk_plan": plan,
        "vcpr": vcpr,
        "checks": checks,
    }


def evaluate_liquidity_sweep(m5, h1, vcpr_levels):
    if len(m5) < 650 or len(h1) < 205:
        return {
            "state": "WARMING_UP",
            "direction": None,
            "score": 0,
            "reason": "Need more closed M5/H1 history.",
        }

    c5 = m5[-1]
    sweep = m5[-2]
    atr = float(c5["atr14"])
    if atr <= 0:
        return {"state": "SCANNING", "direction": None, "score": 0, "reason": "ATR unavailable."}

    prev = _previous_day_levels(m5)
    asia = _asia_range(m5)
    levels = []

    if prev:
        levels.extend([
            ("PDH", float(prev["high"]), "HIGH"),
            ("PDL", float(prev["low"]), "LOW"),
        ])
    if asia and c5["broker_dt"].hour >= 8:
        levels.extend([
            ("ASIA_H", float(asia["high"]), "HIGH"),
            ("ASIA_L", float(asia["low"]), "LOW"),
        ])

    nearest = _nearest_vcpr(vcpr_levels, float(sweep["close"]), sweep["broker_dt"].date().isoformat())
    if nearest.get("nearest"):
        pivot = float(nearest["nearest"]["pivot"])
        if abs(float(sweep["close"]) - pivot) <= 0.75 * atr:
            side = "LOW" if float(sweep["close"]) >= pivot else "HIGH"
            levels.append(("VCPR", pivot, side))

    buy_candidate = None
    sell_candidate = None

    for name, level, kind in levels:
        if kind == "LOW":
            swept = float(sweep["low"]) < level - 0.05 * atr and float(sweep["close"]) > level
            if swept:
                buy_candidate = (name, level)
        else:
            swept = float(sweep["high"]) > level + 0.05 * atr and float(sweep["close"]) < level
            if swept:
                sell_candidate = (name, level)

    direction = None
    level_name = None
    level_price = None
    setup_found = False

    if buy_candidate and not sell_candidate:
        direction = "BUY"
        level_name, level_price = buy_candidate
        setup_found = True
    elif sell_candidate and not buy_candidate:
        direction = "SELL"
        level_name, level_price = sell_candidate
        setup_found = True

    if not setup_found:
        return _common_payload(
            "SCANNING", None, 0,
            "Waiting for a sweep and reclaim of PDH/PDL, Asia H/L or nearby VCPR.",
            c5, None,
            {
                "context": "WATCHING_LEVELS",
                "nearest_pivot": nearest.get("nearest", {}).get("pivot") if nearest.get("nearest") else None,
            },
            {"sweep_found": False, "m5_confirmation": False},
            "Liquidity Sweep + Reversal V1",
        )

    if direction == "BUY":
        confirmed = (
            float(c5["close"]) > float(sweep["high"])
            and float(c5["close"]) > float(c5["open"])
            and float(c5["close"]) > float(c5["sma9"])
        )
        plan = _risk("BUY", float(c5["close"]), float(sweep["low"]), atr)
    else:
        confirmed = (
            float(c5["close"]) < float(sweep["low"])
            and float(c5["close"]) < float(c5["open"])
            and float(c5["close"]) < float(c5["sma9"])
        )
        plan = _risk("SELL", float(c5["close"]), float(sweep["high"]), atr)

    score = 5 + (2 if confirmed else 0)
    h1_last = h1[-1]
    h1_agrees = (
        direction == "BUY" and float(h1_last["close"]) > float(h1_last["ema99"])
    ) or (
        direction == "SELL" and float(h1_last["close"]) < float(h1_last["ema99"])
    )
    if h1_agrees:
        score += 1
    if level_name == "VCPR":
        score += 1

    state = "SETUP"
    reason = f"{direction} sweep/reclaim at {level_name} {level_price:.2f}; waiting for separate M5 confirmation."
    if confirmed:
        state = "SIGNAL"
        reason = f"{direction} sweep/reclaim confirmed by the next M5 candle."
    if plan and plan["risk_too_wide"]:
        state = "BLOCKED_RISK"
        reason = "Reversal setup confirmed but required stop exceeds 1.50 x M5 ATR."

    return _common_payload(
        state, direction, score, reason, c5, plan,
        {
            "context": level_name,
            "level": level_price,
            "nearest_pivot": nearest.get("nearest", {}).get("pivot") if nearest.get("nearest") else None,
        },
        {
            "sweep_found": True,
            "m5_confirmation": confirmed,
            "h1_agrees": h1_agrees,
        },
        "Liquidity Sweep + Reversal V1",
    )


def evaluate_session_break_retest(m5, h1, vcpr_levels):
    if len(m5) < 650 or len(h1) < 205:
        return {
            "state": "WARMING_UP",
            "direction": None,
            "score": 0,
            "reason": "Need more closed M5/H1 history.",
        }

    c5 = m5[-1]
    atr = float(c5["atr14"])
    asia = _asia_range(m5)

    if not asia or c5["broker_dt"].hour < 8 or c5["broker_dt"].hour >= 18:
        return _common_payload(
            "SCANNING", None, 0,
            "Waiting for the completed Asia range and the 08:00-18:00 broker-time breakout window.",
            c5, None, {"context": "ASIA_RANGE"},
            {"asia_ready": bool(asia), "breakout_found": False, "retest": False},
            "Asia Range Break + Retest V1",
        )

    h1_last = h1[-1]
    bull_bias = (
        float(h1_last["close"]) > float(h1_last["ema99"])
        and float(h1_last["sma20"]) > float(h1_last["sma44"])
    )
    bear_bias = (
        float(h1_last["close"]) < float(h1_last["ema99"])
        and float(h1_last["sma20"]) < float(h1_last["sma44"])
    )

    same_day = [b for b in m5 if b["broker_dt"].date() == c5["broker_dt"].date() and b["broker_dt"].hour >= 8]
    recent = same_day[-13:-1] if len(same_day) >= 2 else []

    buy_break = next(
        (b for b in reversed(recent) if float(b["close"]) > float(asia["high"]) + 0.10 * float(b["atr14"])),
        None,
    )
    sell_break = next(
        (b for b in reversed(recent) if float(b["close"]) < float(asia["low"]) - 0.10 * float(b["atr14"])),
        None,
    )

    direction = None
    boundary = None
    breakout = None
    if bull_bias and buy_break and not sell_break:
        direction = "BUY"
        boundary = float(asia["high"])
        breakout = buy_break
    elif bear_bias and sell_break and not buy_break:
        direction = "SELL"
        boundary = float(asia["low"])
        breakout = sell_break

    if not direction:
        return _common_payload(
            "SCANNING", None, 0,
            "Asia range is set. Waiting for a trend-aligned breakout.",
            c5, None,
            {
                "context": "ASIA_RANGE",
                "asia_high": float(asia["high"]),
                "asia_low": float(asia["low"]),
            },
            {
                "asia_ready": True,
                "h1_bull": bull_bias,
                "h1_bear": bear_bias,
                "breakout_found": False,
                "retest": False,
            },
            "Asia Range Break + Retest V1",
        )

    if direction == "BUY":
        retest = (
            float(c5["low"]) <= boundary + 0.15 * atr
            and float(c5["close"]) > boundary
            and float(c5["close"]) > float(c5["open"])
        )
        plan = _risk("BUY", float(c5["close"]), float(c5["low"]), atr)
    else:
        retest = (
            float(c5["high"]) >= boundary - 0.15 * atr
            and float(c5["close"]) < boundary
            and float(c5["close"]) < float(c5["open"])
        )
        plan = _risk("SELL", float(c5["close"]), float(c5["high"]), atr)

    nearest = _nearest_vcpr(vcpr_levels, float(c5["close"]), c5["broker_dt"].date().isoformat())
    score = 6 + (2 if retest else 0)

    state = "SETUP"
    reason = f"{direction} Asia-range breakout found; waiting for retest confirmation."
    if retest:
        state = "SIGNAL"
        reason = f"{direction} Asia-range breakout retest confirmed on M5."
    if plan and plan["risk_too_wide"]:
        state = "BLOCKED_RISK"
        reason = "Retest confirmed but required stop exceeds 1.50 x M5 ATR."

    return _common_payload(
        state, direction, score, reason, c5, plan,
        {
            "context": "ASIA_BREAK_RETEST",
            "asia_high": float(asia["high"]),
            "asia_low": float(asia["low"]),
            "boundary": boundary,
            "nearest_pivot": nearest.get("nearest", {}).get("pivot") if nearest.get("nearest") else None,
        },
        {
            "asia_ready": True,
            "h1_bull": bull_bias,
            "h1_bear": bear_bias,
            "breakout_found": True,
            "retest": retest,
        },
        "Asia Range Break + Retest V1",
    )


def evaluate_compression_expansion(m5, m15, h1, h4, vcpr_levels):
    if min(len(m5), len(m15), len(h1), len(h4)) < 205:
        return {
            "state": "WARMING_UP",
            "direction": None,
            "score": 0,
            "reason": "Need more closed M5/M15/H1/H4 history.",
        }

    c5 = m5[-1]
    c15 = m15[-1]
    c1 = h1[-1]
    c4 = h4[-1]

    atr15 = float(c15["atr14"])
    ma_spread = max(float(c15["sma9"]), float(c15["sma20"]), float(c15["sma44"])) - min(
        float(c15["sma9"]), float(c15["sma20"]), float(c15["sma44"])
    )
    recent_atrs = [float(x["atr14"]) for x in m15[-41:-1] if x.get("atr14") is not None]
    atr_med = median(recent_atrs) if recent_atrs else atr15

    compressed = ma_spread <= 0.45 * atr15 and atr15 <= 0.95 * atr_med

    bull = (
        float(c1["close"]) > float(c1["ema99"])
        and float(c1["sma20"]) > float(c1["sma44"])
        and float(c4["close"]) > float(c4["ema99"])
        and float(c4["sma20"]) > float(c4["sma44"])
    )
    bear = (
        float(c1["close"]) < float(c1["ema99"])
        and float(c1["sma20"]) < float(c1["sma44"])
        and float(c4["close"]) < float(c4["ema99"])
        and float(c4["sma20"]) < float(c4["sma44"])
    )
    direction = "BUY" if bull and not bear else "SELL" if bear and not bull else None

    if not compressed or not direction:
        return _common_payload(
            "SCANNING", direction, 2 if direction else 0,
            "Waiting for M15 MA/ATR compression with aligned H1/H4 direction.",
            c5, None, {"context": "COMPRESSION_WATCH"},
            {
                "compressed": compressed,
                "h1_h4_aligned": bool(direction),
                "m5_expansion": False,
            },
            "MA Compression → Expansion V1",
        )

    atr5 = float(c5["atr14"])
    prev12 = m5[-13:-1]
    prior_high = max(float(b["high"]) for b in prev12)
    prior_low = min(float(b["low"]) for b in prev12)
    candle_range = float(c5["high"]) - float(c5["low"])

    if direction == "BUY":
        expansion = (
            float(c5["close"]) > prior_high
            and float(c5["close"]) > float(c5["open"])
            and candle_range >= 1.20 * atr5
        )
        plan = _risk("BUY", float(c5["close"]), float(c5["low"]), atr5)
    else:
        expansion = (
            float(c5["close"]) < prior_low
            and float(c5["close"]) < float(c5["open"])
            and candle_range >= 1.20 * atr5
        )
        plan = _risk("SELL", float(c5["close"]), float(c5["high"]), atr5)

    nearest = _nearest_vcpr(vcpr_levels, float(c5["close"]), c5["broker_dt"].date().isoformat())
    blocker = False
    if plan and nearest.get("above") and direction == "BUY":
        blocker = float(nearest["above"]["pivot"]) - float(c5["close"]) < 0.75 * float(plan["risk"])
    elif plan and nearest.get("below") and direction == "SELL":
        blocker = float(c5["close"]) - float(nearest["below"]["pivot"]) < 0.75 * float(plan["risk"])

    score = 6 + (2 if expansion else 0)

    state = "SETUP"
    reason = f"{direction} compression is ready; waiting for M5 range expansion."
    if expansion:
        state = "SIGNAL"
        reason = f"{direction} compression expansion confirmed on M5."
    if blocker:
        state = "BLOCKED_VCPR"
        reason = "Expansion detected but a VCPR pivot is too close directly ahead."
    elif plan and plan["risk_too_wide"]:
        state = "BLOCKED_RISK"
        reason = "Expansion detected but required stop exceeds 1.50 x M5 ATR."

    return _common_payload(
        state, direction, score, reason, c5, plan,
        {
            "context": "COMPRESSION_EXPANSION",
            "nearest_pivot": nearest.get("nearest", {}).get("pivot") if nearest.get("nearest") else None,
            "blocker": blocker,
        },
        {
            "compressed": compressed,
            "h1_h4_aligned": bool(direction),
            "m5_expansion": expansion,
        },
        "MA Compression → Expansion V1",
    )
