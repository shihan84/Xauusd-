import argparse
import csv
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(r"E:\xauusd")
DEFAULT_M5 = BASE_DIR / "data" / "historical" / "XAUUSD_M5_UNIFIED_2022_present.csv"
DEFAULT_VCPR = BASE_DIR / "data" / "historical" / "XAUUSD_VCPR_RESULTS_V3_FINAL.csv"
DEFAULT_OUT = BASE_DIR / "data" / "historical" / "XAUUSD_VCPR_REACTION_BACKTEST_V1.csv"

BROKER_TZ = "Europe/Helsinki"
TOUCH_DISTANCE = 0.50
RESET_DISTANCE = 8.00

OUTPUT_FIELDS = [
    "episode_id",
    "origin_date",
    "pivot",
    "source",
    "vcpr_status",
    "approach_side",
    "touch_time_utc",
    "touch_time_broker",
    "touch_price_proxy",
    "touch_count",
    "min_price",
    "max_price",
    "same_side_excursion",
    "opposite_side_excursion",
    "exit_time_utc",
    "exit_time_broker",
    "exit_price_proxy",
    "duration_seconds",
    "outcome",
    "ambiguous_reason",
    "touch_distance",
    "reset_distance",
]


def parse_bool(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def load_vcpr_levels(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(path)
    levels = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if not parse_bool(row.get("is_vcpr")):
                continue
            origin_date = str(row.get("broker_date") or "").strip()
            pp = str(row.get("pp") or "").strip()
            if not origin_date or not pp:
                continue
            levels.append(
                {
                    "origin_date": origin_date,
                    "pivot": float(pp),
                    "vcpr_status": "REVISITED" if parse_bool(row.get("revisited")) else "UNRESOLVED",
                }
            )
    return levels


def clean_m5(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)

    df = pd.read_csv(path)
    required = {"datetime", "open", "high", "low", "close", "source"}
    missing = required.difference(df.columns)
    if missing:
        raise RuntimeError(f"M5 CSV missing columns: {sorted(missing)}")

    df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["source"] = df["source"].astype(str)
    df = df.dropna(subset=["datetime", "open", "high", "low", "close"]).sort_values("datetime").reset_index(drop=True)

    prev_close = df["close"].shift(1)
    prev_time = df["datetime"].shift(1)
    flat = (
        df["open"].eq(df["high"])
        & df["high"].eq(df["low"])
        & df["low"].eq(df["close"])
    )
    copied_previous = df["close"].eq(prev_close)
    kaggle = df["source"].str.lower().eq("kaggle")
    candidate = kaggle & flat & copied_previous

    contiguous = df["datetime"].sub(prev_time).eq(pd.Timedelta(minutes=5))
    group_break = (~candidate) | (~candidate.shift(1, fill_value=False)) | (~contiguous)
    group_id = group_break.cumsum()
    run_len = candidate.groupby(group_id).transform("sum")
    synthetic = candidate & run_len.ge(12)

    raw_rows = len(df)
    synthetic_rows = int(synthetic.sum())
    df = df.loc[~synthetic].copy()

    df["broker_time"] = df["datetime"].dt.tz_convert(BROKER_TZ)
    df["broker_date"] = df["broker_time"].dt.strftime("%Y-%m-%d")
    df = df.loc[df["broker_time"].dt.dayofweek < 5].reset_index(drop=True)

    print(f"Raw M5 rows: {raw_rows}")
    print(f"Synthetic frozen Kaggle rows removed: {synthetic_rows}")
    print(f"Clean broker-weekday M5 rows: {len(df)}")
    return df


def overlap_touch(row, pivot: float) -> bool:
    return float(row.high) >= pivot - TOUCH_DISTANCE and float(row.low) <= pivot + TOUCH_DISTANCE


def replay_level(level: dict, df: pd.DataFrame, level_number: int) -> list[dict]:
    pivot = float(level["pivot"])
    origin_date = level["origin_date"]

    # A VCPR only becomes known after its origin day completes.
    data = df.loc[df["broker_date"] > origin_date]
    if data.empty:
        return []

    episodes = []
    active = None
    was_inside_touch = False
    last_close = None
    episode_seq = 0

    for row in data.itertuples(index=False):
        high = float(row.high)
        low = float(row.low)
        close = float(row.close)
        open_price = float(row.open)
        inside_touch = high >= pivot - TOUCH_DISTANCE and low <= pivot + TOUCH_DISTANCE

        if active is None:
            if inside_touch:
                reference = last_close if last_close is not None else open_price
                approach_side = "ABOVE" if reference >= pivot else "BELOW"
                episode_seq += 1
                active = {
                    "episode_id": f"{origin_date}|{pivot:.5f}|{episode_seq}",
                    "approach_side": approach_side,
                    "touch_time_utc": row.datetime,
                    "touch_time_broker": row.broker_time,
                    "touch_price_proxy": close,
                    "touch_count": 1,
                    "min_price": low,
                    "max_price": high,
                    "started_same_bar": True,
                }

                same_hit = high >= pivot + RESET_DISTANCE if approach_side == "ABOVE" else low <= pivot - RESET_DISTANCE
                opposite_hit = low <= pivot - RESET_DISTANCE if approach_side == "ABOVE" else high >= pivot + RESET_DISTANCE

                # Conservative handling: M5 OHLC cannot tell whether a reset boundary
                # occurred before or after the first touch when both happen in this bar.
                if same_hit or opposite_hit:
                    reason = "INITIAL_TOUCH_AND_RESET_SAME_M5"
                    outcome = "AMBIGUOUS"
                    if same_hit and opposite_hit:
                        reason = "BOTH_RESET_SIDES_SAME_M5"
                    active["min_price"] = min(active["min_price"], low)
                    active["max_price"] = max(active["max_price"], high)
                    episodes.append(finalize_episode(level, active, row, close, outcome, reason))
                    active = None
                    was_inside_touch = inside_touch
                    last_close = close
                    continue

            was_inside_touch = inside_touch
            last_close = close
            continue

        active["min_price"] = min(float(active["min_price"]), low)
        active["max_price"] = max(float(active["max_price"]), high)

        if inside_touch and not was_inside_touch:
            active["touch_count"] = int(active["touch_count"]) + 1

        approach_side = active["approach_side"]
        same_hit = high >= pivot + RESET_DISTANCE if approach_side == "ABOVE" else low <= pivot - RESET_DISTANCE
        opposite_hit = low <= pivot - RESET_DISTANCE if approach_side == "ABOVE" else high >= pivot + RESET_DISTANCE

        if same_hit or opposite_hit:
            if same_hit and opposite_hit:
                outcome = "AMBIGUOUS"
                reason = "BOTH_RESET_SIDES_SAME_M5"
            elif same_hit:
                outcome = "REJECTION"
                reason = ""
            else:
                outcome = "BREAKTHROUGH"
                reason = ""

            episodes.append(finalize_episode(level, active, row, close, outcome, reason))
            active = None

        was_inside_touch = inside_touch
        last_close = close

    return episodes


def finalize_episode(level: dict, active: dict, row, exit_price: float, outcome: str, reason: str) -> dict:
    pivot = float(level["pivot"])
    min_price = float(active["min_price"])
    max_price = float(active["max_price"])
    approach_side = active["approach_side"]

    if approach_side == "BELOW":
        same_excursion = max(0.0, pivot - min_price)
        opposite_excursion = max(0.0, max_price - pivot)
    else:
        same_excursion = max(0.0, max_price - pivot)
        opposite_excursion = max(0.0, pivot - min_price)

    duration_seconds = int((row.datetime - active["touch_time_utc"]).total_seconds())

    return {
        "episode_id": active["episode_id"],
        "origin_date": level["origin_date"],
        "pivot": round(pivot, 5),
        "source": "V3_HISTORICAL_REPLAY",
        "vcpr_status": level["vcpr_status"],
        "approach_side": approach_side,
        "touch_time_utc": active["touch_time_utc"].isoformat(),
        "touch_time_broker": active["touch_time_broker"].isoformat(),
        "touch_price_proxy": round(float(active["touch_price_proxy"]), 5),
        "touch_count": int(active["touch_count"]),
        "min_price": round(min_price, 5),
        "max_price": round(max_price, 5),
        "same_side_excursion": round(same_excursion, 5),
        "opposite_side_excursion": round(opposite_excursion, 5),
        "exit_time_utc": row.datetime.isoformat(),
        "exit_time_broker": row.broker_time.isoformat(),
        "exit_price_proxy": round(float(exit_price), 5),
        "duration_seconds": duration_seconds,
        "outcome": outcome,
        "ambiguous_reason": reason,
        "touch_distance": TOUCH_DISTANCE,
        "reset_distance": RESET_DISTANCE,
    }


def summarize(rows: list[dict]) -> None:
    resolved = [r for r in rows if r["outcome"] in {"REJECTION", "BREAKTHROUGH"}]
    ambiguous = [r for r in rows if r["outcome"] == "AMBIGUOUS"]
    rejection = sum(r["outcome"] == "REJECTION" for r in resolved)
    breakthrough = sum(r["outcome"] == "BREAKTHROUGH" for r in resolved)

    print(f"Historical episodes total: {len(rows)}")
    print(f"Resolved episodes: {len(resolved)}")
    print(f"Ambiguous M5 episodes: {len(ambiguous)}")
    print(f"Resolved REJECTION: {rejection}")
    print(f"Resolved BREAKTHROUGH: {breakthrough}")

    if resolved:
        avg_tests = sum(int(r["touch_count"]) for r in resolved) / len(resolved)
        avg_duration = sum(int(r["duration_seconds"]) for r in resolved) / len(resolved)
        avg_same = sum(float(r["same_side_excursion"]) for r in resolved) / len(resolved)
        avg_opp = sum(float(r["opposite_side_excursion"]) for r in resolved) / len(resolved)
        print(f"Resolved avg tests/episode: {avg_tests:.2f}")
        print(f"Resolved avg duration: {avg_duration/60:.1f} min")
        print(f"Resolved avg same-side excursion: {avg_same:.2f}")
        print(f"Resolved avg opposite excursion: {avg_opp:.2f}")


def main():
    parser = argparse.ArgumentParser(description="Offline historical replay of V3 VCPR touch/reaction episodes.")
    parser.add_argument("--m5", default=str(DEFAULT_M5))
    parser.add_argument("--vcpr", default=str(DEFAULT_VCPR))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit-levels", type=int, default=0, help="Optional smoke-test limit; 0 = all V3 VCPRs")
    args = parser.parse_args()

    print("XAUUSD VCPR Historical Reaction Replay V1")
    print(f"Touch distance: {TOUCH_DISTANCE:.2f}")
    print(f"Reset distance: {RESET_DISTANCE:.2f}")
    print("Source scope: V3 baseline only (matching the external historical dataset)")
    print("ALPARI MT4 broker-only VCPRs are intentionally excluded from this replay.")

    levels = load_vcpr_levels(Path(args.vcpr))
    if args.limit_levels > 0:
        levels = levels[: args.limit_levels]
    print(f"V3 VCPR levels loaded: {len(levels)}")

    df = clean_m5(Path(args.m5))

    all_rows = []
    for idx, level in enumerate(levels, start=1):
        episodes = replay_level(level, df, idx)
        all_rows.extend(episodes)
        if idx % 10 == 0 or idx == len(levels):
            print(f"Processed levels: {idx}/{len(levels)} | episodes={len(all_rows)}", flush=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    summarize(all_rows)
    print(f"Output: {out_path}")
    print("NOTE: Historical M5 OHLC cannot determine intrabar path. Ambiguous same-bar cases are explicitly separated and should not be treated as resolved evidence.")


if __name__ == "__main__":
    main()
