"""Second, stricter truth for the static sites (b20_static_truth.py found the warm SWIR areas are often 100-130 m wide, so
"where is the source" depends on the definition). VIIRS radiance is dominated by the hottest part, so here the truth is the
centroid weighted by the mean 2.2 um excess (B12 - 1.15*B11, only where B12 > 0.2) over 30 clear scenes, plus the single peak
pixel. Out: results/static_sites_peak.csv"""
import os, json, warnings, numpy as np, pandas as pd, rasterio, pystac_client, planetary_computer as pc
from rasterio.windows import from_bounds
from pyproj import Transformer
from concurrent.futures import ThreadPoolExecutor
warnings.filterwarnings('ignore')
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif,.TIF', GDAL_HTTP_MAX_RETRY='5', GDAL_HTTP_RETRY_DELAY='2')
R = '/mnt/project-files/research/big-fires/results'; SC = '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/static'
T = pd.read_csv(f'{R}/static_sites.csv')
cat = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1')
def scenes(lon, lat, n=30):
    its = []
    for yr in range(2019, 2026):
        its += list(cat.search(collections=['sentinel-2-l2a'], intersects={'type': 'Point', 'coordinates': [lon, lat]}, datetime=f'{yr}-01-01/{yr}-06-30', query={'eo:cloud_cover': {'lt': 15}}).items())
    its.sort(key=lambda i: i.properties['eo:cloud_cover']); by = {}
    for i in its: by.setdefault(i.datetime.year, []).append(i)
    out = []
    while len(out) < n and any(by.values()):
        for y in sorted(by):
            if by[y] and len(out) < n: out.append(by[y].pop(0))
    return out
def one(r):
    f = f'{SC}/peak_{int(r.site)}.npz'
    if os.path.exists(f): return dict(np.load(f, allow_pickle=True)['rec'].item())
    try:
        E = np.zeros((150, 150)); N = np.zeros((150, 150)); bounds = crs = None
        for it in scenes(r.lon, r.lat):
            try:
                it = pc.sign(it); b = {}
                with rasterio.open(it.assets['B12'].href) as src:
                    crs = src.crs; tx, ty = Transformer.from_crs('EPSG:4326', crs, always_xy=True).transform(r.lon, r.lat)
                    bounds = (tx - 1500, ty - 1500, tx + 1500, ty + 1500)
                    b['B12'] = src.read(1, window=from_bounds(*bounds, src.transform), out_shape=(150, 150), boundless=True, fill_value=0).astype(np.float32)
                with rasterio.open(it.assets['B11'].href) as src:
                    b['B11'] = src.read(1, window=from_bounds(*bounds, src.transform), out_shape=(150, 150), boundless=True, fill_value=0).astype(np.float32)
                off = 1000 if float(it.properties.get('s2:processing_baseline', '0')) >= 4.0 else 0
                for k in b: b[k] = np.where(b[k] > 0, (b[k] - off) / 10000.0, np.nan)
                ex = np.where(b['B12'] > 0.2, np.clip(b['B12'] - 1.15 * b['B11'], 0, None), 0)
                ok = np.isfinite(b['B12']); E += np.where(ok, np.nan_to_num(ex), 0); N += ok
            except Exception: continue
        if bounds is None: return dict(site=int(r.site), status='no scenes')
        M = np.where(N > 0, E / np.maximum(N, 1), 0)
        tx, ty = Transformer.from_crs('EPSG:4326', crs, always_xy=True).transform(r.lon, r.lat)
        xs = bounds[0] + (np.arange(150) + 0.5) * 20; ys = bounds[3] - (np.arange(150) + 0.5) * 20; X, Y = np.meshgrid(xs, ys)
        near = np.hypot(X - tx, Y - ty) < 1000
        rec = dict(site=int(r.site), status='ok', peak_excess=float(M[near].max()) if near.any() else 0.0)
        if rec['peak_excess'] > 0.02:
            k = np.argmax(np.where(near, M, -1)); px, py = X.flat[k], Y.flat[k]
            grp = (np.hypot(X - px, Y - py) <= 400) & (M > 0.2 * rec['peak_excess'])
            w = M[grp]; cx, cy = np.average(X[grp], weights=w), np.average(Y[grp], weights=w)
            back = Transformer.from_crs(crs, 'EPSG:4326', always_xy=True)
            rec['wt_lon'], rec['wt_lat'] = back.transform(cx, cy); rec['peak_lon'], rec['peak_lat'] = back.transform(px, py)
            rec['wt_sd_m'] = float(np.sqrt(np.average((X[grp] - cx) ** 2 + (Y[grp] - cy) ** 2, weights=w) / 2)); rec['n_px'] = int(grp.sum())
            # a second hot group within 1 km that holds >30% of the excess?
            rec['other_excess_share'] = float(M[near & ~grp & (M > 0.2 * rec['peak_excess'])].sum() / max(M[near & (M > 0.2 * rec['peak_excess'])].sum(), 1e-9))
        np.savez(f, rec=np.array(rec, dtype=object), M=M); return rec
    except Exception as e:
        return dict(site=int(r.site), status=f'fail {str(e)[:60]}')
rows = []
with ThreadPoolExecutor(12) as ex:
    for i, rec in enumerate(ex.map(one, [r for _, r in T.iterrows()])):
        rows.append(rec)
        if i % 10 == 0: print(i, len(T), rec.get('status'), flush=True)
pd.DataFrame(rows).to_csv(f'{R}/static_sites_peak.csv', index=False); print('done', flush=True)
