"""MODIS Terra 8-day inputs per 500 m mp_grid cell without Earth Engine (pc_models/CLOUD_PLAN.md), same recipe as the PC's
mp_ee.py: MOD09A1 NDVI = (b2-b1)/(b2+b1), NDMI = (b2-b6)/(b2+b6), masked to StateQA cloud state clear (bits 0-1 = 0) and no
shadow (bit 2 = 0); MOD11A2 LST_Day_1km x 0.02 (K). Cell value = mean over the cell (sampled on a 125 m sub-grid). A composite
is dated by its first day and counts as available 9 days later (mp_features.modis_asof). Read from Planetary Computer."""
import os
import numpy as np
import pandas as pd

from . import netenv
from .cloud_hls import STAC, _subgrid

SINU = "+proj=sinu +lon_0=0 +x_0=0 +y_0=0 +R=6371007.181 +units=m +no_defs"


def composites(lonlat_bbox, d0, d1, coll):
    """Terra composites starting in [d0, d1]: {start date: [items]} (one item per MODIS tile). Planetary Computer first;
    composites it lacks (it holds only 5 of the 16 Sep-Dec 2025 MOD09A1 over Ujjain) come from NASA LP DAAC as HDF4
    (Earthdata secret via the proxy, read with pyhdf)."""
    import json, urllib.request
    import pystac_client, planetary_computer as pc
    for k in range(4):
        try:
            cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)
            out = {}
            for it in cat.search(collections=[coll], bbox=lonlat_bbox, datetime=f"{d0}T00:00:00Z/{d1}T23:59:59Z").items():
                st = pd.Timestamp(it.properties["start_datetime"][:10])
                if it.id.startswith(("MOD09A1", "MOD11A2")) and pd.Timestamp(d0) <= st <= pd.Timestamp(d1):
                    out.setdefault(st, []).append(it)
            break
        except Exception:
            if k == 3:
                raise
            import time; time.sleep(20 * (k + 1))
    sn = "MOD09A1" if "09" in coll else "MOD11A2"
    u = (f"https://cmr.earthdata.nasa.gov/search/granules.json?short_name={sn}&version=061&page_size=2000"
         f"&bounding_box={','.join(f'{v:.5f}' for v in lonlat_bbox)}&temporal={d0}T00:00:00Z,{d1}T23:59:59Z")
    nasa = {}
    for k in range(4):
        try:
            feed = json.load(urllib.request.urlopen(u, timeout=120))["feed"]["entry"]; break
        except Exception:
            if k == 3:
                raise
            import time; time.sleep(20 * (k + 1))
    for g in feed:
        k = pd.Timestamp(g["time_start"][:10])
        if not (pd.Timestamp(d0) <= k <= pd.Timestamp(d1)):
            continue
        hv = g["producer_granule_id"].split(".")[2]                             # h24v06
        href = next(l["href"] for l in g["links"] if l["href"].startswith("https://data.lpdaac") and l["href"].endswith(".hdf"))
        nasa.setdefault(k, []).append(("nasa", href, int(hv[1:3]), int(hv[4:6])))
    for k, its in nasa.items():
        if len(out.get(k, [])) < len(its):
            out[k] = its
    return dict(sorted(out.items()))


_T = 1111950.5197665                                                            # MODIS sinusoidal tile size (m)
_CACHE = {}


def _nasa_band(item, sds):
    """(array, (x0, y0, pixel)) of one SDS of a NASA MODIS HDF4 tile (whole file read once, kept in memory)."""
    import tempfile
    from pyhdf.SD import SD, SDC
    _, href, h, v = item
    if (href, sds) not in _CACHE:
        if len(_CACHE) > 40:
            _CACHE.clear()
        with tempfile.NamedTemporaryFile(suffix=".hdf") as f:
            import subprocess
            subprocess.run(["curl", "-sS", "-L", "--retry", "6", "--retry-all-errors", "-C", "-", "-o", f.name, href],
                           check=True, timeout=1800)
            hd = SD(f.name, SDC.READ)
            for name in {"sur_refl_state_500m", "sur_refl_b01", "sur_refl_b02", "sur_refl_b06", "LST_Day_1km"} & set(hd.datasets()):
                _CACHE[(href, name)] = hd.select(name).get()
            hd.end()
    a = _CACHE[(href, sds)]
    return a, (-20015109.354 + h * _T, 10007554.677 - v * _T, _T / a.shape[0])


def _sample(items, asset, xs, ys):
    import rasterio
    v = np.full(len(xs), np.nan, np.float32)
    for it in items:
        if isinstance(it, tuple):
            a, (x0, y0, px) = _nasa_band(it, asset)
            col, row = np.floor((xs - x0) / px).astype(int), np.floor((y0 - ys) / px).astype(int)
            ok = (col >= 0) & (col < a.shape[1]) & (row >= 0) & (row < a.shape[0])
            v[ok] = a[row[ok], col[ok]]
            continue
        for k in range(4):
            try:
                with rasterio.open(it.assets[asset].href) as r:
                    a = r.read(1)
                    tr, W_, H_ = r.transform, r.width, r.height
                break
            except Exception:
                if k == 3:
                    raise
                import time
                time.sleep(10 * (k + 1))
        col, row = ~tr * (xs, ys)
        col, row = np.floor(col).astype(int), np.floor(row).astype(int)
        ok = (col >= 0) & (col < W_) & (row >= 0) & (row < H_)
        v[ok] = a[row[ok], col[ok]]
    return v


