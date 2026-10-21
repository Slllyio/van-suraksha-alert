"""HLS 10-day dryness per 500 m mp_grid cell without Earth Engine (pc_models/CLOUD_PLAN.md), same recipe as the PC's
ratapani/mp_grid/dryness/mp_dry_pull.py: for step day d, every HLS S30/L30 look in [d-15, d), clear where Fmask bits 1-4
are off, NDVI / NDMI / NBR (S30 B8A,B04,B11,B12; L30 B05,B04,B06,B07), median over looks at ~120 m, mean over the 500 m
cell, plus the share of the cell with a clear look. Read from NASA LP DAAC (HLS v2.0 COGs found via CMR; the Earthdata
secret is added by the proxy; GDAL needs GDAL_CURL_CA_BUNDLE) at the COGs' 120 m overview, sampled on a 125 m sub-grid (4 x 4 per cell); EE's 120 m pyramid is not reproduced exactly, so values agree
closely but not to the digit (check: scripts/cloud_hls_check.py against the PC's mp_dry_<season>.npz). Microsoft Planetary
Computer (source="pc") misses many 2026 scenes (none over Ujjain 18 Mar-2 Apr 2026, where NASA has six), so NASA is the default."""
import os
import numpy as np
import pandas as pd

X0, Y1, S, W = 399000.0, 2996000.0, 500.0, 1829
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
BANDS = {"hls2-s30": ("B8A", "B04", "B11", "B12"), "hls2-l30": ("B05", "B04", "B06", "B07")}
SUB = 4
from . import netenv
netenv.setup()                                                                  # before GDAL first reads its config


def _subgrid(cells):
    """125 m sub-cell centres (EPSG:32643) for the given cells: (len(cells)*16, 2), and the cell index of each."""
    cells = np.asarray(cells)
    r, c = cells // W, cells % W
    o = (np.arange(SUB) + 0.5) * S / SUB
    ox, oy = np.meshgrid(o, o)
    x = (X0 + c * S)[:, None] + ox.ravel()[None]
    y = (Y1 - r * S)[:, None] - oy.ravel()[None]
    return np.c_[x.ravel(), y.ravel()], np.repeat(np.arange(len(cells)), SUB * SUB)


def looks(lonlat_bbox, d0, d1, source="nasa"):
    """[(collection, {band: href}, epsg)] for every HLS look in [d0, d1)."""
    if source == "pc":
        import pystac_client, planetary_computer as pc
        cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)
        out = []
        for coll in BANDS:
            for it in cat.search(collections=[coll], bbox=lonlat_bbox, datetime=f"{d0}T00:00:00Z/{d1}T00:00:00Z").items():
                epsg = it.properties.get("proj:epsg") or int(str(it.assets["Fmask"].extra_fields.get("proj:epsg", 32643)))
                out.append((coll, {k: a.href for k, a in it.assets.items()}, epsg))
        return out
    import json, urllib.request
    out = []
    for coll, sn in (("hls2-s30", "HLSS30"), ("hls2-l30", "HLSL30")):
        u = (f"https://cmr.earthdata.nasa.gov/search/granules.json?short_name={sn}&version=2.0&page_size=2000"
             f"&bounding_box={','.join(f'{v:.5f}' for v in lonlat_bbox)}&temporal={d0}T00:00:00Z,{d1}T00:00:00Z")
        for k in range(5):
            try:
                feed = json.load(urllib.request.urlopen(u, timeout=120))["feed"]["entry"]; break
            except Exception:
                if k == 4:
                    raise
                import time; time.sleep(10 * (k + 1))
        for g in feed:
            hrefs = {l["href"].rsplit(".", 2)[-2]: l["href"] for l in g["links"]
                     if l["href"].startswith("https://data.lpdaac") and l["href"].endswith(".tif")}
            if pd.Timestamp(g["time_start"][:10]) >= pd.Timestamp(d1):
                continue
            tile = g["producer_granule_id"].split(".")[2]                      # e.g. T43QEF
            out.append((coll, hrefs, 32600 + int(tile[1:3])))
    return out


def _read(href, xy_item, ovr_factor=4, nearest=False):
    for k in range(4):
        try:
            return _read1(href, xy_item, ovr_factor, nearest)
        except Exception:
            if k == 3:
                raise
            import time
            time.sleep(5 * (k + 1))


def _read1(href, xy_item, ovr_factor=4, nearest=False):
    import rasterio
    from rasterio.enums import Resampling
    with rasterio.open(href) as r:
        h, w = r.height // ovr_factor, r.width // ovr_factor
        a = r.read(1, out_shape=(h, w), resampling=Resampling.nearest if nearest else Resampling.average).astype(np.float32)
        tr = r.transform * r.transform.scale(r.width / w, r.height / h)
        nod = r.nodata
    col, row = ~tr * (xy_item[:, 0], xy_item[:, 1])
    col, row = np.floor(col).astype(int), np.floor(row).astype(int)
    ok = (col >= 0) & (col < w) & (row >= 0) & (row < h)
    v = np.full(len(xy_item), np.nan, np.float32)
    v[ok] = a[row[ok], col[ok]]
    if nod is not None:
        v[v == nod] = np.nan
    return v


