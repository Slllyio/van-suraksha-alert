"""Move B — Hawkes re-fit on v17 GOLD+SILVER ignition dates.

The v17 production model uses Hawkes intensity computed from pre-v17 DBSCAN
ignitions (`firms_dbscan_ignition.parquet`). But v17 also discovered 5,138
SILVER fires — burn scars that DBSCAN never saw. These should contribute to
the self-excitation signal.

This script re-fits Hawkes using the v17 GOLD+SILVER ignition dates/locations
(the BA-corroborated ~21K ignitions). Same τ_t=3d, τ_s=5km priors as v9.

Output: data_lake/human_activity/hawkes/hawkes_lambda_v17.parquet
      + hawkes_params_v17.json

Then retrain v17 with these new Hawkes features → v17.2. Expected +1-2 pp R@5%.

Usage:
  python scripts/fit_hawkes_v17.py
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
TIERED_PATH = ROOT / "data_lake" / "fire_detections" / "ignition_labels_tiered_v17.parquet"
CELLS_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live" / "cells.csv"
DATASET_PATH = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v8_ignition_dbscan" / "dataset.parquet"
OUT_DIR = ROOT / "data_lake" / "human_activity" / "hawkes"
OUT_PATH = OUT_DIR / "hawkes_lambda_v17.parquet"

# Same priors as v9 Hawkes (Ver Hoef & Schoenberg 2024)
TAU_T_DAYS = 3.0
TAU_S_KM = 5.0
LOOKBACK_DAYS = 30
COUNT_RADIUS_KM = 10.0
COUNT_WINDOW_DAYS = 7
SEARCH_RADIUS_KM = 30.0

KM_PER_DEG_LAT = 110.6
KM_PER_DEG_LON = 101.4


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Loading v17 tiered labels...")
    tiered = pd.read_parquet(TIERED_PATH)
    tiered["ignition_date"] = pd.to_datetime(tiered["ignition_date"])

    # Use only GOLD + SILVER — BA-corroborated ignitions (+ some FIRMS-matched)
    ign = tiered[tiered["tier"].isin(["GOLD", "SILVER"])].reset_index(drop=True)
    log.info("  Total tiered rows: %d", len(tiered))
    log.info("  GOLD+SILVER ignitions used: %d (vs v9 used ~1.03M FIRMS DBSCAN)", len(ign))

    # Rename for consistency with Hawkes script
    ign = ign.rename(columns={
        "ignition_date": "acq_date",
        "ignition_lat": "latitude",
        "ignition_lon": "longitude",
    })
    ign["x_km"] = ign["longitude"].values * KM_PER_DEG_LON
    ign["y_km"] = ign["latitude"].values * KM_PER_DEG_LAT

    log.info("Loading v6e cells...")
    cells = pd.read_csv(CELLS_PATH)
    cells["x_km"] = cells["centroid_lon"].values * KM_PER_DEG_LON
    cells["y_km"] = cells["centroid_lat"].values * KM_PER_DEG_LAT
    cell_coords = cells[["x_km", "y_km"]].values
    log.info("  %d cells", len(cells))

    log.info("Loading v8 dataset to get unique (cell, date) grid...")
    ds = pd.read_parquet(DATASET_PATH, columns=["cell_id", "date"])
    ds["date"] = pd.to_datetime(ds["date"])
    unique_dates = np.sort(ds["date"].unique().astype("datetime64[ns]"))
    log.info("  %d rows, %d unique dates", len(ds), len(unique_dates))

    cell_id_to_idx = {cid: i for i, cid in enumerate(cells["cell_id"].tolist())}
    n_cells = len(cells)

    ign_sorted = ign.sort_values("acq_date").reset_index(drop=True)
    ign_dates = ign_sorted["acq_date"].values.astype("datetime64[ns]")
    ign_x = ign_sorted["x_km"].values
    ign_y = ign_sorted["y_km"].values

    log.info("Computing Hawkes λ for each date (using v17 GOLD+SILVER ignitions)...")
    t0 = time.time()

    per_date_results: dict = {}
    lookback_ns = np.timedelta64(LOOKBACK_DAYS, "D")

    for di, d in enumerate(unique_dates):
        cutoff = d - lookback_ns
        lo = np.searchsorted(ign_dates, cutoff, side="left")
        hi = np.searchsorted(ign_dates, d, side="left")
        if hi <= lo:
            lam = np.zeros(n_cells, dtype=np.float32)
            n_recent = np.zeros(n_cells, dtype=np.int32)
            nearest_14d = np.full(n_cells, 50.0, dtype=np.float32)
            per_date_results[d] = (lam, n_recent, nearest_14d)
            continue

        past_dates = ign_dates[lo:hi]
        past_x = ign_x[lo:hi]
        past_y = ign_y[lo:hi]
        dt_days = ((d - past_dates) / np.timedelta64(1, "D")).astype(np.float32)

        past_coords = np.stack([past_x, past_y], axis=1)
        tree = cKDTree(past_coords)

        lam = np.zeros(n_cells, dtype=np.float32)
        n_recent = np.zeros(n_cells, dtype=np.int32)
        nearest_14d = np.full(n_cells, 50.0, dtype=np.float32)

        neighbors_per_cell = tree.query_ball_point(cell_coords, r=SEARCH_RADIUS_KM)
        for ci in range(n_cells):
            nbrs = neighbors_per_cell[ci]
            if not nbrs:
                continue
            nbr_dts = dt_days[nbrs]
            nbr_dx = cell_coords[ci, 0] - past_x[nbrs]
            nbr_dy = cell_coords[ci, 1] - past_y[nbrs]
            nbr_dists = np.sqrt(nbr_dx * nbr_dx + nbr_dy * nbr_dy)

            weights = np.exp(-nbr_dts / TAU_T_DAYS) * np.exp(-nbr_dists / TAU_S_KM)
            lam[ci] = weights.sum()

            mask_count = (nbr_dts <= COUNT_WINDOW_DAYS) & (nbr_dists <= COUNT_RADIUS_KM)
            n_recent[ci] = int(mask_count.sum())

            mask_14d = nbr_dts <= 14
            if mask_14d.any():
                nearest_14d[ci] = float(nbr_dists[mask_14d].min())

        per_date_results[d] = (lam, n_recent, nearest_14d)

        if (di + 1) % 30 == 0:
            elapsed = time.time() - t0
            rate = (di + 1) / elapsed
            eta = (len(unique_dates) - di - 1) / rate
            log.info("  dates %d/%d (%.0fs, %.1f dates/s, ETA %.0fs)",
                     di + 1, len(unique_dates), elapsed, rate, eta)

    log.info("Building output dataframe...")
    rows = []
    for d, (lam, n_recent, nearest_14d) in per_date_results.items():
        for cid, ci in cell_id_to_idx.items():
            rows.append({
                "cell_id": cid,
                "date": d,
                "hawkes_lambda": float(lam[ci]),
                "hawkes_lambda_log": float(np.log1p(lam[ci])),
                "hawkes_n_recent_10km_7d": int(n_recent[ci]),
                "hawkes_nearest_ign_14d_km": float(nearest_14d[ci]),
            })

    out_df = pd.DataFrame(rows)
    log.info("Output shape: %s", out_df.shape)

    log.info("\n=== HAWKES v17 FEATURE STATS ===")
    log.info("hawkes_lambda: mean=%.4f p90=%.4f p99=%.4f max=%.4f",
             out_df["hawkes_lambda"].mean(),
             out_df["hawkes_lambda"].quantile(0.9),
             out_df["hawkes_lambda"].quantile(0.99),
             out_df["hawkes_lambda"].max())
    log.info("hawkes_lambda > 0 rate: %.1f%%", 100 * (out_df["hawkes_lambda"] > 0).mean())
    log.info("n_recent_10km_7d: mean=%.2f p99=%.2f max=%d",
             out_df["hawkes_n_recent_10km_7d"].mean(),
             out_df["hawkes_n_recent_10km_7d"].quantile(0.99),
             out_df["hawkes_n_recent_10km_7d"].max())

    out_df.to_parquet(OUT_PATH, index=False)
    log.info("\nSaved: %s (%.0f MB)", OUT_PATH.relative_to(ROOT), OUT_PATH.stat().st_size / 1e6)

    params = {
        "tau_t_days": TAU_T_DAYS,
        "tau_s_km": TAU_S_KM,
        "lookback_days": LOOKBACK_DAYS,
        "count_radius_km": COUNT_RADIUS_KM,
        "count_window_days": COUNT_WINDOW_DAYS,
        "search_radius_km": SEARCH_RADIUS_KM,
        "n_cells": int(n_cells),
        "n_dates": int(len(unique_dates)),
        "n_ignitions_used": int(len(ign)),
        "ignition_source": "v17 GOLD+SILVER tiered labels (BA-corroborated)",
        "rationale": "Re-fit Hawkes on BA-cleaned ignition dates so v17 model sees self-excitation from the fires it was actually trained to predict",
    }
    (OUT_DIR / "hawkes_params_v17.json").write_text(json.dumps(params, indent=2))
    log.info("Params saved: %s", (OUT_DIR / "hawkes_params_v17.json").relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
