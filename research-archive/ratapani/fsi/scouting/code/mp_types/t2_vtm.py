"""Roy et al. 2015 Vegetation Type Map (Zenodo 11615011, 60 m) over MP forest beats.
Outputs: out/beat_vtm.csv (per beat: area per VTM class group), out/viirs_vtm.parquet (VTM class of each in-beat VIIRS point),
out/type_density.csv (VIIRS density per VTM class inside beats, S-NPP 2014-2026)."""
import rasterio, numpy as np, pandas as pd, geopandas as gpd
from rasterio.windows import from_bounds
from rasterio.features import rasterize
VTM = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r14_types_data/vtm.tif'
att = pd.read_csv('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r14_types_data/VegAttributes.csv', encoding='utf-8-sig')
names = dict(zip(att.Value, att.Class_name))
beats = gpd.read_file('/mnt/project-files/ratapani/beats/mp_beats.geojson')[['beat_uid', 'Division', 'Beat_Ar', 'geometry']].to_crs(32643)
r = rasterio.open(VTM)
b = beats.total_bounds
w = from_bounds(*b, r.transform).round_offsets().round_lengths()
a = r.read(1, window=w); T = r.window_transform(w)
print('window', a.shape)
idx = rasterize(((g, i + 1) for i, g in enumerate(beats.geometry)), out_shape=a.shape, transform=T, fill=0, dtype='int32')
m = idx > 0
k = idx[m].astype(np.int64); v = a[m].astype(np.int64)
v[v < 0] = 0
NC = int(v.max()) + 1
cnt = np.bincount(k * NC + v, minlength=(len(beats) + 1) * NC).reshape(len(beats) + 1, NC)[1:]
ha = cnt * 0.36
cols = [c for c in range(NC) if cnt[:, c].sum() > 0]
df = pd.DataFrame(ha[:, cols], columns=[f'{c}:{names.get(c, "")}' for c in cols])
df.insert(0, 'beat_uid', beats.beat_uid.values); df.insert(1, 'Division', beats.Division.values)
df.to_csv('out/beat_vtm.csv', index=False)
tot = df.iloc[:, 2:].sum().sort_values(ascending=False)
print((tot / tot.sum() * 100).round(2).head(30))
# VIIRS points -> VTM class
p = pd.read_parquet('out/viirs_mp_beats.parquet')
xy = gpd.GeoSeries(gpd.points_from_xy(p.longitude, p.latitude), crs=4326).to_crs(32643)
rows, colsx = rasterio.transform.rowcol(T, xy.x.values, xy.y.values)
rows = np.clip(np.array(rows), 0, a.shape[0] - 1); colsx = np.clip(np.array(colsx), 0, a.shape[1] - 1)
p['vtm'] = a[rows, colsx]
p['vtm_name'] = p.vtm.map(names)
p.to_parquet('out/viirs_vtm.parquet')
s = p[p.sat == 'snpp']
area_km2 = (tot / 100)
g = s.groupby('vtm').agg(n=('vtm', 'size'), night=('daynight', lambda x: (x == 'N').mean()), doy_med=('doy', 'median'),
                         early=('doy', lambda x: (x < 46).mean()), late=('doy', lambda x: (x > 135).mean()), frp_med=('frp', 'median'))
g['name'] = g.index.map(names)
g['km2'] = [area_km2.get(f'{c}:{names.get(c, "")}', np.nan) for c in g.index]
g['pts_per_km2_yr'] = g.n / g.km2 / 13
g = g[g.km2 > 50].sort_values('km2', ascending=False)
g.to_csv('out/type_density.csv')
print(g.round(3).to_string())
