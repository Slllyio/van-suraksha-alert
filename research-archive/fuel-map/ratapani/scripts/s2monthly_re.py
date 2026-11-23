"""Monthly Sentinel-2 median red-edge/SWIR reflectance (B05 B06 B8A B11 B12) for Feb Oct Dec May Apr; adapted from monthly NDVI + NDMI script., Sep-May of 2023-24 and 2024-25 pooled by calendar month (cloud <30%, SCL veg/soil only).
For phenology classes: deciduous tree, evergreen tree, shrub candidate, grass, bare."""
import numpy as np, rasterio, planetary_computer as pc, pystac_client, os
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import Affine
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
S = np.load('/tmp/claude-0/fuel/static10.npz'); W, H = int(S['W']), int(S['H']); TR = Affine(*S['transform']); CRS = 'EPSG:32643'
cat = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1', modifier=pc.sign_inplace)
bbox = [77.337, 22.816, 78.068, 23.107]; OD = '/tmp/claude-0/fuel/monthly_re/'; os.makedirs(OD, exist_ok=True)
def rd(href, rs):
    for k in range(4):
        try:
            with rasterio.open(href) as s, WarpedVRT(s, crs=CRS, transform=TR, width=W, height=H, resampling=rs, nodata=0) as v: return v.read(1)
        except Exception as e: err = e
    raise err
BANDS = ['B05', 'B06', 'B8A', 'B11', 'B12']
def one(it):
    ok = np.isin(rd(it.assets['SCL'].href, Resampling.nearest), [4, 5])
    if ok.sum() < 1e5: return None
    return [np.where(ok, rd(it.assets[b].href, Resampling.bilinear).astype('float32') / 10000, np.nan).astype('float16') for b in BANDS]
def day(its):
    m = None
    for it in its:
        x = one(it)
        if x is None: continue
        if m is None: m = [q.copy() for q in x]
        else:
            k = np.isnan(m[0]) & ~np.isnan(x[0])
            for j in range(len(m)): m[j][k] = x[j][k]
    return m
for mo in [2, 10, 12, 5, 4]:
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
    for j, nm in enumerate(BANDS):
        a = np.stack([q[j] for q in st]); med = np.empty((H, W), 'float16')
        for r in range(0, H, 256): med[r:r+256] = np.nanmedian(a[:, r:r+256].astype('float32'), 0)
        out[nm] = med; del a
    np.savez_compressed(f'{OD}m{mo:02d}.npz', **out); del st
print('done')
