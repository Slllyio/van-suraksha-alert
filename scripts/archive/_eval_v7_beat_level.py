"""Apples-to-apples beat-level comparison of v7 vs v6e on 2025 test fold.

Same yardstick as scripts/_diagnose_v6e_failures.py used against the 2026
heatwave, but run on the 2025 test rows of the v6e dataset.parquet so both
models score the exact same days/cells/beats.

Partitions fire-beat-days into:
  * new        — neighbor_fire_yesterday == 0
  * persistent — neighbor_fire_yesterday >  0

For each model reports per-day rank-based recall at top 0.5 / 2 / 5 % beats.

Reads:
  outputs/predictive_fire_risk/predictive_v6e_live/dataset.parquet
  outputs/predictive_fire_risk/predictive_v6e_live/cells.csv
  outputs/predictive_fire_risk/predictive_v6e_live/model_lgbm.lgbm      (v6e)
  outputs/predictive_fire_risk/predictive_v7_ignition/model.txt         (v7)

Writes:
  outputs/predictive_fire_risk/predictive_v7_ignition/eval_vs_v6e_2025.json
"""

from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
V6_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v6e_live"
V7_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v7_ignition"
DATASET = V6_DIR / "dataset.parquet"
CELLS_CSV = V6_DIR / "cells.csv"
MODEL_V6 = V6_DIR / "model_lgbm.lgbm"
MODEL_V7 = V7_DIR / "model.txt"
OUT_JSON = V7_DIR / "eval_vs_v6e_2025.json"


def score(model: lgb.Booster, df: pd.DataFrame, feats: list[str]) -> np.ndarray:
    missing = [f for f in feats if f not in df.columns]
    if missing:
        raise KeyError(f"Missing features in dataset: {missing[:10]}")
    X = df[feats].to_numpy()
    return model.predict(X)


def beat_aggregate(
    df: pd.DataFrame,
    risk_col: str,
    label_col: str = "label",
    yesterday_col: str = "neighbor_fire_yesterday",
) -> pd.DataFrame:
    """Collapse cells to beats per day: beat risk = max cell risk, fire = any."""
    # Persistence flag at cell level first (used for beat-level kind below).
    g = (
        df.groupby(["date", "beat"])
        .agg(
            risk=(risk_col, "max"),
            fire=(label_col, "max"),
            yest=(yesterday_col, "max"),
        )
        .reset_index()
    )
    g["kind"] = "dry"
    g.loc[(g["fire"] > 0) & (g["yest"] == 0), "kind"] = "new"
    g.loc[(g["fire"] > 0) & (g["yest"] > 0), "kind"] = "persistent"
    g["rank"] = g.groupby("date")["risk"].rank(pct=True, method="first")
    return g


def partition_summary(beats: pd.DataFrame, model_name: str) -> dict:
    fires = beats[beats["fire"] > 0]
    counts = fires["kind"].value_counts().to_dict()
    total_fire = int((beats["fire"] > 0).sum())
    out: dict = {
        "model": model_name,
        "n_days": int(beats["date"].nunique()),
        "avg_beats_per_day": float(beats.groupby("date").size().mean()),
        "total_fire_beat_days": total_fire,
        "kind_counts": {k: int(counts.get(k, 0)) for k in ("new", "persistent")},
    }
    for kind in ("new", "persistent"):
        sub = beats[(beats["fire"] > 0) & (beats["kind"] == kind)]
        if len(sub) == 0:
            out[kind] = None
            continue
        ranks = sub["rank"].values
        out[kind] = {
            "n": int(len(sub)),
            "rank_p25": float(np.percentile(ranks, 25)),
            "rank_median": float(np.percentile(ranks, 50)),
            "rank_p75": float(np.percentile(ranks, 75)),
            "recall_top_0.5pct": float((ranks >= 0.995).mean()),
            "recall_top_2pct": float((ranks >= 0.98).mean()),
            "recall_top_5pct": float((ranks >= 0.95).mean()),
        }
    # Overall (both kinds combined) — informative but not the headline.
    all_fires = beats[beats["fire"] > 0]
    if len(all_fires):
        ranks = all_fires["rank"].values
        out["overall"] = {
            "n": int(len(all_fires)),
            "recall_top_0.5pct": float((ranks >= 0.995).mean()),
            "recall_top_2pct": float((ranks >= 0.98).mean()),
            "recall_top_5pct": float((ranks >= 0.95).mean()),
        }
    return out


