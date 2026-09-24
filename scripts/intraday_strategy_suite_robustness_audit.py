import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(r"E:\xauusd")
DEFAULT_INPUT = BASE_DIR / "data" / "historical" / "XAUUSD_INTRADAY_STRATEGY_SUITE_OUTCOME_TEST_V1.csv"

def parse_dt(v):
    return datetime.fromisoformat(v) if v else None

def gross_r(rows, target_r):
    total = 0.0
    for r in rows:
        o = r[f"outcome_{target_r}r"]
        if o == "WIN":
            total += float(target_r)
        elif o == "STOP":
            total -= 1.0
    return total

def break_even_cost_price(rows, target_r):
    gross = gross_r(rows, target_r)
    if gross <= 0:
        return 0.0
    denom = sum(1.0 / float(r["risk"]) for r in rows if float(r["risk"]) > 0)
    return gross / denom if denom else 0.0

def net_r_with_cost(rows, target_r, cost_price):
    total = gross_r(rows, target_r)
    return total - sum(float(cost_price) / float(r["risk"]) for r in rows if float(r["risk"]) > 0)

def cooldown_filter(rows, minutes):
    accepted, last_time = [], None
    for r in rows:
        t = parse_dt(r["signal_time_broker"])
        if last_time is None or t - last_time >= timedelta(minutes=minutes):
            accepted.append(r)
            last_time = t
    return accepted

def non_overlap_filter(rows, target_r):
    accepted, occupied_until = [], None
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
            last_eval = parse_dt(r.get("evaluation_last_broker"))
            occupied_until = last_eval + timedelta(minutes=5) if last_eval else signal_time + timedelta(days=1)
    return accepted

def summary_line(label, rows):
    if not rows:
        print(f"{label}: N=0")
        return
    d = Counter(r["direction"] for r in rows)
    g1, g2 = gross_r(rows, 1), gross_r(rows, 2)
    be1, be2 = break_even_cost_price(rows, 1), break_even_cost_price(rows, 2)
    print(
        f"{label}: N={len(rows)} BUY={d['BUY']} SELL={d['SELL']} | "
        f"1R gross={g1:+.1f}R avg={g1/len(rows):+.3f}R BE_cost=USD {be1:.3f}/trade | "
        f"2R gross={g2:+.1f}R avg={g2/len(rows):+.3f}R BE_cost=USD {be2:.3f}/trade"
    )

def cluster_stats(rows):
    if len(rows) < 2:
        print("  Cluster audit: not enough signals")
        return
    gaps, same_dir = [], []
    for prev, cur in zip(rows, rows[1:]):
        gap = (parse_dt(cur["signal_time_broker"]) - parse_dt(prev["signal_time_broker"])).total_seconds() / 60.0
        gaps.append(gap)
        if prev["direction"] == cur["direction"]:
            same_dir.append(gap)
    count_le = lambda arr, x: sum(1 for v in arr if v <= x)
    print(f"  Gaps <=15m {count_le(gaps,15)}, <=30m {count_le(gaps,30)}, <=60m {count_le(gaps,60)}, <=120m {count_le(gaps,120)}")
    print(f"  Same-dir gaps <=15m {count_le(same_dir,15)}, <=30m {count_le(same_dir,30)}, <=60m {count_le(same_dir,60)}, <=120m {count_le(same_dir,120)}")

def cost_table(rows):
    print("  COST SENSITIVITY (fixed round-trip price cost per trade)")
    for cost in (0.10, 0.20, 0.30, 0.50, 0.75, 1.00):
        n1, n2 = net_r_with_cost(rows, 1, cost), net_r_with_cost(rows, 2, cost)
        print(f"    USD {cost:.2f}: 1R net={n1:+.1f}R ({n1/len(rows):+.3f}/signal) | 2R net={n2:+.1f}R ({n2/len(rows):+.3f}/signal)")

def month_breakdown(rows):
    months = defaultdict(list)
    for r in rows:
        months[parse_dt(r["signal_time_broker"]).strftime("%Y-%m")].append(r)
    print("  MONTHLY")
    for month in sorted(months):
        rs = months[month]
        print(f"    {month}: N={len(rs)} | 1R={gross_r(rs,1):+.1f}R | 2R={gross_r(rs,2):+.1f}R")

def main():
    p = argparse.ArgumentParser(description="Robustness audit for XAUUSD intraday strategy suite")
    p.add_argument("--input", default=str(DEFAULT_INPUT))
    args = p.parse_args()
    path = Path(args.input)
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as h:
        rows = list(csv.DictReader(h))
    grouped = defaultdict(list)
    for r in rows:
        grouped[r["strategy_id"]].append(r)

    print("INTRADAY STRATEGY SUITE V1 ROBUSTNESS AUDIT")
    print("Break-even cost is a price-distance scenario, not a broker-spread claim.")
    print("EXPIRED/AMBIGUOUS count as 0R gross but still incur scenario cost.")
    print("")
    for strategy_id in sorted(grouped):
        rs = sorted(grouped[strategy_id], key=lambda r: parse_dt(r["signal_time_broker"]))
        print(strategy_id)
        summary_line("  RAW", rs)
        cluster_stats(rs)
        for mins in (30, 60, 120, 240):
            summary_line(f"  COOLDOWN_{mins}M", cooldown_filter(rs, mins))
        summary_line("  NON_OVERLAP_1R", non_overlap_filter(rs, 1))
        summary_line("  NON_OVERLAP_2R", non_overlap_filter(rs, 2))
        for direction in ("BUY","SELL"):
            summary_line(f"  {direction}", [r for r in rs if r["direction"] == direction])
        cost_table(rs)
        month_breakdown(rs)
        print("")
    print("Guardrail: stronger candidates should not collapse under cooldown, non-overlap, direction splits, modest cost scenarios, or a few isolated months.")
    print("Historical research only; this does not establish future profitability.")

if __name__ == "__main__":
    main()
