"""Raw daily inputs for pc_models/daily_run.py / build_day_features.py, from cloud sources only (pc_models/CLOUD_PLAN.md).
The PC's exact feature builder needs, besides the shipped static tables, fire_celldays and modis_clim:
  sr_<division>.parquet / lst_<division>.parquet   MODIS composites per cell from 1 Sep of the previous year (cloud_modis)
  mp_dry_<season>.npz                              HLS 10-day dryness steps (cloud_hls)
  gfs_daily.csv                                     daily GFS per division (cloud_gfs)
  swvl1.csv                                         soil moisture per division (cloud_soil: ERA5, not ERA5-Land)
  new FIRMS rows                                    the app's own detections -> make_fire_celldays.to_celldays"""
import numpy as np
import pandas as pd

from . import cloud_modis, cloud_hls, cloud_gfs, cloud_soil
from .cloud_build import hull


def bbox(cells):
    from pyproj import Transformer
    xy, _ = cloud_hls._subgrid(cells)
    lon, lat = Transformer.from_crs(32643, 4326, always_xy=True).transform(xy[:, 0], xy[:, 1])
    return [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())]


def modis_tables(cells, d0, d1):
    """(sr, lst) long tables (date, cell, ndvi, ndmi) / (date, cell, lst_k) for composites starting in [d0, d1]."""
    vals = cloud_modis.load(cells, bbox(cells), d0, d1)
    sr, lst = [], []
    for k, v in vals.items():
        sr.append(pd.DataFrame({"date": k, "cell": cells, "ndvi": v[:, 0], "ndmi": v[:, 1]}))
        lst.append(pd.DataFrame({"date": k, "cell": cells, "lst_k": v[:, 2]}))
    return pd.concat(sr, ignore_index=True), pd.concat(lst, ignore_index=True)


def hls_npz(cells, steps, workers=1):
    """dict(cells, steps, X) like mp_dry_<season>.npz: X[step, cell, ndvi/ndmi/nbr x 1e4, clear %], int16, missing = -32768."""
    X = np.full((len(steps), len(cells), 4), -32768, np.int16)
    for i, s in enumerate(steps):
        v = cloud_hls.step(cells, pd.Timestamp(s))
        idx = np.where(np.isfinite(v[:, :3]), np.round(v[:, :3] * 10000), -32768)
        X[i, :, :3] = idx.astype(np.int16)
        X[i, :, 3] = np.where(np.isfinite(v[:, 3]), np.round(v[:, 3]), -1).astype(np.int16)
    return {"cells": np.asarray(cells, np.int32), "steps": np.asarray([str(pd.Timestamp(s).date()) for s in steps]), "X": X}


def weather(divs, d0, d1, soil_lag_days=5):
    """(gfs_daily, swvl1) for {division: cells} over IST days d0..d1 (soil from d0 - lag)."""
    H = {dv: hull(c) for dv, c in divs.items()}
    W = {dv: cloud_gfs.weights(h) for dv, h in H.items()}
    g = pd.concat([cloud_gfs.daily(d, H) for d in pd.date_range(d0, d1)], ignore_index=True)
    rows = []
    for d in pd.date_range(pd.Timestamp(d0) - pd.Timedelta(days=soil_lag_days), d1):
        for dv, v in cloud_soil.daily(d, W).items():
            rows.append(dict(division=dv, date=d, swvl1=v))
    return g, pd.DataFrame(rows)


def modis_frames(npz, cells, season):
    """(sr, lst) tables for build_day_features.modis() from pc_models/cloud_series/modis_<season>.npz (composites
    1 Sep of the year before .. 31 May)."""
    z = npz if isinstance(npz, dict) else dict(np.load(npz))
    pos = pd.Series(np.arange(len(z["cells"])), index=z["cells"]).reindex(np.asarray(cells)).to_numpy()
    ok = ~np.isnan(pos); p = pos[ok].astype(int); c = np.asarray(cells)[ok]
    dq = lambda a, s, o=0.0: np.where(a == -32768, np.nan, a / s + o).astype(np.float32)
    sr, lst = [], []
    for i, d in enumerate(pd.to_datetime(z["dates"])):
        sr.append(pd.DataFrame({"date": d, "cell": c, "ndvi": dq(z["ndvi"][i, p], 1e4), "ndmi": dq(z["ndmi"][i, p], 1e4)}))
        lst.append(pd.DataFrame({"date": d, "cell": c, "lst_k": dq(z["lst"][i, p], 50, 250)}))
    return pd.concat(sr, ignore_index=True), pd.concat(lst, ignore_index=True)