def main() -> int:
    print("Loading dataset.parquet ...")
    df = pd.read_parquet(DATASET)
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df = df[df["year"] == 2025].reset_index(drop=True)
    print(f"  2025 test rows: {len(df):,}  days: {df['date'].nunique()}")

    # Merge cell -> beat/division (cells.csv is cell-level, static).
    print("Merging cell -> beat mapping from cells.csv ...")
    cells = pd.read_csv(CELLS_CSV, usecols=["cell_id", "beat", "division"])
    df = df.merge(cells, on="cell_id", how="left")
    unmapped = int(df["beat"].isna().sum())
    print(f"  rows unmapped to beat: {unmapped:,}")
    df = df[df["beat"].notna()].reset_index(drop=True)
    print(f"  beats in test fold: {df['beat'].nunique():,}")

    # ---------------------------------------------------------- v6e scoring
    print("\nScoring v6e (with leakage features)...")
    m6 = lgb.Booster(model_file=str(MODEL_V6))
    f6 = m6.feature_name()
    df["risk_v6e"] = score(m6, df, f6)
    print(f"  v6e features: {len(f6)}  trees: {m6.num_trees()}")

    # ----------------------------------------------------------- v7 scoring
    print("\nScoring v7 (no leakage)...")
    m7 = lgb.Booster(model_file=str(MODEL_V7))
    f7 = json.loads((V7_DIR / "feature_list.json").read_text())
    df["risk_v7"] = score(m7, df, f7)
    print(f"  v7  features: {len(f7)}  trees: {m7.num_trees()}")

    # Restrict to days with at least one fire, to match the 2026 heatwave
    # diagnostic yardstick.
    valid = (
        df.groupby("date")["label"].sum().loc[lambda s: s > 0].index
    )
    df = df[df["date"].isin(valid)].reset_index(drop=True)
    print(f"\nValid test days (>=1 fire): {len(valid)}")

    # ----------------------------------------------------------- beat roll-up
    print("\nBeat roll-up (max cell risk per beat-day)...")
    beats_v6 = beat_aggregate(df, "risk_v6e")
    beats_v7 = beat_aggregate(df, "risk_v7")

    summary = {
        "inputs": {
            "dataset": str(DATASET.relative_to(ROOT)),
            "fold": "2025 test",
            "n_rows": int(len(df)),
            "n_days": int(df["date"].nunique()),
            "n_beats_scored_per_day": int(beats_v6.groupby("date").size().mean()),
        },
        "v6e": partition_summary(beats_v6, "v6e_live"),
        "v7": partition_summary(beats_v7, "v7_ignition"),
    }

    # Delta block — headline "did v7 help?"
    def _delta(key: str) -> dict:
        out: dict = {}
        for band in ("recall_top_0.5pct", "recall_top_2pct", "recall_top_5pct"):
            v6 = summary["v6e"][key][band] if summary["v6e"][key] else None
            v7 = summary["v7"][key][band] if summary["v7"][key] else None
            out[band] = {
                "v6e": v6,
                "v7": v7,
                "delta": (v7 - v6) if (v6 is not None and v7 is not None) else None,
            }
        return out

    summary["delta_new_ignition"] = _delta("new")
    summary["delta_persistent"] = _delta("persistent")

    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nWrote {OUT_JSON.relative_to(ROOT)}")

    # ---------------------------------------------------------- screen report
    print("\n" + "=" * 72)
    print(" BEAT-LEVEL v7 vs v6e on 2025 test fold  (per-day rank recall)")
    print("=" * 72)
    for kind in ("new", "persistent"):
        v6 = summary["v6e"][kind]
        v7 = summary["v7"][kind]
        print(f"\n-- {kind.upper()} ignitions --")
        if v6 is None or v7 is None:
            print("  (insufficient data)")
            continue
        print(f"  n_fire_beat_days: {v6['n']}")
        print(
            f"           {'v6e':>8s} {'v7':>8s} {'delta':>8s}"
        )
        for band, label in (
            ("recall_top_0.5pct", "top 0.5%"),
            ("recall_top_2pct",  "top 2.0%"),
            ("recall_top_5pct",  "top 5.0%"),
        ):
            a, b = v6[band], v7[band]
            d = b - a
            print(
                f"  {label:>8s} {a*100:>7.1f}% {b*100:>7.1f}% {d*100:>+7.1f} pp"
            )
    # Overall both-kinds line
    if summary["v6e"]["overall"] and summary["v7"]["overall"]:
        print("\n-- OVERALL (new + persistent) --")
        for band, label in (
            ("recall_top_0.5pct", "top 0.5%"),
            ("recall_top_2pct",  "top 2.0%"),
            ("recall_top_5pct",  "top 5.0%"),
        ):
            a = summary["v6e"]["overall"][band]
            b = summary["v7"]["overall"][band]
            d = b - a
            print(
                f"  {label:>8s} {a*100:>7.1f}% {b*100:>7.1f}% {d*100:>+7.1f} pp"
            )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
