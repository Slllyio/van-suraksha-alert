"""Pivot A v2 — Track T2 — Join Dynamic World monthly features into v17 dataset.

Reads:
  - outputs/predictive_fire_risk/predictive_v8_ignition_dbscan/dataset.parquet
    (v17's training base — 4.6M cell-date rows × 84 features)
  - data_lake/land_cover/dynamic_world_monthly.parquet (DW monthly per cell)
  - data_lake/human_activity/glcm_texture_per_cell.parquet
  - data_lake/human_activity/hydro_features_per_cell.parquet
  - data_lake/human_activity/hawkes/hawkes_lambda_per_cell_date.parquet

Outputs:
  outputs/predictive_fire_risk/predictive_v18_dw/dataset.parquet — v17's
  111 features + 7 DW features = 118 features. Ready for train_v18_dynamic_world.py.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
V8_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v8_ignition_dbscan"
DW_PATH = ROOT / "data_lake" / "land_cover" / "dynamic_world_monthly.parquet"
GLCM_PATH = ROOT / "data_lake" / "human_activity" / "glcm_texture_per_cell.parquet"
HYDRO_PATH = ROOT / "data_lake" / "human_activity" / "hydro_features_per_cell.parquet"
HAWKES_PATH = ROOT / "data_lake" / "human_activity" / "hawkes" / "hawkes_lambda_per_cell_date.parquet"
TIERED_PATH = ROOT / "data_lake" / "fire_detections" / "ignition_labels_tiered_v17.parquet"
OUT_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v18_dw"
OUT_PATH = OUT_DIR / "dataset.parquet"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Loading v8 base dataset...")
    ds = pd.read_parquet(V8_DIR / "dataset.parquet")
    ds["date"] = pd.to_datetime(ds["date"])
    log.info("  %d rows × %d cols", len(ds), len(ds.columns))

    df = ds.copy()

    # Tiered labels (so v18 has the same label_v17 + weight_v17 columns as v17)
    if TIERED_PATH.exists():
        log.info("Merging tiered v17 labels...")
        tiered = pd.read_parquet(TIERED_PATH)
        tiered["ignition_date"] = pd.to_datetime(tiered["ignition_date"])
        by_cd = tiered.groupby(["cell_id", "ignition_date"]).agg(
            best_tier=("tier", lambda s: ("GOLD" if (s == "GOLD").any()
                                          else ("SILVER" if (s == "SILVER").any()
                                                else "BRONZE"))),
            cluster_count=("tier", "count"),
        ).reset_index().rename(columns={"ignition_date": "date"})
        df = df.merge(by_cd, on=["cell_id", "date"], how="left")
        df["best_tier"] = df["best_tier"].astype(str).replace("nan", "none")
        tier_to_label = {"GOLD": 1, "SILVER": 1, "BRONZE": 1, "none": 0}
        tier_to_weight = {"GOLD": 1.0, "SILVER": 0.7, "BRONZE": 0.5, "none": 1.0}
        df["label_v17"] = df["best_tier"].map(tier_to_label).fillna(0).astype(int)
        df["weight_v17"] = df["best_tier"].map(tier_to_weight).fillna(1.0)
        df["label_tier"] = df["best_tier"]

    if HAWKES_PATH.exists():
        log.info("Merging Hawkes...")
        hawkes = pd.read_parquet(HAWKES_PATH)
        hawkes["date"] = pd.to_datetime(hawkes["date"])
        df = df.merge(hawkes, on=["cell_id", "date"], how="left")
        for c in [col for col in df.columns if col.startswith("hawkes_")]:
            df[c] = df[c].fillna(50.0 if c == "hawkes_nearest_ign_14d_km" else 0)

    if GLCM_PATH.exists():
        log.info("Merging GLCM...")
        glcm = pd.read_parquet(GLCM_PATH)
        df = df.merge(glcm, on="cell_id", how="left")
        for c in [col for col in glcm.columns if col != "cell_id"]:
            df[c] = df[c].fillna(df[c].median())

    if HYDRO_PATH.exists():
        log.info("Merging Hydro...")
        hydro = pd.read_parquet(HYDRO_PATH)
        df = df.merge(hydro, on="cell_id", how="left")
        for c in [col for col in hydro.columns if col != "cell_id"]:
            df[c] = df[c].fillna(df[c].median())

    # ---- Dynamic World monthly join ----
    if not DW_PATH.exists():
        log.error("DW monthly parquet not found at %s — run download_dw_monthly_exports.py", DW_PATH)
        return 1

    log.info("Merging Dynamic World monthly features...")
    dw = pd.read_parquet(DW_PATH)
    dw_cols = [c for c in dw.columns if c.startswith("dw_")]
    log.info("  DW columns: %s", dw_cols)
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df = df.merge(dw[["cell_id", "year", "month"] + dw_cols],
                  on=["cell_id", "year", "month"], how="left")
    # LOCF impute by cell for missing months (e.g. early-2026 catch-up before DW publishes)
    df = df.sort_values(["cell_id", "date"])
    for c in dw_cols:
        df[c] = df.groupby("cell_id")[c].ffill()
        df[c] = df[c].fillna(0)  # remaining NaNs (e.g. cell not in DW dump) → 0

    log.info("Final: %d rows × %d cols (DW-augmented)", len(df), len(df.columns))
    df.to_parquet(OUT_PATH, index=False)
    log.info("Wrote: %s", OUT_PATH.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
