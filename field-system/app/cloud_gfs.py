"""Daily GFS weather per division without Earth Engine (pc_models/CLOUD_PLAN.md), reproducing pc_models/gfs_pull.py:
for IST issue day D, the 00Z run of D, forecast hours 3..24 every 3 h -> t_mean, t_max (deg C, of the 3-hourly 2 m
temperature), rh_mean (%), wind_mean (mean of hypot(u10, v10)), prcp (mm, sum of the 6-hour buckets ending at hours 6, 12,
18, 24); mean over the division's convex hull, each 0.25 deg GFS cell weighted by the share of it inside the hull (as an
Earth Engine mean reducer). Read from NOAA's public GFS bucket on AWS (noaa-gfs-bdp-pds), only the needed GRIB records
by byte range. pc_models/gfs_features.py turns the daily series into the model columns."""
import urllib.error, urllib.request
import numpy as np
import pandas as pd

BUCKET = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
LAT0, LAT1, LON0, LON1 = 20.0, 28.0, 73.0, 84.0                     # MP with margin
WANT = {"TMP:2 m above ground", "RH:2 m above ground", "UGRD:10 m above ground", "VGRD:10 m above ground"}


def _get(url, rng=None):
    req = urllib.request.Request(url, headers={"Range": f"bytes={rng[0]}-{rng[1]}"} if rng else {})
    for k in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404 or k == 4:                                  # not on the bucket (yet): no point retrying
                raise
            import time
            time.sleep(3 * (k + 1))
        except Exception:
            if k == 4:
                raise
            import time
            time.sleep(3 * (k + 1))


def _field(msg):
    import eccodes
    h = eccodes.codes_new_from_message(msg)
    try:
        nj, ni = eccodes.codes_get(h, "Nj"), eccodes.codes_get(h, "Ni")
        v = eccodes.codes_get_values(h).reshape(nj, ni)                 # lat 90 -> -90, lon 0 -> 359.75
    finally:
        eccodes.codes_release(h)
    lat = 90 - 0.25 * np.arange(nj)
    lon = 0.25 * np.arange(ni)
    r = (lat >= LAT0) & (lat <= LAT1)
    c = (lon >= LON0) & (lon <= LON1)
    return v[np.ix_(r, c)]


def records(day, hour, cycle=0):
    """{name: 2-D field} for one forecast hour of the 00Z run of `day` (cycle=18: the 18Z run of the day before, at the
    same valid time; its 6-hour rain buckets end at the same hours)."""
    run = pd.Timestamp(day) - pd.Timedelta(hours=(24 - cycle) % 24)
    hour = hour + (24 - cycle) % 24
    base = f"{BUCKET}/gfs.{run:%Y%m%d}/{run.hour:02d}/atmos/gfs.t{run.hour:02d}z.pgrb2.0p25.f{hour:03d}"
    idx = _get(base + ".idx").decode().strip().split("\n")
    rows = [l.split(":") for l in idx]
    out = {}
    for i, r in enumerate(rows):
        name = f"{r[3]}:{r[4]}"
        bucket = r[5].strip()
        take = name in WANT or (name == "APCP:surface" and bucket == f"{hour - 6}-{hour} hour acc fcst")
        if not take or name in out or (name == "APCP:surface" and "APCP" in out):
            continue
        end = int(rows[i + 1][1]) - 1 if i + 1 < len(rows) else None
        out["APCP" if name == "APCP:surface" else name] = _field(_get(base, (int(r[1]), end)))
    return out


def weights(hull_lonlat):
    """share of each 0.25 deg cell (on the subset grid) inside the polygon (shapely, lon/lat)."""
    from shapely.geometry import box
    lat = 90 - 0.25 * np.arange(int((90 - LAT0) / 0.25) + 1)
    lat = lat[(lat >= LAT0) & (lat <= LAT1)]
    lon = 0.25 * np.arange(int(LON1 / 0.25) + 1)
    lon = lon[(lon >= LON0) & (lon <= LON1)]
    w = np.zeros((len(lat), len(lon)))
    x0, y0, x1, y1 = hull_lonlat.bounds
    for i, la in enumerate(lat):
        if la + 0.125 < y0 or la - 0.125 > y1:
            continue
        for j, lo in enumerate(lon):
            if lo + 0.125 < x0 or lo - 0.125 > x1:
                continue
            w[i, j] = box(lo - 0.125, la - 0.125, lo + 0.125, la + 0.125).intersection(hull_lonlat).area / 0.0625
    return w


def daily(day, hulls):
    """DataFrame (division, date, t_mean, t_max, rh_mean, wind_mean, prcp, cycle) for IST issue day `day`. hulls: {division:
    polygon}. When the 00Z run is missing on the bucket, the 18Z run of the day before stands in (same valid times)."""
    try:
        return _daily(day, hulls, 0).assign(cycle="00Z")
    except Exception as e:
        print("GFS 00Z", pd.Timestamp(day).date(), "missing:", str(e)[:80], "- using 18Z of the day before", flush=True)
        return _daily(day, hulls, 18).assign(cycle="18Z-1")


_W = {}


def _daily(day, hulls, cycle):
    key = tuple(sorted((dv, h.wkt) for dv, h in hulls.items()))
    if key not in _W:
        _W.clear(); _W[key] = {dv: weights(h) for dv, h in hulls.items()}
    W = _W[key]
    t, rh, wind, pr = [], [], [], []
    for h in range(3, 25, 3):
        f = records(day, h, cycle)
        t.append(f["TMP:2 m above ground"] - 273.15); rh.append(f["RH:2 m above ground"])
        wind.append(np.hypot(f["UGRD:10 m above ground"], f["VGRD:10 m above ground"]))
        if h % 6 == 0:
            pr.append(f["APCP"])
    T, RH, WD, P = np.stack(t), np.stack(rh), np.stack(wind), np.sum(pr, 0)
    rows = []
    for dv, w in W.items():
        m = lambda a: float((a * w).sum() / w.sum())
        rows.append(dict(division=dv, date=pd.Timestamp(day), t_mean=m(T.mean(0)), t_max=m(T.max(0)), rh_mean=m(RH.mean(0)),
                         wind_mean=m(WD.mean(0)), prcp=m(P)))
    return pd.DataFrame(rows)
