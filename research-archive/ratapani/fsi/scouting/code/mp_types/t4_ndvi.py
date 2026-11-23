"""Leaf-fall curve by forest type and division from MODIS MOD13A1+MYD13A1 (500 m, 16-day, staggered = 8-day), seasons 2022 and 2023.
Sample: up to 60 random 60 m VTM forest pixels inside beats per division (labelled with VTM class group).
Per pixel: NDVI series Oct(Y-1)..Jun(Y) with pixel_reliability<=1; leaf-fall half date = first date after 1 Dec when NDVI falls below
min + 0.5*(Oct-Nov max - min), min = Jan-Jun 10th percentile. Keyless Planetary Computer STAC (SAS token fetched at run time, not stored).
Outputs: out/ndvi_samples.parquet, out/leaf_fall_division.csv, out/leaf_fall_type.csv"""
import json, urllib.request, numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.windows import from_bounds
from rasterio.features import rasterize
from pyproj import Transformer
rng = np.random.default_rng(0)
VTM = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r14_types_data/vtm.tif'
GROUPS = {'sal': [24, 27, 36], 'teak': [25, 28, 37], 'dry_mixed': [26], 'moist_mixed': [23], 'degraded': [106],
          'bamboo': [30, 40], 'north_dry': [29, 46, 49, 53, 54, 55, 116, 120, 121, 123, 124, 132, 135]}
c2g = {c: g for g, cs in GROUPS.items() for c in cs}
beats = gpd.read_file('/mnt/project-files/ratapani/beats/mp_beats.geojson')[['Division', 'geometry']].to_crs(32643)
divs = sorted(beats.Division.unique()); dcode = {d: i + 1 for i, d in enumerate(divs)}
r = rasterio.open(VTM)
w = from_bounds(*beats.total_bounds, r.transform).round_offsets().round_lengths()
a = r.read(1, window=w); T = r.window_transform(w)
idx = rasterize(((g, dcode[d]) for g, d in zip(beats.geometry, beats.Division)), out_shape=a.shape, transform=T, fill=0, dtype='int16')
fm = np.isin(a, list(c2g)) & (idx > 0)
rr, cc = np.nonzero(fm)
di = idx[rr, cc]
pick = []
for k in range(1, len(divs) + 1):
    ii = np.nonzero(di == k)[0]
    if len(ii): pick += list(rng.choice(ii, min(60, len(ii)), replace=False))
pick = np.array(pick)
xs, ys = rasterio.transform.xy(T, rr[pick], cc[pick])
S = pd.DataFrame({'x': xs, 'y': ys, 'div': [divs[k - 1] for k in di[pick]], 'vtm': a[rr[pick], cc[pick]]})
S['grp'] = S.vtm.map(c2g)
del a, idx, fm
print(len(S), S.grp.value_counts().to_dict(), flush=True)
lon, lat = Transformer.from_crs(32643, 4326, always_xy=True).transform(S.x.values, S.y.values)
S['lon'], S['lat'] = lon, lat
import urllib.parse
TOK = json.load(urllib.request.urlopen('https://planetarycomputer.microsoft.com/api/sas/v1/token/modiseuwest/modis-061-cogs'))['token']
def sign(h): return h + '?' + TOK
def search(dt):
    body = json.dumps({'collections': ['modis-13A1-061'], 'bbox': [74, 21, 83, 27], 'datetime': dt, 'limit': 500}).encode()
    req = urllib.request.Request('https://planetarycomputer.microsoft.com/api/stac/v1/search', data=body, headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req))['features']
