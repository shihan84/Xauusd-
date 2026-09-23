import argparse
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from intraday_mtf_core import find_hst, parse_hst

BASE_DIR = Path(r"E:\xauusd")
DEFAULT_SIGNALS = BASE_DIR / "data" / "historical" / "XAUUSD_INTRADAY_MTF_SIGNAL_TEST_V1.csv"
DEFAULT_OUT = BASE_DIR / "data" / "historical" / "XAUUSD_INTRADAY_MTF_OUTCOME_TEST_V1.csv"


def parse_iso(value):
    return datetime.fromisoformat(value)


def hit_outcome(direction, bar, stop, target):
    if direction == "BUY":
        stop_hit = float(bar["low"]) <= stop
        target_hit = float(bar["high"]) >= target
    else:
        stop_hit = float(bar["high"]) >= stop
        target_hit = float(bar["low"]) <= target

    if stop_hit and target_hit:
        return "AMBIGUOUS"
    if target_hit:
        return "WIN"
    if stop_hit:
        return "STOP"
    return None


def main():
    parser = argparse.ArgumentParser(description="Outcome test for INTRADAY_MTF_V1 paper signals")
    parser.add_argument("--signals", default=str(DEFAULT_SIGNALS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--max-m5-rows", type=int, default=50000)
    args = parser.parse_args()

    signals_path = Path(args.signals)
    if not signals_path.exists():
        raise FileNotFoundError(signals_path)

    with signals_path.open("r", encoding="utf-8-sig", newline="") as handle:
        signals = list(csv.DictReader(handle))

    if not signals:
        print("No signals found in input CSV.")
        return

    hst = find_hst(5)
    parsed = parse_hst(hst, 5, max_rows=args.max_m5_rows)
    bars = parsed["rows"]
    print(
        f"M5 evaluation rows={len(bars)} "
        f"coverage={bars[0]['broker_dt'].isoformat()} -> {bars[-1]['broker_dt'].isoformat()} "
        f"file={hst}"
    )

    results = []
    for sig in signals:
        direction = sig["direction"]
        signal_utc = parse_iso(sig["signal_time_utc"])
        signal_broker = parse_iso(sig["signal_time_broker"])
        entry = float(sig["entry"])
        stop = float(sig["stop"])
        t1 = float(sig["target1"])
        t2 = float(sig["target2"])
        risk = float(sig["risk"])

        future = [
            b for b in bars
            if b["utc_dt"] >= signal_utc and b["broker_dt"].date() == signal_broker.date()
        ]

        out1 = None
        out2 = None
        time1 = None
        time2 = None
        max_favorable = 0.0
        max_adverse = 0.0
        last_time = None

        for bar in future:
            last_time = bar["broker_dt"].isoformat()

            if direction == "BUY":
                favorable = max(0.0, float(bar["high"]) - entry)
                adverse = max(0.0, entry - float(bar["low"]))
            else:
                favorable = max(0.0, entry - float(bar["low"]))
                adverse = max(0.0, float(bar["high"]) - entry)

            max_favorable = max(max_favorable, favorable)
            max_adverse = max(max_adverse, adverse)

            if out1 is None:
                o1 = hit_outcome(direction, bar, stop, t1)
                if o1 is not None:
                    out1 = o1
                    time1 = bar["broker_dt"].isoformat()

            if out2 is None:
                o2 = hit_outcome(direction, bar, stop, t2)
                if o2 is not None:
                    out2 = o2
                    time2 = bar["broker_dt"].isoformat()

            if out1 is not None and out2 is not None:
                break

        if out1 is None:
            out1 = "EXPIRED"
        if out2 is None:
            out2 = "EXPIRED"

        results.append({
            **sig,
            "outcome_1r": out1,
            "outcome_1r_time_broker": time1,
            "outcome_2r": out2,
            "outcome_2r_time_broker": time2,
            "mfe_price": f"{max_favorable:.5f}",
            "mae_price": f"{max_adverse:.5f}",
            "mfe_r": f"{(max_favorable / risk) if risk else 0.0:.4f}",
            "mae_r": f"{(max_adverse / risk) if risk else 0.0:.4f}",
            "evaluation_last_broker": last_time,
        })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = list(results[0].keys())
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    c1 = Counter(r["outcome_1r"] for r in results)
    c2 = Counter(r["outcome_2r"] for r in results)
    dirs = Counter(r["direction"] for r in results)

    print("")
    print("INTRADAY MTF V1 OUTCOME TEST")
    print(f"Signals evaluated: {len(results)} | {dict(dirs)}")
    print(f"1R first-hit outcomes: {dict(c1)}")
    print(f"2R first-hit outcomes: {dict(c2)}")
    print(f"Output: {out}")
    print("Rules: entry is the completed trigger close; evaluation starts with the next M5 bar and expires at broker-day end.")
    print("If stop and target are both touched inside the same M5 candle, the result is AMBIGUOUS.")
    print("No spread, slippage, commission, partial-exit or trailing-stop assumptions are included.")


if __name__ == "__main__":
    main()
