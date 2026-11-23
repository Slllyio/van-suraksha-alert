"""ERA5 -> ERA5-Land top-layer soil moisture, per division (cloud scoring without Earth Engine).

The live models were trained on ERA5-Land volumetric_soil_water_layer_1 (division mean, 5 days old). The cloud reads
plain ERA5 from Google's public ARCO-ERA5 (app/cloud_soil.py), which is wetter and smoother. This maps it onto the
ERA5-Land scale by per-division quantile mapping: 101 quantiles of each series over the days both exist.

Fit:   python soil_map.py fit ERA5LAND_CSV CLOUD_CSV [CLOUD_CSV ...]   -> soil_map.csv (division, q, era5, era5land)
Use:   from soil_map import load, apply;  M = load();  swvl1_landlike = apply(M, division, era5_values)

Check (20 Oct 2026), fit on 2025 season only, tested on 2026 season (Feb-Jun):
  error vs ERA5-Land  raw 0.030 (bias +0.028)  ->  mapped 0.006 (bias +0.001); per-division r median 0.97.
  5-check-day statewide replay (field-system scripts/cloud_replay.py, everything else the same):
  same flags as PC 92.2% raw -> 94.2% mapped (95.3% with true ERA5-Land); fires caught PC 60.1%, cloud 60.6%.
The shipped soil_map.csv is fitted on both seasons (Sep 2024 - Jun 2026)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
QS = np.linspace(0, 1, 101)


def fit(el_csv, cloud_csvs):
    el = pd.read_csv(el_csv, parse_dates=["date"])
    cl = pd.concat([pd.read_csv(f, parse_dates=["date"]) for f in cloud_csvs])
    m = cl.merge(el, on=["division", "date"], suffixes=("_e5", "_el")).dropna()
    rows = [pd.DataFrame({"division": dv, "q": QS, "era5": np.quantile(g.swvl1_e5, QS), "era5land": np.quantile(g.swvl1_el, QS)})
            for dv, g in m.groupby("division")]
    return pd.concat(rows, ignore_index=True)


def load(path=HERE / "soil_map.csv"):
    t = pd.read_csv(path)
    return {dv: (g.era5.to_numpy(), g.era5land.to_numpy()) for dv, g in t.groupby("division")}


def apply(M, division, values):
    x, y = M[division]
    return np.interp(np.asarray(values, float), x, y)


if __name__ == "__main__" and sys.argv[1:2] == ["fit"]:
    fit(sys.argv[2], sys.argv[3:]).to_csv(HERE / "soil_map.csv", index=False)
