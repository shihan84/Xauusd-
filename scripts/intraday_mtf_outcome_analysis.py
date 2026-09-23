import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

BASE_DIR = Path(r"E:\xauusd")
DEFAULT_INPUT = BASE_DIR / "data" / "historical" / "XAUUSD_INTRADAY_MTF_OUTCOME_TEST_V1.csv"


def pct(a, b):
    return (100.0 * a / b) if b else 0.0


def gross_r(rows, target_r):
    total = 0.0
    for r in rows:
        outcome = r[f"outcome_{target_r}r"]
        if outcome == "WIN":
            total += float(target_r)
        elif outcome == "STOP":
            total -= 1.0
        # EXPIRED/AMBIGUOUS treated as 0R for this simple descriptive summary.
    return total


def summarize(label, rows):
    n = len(rows)
    if not n:
        return None

    out1 = Counter(r["outcome_1r"] for r in rows)
    out2 = Counter(r["outcome_2r"] for r in rows)

    resolved1 = out1["WIN"] + out1["STOP"]
    resolved2 = out2["WIN"] + out2["STOP"]

    mfe = [float(r["mfe_r"]) for r in rows if r.get("mfe_r")]
    mae = [float(r["mae_r"]) for r in rows if r.get("mae_r")]

    return {
        "label": label,
        "n": n,
        "buy": sum(1 for r in rows if r["direction"] == "BUY"),
        "sell": sum(1 for r in rows if r["direction"] == "SELL"),
        "w1": out1["WIN"],
        "s1": out1["STOP"],
        "e1": out1["EXPIRED"],
        "a1": out1["AMBIGUOUS"],
        "wr1_resolved": pct(out1["WIN"], resolved1),
        "gross1": gross_r(rows, 1),
        "avg1": gross_r(rows, 1) / n,
        "w2": out2["WIN"],
        "s2": out2["STOP"],
        "e2": out2["EXPIRED"],
        "a2": out2["AMBIGUOUS"],
        "wr2_resolved": pct(out2["WIN"], resolved2),
        "gross2": gross_r(rows, 2),
        "avg2": gross_r(rows, 2) / n,
        "mean_mfe": mean(mfe) if mfe else 0.0,
        "median_mfe": median(mfe) if mfe else 0.0,
        "mean_mae": mean(mae) if mae else 0.0,
        "median_mae": median(mae) if mae else 0.0,
    }


def print_summary(s):
    if not s:
        return
    print(
        f"{s['label']}: N={s['n']} BUY={s['buy']} SELL={s['sell']} | "
        f"1R W/S/E/A={s['w1']}/{s['s1']}/{s['e1']}/{s['a1']} "
        f"resolved-WR={s['wr1_resolved']:.1f}% gross={s['gross1']:+.1f}R avg={s['avg1']:+.3f}R | "
        f"2R W/S/E/A={s['w2']}/{s['s2']}/{s['e2']}/{s['a2']} "
        f"resolved-WR={s['wr2_resolved']:.1f}% gross={s['gross2']:+.1f}R avg={s['avg2']:+.3f}R | "
        f"MFE mean/median={s['mean_mfe']:.2f}/{s['median_mfe']:.2f}R "
        f"MAE mean/median={s['mean_mae']:.2f}/{s['median_mae']:.2f}R"
    )


def session_name(iso_broker):
    # Broker timestamps are Europe/Helsinki; this is descriptive broker-clock bucketing only.
    hour = int(iso_broker[11:13])
    if 0 <= hour < 8:
        return "ASIA_BROKER_00_08"
    if 8 <= hour < 13:
        return "LONDON_EARLY_08_13"
    if 13 <= hour < 18:
        return "LONDON_NY_OVERLAP_13_18"
    return "NY_LATE_18_24"


def group(rows, keyfunc):
    out = defaultdict(list)
    for r in rows:
        out[keyfunc(r)].append(r)
    return out


def main():
    parser = argparse.ArgumentParser(description="Segment INTRADAY_MTF_V1 outcome-test results")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        print("No rows.")
        return

    print("INTRADAY MTF V1 OUTCOME ANALYSIS")
    print("Descriptive only. EXPIRED/AMBIGUOUS are counted as 0R in gross/average R summaries.")
    print("No spread, slippage, commission, swap, partial exits, or trailing-stop assumptions.")
    print("")
    print_summary(summarize("ALL", rows))

    print("\nBY DIRECTION")
    for key in ("BUY", "SELL"):
        print_summary(summarize(key, [r for r in rows if r["direction"] == key]))

    print("\nBY SCORE")
    for key, subset in sorted(group(rows, lambda r: r["score"]).items(), key=lambda kv: float(kv[0])):
        print_summary(summarize(f"SCORE {key}", subset))

    print("\nBY VCPR CONTEXT")
    for key, subset in sorted(group(rows, lambda r: r.get("vcpr_context") or "UNKNOWN").items()):
        print_summary(summarize(key, subset))

    print("\nBY BROKER-CLOCK SESSION")
    for key, subset in group(rows, lambda r: session_name(r["signal_time_broker"])).items():
        print_summary(summarize(key, subset))

    print("\nBY MONTH")
    for key, subset in sorted(group(rows, lambda r: r["signal_time_broker"][:7]).items()):
        print_summary(summarize(key, subset))


if __name__ == "__main__":
    main()
