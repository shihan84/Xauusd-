import argparse
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

BASE_DIR = Path(r"E:\xauusd")
DEFAULT_REPLAY = BASE_DIR / "data" / "historical" / "XAUUSD_VCPR_REACTION_BACKTEST_V1.csv"
DEFAULT_V3 = BASE_DIR / "data" / "historical" / "XAUUSD_VCPR_RESULTS_V3_FINAL.csv"
DEFAULT_OUT = BASE_DIR / "data" / "historical" / "XAUUSD_VCPR_REACTION_ANALYSIS_V1.csv"

MIN_SEGMENT_N = 50
BOOTSTRAP_SAMPLES = 2000
RNG_SEED = 84


def parse_bool(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def load_data(replay_path: Path, v3_path: Path) -> pd.DataFrame:
    if not replay_path.exists():
        raise FileNotFoundError(replay_path)
    df = pd.read_csv(replay_path)

    required = {
        "origin_date", "pivot", "vcpr_status", "approach_side",
        "touch_time_utc", "touch_count", "duration_seconds",
        "same_side_excursion", "opposite_side_excursion", "outcome",
    }
    missing = required.difference(df.columns)
    if missing:
        raise RuntimeError(f"Replay CSV missing columns: {sorted(missing)}")

    df["origin_date"] = pd.to_datetime(df["origin_date"], errors="coerce").dt.date
    df["touch_time_utc"] = pd.to_datetime(df["touch_time_utc"], utc=True, errors="coerce")
    for col in [
        "pivot", "touch_count", "duration_seconds",
        "same_side_excursion", "opposite_side_excursion",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["origin_date", "pivot", "touch_time_utc", "outcome"]).copy()
    df["level_key"] = (
        df["origin_date"].astype(str) + "|" + df["pivot"].round(5).map(lambda x: f"{x:.5f}")
    )
    df["resolved"] = df["outcome"].isin(["REJECTION", "BREAKTHROUGH"])
    df["is_rejection"] = df["outcome"].eq("REJECTION")
    df["touch_date"] = df["touch_time_utc"].dt.date
    df["level_age_days"] = (
        pd.to_datetime(df["touch_date"]) - pd.to_datetime(df["origin_date"])
    ).dt.days

    if v3_path.exists():
        v3 = pd.read_csv(v3_path)
        v3["origin_date"] = pd.to_datetime(v3["broker_date"], errors="coerce").dt.date
        v3["pivot"] = pd.to_numeric(v3["pp"], errors="coerce")
        v3 = v3.loc[v3["is_vcpr"].map(parse_bool)].copy()
        keep = [
            "origin_date", "pivot", "origin_side", "trend20_safe",
            "distance_atr", "atr14", "revisited",
        ]
        keep = [c for c in keep if c in v3.columns]
        v3 = v3[keep].drop_duplicates(subset=["origin_date", "pivot"])
        df = df.merge(v3, on=["origin_date", "pivot"], how="left")

    df["age_bucket"] = pd.cut(
        df["level_age_days"],
        bins=[-1, 5, 20, 90, 365, np.inf],
        labels=["0-5d", "6-20d", "21-90d", "91-365d", "365d+"],
    )

    df["touch_year"] = df["touch_time_utc"].dt.year
    df["era"] = pd.cut(
        df["touch_year"],
        bins=[2021, 2023, 2025, 2026],
        labels=["2022-2023", "2024-2025", "2026"],
    )

    df["session"] = df["touch_time_utc"].map(classify_session)
    return df


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


def cluster_bootstrap_rejection_ci(resolved: pd.DataFrame) -> tuple[float, float]:
    if resolved.empty:
        return (np.nan, np.nan)

    groups = {
        key: grp["is_rejection"].to_numpy(dtype=float)
        for key, grp in resolved.groupby("level_key")
    }
    keys = list(groups)
    if len(keys) < 2:
        p = float(resolved["is_rejection"].mean())
        return (p, p)

    rng = np.random.default_rng(RNG_SEED)
    estimates = np.empty(BOOTSTRAP_SAMPLES, dtype=float)

    for i in range(BOOTSTRAP_SAMPLES):
        sampled_keys = rng.choice(keys, size=len(keys), replace=True)
        values = np.concatenate([groups[k] for k in sampled_keys])
        estimates[i] = values.mean()

    lo, hi = np.quantile(estimates, [0.025, 0.975])
    return float(lo), float(hi)


def segment_table(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    rows = []
    for value, grp in df.groupby(dimension, dropna=False, observed=True):
        total = len(grp)
        resolved = grp.loc[grp["resolved"]]
        n = len(resolved)
        ambiguous = total - n
        if n == 0:
            rejection_rate = np.nan
            lo = np.nan
            hi = np.nan
        else:
            rejection_rate = float(resolved["is_rejection"].mean())
            lo, hi = cluster_bootstrap_rejection_ci(resolved)

        rows.append({
            "dimension": dimension,
            "group": str(value),
            "episodes_total": total,
            "resolved_n": n,
            "ambiguous_n": ambiguous,
            "ambiguous_rate": ambiguous / total if total else np.nan,
            "rejections": int(resolved["is_rejection"].sum()),
            "breakthroughs": int((~resolved["is_rejection"]).sum()),
            "rejection_rate": rejection_rate,
            "cluster_bootstrap_ci_low": lo,
            "cluster_bootstrap_ci_high": hi,
            "unique_levels": int(resolved["level_key"].nunique()) if n else 0,
            "avg_tests": float(resolved["touch_count"].mean()) if n else np.nan,
            "avg_duration_min": float(resolved["duration_seconds"].mean() / 60) if n else np.nan,
            "avg_same_excursion": float(resolved["same_side_excursion"].mean()) if n else np.nan,
            "avg_opposite_excursion": float(resolved["opposite_side_excursion"].mean()) if n else np.nan,
        })
    return pd.DataFrame(rows)


def print_overall(df: pd.DataFrame) -> None:
    resolved = df.loc[df["resolved"]].copy()
    ambiguous = df.loc[~df["resolved"]]
    rejection_rate = float(resolved["is_rejection"].mean())
    lo, hi = cluster_bootstrap_rejection_ci(resolved)

    counts = resolved.groupby("level_key").size().sort_values(ascending=False)
    top5_share = float(counts.head(5).sum() / counts.sum()) if len(counts) else np.nan
    top10_share = float(counts.head(10).sum() / counts.sum()) if len(counts) else np.nan

    print("=== OVERALL ===")
    print(f"Total episodes: {len(df)}")
    print(f"Resolved: {len(resolved)}")
    print(f"Ambiguous: {len(ambiguous)} ({len(ambiguous)/len(df):.2%})")
    print(f"Unique levels with resolved episodes: {resolved['level_key'].nunique()}")
    print(f"Rejections: {int(resolved['is_rejection'].sum())}")
    print(f"Breakthroughs: {int((~resolved['is_rejection']).sum())}")
    print(f"Rejection share: {rejection_rate:.2%}")
    print(f"Cluster-bootstrap 95% CI by VCPR level: {lo:.2%} to {hi:.2%}")
    print(f"Median resolved episodes per level: {counts.median():.1f}")
    print(f"Top 5 levels share of resolved episodes: {top5_share:.2%}")
    print(f"Top 10 levels share of resolved episodes: {top10_share:.2%}")
    print()


def print_segment_summary(table: pd.DataFrame, dimension: str) -> None:
    subset = table.loc[
        (table["dimension"] == dimension)
        & (table["resolved_n"] >= MIN_SEGMENT_N)
    ].copy()

    if subset.empty:
        return

    subset = subset.sort_values(["rejection_rate", "resolved_n"], ascending=[False, False])
    print(f"=== {dimension.upper()} (resolved N >= {MIN_SEGMENT_N}) ===")
    for row in subset.itertuples(index=False):
        print(
            f"{row.group:22s} "
            f"N={int(row.resolved_n):4d} "
            f"rej={row.rejection_rate:6.2%} "
            f"CI={row.cluster_bootstrap_ci_low:6.2%}-{row.cluster_bootstrap_ci_high:6.2%} "
            f"amb={row.ambiguous_rate:6.2%} "
            f"levels={int(row.unique_levels):3d}"
        )
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Conservative segmented analysis of VCPR historical reaction replay."
    )
    parser.add_argument("--replay", default=str(DEFAULT_REPLAY))
    parser.add_argument("--v3", default=str(DEFAULT_V3))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    df = load_data(Path(args.replay), Path(args.v3))

    print("XAUUSD VCPR Reaction Analysis V1")
    print("Resolved outcomes only are used for rejection/breakthrough shares.")
    print("Ambiguous M5 episodes are reported separately, never forced into an outcome.")
    print("Bootstrap resamples whole VCPR levels to reduce false confidence from repeated episodes.")
    print()

    print_overall(df)

    dimensions = [
        "approach_side",
        "vcpr_status",
        "age_bucket",
        "session",
        "era",
    ]
    for optional in ["origin_side", "trend20_safe"]:
        if optional in df.columns and df[optional].notna().any():
            dimensions.append(optional)

    tables = [segment_table(df, dim) for dim in dimensions]
    out = pd.concat(tables, ignore_index=True)
    out.to_csv(args.out, index=False)

    for dim in dimensions:
        print_segment_summary(out, dim)

    print("=== CHRONOLOGICAL STABILITY CHECK ===")
    resolved = df.loc[df["resolved"]].copy()
    for era, grp in resolved.groupby("era", observed=True):
        if len(grp) == 0:
            continue
        lo, hi = cluster_bootstrap_rejection_ci(grp)
        print(
            f"{era}: N={len(grp)} | levels={grp['level_key'].nunique()} | "
            f"rejection={grp['is_rejection'].mean():.2%} | CI={lo:.2%}-{hi:.2%}"
        )
    print()
    print(f"Detailed segment CSV: {args.out}")
    print(
        "Interpretation guardrail: this script is descriptive. Do not promote a subgroup into a strategy "
        "from one historical scan; any candidate must remain stable across eras and then survive forward data."
    )


if __name__ == "__main__":
    main()
