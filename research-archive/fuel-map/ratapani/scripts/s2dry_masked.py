"""Sentinel-2 L2A 10 m median NDVI composites: leaf-on (Oct 15-Dec 15, 2023+2024) and dry season (Mar 1-Apr 30, 2024+2025)."""
import numpy as np, rasterio, planetary_computer as pc, pystac_client, sys
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import Affine
from concurrent.futures import ThreadPoolExecutor
S = np.load('/tmp/claude-0/fuel/static10.npz'); W, H = int(S['W']), int(S['H']); TR = Affine(*S['transform']); CRS = 'EPSG:32643'
cat = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1', modifier=pc.sign_inplace)
bbox = [77.337, 22.816, 78.068, 23.107]
def rd(href, rs):
    for k in range(4):
        try:
            with rasterio.open(href) as s, WarpedVRT(s, crs=CRS, transform=TR, width=W, height=H, resampling=rs, nodata=0) as v: return v.read(1)
        except Exception as e: err = e
    raise err
def one(it):
    scl = rd(it.assets['SCL'].href, Resampling.nearest)
    ok = np.isin(scl, [4, 5])
    if ok.sum() < 1e5: return None
    r = rd(it.assets['B04'].href, Resampling.bilinear).astype('float32'); n = rd(it.assets['B08'].href, Resampling.bilinear).astype('float32')
    nd = np.where(ok & (r + n > 0), (n - r) / (n + r + 1e-6), np.nan).astype('float32')
    return nd
out = {}
import rasterio as rio
def burnmask(y):
    with rio.open(f'/mnt/project-files/research/ratapani-burn-labels/rasters/burn_{y}.tif') as s: b = s.read(1) > -999
    return np.repeat(np.repeat(b, 2, 0), 2, 1)[:H, :W]
BM = {2024: burnmask(2024), 2025: burnmask(2025)}
for name, wins in (('dry', ['2024-03-01/2024-04-30', '2025-03-01/2025-04-30']),):
    items = [it for w in wins for it in cat.search(collections=['sentinel-2-l2a'], bbox=bbox, datetime=w, query={'eo:cloud_cover': {'lt': 20}}).items()]
    print(name, len(items), flush=True)
    from collections import defaultdict
    byd = defaultdict(list)
    for it in items: byd[it.datetime.date()].append(it)
    def day(its):
        m = None
        for it in its:
            x = one(it)
            if x is None: continue
            x[BM[it.datetime.year]] = np.nan   # drop pixels that burned that season: scars must not read as leaf fall
            if m is None: m = x
            else: k = np.isnan(m) & ~np.isnan(x); m[k] = x[k]
        return None if m is None else m.astype('float16')
    with ThreadPoolExecutor(3) as ex: stack = [x for x in ex.map(day, byd.values()) if x is not None]
    stack = np.stack(stack); print(name, 'dates', len(stack), flush=True)
    med = np.empty((H, W), 'float32')
    for r in range(0, H, 256): med[r:r+256] = np.nanmedian(stack[:, r:r+256].astype('float32'), 0)
    out[name] = med; out[name + '_n'] = np.isfinite(stack).sum(0).astype('uint8')
    del stack
old = dict(np.load('/tmp/claude-0/fuel/s2ndvi10.npz')); old['dry_unmasked'] = old['dry']; old.update(out); out = old
np.savez_compressed('/tmp/claude-0/fuel/s2ndvi10.npz', **out)
ins = S['inside']; print({k: float(np.nanmean(v[ins])) for k, v in out.items()})
