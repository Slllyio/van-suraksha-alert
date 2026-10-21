"""One issue day end to end: build every division's feature table (build_day_features.py), then score it with the live
rule (live_score.py). Needs numpy, pandas, scipy, lightgbm (+ geopandas only to append new FIRMS rows).

Usage:
  python daily_run.py --date 2026-04-05 --models <pc_models> --gis static_gis_v1.parquet
      --fires fire_celldays.parquet [--firms new_firms.csv ...] --modis <dir> --dryness mp_dry_2026.npz
      --gfs gfs_daily.csv --swvl1 era5_swvl1.csv --state season_state.csv --out <dir>

  --models   folder with models/, calibration/, meta.json, static_inputs.parquet, modis_clim.parquet
  --fires    fire cell-days (date, row, col); --firms adds FIRMS CSVs/parquets (latitude, longitude, acq_date, acq_time,
             type), converted with make_fire_celldays.to_celldays
  --modis    folder with sr_<division>.parquet (date, cell, ndvi, ndmi; MOD09A1) and lst_<division>.parquet (date, cell,
             lst_k; MOD11A2), from 1 Sep of the previous year
  --gfs      daily GFS per division (division, date, t_mean, t_max, rh_mean, wind_mean, prcp), from 1 Oct of the previous year
  --swvl1    ERA5-Land soil moisture per division (division, date, swvl1), same period
  --state    running daily mean score per division (omit on the season's first issue day)
Writes <out>/features/<division>.parquet and, via live_score.py, flags_<date>.parquet, counts_<date>.csv, season_state.csv."""
import argparse, json, subprocess, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import build_day_features as B
import gfs_features as G


def main():
    ap = argparse.ArgumentParser()
    for a in ("--date", "--models", "--gis", "--fires", "--modis", "--dryness", "--gfs", "--swvl1", "--out"):
        ap.add_argument(a, required=True)
    ap.add_argument("--firms", nargs="*", default=[]); ap.add_argument("--state", default=None)
    a = ap.parse_args()
    t = pd.Timestamp(a.date); M = Path(a.models); out = Path(a.out); (out / "features").mkdir(parents=True, exist_ok=True)
    meta = json.loads((M / "meta.json").read_text())
    static = pd.read_parquet(M / "static_inputs.parquet"); clim = pd.read_parquet(M / "modis_clim.parquet")
    gis = pd.read_parquet(a.gis)
    fires = pd.read_parquet(a.fires)
    if a.firms:
        from make_fire_celldays import to_celldays
        new = [to_celldays(pd.read_parquet(f) if f.endswith(".parquet") else pd.read_csv(f)) for f in a.firms]
        fires = pd.concat([fires] + new, ignore_index=True).drop_duplicates()
    fires["date"] = pd.to_datetime(fires.date)
    npz = dict(np.load(a.dryness))
    gfs = pd.read_csv(a.gfs, parse_dates=["date"]); sw = pd.read_csv(a.swvl1, parse_dates=["date"])
    for dv, info in sorted(meta["divisions"].items()):
        cells = static.loc[static.division == dv, "cell"].to_numpy()
        div = B.Division(dv, cells)
        w = G.weather_table(gfs[gfs.division == dv].set_index("date"), sw[sw.division == dv].set_index("date").swvl1)
        sr = pd.read_parquet(Path(a.modis) / f"sr_{dv}.parquet"); lst = pd.read_parquet(Path(a.modis) / f"lst_{dv}.parquet")
        df = B.build(div, t, static, gis, fires, sr, lst, clim[clim.division == dv], npz, w.loc[t], info["features"])
        df.to_parquet(out / "features" / f"{dv}.parquet", index=False)
        print("features", dv, len(df), flush=True)
    cmd = [sys.executable, str(HERE / "live_score.py"), "--models", str(M), "--features", str(out / "features"),
           "--date", str(t.date()), "--out", str(out)]
    if a.state:
        cmd += ["--state", a.state]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
