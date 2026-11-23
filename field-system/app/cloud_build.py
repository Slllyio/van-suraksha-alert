"""Assemble one division's input table for pc_models/live_score.py from cloud sources only (pc_models/CLOUD_PLAN.md):
static_inputs.parquet + ratapani/mp_grid/static_gis_v1.parquet (fixed for the season), fire history (cloud_features),
GFS weather (cloud_gfs -> pc_models/gfs_features.py), ERA5 soil moisture (cloud_soil), MODIS (cloud_modis), HLS (cloud_hls)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
PCM = BASE / "pc_models"
GIS = Path("/mnt/project-files/ratapani/mp_grid/static_gis_v1.parquet")
sys.path.insert(0, str(PCM))


def static(division):
    st = pd.read_parquet(PCM / "static_inputs.parquet")
    st = st[st.division == division].drop(columns="division")
    gis = pd.read_parquet(GIS).drop(columns=["row", "col"])
    return st.merge(gis, on="cell", how="left").set_index("cell")


def hull(cells):
    from shapely.geometry import MultiPoint
    from pyproj import Transformer
    r, c = cells // 1829, cells % 1829
    lon, lat = Transformer.from_crs(32643, 4326, always_xy=True).transform(np.r_[399000 + c * 500, 399500 + c * 500],
                                                                        np.r_[2996000 - r * 500, 2995500 - r * 500])
    return MultiPoint(np.c_[lon, lat]).convex_hull


def hls_asof(cells, day, steps):
    """steps: {step date: cloud_hls.step() output}; latest step <= day, changes vs 1 and 3 steps before."""
    ds = sorted(k for k in steps if k <= pd.Timestamp(day))
    cur = steps[ds[-1]]
    p1 = steps[ds[-2]] if len(ds) > 1 else np.full_like(cur, np.nan)
    p3 = steps[ds[-4]] if len(ds) > 3 else np.full_like(cur, np.nan)
    f = {"hls_ndvi": cur[:, 0], "hls_ndmi": cur[:, 1], "hls_nbr": cur[:, 2], "hls_clear": cur[:, 3]}
    for j, c in enumerate(("ndvi", "ndmi", "nbr")):
        f[f"hls_{c}_d10"] = cur[:, j] - p1[:, j]
        f[f"hls_{c}_d30"] = cur[:, j] - p3[:, j]
    return pd.DataFrame(f, index=cells)


def build(division, day, fire, modis, gfs_daily, swvl1, hls):
    """fire: cloud_features.fire_history() frame; modis: cloud_modis.features() frame; gfs_daily: this division's
    daily GFS rows (date index; t_mean, t_max, rh_mean, wind_mean, prcp) from at least 60 days before; swvl1: daily
    soil-moisture series (date index; the value 5 days before `day` is used); hls: hls_asof() frame."""
    from gfs_features import weather_table, add_weather
    X = static(division)
    X = X.join(fire).join(modis).join(hls)
    w = weather_table(gfs_daily, swvl1)
    X = add_weather(X, w, day)
    X["spread_slope"] = X.nb3_d3 * X.slope_deg_mean
    X["quiet"] = X["quiet"].astype(np.uint8)
    return X.reset_index().rename(columns={"index": "cell"})
