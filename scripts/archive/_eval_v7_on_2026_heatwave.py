"""Score v7 on the 2026 heatwave grid and compare beat-level recall to v6e.

Reuses the heavy lifting from mp_statewide_simulation_2026.py: cell loading,
weather assembly, FIRMS history, neighbor maps, and `score_day`. The trick:
we call `score_day` with (m6, f6) in the v6 slot and (m7, f7) in the v3 slot,
then rename the output `risk_v3_no_leak` column to `risk_v7`.

Then runs the same diagnostic partition as _diagnose_v6e_failures.py on the
resulting beat-level roll-up — apples-to-apples comparison of v6e vs v7.

Writes:
  data_lake/statewide_2026_heatwave/all_predictions_v7.parquet
  outputs/predictive_fire_risk/predictive_v7_ignition/eval_vs_v6e_2026.json
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Reuse everything from the simulation script.
from mp_statewide_simulation_2026 import (  # noqa: E402
    load_cells,
    load_models,
    build_weather_by_grid,
    assign_cells_to_grid,
    load_firms,
    build_fires_by_cell,
    compute_hist_fire_features,
    build_fire_date_index,
    build_neighbor_map,
    score_day,
)
from train_predictive_fire_risk import ndvi_features, load_ndvi_model  # noqa: E402

log = logging.getLogger("v7_2026_eval")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)

V7_DIR = ROOT / "outputs" / "predictive_fire_risk" / "predictive_v7_ignition"
MODEL_V7 = V7_DIR / "model.txt"
FEATS_V7 = V7_DIR / "feature_list.json"
OUT_PRED = ROOT / "data_lake" / "statewide_2026_heatwave" / "all_predictions_v7.parquet"
OUT_JSON = V7_DIR / "eval_vs_v6e_2026.json"

START = date(2026, 3, 20)
END = date(2026, 4, 7)


def score_window() -> pd.DataFrame:
    cells, grid_meta = load_cells()
    m6, feats_v6, _m3_stub, _feats_v3_stub = load_models()

    log.info("Loading v7 model from %s", MODEL_V7.relative_to(ROOT))
    m7 = lgb.Booster(model_file=str(MODEL_V7))
    feats_v7: list[str] = json.loads(FEATS_V7.read_text())
    log.info("  v7: %d features, %d trees", len(feats_v7), m7.num_trees())

    weather_by_grid, grid_coords = build_weather_by_grid(END)
    log.info("Assigning cells to nearest weather station...")
    cell_to_grid = assign_cells_to_grid(cells, grid_coords)

    firms, _ = load_firms(grid_meta)
    hist_fires = build_fires_by_cell(
        firms, cells, grid_meta, date_cutoff=date(2026, 1, 1)
    )
    hist_feats = compute_hist_fire_features(hist_fires, year_cutoff=2026)
    fire_date_index = build_fire_date_index(firms, cells, grid_meta)
    neighbor_map = build_neighbor_map(cells)
    ndvi_model = load_ndvi_model()

    all_preds: list[pd.DataFrame] = []
    d = START
    while d <= END:
        t0 = time.time()
        doy = d.timetuple().tm_yday
        nf = ndvi_features(doy, ndvi_model)
        # Trick: pass v7 in the v3 slot — score_day treats it generically,
        # just assigns features by name. The 4 leakage features are NOT in
        # feats_v7 so they're silently skipped. The output column
        # "risk_v3_no_leak" then holds v7 predictions.
        preds = score_day(
            d=d,
            cells=cells,
            cell_to_grid=cell_to_grid,
            weather_by_grid=weather_by_grid,
            hist_feats=hist_feats,
            ndvi_feat=nf,
            fire_date_index=fire_date_index,
            neighbor_map=neighbor_map,
            feats_v6=feats_v6,
            feats_v3=feats_v7,
            m6=m6,
            m3=m7,
        )
        preds = preds.rename(columns={"risk_v3_no_leak": "risk_v7"})
        preds = preds.drop(columns=[c for c in ["actual_detections"] if c in preds.columns])
        all_preds.append(preds)
        log.info(
            "  %s: %d fire-cells, v6e_max=%.4f v7_max=%.4f in %.1fs",
            d,
            int(preds["actual_fire"].sum()),
            float(preds["risk_v6e_live"].max()),
            float(preds["risk_v7"].max()),
            time.time() - t0,
        )
        d += timedelta(days=1)

    combined = pd.concat(all_preds, ignore_index=True)
    OUT_PRED.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(OUT_PRED, index=False)
    log.info("Saved %d rows to %s", len(combined), OUT_PRED.relative_to(ROOT))
    return combined


def beat_eval(df: pd.DataFrame) -> dict:
    """Same partition yardstick as _diagnose_v6e_failures.py."""
    # Restrict to valid days (at least one fire).
    valid = (
        df.groupby("date")["actual_fire"].sum().loc[lambda s: s > 0].index
    )
    df = df[df["date"].isin(valid)].reset_index(drop=True)

    def rollup(risk_col: str) -> pd.DataFrame:
        g = (
            df.groupby(["date", "beat"])
            .agg(
                risk=(risk_col, "max"),
                fire=("actual_fire", "max"),
            )
            .reset_index()
        )
        g = g.sort_values(["beat", "date"]).reset_index(drop=True)
        g["yesterday_fire"] = (
            g.groupby("beat")["fire"].shift(1).fillna(0).astype(int)
        )
        g["kind"] = "dry"
        g.loc[(g["fire"] > 0) & (g["yesterday_fire"] == 0), "kind"] = "new"
        g.loc[(g["fire"] > 0) & (g["yesterday_fire"] > 0), "kind"] = "persistent"
        g["rank"] = g.groupby("date")["risk"].rank(pct=True, method="first")
        return g

    def summarise(beats: pd.DataFrame, name: str) -> dict:
        out = {
            "model": name,
            "n_days": int(beats["date"].nunique()),
            "avg_beats_per_day": float(beats.groupby("date").size().mean()),
            "total_fire_beat_days": int((beats["fire"] > 0).sum()),
        }
        for kind in ("new", "persistent"):
            sub = beats[(beats["fire"] > 0) & (beats["kind"] == kind)]
            if len(sub) == 0:
                out[kind] = None
                continue
            r = sub["rank"].values
            out[kind] = {
                "n": int(len(sub)),
                "rank_p25": float(np.percentile(r, 25)),
                "rank_median": float(np.percentile(r, 50)),
                "rank_p75": float(np.percentile(r, 75)),
                "recall_top_0.5pct": float((r >= 0.995).mean()),
                "recall_top_2pct":   float((r >= 0.98).mean()),
                "recall_top_5pct":   float((r >= 0.95).mean()),
            }
        # overall
        sub = beats[beats["fire"] > 0]
        r = sub["rank"].values
        out["overall"] = {
            "n": int(len(sub)),
            "recall_top_0.5pct": float((r >= 0.995).mean()),
            "recall_top_2pct":   float((r >= 0.98).mean()),
            "recall_top_5pct":   float((r >= 0.95).mean()),
        }
        return out

    beats_v6 = rollup("risk_v6e_live")
    beats_v7 = rollup("risk_v7")
    return {
        "v6e": summarise(beats_v6, "v6e_live"),
        "v7": summarise(beats_v7, "v7_ignition"),
    }


def delta_block(summary: dict, kind: str) -> dict:
    out: dict = {}
    for band in ("recall_top_0.5pct", "recall_top_2pct", "recall_top_5pct"):
        v6 = summary["v6e"][kind][band] if summary["v6e"][kind] else None
        v7 = summary["v7"][kind][band] if summary["v7"][kind] else None
        out[band] = {
            "v6e": v6,
            "v7": v7,
            "delta_pp": (v7 - v6) * 100 if (v6 is not None and v7 is not None) else None,
        }
    return out


def print_report(summary: dict) -> None:
    print()
    print("=" * 72)
    print(" BEAT-LEVEL v7 vs v6e on 2026 HEATWAVE (per-day rank recall)")
    print("=" * 72)
    for kind in ("new", "persistent", "overall"):
        v6 = summary["v6e"].get(kind)
        v7 = summary["v7"].get(kind)
        if v6 is None or v7 is None:
            continue
        label = kind.upper()
        print(f"\n-- {label} --")
        print(f"  n_fire_beat_days: {v6['n']}")
        print(f"           {'v6e':>8s} {'v7':>8s} {'delta':>10s}")
        for band, tag in (
            ("recall_top_0.5pct", "top 0.5%"),
            ("recall_top_2pct",   "top 2.0%"),
            ("recall_top_5pct",   "top 5.0%"),
        ):
            a, b = v6[band], v7[band]
            print(
                f"  {tag:>8s} {a*100:>7.1f}% {b*100:>7.1f}%  {(b-a)*100:>+7.1f} pp"
            )
    print()


def main() -> int:
    if OUT_PRED.exists():
        log.info("Loading cached v7 predictions from %s", OUT_PRED.relative_to(ROOT))
        combined = pd.read_parquet(OUT_PRED)
    else:
        combined = score_window()

    summary = beat_eval(combined)
    summary["delta_new"] = delta_block(summary, "new")
    summary["delta_persistent"] = delta_block(summary, "persistent")
    summary["delta_overall"] = delta_block(summary, "overall")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str))
    log.info("Wrote %s", OUT_JSON.relative_to(ROOT))

    print_report(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