rows = []
for Y in (2022, 2023):
    feats = search(f'{Y-1}-10-01/{Y}-06-30')
    print(Y, len(feats), flush=True)
    for f in feats:
        tile = f['id'].split('.')[2]
        if tile not in ('h24v06', 'h25v06', 'h24v07', 'h25v07'): continue
        date = pd.Timestamp(f['properties']['start_datetime'][:10]) + pd.Timedelta(days=8)
        u = sign(f['assets']['500m_16_days_NDVI']['href'])
        q = sign(f['assets']['500m_16_days_pixel_reliability']['href'])
        with rasterio.open(u) as src:
            tr = Transformer.from_crs(4326, src.crs, always_xy=True)
            X, Yy = tr.transform(S.lon.values, S.lat.values)
            rc = [src.index(x, y) for x, y in zip(X, Yy)]
            ri = np.array([p[0] for p in rc]); ci = np.array([p[1] for p in rc])
            ok = (ri >= 0) & (ri < src.height) & (ci >= 0) & (ci < src.width)
            if not ok.any(): continue
            arr = src.read(1)
        with rasterio.open(q) as src: rel = src.read(1)
        nd = np.full(len(S), np.nan)
        v = arr[ri[ok], ci[ok]].astype(float) * 1e-4; rl = rel[ri[ok], ci[ok]]
        v[(rl > 1) | (v < -0.2)] = np.nan
        nd[ok] = v
        for i in np.nonzero(ok)[0]:
            rows.append((i, Y, date, nd[i]))
N = pd.DataFrame(rows, columns=['i', 'season', 'date', 'ndvi']).dropna()
N = N.groupby(['i', 'season', 'date']).ndvi.mean().reset_index()
N.to_parquet('out/ndvi_samples.parquet'); S.to_parquet('out/ndvi_sample_points.parquet')
res = []
for (i, Y), x in N.groupby(['i', 'season']):
    x = x.sort_values('date')
    on = x[(x.date.dt.month >= 10) & (x.date.dt.year == Y - 1)]
    dry = x[(x.date.dt.year == Y) & (x.date.dt.month <= 6)]
    if len(on) < 3 or len(dry) < 8: continue
    hi = on.ndvi.max(); lo = dry.ndvi.quantile(0.1)
    if hi - lo < 0.05:
        res.append((i, Y, hi, lo, np.nan, np.nan, np.nan)); continue
    d = x[x.date >= pd.Timestamp(f'{Y-1}-12-01')]
    thr50 = lo + 0.5 * (hi - lo); thr80 = lo + 0.2 * (hi - lo)
    b50 = d[d.ndvi < thr50].date.min(); b80 = d[d.ndvi < thr80].date.min()
    tmin = dry.loc[dry.ndvi.idxmin(), 'date']
    res.append((i, Y, hi, lo, b50.dayofyear if pd.notna(b50) else np.nan, b80.dayofyear if pd.notna(b80) else np.nan, tmin.dayofyear))
R = pd.DataFrame(res, columns=['i', 'season', 'ndvi_wet', 'ndvi_dry', 'doy_50pct_drop', 'doy_80pct_drop', 'doy_min']).join(S, on='i')
R['amp'] = R.ndvi_wet - R.ndvi_dry
R.to_csv('out/leaf_fall_pixels.csv', index=False)
ft = R.groupby('grp').agg(n=('i', 'size'), ndvi_wet=('ndvi_wet', 'median'), ndvi_dry=('ndvi_dry', 'median'), amp=('amp', 'median'),
                          doy50=('doy_50pct_drop', 'median'), doy80=('doy_80pct_drop', 'median'), doymin=('doy_min', 'median'))
ft.to_csv('out/leaf_fall_type.csv', float_format='%.3g'); print(ft.round(3).to_string())
fd = R.groupby('div').agg(n=('i', 'size'), ndvi_wet=('ndvi_wet', 'median'), ndvi_dry=('ndvi_dry', 'median'), amp=('amp', 'median'),
                          doy50=('doy_50pct_drop', 'median'), doy80=('doy_80pct_drop', 'median'), doymin=('doy_min', 'median'))
fd.to_csv('out/leaf_fall_division.csv', float_format='%.3g'); print(fd.round(3).to_string())
