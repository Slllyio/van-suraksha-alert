"""Grazing proxy check: does open grass (class 4) near buildings hold less dry matter (NDTI, Sentinel-2 B11/B12) and
burn less than far grass, relative to deciduous tree pixels? Also hazard of burning per window by distance band.
Pixels unburned in 2024 and 2025 for the index part. Scar outlines v2 FIRMS events."""
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.features import rasterize
from rasterio.enums import Resampling
R = '/mnt/project-files/fuel-map/ratapani/'; WK = R + 'work/'
src = rasterio.open(R + 'cover_phenology_10m.tif'); H, W = src.height // 2, src.width // 2
T = src.transform * src.transform.scale(2, 2)
cls = src.read(1, out_shape=(H, W), resampling=Resampling.mode)
g = gpd.read_file('/mnt/project-files/fire-alert-scars/reference/v2_2026-10-16/firms_event_scars.geojson', columns=['date']).to_crs(src.crs)
g = g[g.geometry.notna()]
g['date'] = pd.to_datetime(g.date); g['season'] = np.where(g.date.dt.month >= 8, g.date.dt.year + 1, g.date.dt.year)
g['dos'] = (g.date - pd.to_datetime((g.season - 1).astype(str) + '-11-01')).dt.days
FB = {}
for s, gs in g.groupby('season'):
    gs = gs.sort_values('dos', ascending=False)
    FB[s] = rasterize(((geom, int(d)) for geom, d in zip(gs.geometry, gs.dos)), out_shape=(H, W), transform=T, fill=-1, dtype='int16')
grid = gpd.read_file('/mnt/project-files/ratapani/grid_500m.geojson').to_crs(src.crs)
cid = rasterize(((geom, int(c)) for geom, c in zip(grid.geometry, grid.cell_id)), out_shape=(H, W), transform=T, fill=0, dtype='int32')
ob = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/openbuildings_cell_features.csv')[['cell_id', 'd_ob']]
dob = np.full(cid.max() + 1, np.nan); dob[ob.cell_id.values] = ob.d_ob.values
dpx = np.where(cid > 0, dob[cid], np.nan)
bands = [('<1 km', 0, 1000), ('1-2 km', 1000, 2000), ('2-3 km', 2000, 3000), ('>3 km', 3000, 1e9)]
unb = (FB[2024] < 0) & (FB[2025] < 0)
rows = []
for mo in [10, 12, 2, 4, 5]:
    q = np.load(f'{WK}monthly_re/m{mo:02d}.npz'); b11 = q['B11'][::2, ::2].astype('float32'); b12 = q['B12'][::2, ::2].astype('float32')
    ndti = (b11 - b12) / (b11 + b12)
    for k, nm in [(1, 'deciduous'), (4, 'grass')]:
        for lab, a, b in bands:
            m = (cls == k) & unb & (dpx >= a) & (dpx < b)
            rows.append(dict(month=mo, cls=nm, dist=lab, ndti=np.nanmedian(ndti[m]), b12=np.nanmedian(b12[m]), n=int(m.sum())))
N = pd.DataFrame(rows).pivot_table(index=['cls', 'dist'], columns='month', values='ndti')[[10, 12, 2, 4, 5]]
print('Median NDTI by month, unburned 2024-25 pixels'); print(N.round(3).to_string())
WIN = [('Nov-14Feb', 0, 106), ('15Feb-Mar', 106, 151), ('Apr-Jun', 151, 243)]
rows = []
seasons = [s for s in sorted(FB) if 2017 <= s <= 2026]
for k, nm in [(1, 'deciduous'), (4, 'grass')]:
    for lab, a, b in bands:
        m = (cls == k) & (dpx >= a) & (dpx < b)
        d = np.concatenate([FB[s][m] for s in seasons])
        r = dict(cls=nm, dist=lab)
        for wl, w0, w1 in WIN:
            r[wl] = 100 * ((d >= w0) & (d < w1)).sum() / ((d < 0) | (d >= w0)).sum()
        rows.append(r)
Z = pd.DataFrame(rows); print('\nHazard (% of still-unburned pixels that burn in window), pooled 2017-2026'); print(Z.round(2).to_string(index=False))
P = Z[Z.cls == 'grass'].set_index('dist').drop(columns='cls') / Z[Z.cls == 'deciduous'].set_index('dist').drop(columns='cls')
print('\nGrass / deciduous hazard ratio'); print(P.round(2).to_string())