def composite_values(cells, start, items09, items11):
    """(len(cells), 3): ndvi, ndmi, lst_k for one composite."""
    netenv.setup()
    from pyproj import Transformer
    xy, idx = _subgrid(cells)
    xs, ys = Transformer.from_crs(32643, SINU, always_xy=True).transform(xy[:, 0], xy[:, 1])
    out = np.full((len(cells), 3), np.nan, np.float32)
    if items09:
        qa = _sample(items09, "sur_refl_state_500m", xs, ys)
        q = np.nan_to_num(qa, nan=3).astype(np.int64)
        clear = ((q & 3) == 0) & (((q >> 2) & 1) == 0)
        b1, b2, b6 = (_sample(items09, f"sur_refl_b0{k}", xs, ys) * 1e-4 for k in (1, 2, 6))
        with np.errstate(all="ignore"):
            nd = np.c_[(b2 - b1) / (b2 + b1), (b2 - b6) / (b2 + b6)]
        nd[~clear] = np.nan
        g = pd.DataFrame(nd, columns=["ndvi", "ndmi"]).assign(i=idx).groupby("i").mean()
        out[g.index.to_numpy(), :2] = g.to_numpy(np.float32)
    if items11:
        lst = _sample(items11, "LST_Day_1km", xs, ys)
        lst = np.where(lst > 0, lst * 0.02, np.nan)
        g = pd.DataFrame({"lst": lst, "i": idx}).groupby("i").lst.mean()
        out[g.index.to_numpy(), 2] = g.to_numpy(np.float32)
    return out


# ---- as-of inputs for an issue day (mp_features.py: modis_asof lag 9 / ffill limit 40, 14-day doy-bin anomalies, changes, leaf-fall)
LAG, LIMIT = pd.Timedelta(days=9), pd.Timedelta(days=40)
CLIM_YEARS = range(2014, 2025)          # the anomaly baseline the live models were built with (checked on Ujjain 5 Apr 2026)


def load(cells, lonlat_bbox, d0, d1):
    """{composite start: (len(cells), 3) ndvi, ndmi, lst_k} for composites starting in [d0, d1]."""
    c09 = composites(lonlat_bbox, d0, d1, "modis-09A1-061")
    c11 = composites(lonlat_bbox, d0, d1, "modis-11A2-061")
    return {k: composite_values(cells, k, c09.get(k, []), c11.get(k, [])) for k in sorted(set(c09) | set(c11))}


def asof(vals, day):
    """(n, 3) values on `day`: per cell the latest composite available (start + 9 d <= day) within the last 40 days."""
    day = pd.Timestamp(day)
    ks = sorted((k for k in vals if k + LAG <= day and day - (k + LAG) <= LIMIT), reverse=True)
    out = np.full(next(iter(vals.values())).shape, np.nan, np.float32)
    for k in ks:
        m = np.isnan(out)
        out[m] = vals[k][m]
    return out


def climatology(cells, lonlat_bbox, bins, years=CLIM_YEARS):
    """{doy bin (doy // 14): (n, 3) mean of the daily as-of values over that bin's days in `years`} (once per season)."""
    out = {}
    for b in bins:
        acc = []
        for Y in years:
            days = [d for d in pd.date_range(f"{Y}-01-01", f"{Y}-12-31") if d.dayofyear // 14 == b]
            vals = load(cells, lonlat_bbox, (days[0] - LAG - LIMIT).date(), (days[-1] - LAG).date())
            if vals:
                acc += [asof(vals, d) for d in days]
        with np.errstate(all="ignore"):
            import warnings
            warnings.simplefilter("ignore", RuntimeWarning)
            out[b] = np.nanmean(np.stack(acc), 0)
    return out


def features(cells, lonlat_bbox, day, clim):
    """MODIS columns of the live models for issue day `day`: ndvi, ndmi, lst_k, *_anom, ndmi_d16, ndvi/ndmi_chg16/32,
    ndvi_peak (90th percentile of Sep-Dec NDVI of the previous year), leaf_loss."""
    t = pd.Timestamp(day)
    vals = load(cells, lonlat_bbox, (t - pd.Timedelta(days=32) - LAG - LIMIT).date(), (t - LAG).date())
    cur, p16, p32 = asof(vals, t), asof(vals, t - pd.Timedelta(days=16)), asof(vals, t - pd.Timedelta(days=32))
    y0 = t.year - 1 if t.month < 9 else t.year
    pv = load(cells, lonlat_bbox, f"{y0}-09-01", f"{y0}-12-31")
    with np.errstate(all="ignore"):
        import warnings
        warnings.simplefilter("ignore", RuntimeWarning)
        peak = np.nanquantile(np.stack([v[:, 0] for v in pv.values()]), 0.9, axis=0) if pv else np.full(len(cells), np.nan)
    c = clim[t.dayofyear // 14]
    f = {"ndvi": cur[:, 0], "ndmi": cur[:, 1], "lst_k": cur[:, 2], "ndvi_anom": cur[:, 0] - c[:, 0], "ndmi_anom": cur[:, 1] - c[:, 1],
         "lst_k_anom": cur[:, 2] - c[:, 2], "ndmi_d16": cur[:, 1] - p16[:, 1], "ndvi_chg16": cur[:, 0] - p16[:, 0],
         "ndmi_chg16": cur[:, 1] - p16[:, 1], "ndvi_chg32": cur[:, 0] - p32[:, 0], "ndmi_chg32": cur[:, 1] - p32[:, 1],
         "ndvi_peak": peak, "leaf_loss": 1 - cur[:, 0] / peak}
    return pd.DataFrame({k: np.asarray(v, np.float32) for k, v in f.items()}, index=np.asarray(cells))
