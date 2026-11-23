"""Monthly Sentinel-2 median NDVI + NDMI, Sep-May of 2023-24 and 2024-25 pooled by calendar month (cloud <30%, SCL veg/soil only).
For phenology classes: deciduous tree, evergreen tree, shrub candidate, grass, bare."""
import numpy as np, rasterio, planetary_computer as pc, pystac_client, os
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import Affine
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
S = np.load('/tmp/claude-0/fuel/static10.npz'); W, H = int(S['W']), int(S['H']); TR = Affine(*S['transform']); CRS = 'EPSG:32643'
cat = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1', modifier=pc.sign_inplace)
bbox = [77.337, 22.816, 78.068, 23.107]; OD = '/tmp/claude-0/fuel/monthly/'; os.makedirs(OD, exist_ok=True)
def rd(href, rs):
    for k in range(4):
        try:
            with rasterio.open(href) as s, WarpedVRT(s, crs=CRS, transform=TR, width=W, height=H, resampling=rs, nodata=0) as v: return v.read(1)
        except Exception as e: err = e
    raise err
def one(it):
    ok = np.isin(rd(it.assets['SCL'].href, Resampling.nearest), [4, 5])
    if ok.sum() < 1e5: return None
    r = rd(it.assets['B04'].href, Resampling.bilinear).astype('float32'); n = rd(it.assets['B08'].href, Resampling.bilinear).astype('float32')
    s1 = rd(it.assets['B11'].href, Resampling.bilinear).astype('float32')
    nd = np.where(ok & (r + n > 0), (n - r) / (n + r + 1e-6), np.nan); nm = np.where(ok & (s1 + n > 0), (n - s1) / (n + s1 + 1e-6), np.nan)
    return nd.astype('float16'), nm.astype('float16')
def day(its):
    m = None
    for it in its:
        x = one(it)
        if x is None: continue
        if m is None: m = [x[0].copy(), x[1].copy()]
        else:
            k = np.isnan(m[0]) & ~np.isnan(x[0]); m[0][k] = x[0][k]; m[1][k] = x[1][k]
    return m
for mo in [9, 10, 11, 12, 1, 2, 3, 4, 5]:
    if os.path.exists(f'{OD}m{mo:02d}.npz'): continue
    wins = []
    for y0 in (2023, 2024):
        y = y0 if mo >= 9 else y0 + 1
        e = 30 if mo in (9, 11, 4) else (28 if mo == 2 else 31)
        wins.append(f'{y}-{mo:02d}-01/{y}-{mo:02d}-{e}')
    items = [it for w in wins for it in cat.search(collections=['sentinel-2-l2a'], bbox=bbox, datetime=w, query={'eo:cloud_cover': {'lt': 30}}).items()]
    byd = defaultdict(list)
    for it in items: byd[it.datetime.date()].append(it)
    with ThreadPoolExecutor(3) as ex: st = [x for x in ex.map(day, byd.values()) if x is not None]
    print(mo, 'items', len(items), 'dates', len(st), flush=True)
    if not st: continue
    out = {}
    for j, nm in enumerate(['ndvi', 'ndmi']):
        a = np.stack([s[j] for s in st]); med = np.empty((H, W), 'float16')
        for r in range(0, H, 256): med[r:r+256] = np.nanmedian(a[:, r:r+256].astype('float32'), 0)
        out[nm] = med; out[nm + '_n'] = np.isfinite(a).sum(0).astype('uint8'); del a
    np.savez_compressed(f'{OD}m{mo:02d}.npz', **out); del st
print('done')
