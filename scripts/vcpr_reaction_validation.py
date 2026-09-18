import argparse
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

BASE_DIR = Path(r"E:\xauusd")
DEFAULT_REPLAY = BASE_DIR / "data" / "historical" / "XAUUSD_VCPR_REACTION_BACKTEST_V1.csv"
DEFAULT_V3 = BASE_DIR / "data" / "historical" / "XAUUSD_VCPR_RESULTS_V3_FINAL.csv"
DEFAULT_OUT = BASE_DIR / "data" / "historical" / "XAUUSD_VCPR_REACTION_VALIDATION_V3.csv"

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

    return df.sort_values("touch_time_utc").reset_index(drop=True)


def cluster_ci(resolved: pd.DataFrame) -> tuple[float, float]:
    if resolved.empty:
        return np.nan, np.nan
    groups = {k: g["is_rejection"].to_numpy(float) for k, g in resolved.groupby("level_key")}
    keys = list(groups)
    if len(keys) < 2:
        p = float(resolved["is_rejection"].mean())
        return p, p

    rng = np.random.default_rng(RNG_SEED)
    estimates = np.empty(BOOTSTRAP_SAMPLES)
    for i in range(BOOTSTRAP_SAMPLES):
        sampled = rng.choice(keys, size=len(keys), replace=True)
        values = np.concatenate([groups[k] for k in sampled])
        estimates[i] = values.mean()
    lo, hi = np.quantile(estimates, [0.025, 0.975])
    return float(lo), float(hi)


def first_per_level_all_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    # Critical: deduplicate BEFORE removing ambiguous outcomes.
    # Otherwise an ambiguous true first touch can be silently replaced by a later resolved touch.
    return df.drop_duplicates(subset=["level_key"], keep="first").copy()


def first_per_level_year_all_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    # Same guardrail for first touch within each level/year.
    return df.drop_duplicates(subset=["level_key", "touch_year"], keep="first").copy()


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


def summarize_slice(name: str, selected: pd.DataFrame, sample_mode: str, period: str) -> dict:
    total_n = len(selected)
    resolved = selected.loc[selected["resolved"]].copy()
    resolved_n = len(resolved)
    ambiguous_n = total_n - resolved_n

    if resolved_n:
        rejection_rate = float(resolved["is_rejection"].mean())
        lo, hi = cluster_ci(resolved)
        unique_levels_resolved = int(resolved["level_key"].nunique())
    else:
        rejection_rate = np.nan
        lo, hi = np.nan, np.nan
        unique_levels_resolved = 0

    return {
        "candidate": name,
        "sample_mode": sample_mode,
        "period": period,
        "selected_n": total_n,
        "resolved_n": resolved_n,
        "ambiguous_n": ambiguous_n,
        "ambiguous_rate": (ambiguous_n / total_n) if total_n else np.nan,
        "unique_levels_selected": int(selected["level_key"].nunique()) if total_n else 0,
        "unique_levels_resolved": unique_levels_resolved,
        "rejections": int(resolved["is_rejection"].sum()) if resolved_n else 0,
        "breakthroughs": int((~resolved["is_rejection"]).sum()) if resolved_n else 0,
        "rejection_rate": rejection_rate,
        "ci_low": lo,
        "ci_high": hi,
    }


def print_row(row: dict):
    if row["selected_n"] == 0:
        return
    rej = row["rejection_rate"]
    rej_text = "   n/a" if pd.isna(rej) else f"{rej:6.2%}"
    ci_text = "n/a" if pd.isna(row["ci_low"]) else f"{row['ci_low']:.2%}-{row['ci_high']:.2%}"
    print(
        f"{row['candidate']:22s} "
        f"{row['sample_mode']:18s} "
        f"{row['period']:10s} "
        f"selected={row['selected_n']:4d} "
        f"resolved={row['resolved_n']:4d} "
        f"amb={row['ambiguous_rate']:6.2%} "
        f"levels={row['unique_levels_selected']:3d} "
        f"rej={rej_text} "
        f"CI={ci_text}"
    )


def main():
    parser = argparse.ArgumentParser(description="Corrected robustness validation for VCPR reaction replay.")
    parser.add_argument("--replay", default=str(DEFAULT_REPLAY))
    parser.add_argument("--v3", default=str(DEFAULT_V3))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    df = load_data(Path(args.replay), Path(args.v3))

    print("XAUUSD VCPR Reaction Validation V3")
    print("Correction: first-touch samples are selected from ALL outcomes before ambiguous rows are excluded.")
    print("This prevents a later resolved touch from replacing an ambiguous true first touch.")
    print("This remains post-hoc research, not proof of a trading edge.")
    print()

    sample_modes = {
        "ALL_EPISODES": df,
        "FIRST_PER_LEVEL": first_per_level_all_outcomes(df),
        "FIRST_LEVEL_YEAR": first_per_level_year_all_outcomes(df),
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

    print("=== CORRECTED ROBUSTNESS TABLE ===")
    for row in rows:
        if row["period"] in {"ALL", "2026"}:
            print_row(row)

    print()
    print("=== TRUE FIRST-TOUCH YEAR STABILITY ===")
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
    print("Decision guardrails:")
    print("- First-touch rows now preserve ambiguous true first episodes instead of skipping them.")
    print("- Judge rejection share together with ambiguity, sample size, unique levels, and year stability.")
    print("- Small subgroup percentages are descriptive only.")
    print("- Any candidate still requires independent live forward confirmation.")


if __name__ == "__main__":
    main()
