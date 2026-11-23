"""Absolute VIIRS position error from fixed industrial heat sources (Akkshay 18 Oct 04:32Z: "offset error in distance and
direction, very deeply and scientifically").
Why static sources: a steel plant or kiln does not move or grow, so fire size, fire movement and the time gap between sensors
all drop out. The research thread (squares_v2_tracking.md 1a) measured offsets between satellites at 91 such sites, but only
relative to the mean of all VIIRS points; the absolute truth was missing. Here the truth is the 20 m Sentinel-2 SWIR hot area of
each site (hot = B12 above B11 and bright, i.e. emitting at 2.2 um; S2 geolocation error < 12 m), averaged over many clear scenes.
Stage 1: sites = DBSCAN clusters of FIRMS type-2 (static land source) VIIRS points, all MP, 2014-26, >=100 points over >=3 years.
Stage 2: S2 truth per site (Planetary Computer, no login). Out: results/static_sites.csv (site, VIIRS mean, S2 truth, extent)."""
import os, sys, glob, json, warnings, numpy as np, pandas as pd, rasterio, pystac_client, planetary_computer as pc
from rasterio.windows import from_bounds
from pyproj import Transformer
from sklearn.cluster import DBSCAN
from concurrent.futures import ThreadPoolExecutor
warnings.filterwarnings('ignore')
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif,.TIF', GDAL_HTTP_MAX_RETRY='5', GDAL_HTTP_RETRY_DELAY='2')
R = '/mnt/project-files/research/big-fires/results'; AM = '/mnt/project-files/fire-alert-scars/alerts_mp'
SC = '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/static'
NSC = int(os.environ.get('NSCENES', 30))
A = pd.concat([pd.read_csv(f).assign(sat=os.path.basename(f).split('_')[0]) for f in sorted(glob.glob(f'{AM}/viirs-*.csv'))], ignore_index=True)
S = A[A.type == 2].copy(); S['year'] = S.acq_date.str[:4].astype(int)
to43 = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True); S['x'], S['y'] = to43.transform(S.longitude.values, S.latitude.values)
S['site'] = DBSCAN(eps=750, min_samples=20).fit_predict(S[['x', 'y']].values)
g = S[S.site >= 0].groupby('site').agg(n=('x', 'size'), years=('year', 'nunique'), lat=('latitude', 'mean'), lon=('longitude', 'mean'),
                                         sx=('x', 'std'), sy=('y', 'std'))
sites = g[(g.n >= 100) & (g.years >= 3)].reset_index(); print('static points', len(S), 'clusters', S.site.nunique() - 1, 'kept sites', len(sites), flush=True)
S.to_parquet(f'{SC}/static_points.parquet')
# ---- stage 2: Sentinel-2 truth
cat = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1')
def scenes(lon, lat):
    its = []
    for yr in range(2019, 2026):
        its += list(cat.search(collections=['sentinel-2-l2a'], intersects={'type': 'Point', 'coordinates': [lon, lat]},
                               datetime=f'{yr}-01-01/{yr}-06-30', query={'eo:cloud_cover': {'lt': 15}}).items())
    its.sort(key=lambda i: i.properties['eo:cloud_cover'])
    # spread over years: round-robin by year
    by = {}
    for i in its: by.setdefault(i.datetime.year, []).append(i)
    out = []
    while len(out) < NSC and any(by.values()):
        for y in sorted(by):
            if by[y] and len(out) < NSC: out.append(by[y].pop(0))
    return out
def read(it, lon, lat):
    it = pc.sign(it); b = {}
    with rasterio.open(it.assets['B12'].href) as src:
        crs = src.crs; tx, ty = Transformer.from_crs('EPSG:4326', crs, always_xy=True).transform(lon, lat)
        bounds = (tx - 1500, ty - 1500, tx + 1500, ty + 1500); w = from_bounds(*bounds, src.transform)
        b['B12'] = src.read(1, window=w, out_shape=(150, 150), boundless=True, fill_value=0).astype(np.float32)
    for k in ['B11', 'B8A']:
        with rasterio.open(it.assets[k].href) as src:
            b[k] = src.read(1, window=from_bounds(*bounds, src.transform), out_shape=(150, 150), boundless=True, fill_value=0).astype(np.float32)
    off = 1000 if float(it.properties.get('s2:processing_baseline', '0')) >= 4.0 else 0
    for k in b: b[k] = np.where(b[k] > 0, (b[k] - off) / 10000.0, np.nan)
    with np.errstate(all='ignore'):
        hot = (b['B12'] > 0.20) & (b['B12'] > 1.15 * b['B11']) & ((b['B12'] - b['B8A']) / (b['B12'] + b['B8A']) > 0.25)
    return hot, np.isfinite(b['B12']), bounds, crs
def site_truth(r):
    f = f'{SC}/s2_{r.site}.npz'
    if os.path.exists(f): z = np.load(f, allow_pickle=True); return dict(z['rec'].item())
    try:
        its = scenes(r.lon, r.lat); H = np.zeros((150, 150)); N = np.zeros((150, 150)); bounds = crs = None
        for it in its:
            try: hot, ok, bounds, crs = read(it, r.lon, r.lat)
            except Exception: continue
            H += hot; N += ok
        if bounds is None: return dict(site=r.site, status='no scenes')
        freq = np.where(N > 0, H / np.maximum(N, 1), 0); n_sc = int(N.max())
        pers = freq >= 0.15
        rec = dict(site=int(r.site), status='ok', n_scenes=n_sc, n_hot_px=int(pers.sum()), max_freq=float(freq.max()))
        if pers.sum() >= 1:
            rr, cc = np.where(pers); px = bounds[0] + (cc + 0.5) * 20; py = bounds[3] - (rr + 0.5) * 20; wgt = freq[rr, cc]
            # keep the hot group nearest the VIIRS mean (pixels within 400 m of the strongest pixel near the site centre)
            tx, ty = Transformer.from_crs('EPSG:4326', crs, always_xy=True).transform(r.lon, r.lat)
            d0 = np.hypot(px - tx, py - ty); k = np.argmax(wgt * (d0 < 1000)) if (d0 < 1000).any() else np.argmin(d0)
            keep = np.hypot(px - px[k], py - py[k]) <= 400; px, py, wgt = px[keep], py[keep], wgt[keep]
            cx, cy = np.average(px, weights=wgt), np.average(py, weights=wgt)
            lon_t, lat_t = Transformer.from_crs(crs, 'EPSG:4326', always_xy=True).transform(cx, cy)
            rec.update(truth_lon=lon_t, truth_lat=lat_t, extent_e=float(np.sqrt(np.average((px - cx) ** 2, weights=wgt))),
                       extent_n=float(np.sqrt(np.average((py - cy) ** 2, weights=wgt))), n_hot_group=int(keep.sum()), utm=str(crs))
        np.savez(f, rec=np.array(rec, dtype=object), freq=freq)
        return rec
    except Exception as e:
        return dict(site=int(r.site), status=f'fail {str(e)[:60]}')
rows = []
with ThreadPoolExecutor(int(os.environ.get('THREADS', 12))) as ex:
    for i, rec in enumerate(ex.map(site_truth, [r for _, r in sites.iterrows()])):
        rows.append(rec)
        if i % 10 == 0: print(i, len(sites), rec.get('status'), rec.get('n_hot_px'), flush=True)
T = sites.merge(pd.DataFrame(rows), on='site', how='left'); T.to_csv(f'{R}/static_sites.csv', index=False)
print(T.status.value_counts()); print(T[['n', 'n_scenes', 'n_hot_px', 'n_hot_group', 'extent_e', 'extent_n']].describe().round(1))