def step(cells, d, source="nasa"):
    """(len(cells), 4) float32: ndvi, ndmi, nbr (NaN = no clear look) and clear % for step day d (Timestamp)."""
    netenv.setup()
    from pyproj import Transformer
    xy, idx = _subgrid(cells)
    lon, lat = Transformer.from_crs(32643, 4326, always_xy=True).transform(xy[:, 0], xy[:, 1])
    bbox = [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())]
    d = pd.Timestamp(d)
    stack = []
    for coll, hrefs, crs in looks(bbox, (d - pd.Timedelta(days=15)).date(), d.date(), source):
        tx, ty = Transformer.from_crs(32643, crs, always_xy=True).transform(xy[:, 0], xy[:, 1])
        p = np.c_[tx, ty]
        try:
            fm = _read(hrefs["Fmask"], p)      # averaged like the bands: drops cloud-edge looks (nearest left NDMI 0.011 high)
            clear = (np.nan_to_num(fm, nan=255).astype(np.int64) & 0b11110) == 0
            if not clear.any():
                continue
            nir, red, s1, s2 = (_read(hrefs[b], p) for b in BANDS[coll])
        except Exception as e:                 # an unreadable look is skipped, as if cloudy
            print("HLS look skipped:", hrefs.get("Fmask", "?").rsplit("/", 1)[-1], str(e)[:80], flush=True)
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            ind = np.stack([(nir - red) / (nir + red), (nir - s1) / (nir + s1), (nir - s2) / (nir + s2)], 1)
        ind[~clear] = np.nan
        stack.append(ind)
    out = np.full((len(cells), 4), np.nan, np.float32)
    if not stack:
        out[:, 3] = 0
        return out
    with np.errstate(all="ignore"):
        import warnings
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(np.stack(stack), 0)                        # (subcells, 3)
    df = pd.DataFrame(med, columns=["ndvi", "ndmi", "nbr"]).assign(i=idx, clear=np.isfinite(med[:, 0]) * 100.0)
    g = df.groupby("i").mean()
    out[g.index.to_numpy()] = g[["ndvi", "ndmi", "nbr", "clear"]].to_numpy(np.float32)
    return out


def step_fast(cells, d, threads=24, source="nasa"):
    """step() for many cells at once (statewide): looks read in parallel threads, only the sub-cells inside each look's
    tile kept, median taken over the kept values only (memory ~ sub-cells x looks per sub-cell, not x all looks).
    Same recipe and output as step()."""
    for k, v in (("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR"), ("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif"),
                 ("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES"), ("GDAL_HTTP_MULTIPLEX", "YES"), ("GDAL_HTTP_VERSION", "2")):
        os.environ.setdefault(k, v)                                   # ~3x faster opens on LP DAAC
    from concurrent.futures import ThreadPoolExecutor
    from pyproj import Transformer
    xy, idx = _subgrid(cells)
    lon, lat = Transformer.from_crs(32643, 4326, always_xy=True).transform(xy[:, 0], xy[:, 1])
    bbox = [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())]
    d = pd.Timestamp(d)
    L = looks(bbox, (d - pd.Timedelta(days=15)).date(), d.date(), source)
    tr = {}

    def one(item):
        coll, hrefs, crs = item
        if crs not in tr:
            tr[crs] = np.c_[Transformer.from_crs(32643, crs, always_xy=True).transform(xy[:, 0], xy[:, 1])]
        p = tr[crs]
        try:
            import rasterio
            with rasterio.open(hrefs["Fmask"]) as r:
                b = r.bounds
            sel = np.flatnonzero((p[:, 0] >= b.left) & (p[:, 0] < b.right) & (p[:, 1] > b.bottom) & (p[:, 1] <= b.top))
            if not len(sel):
                return None
            q = p[sel]
            fm = _read(hrefs["Fmask"], q)
            clear = (np.nan_to_num(fm, nan=255).astype(np.int64) & 0b11110) == 0
            sel, q = sel[clear], q[clear]
            if not len(sel):
                return None
            nir, red, s1, s2 = (_read(hrefs[k], q) for k in BANDS[coll])
        except Exception as e:
            print("HLS look skipped:", hrefs.get("Fmask", "?").rsplit("/", 1)[-1], str(e)[:80], flush=True)
            return None
        with np.errstate(invalid="ignore", divide="ignore"):
            ind = np.stack([(nir - red) / (nir + red), (nir - s1) / (nir + s1), (nir - s2) / (nir + s2)], 1)
        ok = np.isfinite(ind).all(1)
        return sel[ok].astype(np.int32), ind[ok].astype(np.float32)

    for crs in {c for _, _, c in L}:                                  # transforms once, outside the threads
        tr[crs] = np.c_[Transformer.from_crs(32643, crs, always_xy=True).transform(xy[:, 0], xy[:, 1])]
    with ThreadPoolExecutor(threads) as ex:
        parts = [r for r in ex.map(one, L) if r is not None]
    out = np.full((len(cells), 4), np.nan, np.float32); out[:, 3] = 0
    if not parts:
        return out
    si = np.concatenate([a for a, _ in parts]); v = np.concatenate([b for _, b in parts]); del parts
    med = pd.DataFrame(v, columns=["ndvi", "ndmi", "nbr"]).assign(s=si).groupby("s").median()
    full = np.full((len(xy), 3), np.nan, np.float32); full[med.index.to_numpy()] = med.to_numpy(np.float32)
    df = pd.DataFrame(full, columns=["ndvi", "ndmi", "nbr"]).assign(i=idx, clear=np.isfinite(full[:, 0]) * 100.0)
    g = df.groupby("i").mean()
    out[g.index.to_numpy()] = g[["ndvi", "ndmi", "nbr", "clear"]].to_numpy(np.float32)
    return out
