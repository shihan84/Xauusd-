import argparse
import bisect
import csv
from collections import Counter, defaultdict
from pathlib import Path

from intraday_mtf_core import closed_rows, enrich_bars, find_hst, parse_hst
from intraday_mtf_engine import config, load_vcpr_levels
from intraday_strategy_suite_core import (
    STRATEGY_IDS,
    evaluate_compression_expansion,
    evaluate_liquidity_sweep,
    evaluate_session_break_retest,
)

BASE_DIR = Path(r"E:\xauusd")
DEFAULT_OUT = BASE_DIR / "data" / "historical" / "XAUUSD_INTRADAY_STRATEGY_SUITE_SIGNAL_TEST_V1.csv"
PERIODS = {"M5": 5, "M15": 15, "H1": 60, "H4": 240}


def load_series():
    result = {}
    for name, period in PERIODS.items():
        path = find_hst(period)
        parsed = parse_hst(path, period)
        rows = closed_rows(parsed)
        result[name] = enrich_bars(rows)
        print(
            f"{name}: rows={len(rows)} "
            f"coverage={rows[0]['broker_dt'].isoformat()} -> {rows[-1]['broker_dt'].isoformat()} "
            f"file={path}"
        )
    return result


def slice_end(series, idx, size):
    return series[max(0, idx - size + 1):idx + 1]


def signal_row(strategy_id, result):
    plan = result.get("risk_plan") or {}
    vcpr = result.get("vcpr") or {}
    return {
        "strategy_id": strategy_id,
        "strategy_name": result.get("strategy_name"),
        "signal_time_broker": result.get("signal_time_broker"),
        "signal_time_utc": result.get("signal_time_utc"),
        "direction": result.get("direction"),
        "score": result.get("score"),
        "entry": plan.get("entry"),
        "stop": plan.get("stop"),
        "target1": plan.get("target1"),
        "target2": plan.get("target2"),
        "risk": plan.get("risk"),
        "context": vcpr.get("context"),
        "level": vcpr.get("level") or vcpr.get("boundary"),
        "nearest_vcpr": vcpr.get("nearest_pivot"),
        "reason": result.get("reason"),
    }


def main():
    parser = argparse.ArgumentParser(description="Historical signal discovery for the three-strategy intraday suite")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    url, key, _, _ = config()
    vcpr_levels = load_vcpr_levels(url, key)
    series = load_series()

    m5 = series["M5"]
    m15 = series["M15"]
    h1 = series["H1"]
    h4 = series["H4"]

    latest_broker = m5[-1]["broker_dt"]
    cutoff_ts = latest_broker.timestamp() - max(1, args.days) * 86400

    close_times = {
        "M15": [b["raw_ts"] + 15 * 60 for b in m15],
        "H1": [b["raw_ts"] + 60 * 60 for b in h1],
        "H4": [b["raw_ts"] + 240 * 60 for b in h4],
    }

    signals = []
    state_counts = defaultdict(Counter)
    evaluated = 0

    for i in range(799, len(m5)):
        c5 = m5[i]
        if c5["broker_dt"].timestamp() < cutoff_ts:
            continue

        signal_close_raw = c5["raw_ts"] + 5 * 60
        i15 = bisect.bisect_right(close_times["M15"], signal_close_raw) - 1
        i1 = bisect.bisect_right(close_times["H1"], signal_close_raw) - 1
        i4 = bisect.bisect_right(close_times["H4"], signal_close_raw) - 1
        if min(i15, i1, i4) < 204:
            continue

        w5 = slice_end(m5, i, 800)
        w15 = slice_end(m15, i15, 300)
        w1 = slice_end(h1, i1, 300)
        w4 = slice_end(h4, i4, 300)

        results = {
            STRATEGY_IDS["liquidity"]: evaluate_liquidity_sweep(w5, w1, vcpr_levels),
            STRATEGY_IDS["session"]: evaluate_session_break_retest(w5, w1, vcpr_levels),
            STRATEGY_IDS["compression"]: evaluate_compression_expansion(w5, w15, w1, w4, vcpr_levels),
        }
        evaluated += 1

        for strategy_id, result in results.items():
            state_counts[strategy_id][result.get("state") or "UNKNOWN"] += 1
            if result.get("state") == "SIGNAL":
                signals.append(signal_row(strategy_id, result))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "strategy_id","strategy_name","signal_time_broker","signal_time_utc",
        "direction","score","entry","stop","target1","target2","risk",
        "context","level","nearest_vcpr","reason",
    ]
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(signals)

    print("")
    print("INTRADAY STRATEGY SUITE V1 SIGNAL TEST")
    print(f"Evaluated M5 closes: {evaluated}")

    for strategy_id in STRATEGY_IDS.values():
        subset = [r for r in signals if r["strategy_id"] == strategy_id]
        dirs = Counter(r["direction"] for r in subset)
        print(f"{strategy_id}:")
        print(f"  State counts: {dict(state_counts[strategy_id])}")
        print(f"  Signals: {len(subset)} | {dict(dirs)}")

    print(f"TOTAL SIGNALS: {len(signals)}")
    print(f"Output: {out}")
    print("Signal-discovery only. No profitability or execution claim is made by this test.")


if __name__ == "__main__":
    main()
