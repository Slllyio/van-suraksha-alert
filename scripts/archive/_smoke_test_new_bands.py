"""Smoke-test the rank-based risk bands against real FIRMS fires.

Two views on the same data:

1. CELL-LEVEL (2 km grid) — the raw model output. Reports exact-cell
   precision/recall and a tolerance sweep for reference.

2. BEAT-LEVEL — the operational unit dispatchers actually work in.
   Forest beats in MP are ~5 cells, ~20 km^2. Rank beats by the max
   cell risk inside them, pick top-K% of beats per day, and ask:
   did any FIRMS fire fall inside the selected beats? No spatial
   tolerance needed — the beat polygon IS the match region.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

PATH = "data_lake/statewide_2026_heatwave/all_predictions.parquet"
DEG_PER_KM = 1.0 / 111.32

TOLERANCES_KM = [0.0, 2.0, 3.0, 6.0]
CELL_BANDS = [("CRITICAL", 0.995), ("HIGH", 0.98), ("MODERATE", 0.95)]
BEAT_BANDS = [("CRITICAL", 0.995), ("HIGH", 0.98), ("MODERATE", 0.95)]


def cell_level_report(df: pd.DataFrame, n_days: int, total_fires: int) -> None:
    caught: dict[tuple[float, str], int] = {
        (t, tag): 0 for t in TOLERANCES_KM for tag, _ in CELL_BANDS
    }
    band_cell_totals = {tag: 0 for tag, _ in CELL_BANDS}
    flagged_cells = {tag: 0 for tag, _ in CELL_BANDS}
    flagged_hits = {tag: 0 for tag, _ in CELL_BANDS}

    for day, sub in df.groupby("date"):
        sub = sub.copy()
        r = sub["v6e"].rank(pct=True, method="first")
        fires = sub[sub["fire"] > 0]
        fire_xy = fires[["lon", "lat"]].to_numpy()

        for tag, floor in CELL_BANDS:
            mask = r >= floor
            band_df = sub[mask]
            band_cell_totals[tag] += len(band_df)
            flagged_cells[tag] += len(band_df)
            flagged_hits[tag] += int((band_df["fire"] > 0).sum())

            if len(band_df) == 0 or len(fires) == 0:
                continue
            tree = cKDTree(band_df[["lon", "lat"]].to_numpy())
            for tol_km in TOLERANCES_KM:
                if tol_km == 0.0:
                    merged = fires.merge(
                        band_df[["cell_id"]], on="cell_id", how="inner"
                    )
                    caught[(0.0, tag)] += len(merged)
                else:
                    tol_deg = tol_km * DEG_PER_KM
                    d, _ = tree.query(
                        fire_xy, k=1, p=float("inf"), distance_upper_bound=tol_deg
                    )
                    caught[(tol_km, tag)] += int(np.isfinite(d).sum())

    print("## CELL LEVEL (2 km grid)")
    print()
    print(f"{'tolerance':>12s} | {'CRITICAL':>14s}  {'HIGH':>14s}  {'MODERATE':>14s}")
    print("-" * 62)
    for tol_km in TOLERANCES_KM:
        row = []
        for tag, _ in CELL_BANDS:
            c = caught[(tol_km, tag)]
            rec = c / total_fires * 100
            row.append(f"{c:>4d}/{total_fires} {rec:>4.1f}%")
        label = "exact cell" if tol_km == 0 else f"+- {tol_km:.0f} km"
        print(f"{label:>12s} | {row[0]:>14s}  {row[1]:>14s}  {row[2]:>14s}")
    print()
    print("Per-band exact-cell precision:")
    print(f"{'band':>10s}  {'cells/day':>10s}  {'hits':>6s}  {'precision':>10s}  {'recall':>8s}")
    for tag, _ in CELL_BANDS:
        cpd = band_cell_totals[tag] / n_days
        hits = flagged_hits[tag]
        cells = flagged_cells[tag]
        prec = hits / cells * 100 if cells else 0
        rec = hits / total_fires * 100
        print(f"{tag:>10s}  {cpd:>10.0f}  {hits:>6d}  {prec:>9.2f}%  {rec:>7.1f}%")


def beat_level_report(df: pd.DataFrame, n_days: int) -> None:
    """Beat = atomic dispatch unit. Score each beat by max cell risk, rank,
    take top-K% of beats per day, count real fires inside those beats."""
    print()
    print("## BEAT LEVEL (atomic dispatch unit, no spatial tolerance)")
    print()

    totals = {tag: 0 for tag, _ in BEAT_BANDS}
    hits = {tag: 0 for tag, _ in BEAT_BANDS}
    beats_per_day_sum = 0
    total_fire_beats = 0

    for day, sub in df.groupby("date"):
        beat_agg = (
            sub.groupby("beat")
            .agg(risk=("v6e", "max"), fire=("fire", "max"))
            .reset_index()
        )
        n_beats = len(beat_agg)
        beats_per_day_sum += n_beats
        total_fire_beats += int((beat_agg["fire"] > 0).sum())
        r = beat_agg["risk"].rank(pct=True, method="first")
        for tag, floor in BEAT_BANDS:
            mask = r >= floor
            sel = beat_agg[mask]
            totals[tag] += len(sel)
            hits[tag] += int((sel["fire"] > 0).sum())

    avg_beats = beats_per_day_sum / n_days
    print(f"Avg beats scored/day: {avg_beats:,.0f}")
    print(f"Total fire-beat-days in window: {total_fire_beats:,}")
    print()
    print(f"{'band':>10s}  {'beats/day':>10s}  {'fire hits':>10s}  {'precision':>10s}  {'recall':>8s}")
    for tag, _ in BEAT_BANDS:
        bpd = totals[tag] / n_days
        h = hits[tag]
        prec = h / totals[tag] * 100 if totals[tag] else 0
        rec = h / total_fire_beats * 100 if total_fire_beats else 0
        print(f"{tag:>10s}  {bpd:>10.1f}  {h:>10d}  {prec:>9.2f}%  {rec:>7.1f}%")

    print()
    print("Cumulative (at-least-X) beat recall:")
    # cumulative hits = anything at or above the band floor
    cum = {"MODERATE": 0, "HIGH": 0, "CRITICAL": 0}
    cum_beats = {"MODERATE": 0, "HIGH": 0, "CRITICAL": 0}
    for day, sub in df.groupby("date"):
        beat_agg = (
            sub.groupby("beat")
            .agg(risk=("v6e", "max"), fire=("fire", "max"))
            .reset_index()
        )
        r = beat_agg["risk"].rank(pct=True, method="first")
        for tag, floor in BEAT_BANDS:
            mask = r >= floor
            cum[tag] += int((beat_agg.loc[mask, "fire"] > 0).sum())
            cum_beats[tag] += int(mask.sum())
    for tag, floor in BEAT_BANDS:
        pct_label = f"top {(1-floor)*100:.1f}%"
        rec = cum[tag] / total_fire_beats * 100 if total_fire_beats else 0
        prec = cum[tag] / cum_beats[tag] * 100 if cum_beats[tag] else 0
        bpd = cum_beats[tag] / n_days
        print(
            f"  at_least_{tag:>8s} ({pct_label:>8s}): "
            f"{cum[tag]:>3d}/{total_fire_beats} = {rec:>5.1f}% recall  "
            f"| {bpd:>5.0f} beats/day  | {prec:>5.2f}% precision"
        )


def main() -> int:
    df = pd.read_parquet(PATH)
    df = df.rename(columns={"risk_v6e_live": "v6e", "actual_fire": "fire"})
    valid = df.groupby("date")["fire"].sum().loc[lambda s: s > 0].index
    df = df[df["date"].isin(valid)].reset_index(drop=True)

    n_days = len(valid)
    total_fires = int((df["fire"] > 0).sum())

    print(f"Window: {n_days} valid days | 2 km cell grid | {total_fires} fire-cell-days")
    print()
    cell_level_report(df, n_days, total_fires)
    beat_level_report(df, n_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
