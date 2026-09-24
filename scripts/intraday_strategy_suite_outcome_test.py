import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from intraday_mtf_core import find_hst, parse_hst

BASE_DIR = Path(r"E:\xauusd")
DEFAULT_SIGNALS = BASE_DIR / "data" / "historical" / "XAUUSD_INTRADAY_STRATEGY_SUITE_SIGNAL_TEST_V1.csv"
DEFAULT_OUT = BASE_DIR / "data" / "historical" / "XAUUSD_INTRADAY_STRATEGY_SUITE_OUTCOME_TEST_V1.csv"


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


def gross_r(rows, target_r):
    total = 0.0
    resolved = 0
    for row in rows:
        outcome = row[f"outcome_{target_r}r"]
        if outcome == "WIN":
            total += float(target_r)
            resolved += 1
        elif outcome == "STOP":
            total -= 1.0
            resolved += 1
    return total, resolved


def print_group(name, rows):
    c1 = Counter(r["outcome_1r"] for r in rows)
    c2 = Counter(r["outcome_2r"] for r in rows)
    dirs = Counter(r["direction"] for r in rows)
    g1, resolved1 = gross_r(rows, 1)
    g2, resolved2 = gross_r(rows, 2)

    win1 = c1.get("WIN", 0)
    stop1 = c1.get("STOP", 0)
    win2 = c2.get("WIN", 0)
    stop2 = c2.get("STOP", 0)

    wr1 = (100.0 * win1 / (win1 + stop1)) if (win1 + stop1) else 0.0
    wr2 = (100.0 * win2 / (win2 + stop2)) if (win2 + stop2) else 0.0

    mfe = [float(r["mfe_r"]) for r in rows]
    mae = [float(r["mae_r"]) for r in rows]

    print(name)
    print(f"  Signals: {len(rows)} | Directions: {dict(dirs)}")
    print(f"  1R: {dict(c1)} | resolved WR={wr1:.1f}% | gross={g1:+.1f}R | avg/signal={(g1/len(rows)) if rows else 0.0:+.3f}R")
    print(f"  2R: {dict(c2)} | resolved WR={wr2:.1f}% | gross={g2:+.1f}R | avg/signal={(g2/len(rows)) if rows else 0.0:+.3f}R")
    print(f"  MFE mean={(sum(mfe)/len(mfe)) if mfe else 0.0:.2f}R | MAE mean={(sum(mae)/len(mae)) if mae else 0.0:.2f}R")
    print(f"  Resolved counts: 1R={resolved1}, 2R={resolved2}")


def main():
    parser = argparse.ArgumentParser(description="Outcome test for the additional XAUUSD intraday strategy suite")
    parser.add_argument("--signals", default=str(DEFAULT_SIGNALS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--max-m5-rows", type=int, default=150000)
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

    grouped = defaultdict(list)
    for row in results:
        grouped[row["strategy_id"]].append(row)

    print("")
    print("INTRADAY STRATEGY SUITE V1 OUTCOME TEST")
    print_group("ALL STRATEGIES", results)
    print("")
    for strategy_id in sorted(grouped):
        print_group(strategy_id, grouped[strategy_id])
        print("")

    print(f"Output: {out}")
    print("Evaluation begins with the first M5 bar after the completed trigger candle and expires at broker-day end.")
    print("If stop and target are both touched inside the same M5 candle, that target outcome is AMBIGUOUS.")
    print("Gross R figures ignore EXPIRED/AMBIGUOUS outcomes and exclude spread, slippage, commission, swap, partial exits and trailing stops.")
    print("These are descriptive historical results, not proof of a future trading edge.")


if __name__ == "__main__":
    main()
