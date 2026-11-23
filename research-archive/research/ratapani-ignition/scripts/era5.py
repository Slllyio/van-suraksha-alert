"""ERA5-Land hourly at 33 native 0.1 deg points -> daily per-point summary and nearest point per cell.
Outputs <out_dir>/era5_daily_points.parquet (date, point_id, tmax, tmin, rh_min, rh_pm, ws_pm, wd_pm, rain, soil, rad)
and <out_dir>/cell_point.csv (cell_id, point_id, dist_km).
Usage: python era5.py <era5_dir> <ign_dir> <out_dir>
"""
import os, sys, glob
import numpy as np, pandas as pd
from pyproj import Transformer


def rh(t, td):
    return 100 * np.exp(17.625 * td / (243.04 + td)) / np.exp(17.625 * t / (243.04 + t))


def main(era5_dir, ign_dir, out_dir):
    frames = []
    for f in sorted(glob.glob(os.path.join(era5_dir, "era5land_hourly_*.csv"))):
        d = pd.read_csv(f, parse_dates=["datetime_utc"])
        frames.append(d)
    h = pd.concat(frames, ignore_index=True)
    # point ids were assigned per file; redo them globally from coordinates
    pts = h[["longitude", "latitude"]].drop_duplicates().sort_values(["latitude", "longitude"]).reset_index(drop=True)
    pts["point_id"] = np.arange(len(pts))
    h = h.drop(columns="point_id").merge(pts, on=["longitude", "latitude"])
    h["t"] = h.temperature_2m - 273.15; h["td"] = h.dewpoint_temperature_2m - 273.15
    h["rh"] = rh(h.t, h.td)
    h["ws"] = np.hypot(h.u_component_of_wind_10m, h.v_component_of_wind_10m)
    h["local_date"] = (h.datetime_utc + pd.Timedelta(hours=5, minutes=30)).dt.date
    h["hour_utc"] = h.datetime_utc.dt.hour
    pm = h[(h.hour_utc >= 6) & (h.hour_utc <= 12)]
    g = h.groupby(["local_date", "point_id"])
    d = g.agg(tmax=("t", "max"), tmin=("t", "min"), rh_min=("rh", "min"), rain=("total_precipitation_hourly", "sum"),
              soil=("volumetric_soil_water_layer_1", "mean"), rad=("surface_solar_radiation_downwards_hourly", "sum"))
    gp = pm.groupby(["local_date", "point_id"])
    d["rh_pm"] = gp.rh.mean(); d["ws_pm"] = gp.ws.mean()
    u = gp.u_component_of_wind_10m.mean(); v = gp.v_component_of_wind_10m.mean()
    d["wd_pm"] = (np.degrees(np.arctan2(-u, -v)) + 360) % 360
    d["rain"] *= 1000   # m -> mm
    d["rad"] /= 1e6     # J/m2 -> MJ/m2
    d = d.reset_index().rename(columns={"local_date": "date"})
    d["date"] = pd.to_datetime(d.date)
    d.to_parquet(os.path.join(out_dir, "era5_daily_points.parquet"), index=False)
    pts.to_csv(os.path.join(out_dir, "era5_points.csv"), index=False)
    # nearest point per cell
    cells = pd.read_csv(os.path.join(ign_dir, "cells_static.csv"))
    sys.path.insert(0, "/mnt/project-files/research/ratapani-burn-labels/scripts"); import fetch
    cell = np.load(os.path.join(ign_dir, "cell_px.npy")); r, c = np.where(fetch.INSIDE); ok = cell >= 0
    n = cell.max() + 1; cnt = np.bincount(cell[ok], minlength=n)
    cx = fetch.TR.c + (np.bincount(cell[ok], weights=c[ok], minlength=n) / np.maximum(cnt, 1)) * fetch.RES
    cy = fetch.TR.f - (np.bincount(cell[ok], weights=r[ok], minlength=n) / np.maximum(cnt, 1)) * fetch.RES
    px, py = Transformer.from_crs("EPSG:4326", fetch.CRS, always_xy=True).transform(pts.longitude.values, pts.latitude.values)
    dist = np.hypot(cx[:, None] - px[None], cy[:, None] - py[None])
    j = dist.argmin(1)
    cp = pd.DataFrame(dict(cell_id=np.arange(n), point_id=pts.point_id.values[j], dist_km=dist[np.arange(n), j] / 1000))
    cp = cp[cp.cell_id.isin(cells.cell_id)]
    cp.to_csv(os.path.join(out_dir, "cell_point.csv"), index=False)
    print("points", len(pts), "daily rows", len(d), d.date.min().date(), d.date.max().date(), "cells per point",
          cp.point_id.value_counts().describe()[["min", "50%", "max"]].to_dict())
    # how much do points differ on a fire-season day? spread across points of rh_min and tmax
    s = d[(d.date.dt.month == 3)].groupby("date")[["rh_min", "tmax", "ws_pm"]].agg(["min", "max"])
    print("March, median across days of (max - min across points):",
          {k: round(float((s[(k, "max")] - s[(k, "min")]).median()), 2) for k in ("rh_min", "tmax", "ws_pm")})


if __name__ == "__main__":
    main(*sys.argv[1:4])
