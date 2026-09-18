import argparse
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

BASE_DIR = Path(r"E:\xauusd")
DEFAULT_REPLAY = BASE_DIR / "data" / "historical" / "XAUUSD_VCPR_REACTION_BACKTEST_V1.csv"
DEFAULT_V3 = BASE_DIR / "data" / "historical" / "XAUUSD_VCPR_RESULTS_V3_FINAL.csv"
DEFAULT_OUT = BASE_DIR / "data" / "historical" / "XAUUSD_VCPR_REACTION_VALIDATION_V2.csv"

BOOTSTRAP_SAMPLES = 2000
RNG_SEED = 84


def parse_bool(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def classify_session(ts: pd.Timestamp) -> str:
    dt = ts.to_pydatetime()
    london = dt.astimezone(ZoneInfo("Europe/London"))
    new_york = dt.astimezone(ZoneInfo("America/New_York"))
    tokyo = dt.astimezone(ZoneInfo("Asia/Tokyo"))
    sydney = dt.astimezone(ZoneInfo("Australia/Sydney"))

    london_open = london.weekday() < 5 and 8 <= london.hour < 17
    ny_open = new_york.weekday() < 5 and 8 <= new_york.hour < 17
    tokyo_open = tokyo.weekday() < 5 and 9 <= tokyo.hour < 18
    sydney_open = sydney.weekday() < 5 and 8 <= sydney.hour < 17

    if london_open and ny_open:
        return "LONDON_NY_OVERLAP"
    if london_open:
        return "LONDON_ONLY"
    if ny_open:
        return "NEW_YORK_ONLY"
    if tokyo_open:
        return "TOKYO"
    if sydney_open:
        return "SYDNEY"
    return "OTHER"


def load_data(replay_path: Path, v3_path: Path) -> pd.DataFrame:
    df = pd.read_csv(replay_path)
    df["origin_date"] = pd.to_datetime(df["origin_date"], errors="coerce").dt.date
    df["touch_time_utc"] = pd.to_datetime(df["touch_time_utc"], utc=True, errors="coerce")
    df["exit_time_utc"] = pd.to_datetime(df["exit_time_utc"], utc=True, errors="coerce")
    for col in ["pivot", "touch_count", "duration_seconds", "same_side_excursion", "opposite_side_excursion"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["origin_date", "pivot", "touch_time_utc", "outcome"]).copy()
    df["level_key"] = df["origin_date"].astype(str) + "|" + df["pivot"].round(5).map(lambda x: f"{x:.5f}")
    df["resolved"] = df["outcome"].isin(["REJECTION", "BREAKTHROUGH"])
    df["is_rejection"] = df["outcome"].eq("REJECTION")
    df["session"] = df["touch_time_utc"].map(classify_session)
    df["touch_year"] = df["touch_time_utc"].dt.year
    df["touch_date"] = df["touch_time_utc"].dt.date
    df["level_age_days"] = (
        pd.to_datetime(df["touch_date"]) - pd.to_datetime(df["origin_date"])
    ).dt.days

    if v3_path.exists():
        v3 = pd.read_csv(v3_path)
        v3["origin_date"] = pd.to_datetime(v3["broker_date"], errors="coerce").dt.date
        v3["pivot"] = pd.to_numeric(v3["pp"], errors="coerce")
        v3 = v3.loc[v3["is_vcpr"].map(parse_bool)].copy()
        keep = [c for c in ["origin_date", "pivot", "origin_side", "trend20_safe"] if c in v3.columns]
        v3 = v3[keep].drop_duplicates(subset=["origin_date", "pivot"])
        df = df.merge(v3, on=["origin_date", "pivot"], how="left")

    return df


def cluster_ci(df: pd.DataFrame) -> tuple[float, float]:
    if df.empty:
        return np.nan, np.nan
    groups = {k: g["is_rejection"].to_numpy(float) for k, g in df.groupby("level_key")}
    keys = list(groups)
    if len(keys) < 2:
        p = float(df["is_rejection"].mean())
        return p, p

    rng = np.random.default_rng(RNG_SEED)
    estimates = np.empty(BOOTSTRAP_SAMPLES)
    for i in range(BOOTSTRAP_SAMPLES):
        sampled = rng.choice(keys, size=len(keys), replace=True)
        values = np.concatenate([groups[k] for k in sampled])
        estimates[i] = values.mean()
    lo, hi = np.quantile(estimates, [0.025, 0.975])
    return float(lo), float(hi)


def one_per_level_first(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.sort_values("touch_time_utc")
        .drop_duplicates(subset=["level_key"], keep="first")
        .copy()
    )


def one_per_level_year(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.sort_values("touch_time_utc")
        .drop_duplicates(subset=["level_key", "touch_year"], keep="first")
        .copy()
    )


def candidate_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    masks = {
        "ALL": pd.Series(True, index=df.index),
        "APPROACH_ABOVE": df["approach_side"].eq("ABOVE"),
        "LONDON_ONLY": df["session"].eq("LONDON_ONLY"),
        "ABOVE_AND_LONDON": df["approach_side"].eq("ABOVE") & df["session"].eq("LONDON_ONLY"),
        "AGE_0_20D": df["level_age_days"].between(0, 20, inclusive="both"),
    }
    if "origin_side" in df.columns:
        masks["ORIGIN_BELOW_KNOWN"] = df["origin_side"].eq("BELOW")
    if "trend20_safe" in df.columns:
        masks["TREND_DOWN_KNOWN"] = df["trend20_safe"].eq("DOWN")
    return masks


def summarize_slice(name: str, df: pd.DataFrame, sample_mode: str, period: str) -> dict:
    n = len(df)
    if n == 0:
        return {
            "candidate": name,
            "sample_mode": sample_mode,
            "period": period,
            "n": 0,
            "unique_levels": 0,
            "rejection_rate": np.nan,
            "ci_low": np.nan,
            "ci_high": np.nan,
        }
    lo, hi = cluster_ci(df)
    return {
        "candidate": name,
        "sample_mode": sample_mode,
        "period": period,
        "n": n,
        "unique_levels": int(df["level_key"].nunique()),
        "rejection_rate": float(df["is_rejection"].mean()),
        "ci_low": lo,
        "ci_high": hi,
    }


def print_row(row: dict):
    if row["n"] == 0:
        return
    print(
        f"{row['candidate']:22s} "
        f"{row['sample_mode']:16s} "
        f"{row['period']:10s} "
        f"N={row['n']:4d} "
        f"levels={row['unique_levels']:3d} "
        f"rej={row['rejection_rate']:6.2%} "
        f"CI={row['ci_low']:6.2%}-{row['ci_high']:6.2%}"
    )


def main():
    parser = argparse.ArgumentParser(description="Robustness validation for VCPR reaction replay.")
    parser.add_argument("--replay", default=str(DEFAULT_REPLAY))
    parser.add_argument("--v3", default=str(DEFAULT_V3))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    df = load_data(Path(args.replay), Path(args.v3))
    resolved = df.loc[df["resolved"]].copy()

    print("XAUUSD VCPR Reaction Validation V2")
    print("Goal: check whether apparent historical subgroups survive de-duplication and time splits.")
    print("This is post-hoc validation, not proof of a trading edge.")
    print()

    sample_modes = {
        "ALL_EPISODES": resolved,
        "FIRST_PER_LEVEL": one_per_level_first(resolved),
        "FIRST_PER_LEVEL_YEAR": one_per_level_year(resolved),
    }

    periods = {
        "ALL": lambda d: pd.Series(True, index=d.index),
        "2022-2023": lambda d: d["touch_year"].between(2022, 2023),
        "2024-2025": lambda d: d["touch_year"].between(2024, 2025),
        "2026": lambda d: d["touch_year"].eq(2026),
    }

    rows = []
    for sample_mode, base in sample_modes.items():
        masks = candidate_masks(base)
        for candidate, cmask in masks.items():
            candidate_df = base.loc[cmask].copy()
            for period_name, period_mask_fn in periods.items():
                subset = candidate_df.loc[period_mask_fn(candidate_df)].copy()
                rows.append(summarize_slice(candidate, subset, sample_mode, period_name))

    out = pd.DataFrame(rows)
    out.to_csv(args.out, index=False)

    print("=== ROBUSTNESS TABLE ===")
    for row in rows:
        if row["period"] in {"ALL", "2026"}:
            print_row(row)

    print()
    print("=== FIRST-TOUCH-ONLY YEAR STABILITY ===")
    first = sample_modes["FIRST_PER_LEVEL"]
    masks = candidate_masks(first)
    for candidate, cmask in masks.items():
        cdf = first.loc[cmask].copy()
        for year in sorted(cdf["touch_year"].dropna().unique()):
            ydf = cdf.loc[cdf["touch_year"].eq(year)]
            row = summarize_slice(candidate, ydf, "FIRST_PER_LEVEL", str(int(year)))
            print_row(row)
        print()

    print(f"Detailed validation CSV: {args.out}")
    print()
    print("Decision rule:")
    print("- Prefer candidates whose direction is stable in first-touch-only samples, not just repeated episodes.")
    print("- Require meaningful sample size and multiple levels.")
    print("- Treat 2026 cautiously because M5 ambiguity was unusually high in the replay.")
    print("- Any surviving candidate remains research-only until live forward data independently confirms it.")


if __name__ == "__main__":
    main()
