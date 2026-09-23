import argparse
import bisect
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from intraday_mtf_core import PERIODS, closed_rows, enrich_bars, evaluate_strategy, find_hst, parse_hst
from intraday_mtf_engine import config, load_vcpr_levels

BASE_DIR = Path(r"E:\xauusd")
DEFAULT_OUT = BASE_DIR / "data" / "historical" / "XAUUSD_INTRADAY_MTF_SIGNAL_TEST_V1.csv"


def load_all_timeframes(max_rows=None):
    series = {}
    paths = {}
    for name, period in PERIODS.items():
        path = find_hst(period)
        parsed = parse_hst(path, period, max_rows=max_rows)
        rows = closed_rows(parsed)
        series[name] = enrich_bars(rows)
        paths[name] = str(path)
        print(
            f"{name}: rows={len(rows)} "
            f"coverage={rows[0]['broker_dt'].isoformat()} -> {rows[-1]['broker_dt'].isoformat()} "
            f"file={path}"
        )
    return series, paths


def aligned_index(series, period_minutes, signal_close_raw):
    closes = [b["raw_ts"] + period_minutes * 60 for b in series]
    return bisect.bisect_right(closes, signal_close_raw) - 1


def window(series, end_index, size=260):
    start = max(0, end_index - size + 1)
    return series[start:end_index + 1]


def main():
    parser = argparse.ArgumentParser(description="Historical signal discovery for INTRADAY_MTF_V1")
    parser.add_argument("--days", type=int, default=45, help="Only report signals in the latest N calendar days of M5 coverage")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    url, key, _, _ = config()
    vcpr_levels = load_vcpr_levels(url, key)
    series, paths = load_all_timeframes()

    m5 = series["M5"]
    m15 = series["M15"]
    h1 = series["H1"]
    h4 = series["H4"]

    if len(m5) < 205:
        raise RuntimeError("Not enough M5 history")

    latest_broker = m5[-1]["broker_dt"]
    cutoff = latest_broker.timestamp() - max(1, args.days) * 86400

    close_times = {
        "M15": [b["raw_ts"] + 15 * 60 for b in m15],
        "H1": [b["raw_ts"] + 60 * 60 for b in h1],
        "H4": [b["raw_ts"] + 240 * 60 for b in h4],
    }

    rows = []
    state_counts = Counter()
    evaluated = 0

    for i in range(203, len(m5)):
        bar = m5[i]
        if bar["broker_dt"].timestamp() < cutoff:
            continue

        signal_close_raw = bar["raw_ts"] + 5 * 60
        i15 = bisect.bisect_right(close_times["M15"], signal_close_raw) - 1
        i1 = bisect.bisect_right(close_times["H1"], signal_close_raw) - 1
        i4 = bisect.bisect_right(close_times["H4"], signal_close_raw) - 1

        if min(i15, i1, i4) < 203:
            continue

        result = evaluate_strategy(
            window(m5, i),
            window(m15, i15),
            window(h1, i1),
            window(h4, i4),
            vcpr_levels,
        )
        evaluated += 1
        state_counts[result["state"]] += 1

        if result["state"] != "SIGNAL":
            continue

        plan = result.get("risk_plan") or {}
        vcpr = result.get("vcpr") or {}
        checks = result.get("checks") or {}
        rows.append({
            "signal_time_broker": result.get("signal_time_broker"),
            "signal_time_utc": result.get("signal_time_utc"),
            "direction": result.get("direction"),
            "score": result.get("score"),
            "entry": plan.get("entry"),
            "stop": plan.get("stop"),
            "target1": plan.get("target1"),
            "target2": plan.get("target2"),
            "risk": plan.get("risk"),
            "vcpr_context": vcpr.get("context"),
            "nearest_vcpr": vcpr.get("nearest_pivot"),
            "nearest_vcpr_origin": vcpr.get("nearest_origin_date"),
            "h4_bull": checks.get("h4_bull"),
            "h4_bear": checks.get("h4_bear"),
            "h1_bull": checks.get("h1_bull"),
            "h1_bear": checks.get("h1_bear"),
            "m15_setup": checks.get("m15_setup"),
            "m5_trigger": checks.get("m5_trigger"),
            "m5_stack": checks.get("m5_stack"),
        })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "signal_time_broker","signal_time_utc","direction","score",
        "entry","stop","target1","target2","risk",
        "vcpr_context","nearest_vcpr","nearest_vcpr_origin",
        "h4_bull","h4_bear","h1_bull","h1_bear",
        "m15_setup","m5_trigger","m5_stack",
    ]
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    direction_counts = Counter(r["direction"] for r in rows)
    print("")
    print("INTRADAY MTF V1 SIGNAL TEST")
    print(f"Evaluated M5 closes: {evaluated}")
    print(f"State counts: {dict(state_counts)}")
    print(f"Signals: {len(rows)} | {dict(direction_counts)}")
    print(f"Output: {out}")
    print("This test discovers rule-matching paper signals only; it does not measure profitability or execution quality.")


if __name__ == "__main__":
    main()
