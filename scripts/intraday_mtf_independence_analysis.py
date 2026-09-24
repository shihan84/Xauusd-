import argparse
import csv
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(r"E:\xauusd")
DEFAULT_INPUT = BASE_DIR / "data" / "historical" / "XAUUSD_INTRADAY_MTF_OUTCOME_TEST_V1.csv"


def parse_dt(value):
    return datetime.fromisoformat(value) if value else None


def gross_r(rows, target_r):
    total = 0.0
    for r in rows:
        outcome = r[f"outcome_{target_r}r"]
        if outcome == "WIN":
            total += float(target_r)
        elif outcome == "STOP":
            total -= 1.0
    return total


def summarize(label, rows):
    n = len(rows)
    d = Counter(r["direction"] for r in rows)
    o1 = Counter(r["outcome_1r"] for r in rows)
    o2 = Counter(r["outcome_2r"] for r in rows)
    g1 = gross_r(rows, 1)
    g2 = gross_r(rows, 2)
    print(
        f"{label}: N={n} BUY={d['BUY']} SELL={d['SELL']} | "
        f"1R W/S/E/A={o1['WIN']}/{o1['STOP']}/{o1['EXPIRED']}/{o1['AMBIGUOUS']} "
        f"gross={g1:+.1f}R avg={(g1/n if n else 0):+.3f}R | "
        f"2R W/S/E/A={o2['WIN']}/{o2['STOP']}/{o2['EXPIRED']}/{o2['AMBIGUOUS']} "
        f"gross={g2:+.1f}R avg={(g2/n if n else 0):+.3f}R"
    )


def cooldown_filter(rows, minutes):
    accepted = []
    last_time = None
    for r in rows:
        t = parse_dt(r["signal_time_broker"])
        if last_time is None or t - last_time >= timedelta(minutes=minutes):
            accepted.append(r)
            last_time = t
    return accepted


def non_overlap_filter(rows, target_r):
    accepted = []
    occupied_until = None

    for r in rows:
        signal_time = parse_dt(r["signal_time_broker"])
        if occupied_until is not None and signal_time < occupied_until:
            continue

        accepted.append(r)

        outcome = r[f"outcome_{target_r}r"]
        outcome_time = parse_dt(r.get(f"outcome_{target_r}r_time_broker"))
        if outcome in ("WIN", "STOP", "AMBIGUOUS") and outcome_time is not None:
            occupied_until = outcome_time + timedelta(minutes=5)
        else:
            # EXPIRED: hold through the last evaluated bar for that broker day.
            last_eval = parse_dt(r.get("evaluation_last_broker"))
            occupied_until = (last_eval + timedelta(minutes=5)) if last_eval else signal_time + timedelta(days=1)

    return accepted


def same_direction_cluster_stats(rows):
    gaps = []
    same_dir_gaps = []
    same_day_same_dir = 0

    for prev, cur in zip(rows, rows[1:]):
        t0 = parse_dt(prev["signal_time_broker"])
        t1 = parse_dt(cur["signal_time_broker"])
        minutes = (t1 - t0).total_seconds() / 60.0
        gaps.append(minutes)

        if prev["direction"] == cur["direction"]:
            same_dir_gaps.append(minutes)
            if t0.date() == t1.date():
                same_day_same_dir += 1

    def count_le(arr, mins):
        return sum(1 for x in arr if x <= mins)

    print("SIGNAL GAP / CLUSTER AUDIT")
    if gaps:
        print(
            f"Consecutive gaps <=15m={count_le(gaps,15)} "
            f"<=30m={count_le(gaps,30)} <=60m={count_le(gaps,60)} "
            f"<=120m={count_le(gaps,120)}"
        )
    if same_dir_gaps:
        print(
            f"Same-direction consecutive gaps <=15m={count_le(same_dir_gaps,15)} "
            f"<=30m={count_le(same_dir_gaps,30)} <=60m={count_le(same_dir_gaps,60)} "
            f"<=120m={count_le(same_dir_gaps,120)}"
        )
    print(f"Adjacent same-direction signals on the same broker day: {same_day_same_dir}")


def main():
    parser = argparse.ArgumentParser(description="Audit overlap and signal independence for INTRADAY_MTF_V1")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    rows.sort(key=lambda r: parse_dt(r["signal_time_broker"]))

    print("INTRADAY MTF V1 SIGNAL INDEPENDENCE AUDIT")
    print("Purpose: check whether repeated/overlapping signals inflate the apparent sample.")
    print("")
    same_direction_cluster_stats(rows)

    print("\nRAW VS COOLDOWN")
    summarize("RAW", rows)
    for mins in (30, 60, 120, 240):
        summarize(f"COOLDOWN_{mins}M", cooldown_filter(rows, mins))

    print("\nONE POSITION AT A TIME")
    summarize("NON_OVERLAP_1R_EXIT", non_overlap_filter(rows, 1))
    summarize("NON_OVERLAP_2R_EXIT", non_overlap_filter(rows, 2))

    print("\nInterpretation guardrail:")
    print("If performance changes sharply after cooldown/non-overlap filtering, the raw 60-signal sample contains meaningful dependence/clustering.")
    print("This remains descriptive research only; it does not establish future profitability.")


if __name__ == "__main__":
    main()
