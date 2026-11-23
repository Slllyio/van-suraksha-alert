"""Step 6a: does FRP say how much of a block is burning? Independent check with same-minute Sentinel-2/Landsat hot pixels.

Terra MODIS (~10:30 local) passes within ~30 min of Sentinel-2 and Landsat (~10:30), so the same fire is seen twice at
nearly the same moment: once as a 1 km block with an FRP, once as 20-30 m hot pixels (scar thread's af_scan).
Physics: FRP = sigma * (Tf^4 - Tb^4) * A_burning, so A_burning = FRP / (sigma (Tf^4 - Tb^4)). With Tf 600-1000 K, Tb 300 K.
Test: per Terra detection, FRP against hot-pixel count inside its footprint (Spearman), and the FRP burning area against
the hot-pixel area. Only Terra detections with a hot pixel within 3 km that day (scene present, fire present).
Out: results/frp_vs_hotpix.csv, printed table.
"""
import glob
import numpy as np, pandas as pd, pyproj
from scipy.stats import spearmanr
from scipy.spatial import cKDTree
ROOT = '/mnt/project-files'
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
m = pd.concat([pd.read_csv(f) for f in glob.glob(f'{ROOT}/fire-alert-scars/alerts/modis_*.csv')], ignore_index=True)
m = m[(m.satellite == 'Terra') & (m.daynight == 'D')].copy()
m['t'] = pd.to_datetime(m.acq_date) + pd.to_timedelta(m.acq_time // 100, 'h') + pd.to_timedelta(m.acq_time % 100, 'min')
m['x'], m['y'] = tp(m.longitude.values, m.latitude.values)
h = pd.concat([pd.read_csv(f) for f in glob.glob(f'{ROOT}/fire-alert-scars/out/af/af_*.csv')], ignore_index=True)
h['t'] = pd.to_datetime(h.date + ' ' + h.time_utc); h['x'], h['y'] = tp(h.lon.values, h.lat.values)
h['pix_m2'] = np.where(h.sensor == 's2', 400.0, 900.0)
rows = []
for d, g in m.groupby('acq_date'):
    hh = h[h.date == d]
    if not len(hh): continue
    tree = cKDTree(hh[['x', 'y']].values)
    for r in g.itertuples():
        near = tree.query_ball_point([r.x, r.y], 3000)
        if not near: continue
        hn = hh.iloc[near]
        dt = abs((hn.t.iloc[0] - r.t).total_seconds()) / 60
        if dt > 60: continue
        inn = hn[(abs(hn.x - r.x) <= r.scan * 500) & (abs(hn.y - r.y) <= r.track * 500)]
        rows.append(dict(date=d, frp=r.frp, scan=r.scan, track=r.track, dt_min=dt, n_hot=len(inn), hot_m2=inn.pix_m2.sum(),
                         sensor=hn.sensor.iloc[0], n_hot_3km=len(hn)))
D = pd.DataFrame(rows)
D.to_csv(f'{ROOT}/research/big-fires/results/frp_vs_hotpix.csv', index=False)
sig = 5.67e-8
print('Terra detections with a same-morning hot-pixel scene and fire within 3 km:', len(D))
print('share with >= 1 hot pixel inside the block:', round((D.n_hot > 0).mean(), 2))
print('Spearman FRP vs hot pixels in block:', round(spearmanr(D.frp, D.n_hot)[0], 2),
      '| FRP per km2 vs hot pixels:', round(spearmanr(D.frp / (D.scan * D.track), D.n_hot)[0], 2))
for Tf in (600, 800, 1000):
    D[f'a{Tf}'] = D.frp * 1e6 / (sig * (Tf ** 4 - 300 ** 4))
print(D[['frp', 'n_hot', 'hot_m2', 'a600', 'a800', 'a1000']].describe(percentiles=[.25, .5, .75]).round(0))
D['frp_bin'] = pd.qcut(D.frp, 4)
print(D.groupby('frp_bin', observed=True).agg(n=('frp', 'size'), hot_med=('n_hot', 'median'), hot_mean=('n_hot', 'mean'),
      any_hot=('n_hot', lambda s: (s > 0).mean()), a800_med=('a800', 'median'), hot_m2_med=('hot_m2', 'median')).round(2))
