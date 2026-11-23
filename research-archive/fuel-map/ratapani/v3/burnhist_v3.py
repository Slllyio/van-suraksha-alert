"""Burn history 2017-2026 at 10 m from the frozen scar outlines v1 (2026-10-15): FIRMS + FSI event polygons.
Season = Nov-Jun, labelled by the Jan-Jun year. Outputs (10 m, EPSG:32643, fuel-map grid):
  burn_seasons_bitmask_10m.tif  uint16, bit k set if burned in season 2017+k
  burn_count_10m.tif            uint8, number of seasons burned 2017-2026
  last_burn_day_10m.tif         uint16, alert date of the latest fire as days since 2016-11-01 (0 = never)
Truth = scar outlines v1 (2026-10-15), error bands per fire-alert-scars/reference/v1_2026-10-15/USE_AND_LIMITS.md
(outlines lean small: medium/large fires ~10-20% under-drawn, small fires ~half; 9% false edge)."""
import json, numpy as np, rasterio, pandas as pd
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely.ops import transform as stx
from pyproj import Transformer
from affine import Affine
R = '/mnt/project-files/fire-alert-scars/reference/v1_2026-10-15/'
OUT = '/mnt/project-files/fuel-map/ratapani/v3/'
W, H = 7544, 3348; TR = Affine(10, 0, 739300, 0, -10, 2558500)
tr = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
bits = np.zeros((H, W), np.uint16); last = np.zeros((H, W), np.uint16)
base = pd.Timestamp('2016-11-01'); n = {}
for f in ('firms_event_scars.geojson', 'fsi_event_scars.geojson'):
    g = json.load(open(R + f))
    for ft in g['features']:
        p = ft['properties']; d = pd.Timestamp(str(p.get('date'))[:10])
        if pd.isna(d) or not ft['geometry']: continue
        season = d.year + (1 if d.month >= 11 else 0)
        if not 2017 <= season <= 2026: continue
        geom = stx(tr, shape(ft['geometry']))
        x0, y0, x1, y1 = geom.bounds
        j0, i0 = max(int((x0 - TR.c) // 10), 0), max(int((TR.f - y1) // 10), 0)
        j1, i1 = min(int((x1 - TR.c) // 10) + 1, W), min(int((TR.f - y0) // 10) + 1, H)
        if j1 <= j0 or i1 <= i0: continue
        m = rasterize([geom], out_shape=(i1 - i0, j1 - j0), transform=Affine(10, 0, TR.c + j0 * 10, 0, -10, TR.f - i0 * 10)).astype(bool)
        bits[i0:i1, j0:j1][m] |= np.uint16(1 << (season - 2017))
        dd = (d - base).days; sub = last[i0:i1, j0:j1]; sub[m] = np.maximum(sub[m], dd)
        n[f] = n.get(f, 0) + 1
cnt = np.zeros((H, W), np.uint8)
for k in range(10): cnt += ((bits >> k) & 1).astype(np.uint8)
prof = dict(driver='GTiff', width=W, height=H, count=1, crs='EPSG:32643', transform=TR, compress='deflate')
for name, a in (('burn_seasons_bitmask_10m.tif', bits), ('burn_count_10m.tif', cnt), ('last_burn_day_10m.tif', last)):
    with rasterio.open(OUT + name, 'w', dtype=a.dtype, **prof) as s: s.write(a, 1)
inside = np.load('/tmp/claude-0/fuel/static10.npz')['inside']
print(n); print('share of sanctuary ever burned 2017-26', (cnt[inside] > 0).mean().round(3), 'mean seasons burned', cnt[inside].mean().round(2))
print('per season burned share', [round(float(((bits[inside] >> k) & 1).mean()), 3) for k in range(10)])
