"""Diagnose WHERE v6e_live fails on the 2026 heatwave.

Before retraining, figure out what the current model is blind to.
The retrain should target the dominant failure mode, not blanket-fix.

Partitions of the 1,467 fire-beat-days:
  - New ignition  vs persistent (beat burned yesterday)
  - By beat historical ignition frequency quintile (if available)
  - By FRP bucket (small/medium/large fires)
  - By day-of-heatwave (does recall degrade over time?)

Reports per partition:
  - count of real fires
  - v6e beat-level rank percentile distribution (median, p25, p75)
  - recall at top 0.5% / 2% / 5% bands
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PATH = "data_lake/statewide_2026_heatwave/all_predictions.parquet"


def beat_agg(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse cells to beats per day, keep max risk + any-fire flag + FRP sum."""
    return (
        df.groupby(["date", "beat"])
        .agg(
            risk=("risk_v6e_live", "max"),
            fire=("actual_fire", "max"),
            frp=("actual_frp_sum", "sum"),
            lat=("lat", "mean"),
            lon=("lon", "mean"),
            division=("division", "first"),
        )
        .reset_index()
    )


def add_rank(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rank"] = df.groupby("date")["risk"].rank(pct=True, method="first")
    return df


def recall_at_band(sub: pd.DataFrame, floor: float) -> float:
    if len(sub) == 0:
        return float("nan")
    hits = int((sub[sub["rank"] >= floor]["fire"] > 0).sum())
    total = int((sub["fire"] > 0).sum())
    return hits / total if total else float("nan")


def add_persistence(beats: pd.DataFrame) -> pd.DataFrame:
    """Flag each fire-beat-day as 'new' (didn't burn yesterday) vs 'persistent'."""
    beats = beats.sort_values(["beat", "date"]).reset_index(drop=True)
    beats["yesterday_fire"] = (
        beats.groupby("beat")["fire"].shift(1).fillna(0).astype(int)
    )
    beats["kind"] = "dry"
    beats.loc[(beats["fire"] > 0) & (beats["yesterday_fire"] == 0), "kind"] = "new"
    beats.loc[(beats["fire"] > 0) & (beats["yesterday_fire"] > 0), "kind"] = "persistent"
    return beats


def report_section(title: str, rows: list[tuple]) -> None:
    print()
    print(f"## {title}")
    print()
    header = f"{'group':>22s}  {'n_fire':>7s}  {'p25':>7s}  {'median':>7s}  {'p75':>7s}  {'top0.5%':>9s}  {'top2%':>7s}  {'top5%':>7s}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(row)


def main() -> int:
    df = pd.read_parquet(PATH)
    # Restrict to valid days (FIRMS had data)
    valid = (
        df.groupby("date")["actual_fire"].sum().loc[lambda s: s > 0].index
    )
    df = df[df["date"].isin(valid)].reset_index(drop=True)

    beats = beat_agg(df)
    beats = add_rank(beats)
    beats = add_persistence(beats)

    total_fire_beats = int((beats["fire"] > 0).sum())
    n_days = len(valid)
    print(
        f"Valid days: {n_days} | beats/day: {beats.groupby('date').size().iloc[0]:,} "
        f"| total fire-beat-days: {total_fire_beats}"
    )

    # -------------------------------------------------------------- new vs persistent
    rows = []
    for kind in ("new", "persistent"):
        sub = beats[beats["kind"] == kind]
        if len(sub) == 0:
            continue
        ranks = sub["rank"].values
        p25, med, p75 = np.percentile(ranks, [25, 50, 75])
        r05 = float((ranks >= 0.995).mean())
        r2 = float((ranks >= 0.98).mean())
        r5 = float((ranks >= 0.95).mean())
        rows.append(
            f"{kind:>22s}  {len(sub):>7d}  {p25:>7.3f}  {med:>7.3f}  {p75:>7.3f}  "
            f"{r05*100:>8.1f}%  {r2*100:>6.1f}%  {r5*100:>6.1f}%"
        )
    report_section("NEW vs PERSISTENT ignition (v6e rank + recall at band)", rows)
    # How many fire-beat-days are new vs persistent?
    counts = beats[beats["fire"] > 0]["kind"].value_counts()
    print()
    for k in ("new", "persistent"):
        n = int(counts.get(k, 0))
        pct = n / total_fire_beats * 100
        print(f"  {k}: {n} ({pct:.1f}% of fire-beat-days)")

    # -------------------------------------------------------------- FRP bucket
    rows = []
    fires = beats[beats["fire"] > 0].copy()
    fires["frp_bucket"] = pd.cut(
        fires["frp"],
        bins=[-0.01, 5, 20, 100, 10_000],
        labels=["tiny<5", "small5-20", "med20-100", "large>=100"],
    )
    for b, sub in fires.groupby("frp_bucket", observed=True):
        if len(sub) == 0:
            continue
        ranks = sub["rank"].values
        p25, med, p75 = np.percentile(ranks, [25, 50, 75])
        r05 = float((ranks >= 0.995).mean())
        r2 = float((ranks >= 0.98).mean())
        r5 = float((ranks >= 0.95).mean())
        rows.append(
            f"{str(b):>22s}  {len(sub):>7d}  {p25:>7.3f}  {med:>7.3f}  {p75:>7.3f}  "
            f"{r05*100:>8.1f}%  {r2*100:>6.1f}%  {r5*100:>6.1f}%"
        )
    report_section("By FRP bucket (fire intensity)", rows)

    # -------------------------------------------------------------- day of heatwave
    rows = []
    for day, sub in fires.groupby("date"):
        ranks = sub["rank"].values
        if len(ranks) == 0:
            continue
        med = float(np.median(ranks))
        r05 = float((ranks >= 0.995).mean())
        r2 = float((ranks >= 0.98).mean())
        r5 = float((ranks >= 0.95).mean())
        rows.append(
            f"{str(day):>22s}  {len(sub):>7d}  {'':>7s}  {med:>7.3f}  {'':>7s}  "
            f"{r05*100:>8.1f}%  {r2*100:>6.1f}%  {r5*100:>6.1f}%"
        )
    report_section("Per-day fire rank distribution (does recall degrade?)", rows)

    # -------------------------------------------------------------- division (spatial generalization)
    rows = []
    for div, sub in fires.groupby("division"):
        if len(sub) < 5:
            continue
        ranks = sub["rank"].values
        med = float(np.median(ranks))
        r5 = float((ranks >= 0.95).mean())
        rows.append(
            f"{div:>22s}  {len(sub):>7d}  {'':>7s}  {med:>7.3f}  {'':>7s}  "
            f"{'':>9s}  {'':>7s}  {r5*100:>6.1f}%"
        )
    # top 10 divisions by fire count
    rows = rows[:10]
    report_section("Top divisions by fire count (spatial bias)", rows)

    # -------------------------------------------------------------- summary
    print()
    print("### Key diagnostic numbers")
    new_fires = beats[(beats["fire"] > 0) & (beats["kind"] == "new")]
    persist_fires = beats[(beats["fire"] > 0) & (beats["kind"] == "persistent")]
    new_top5 = float((new_fires["rank"] >= 0.95).mean()) if len(new_fires) else 0
    persist_top5 = (
        float((persist_fires["rank"] >= 0.95).mean()) if len(persist_fires) else 0
    )
    print(f"  NEW-ignition beats caught at top 5%:        {new_top5*100:.1f}%")
    print(f"  PERSISTENT  beats caught at top 5%:        {persist_top5*100:.1f}%")
    print()
    if persist_top5 > new_top5 + 0.10:
        print("  >>> v6e is a SPREAD TRACKER: it catches persistent fires")
        print("      much better than new ignitions. Retrain must target")
        print("      new-ignition discrimination.")
    elif new_top5 > 0.40:
        print("  >>> v6e has genuine new-ignition signal. Weakness is not")
        print("      structural — gains will come from calibration, more data,")
        print("      or additional features, not an architecture change.")
    else:
        print("  >>> v6e is uniformly weak on both new and persistent fires.")
        print("      Feature set is the bottleneck; retrain must add features,")
        print("      not just retune hyperparams.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
