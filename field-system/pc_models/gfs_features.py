"""GFS -> weather features of the live models (the code path of mp_forward.py with MP_WEATHER=gfs), standalone.

1) Daily GFS per division (gfs_pull.py, Earth Engine NOAA/GFS0P25): for IST issue day D, the 00Z run of D
   (out by ~10:00 IST), forecast hours 3..24 every 3 h, mean over the division's convex hull at 27.83 km:
     t_mean, t_max (deg C, of the 3-hourly 2 m temperature), rh_mean (%), wind_mean (m/s, mean of hypot(u10, v10)),
     prcp (mm: sum of the 6-hourly total_precipitation_surface buckets at hours 6, 12, 18, 24).
2) Soil moisture: ERA5-Land daily volumetric_soil_water_layer_1, division mean, taken from 5 days earlier (what exists
   on the issue morning).
3) This module turns those daily series into the model columns. Every square of a division gets the same values.

The series must start well before the season (the pipeline uses 1 Oct of the previous year; 30 days is the minimum
for prcp_30 and up to 60 for dry_days) and have one row per calendar day."""
import numpy as np
import pandas as pd

WCOLS = ["tmax", "rh", "vpd_max", "wind", "prcp_mm", "swvl1", "prcp_7", "prcp_30", "dry_days", "vpd_3"]


def es(t):
    """saturation vapour pressure (kPa) at t deg C (Tetens)."""
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def weather_table(gfs: pd.DataFrame, swvl1: pd.Series) -> pd.DataFrame:
    """gfs: daily rows indexed by date with t_mean, t_max, rh_mean, wind_mean, prcp (one division).
    swvl1: ERA5-Land volumetric_soil_water_layer_1 indexed by date (same division), NOT yet lagged.
    Returns the daily weather columns indexed by date."""
    days = pd.date_range(gfs.index.min(), gfs.index.max())
    g = gfs.reindex(days)
    w = pd.DataFrame(index=days)
    w["tmax"] = g.t_max
    w["rh"] = g.rh_mean
    w["vpd_max"] = es(g.t_max) - g.rh_mean / 100 * es(g.t_mean)
    w["wind"] = g.wind_mean
    w["prcp_mm"] = g.prcp.clip(lower=0)
    w["swvl1"] = swvl1.reindex(days).shift(5)
    w["prcp_7"] = w.prcp_mm.rolling(7, min_periods=1).sum()
    w["prcp_30"] = w.prcp_mm.rolling(30, min_periods=1).sum()
    since = np.zeros(len(days)); cnt = 60
    for k, wet in enumerate((w.prcp_mm > 1).to_numpy()):          # days since > 1 mm of rain, capped at 60
        cnt = 0 if wet else min(cnt + 1, 60); since[k] = cnt
    w["dry_days"] = since
    w["vpd_3"] = w.vpd_max.rolling(3, min_periods=1).mean()
    return w.astype(np.float32)


def add_weather(features: pd.DataFrame, w: pd.DataFrame, date) -> pd.DataFrame:
    """put one day's weather on every square of a division table and recompute the two weather interactions
    (needs the fire-history columns nb7_d3 and fdist_d7 already in the table)."""
    row = w.loc[pd.Timestamp(date)]
    out = features.assign(**{c: np.float32(row[c]) for c in WCOLS})
    return out.assign(spread_vpd=(out.nb7_d3 * out.vpd_max).astype(np.float32),
                      dry_nearfire=(out.dry_days / (1 + out.fdist_d7)).astype(np.float32))


if __name__ == "__main__":
    # self-check against the PC's stored 2026-04-05 table for one division
    import sys
    from pathlib import Path
    div, gfs_csv, era5_csv, table = sys.argv[1:5]
    g = pd.read_csv(gfs_csv, parse_dates=["date"]); g = g[g.division == div].set_index("date")
    e = pd.read_csv(era5_csv); e.index = pd.to_datetime(e.time.str[:10])
    w = weather_table(g, e.volumetric_soil_water_layer_1)
    t = pd.read_parquet(table)
    new = add_weather(t.drop(columns=WCOLS + ["spread_vpd", "dry_nearfire"]), w, "2026-04-05")
    for c in WCOLS + ["spread_vpd", "dry_nearfire"]:
        print(c, float(np.nanmax(np.abs(new[c].to_numpy() - t[c].to_numpy()))))
