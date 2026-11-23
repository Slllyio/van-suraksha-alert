"""Per VIIRS fire event (spread thread's 1,862 events, 2017-24): its burn scar (same rule as spread/score.py:
burn-label pixels dated overlapping the event, connected components within 400 m of a detection), scar area, class
composition of the scar, FRP samples. 20 m grid = burn-label grid; fuel layers are 10 m aligned 2x2."""
import numpy as np, pandas as pd, rasterio
from scipy import ndimage
B = '/mnt/project-files/research/ratapani-burn-labels/rasters/burn_{}.tif'
F = '/tmp/claude-0/fuel/'
S = np.load(F + 'static10.npz'); H, W = int(S['H']), int(S['W'])
def to20(a, fn=np.nanmean):
    a = a[:H // 2 * 2, :W // 2 * 2].astype('float32'); return fn(a.reshape(H // 2, 2, W // 2, 2), axis=(1, 3))
cov = to20(np.load(F + 'canopy_s2.npz')['s2']); tp = to20(np.load(F + 'teakprob2.npy'))
pc = np.load(F + 'phenoclass.npz')['c'][:H // 2 * 2:2, :W // 2 * 2:2]
forest = to20(np.isin(S['wc'], [10, 20, 30]).astype('float32')) > 0.5
# classes: 1 closed teak, 2 closed other deciduous, 3 open forest, 4 grass/scrub/sparse
cls = np.zeros(cov.shape, np.uint8)
cls[forest & (cov >= 0.4) & (tp >= 0.5)] = 1; cls[forest & (cov >= 0.4) & (tp < 0.5)] = 2
cls[forest & (cov >= 0.1) & (cov < 0.4)] = 3; cls[forest & ((cov < 0.1) | np.isin(pc, [4, 5])) & (cls != 1) & (cls != 2)] = 4
np.save('cls20.npy', cls)
v = pd.read_parquet('/tmp/claude-0/fuel/inv/viirs_events_spread.parquet')
v = v[v.t.dt.month <= 6]
with rasterio.open(B.format(2017)) as s: TR = s.transform
rows = []
for yr in range(2017, 2025):
    with rasterio.open(B.format(yr)) as s: be, bs = s.read(1), s.read(2)
    for e, ev in v[v.season == yr].groupby('event'):
        d0, d1 = ev.t.min().dayofyear, ev.t.max().dayofyear
        r, c = rasterio.transform.rowcol(TR, ev.x.values, ev.y.values); r, c = np.array(r), np.array(c)
        if (r < 0).any() or (c < 0).any() or (r >= be.shape[0]).any() or (c >= be.shape[1]).any(): continue
        i0, i1, j0, j1 = max(r.min() - 150, 0), r.max() + 150, max(c.min() - 150, 0), c.max() + 150
        m = (be[i0:i1, j0:j1] > -999) & (be[i0:i1, j0:j1] >= d0) & (bs[i0:i1, j0:j1] <= d1)
        lab, n = ndimage.label(m, structure=np.ones((3, 3)))
        near = np.zeros(m.shape, bool); near[r - i0, c - j0] = True; near = ndimage.binary_dilation(near, iterations=20)
        keep = np.unique(lab[near & m]); keep = keep[keep > 0]
        Sm = np.isin(lab, keep) if n else m
        cc = cls[i0:i1, j0:j1][Sm]
        row = dict(event=e, season=yr, t0=ev.t.min(), t1=ev.t.max(), month=ev.t.min().month, n_det=len(ev), n_pass=ev.overpass.nunique(),
                   scar_ha=Sm.sum() * 0.04, frp_sum=ev.frp.sum(), frp_max=ev.frp.max(), frp_day=ev[ev.daynight == 'D'].frp.sum(), frp_night=ev[ev.daynight == 'N'].frp.sum(),
                   n_day=(ev.daynight == 'D').sum(), n_night=(ev.daynight == 'N').sum())
        for k in range(5): row[f'c{k}'] = (cc == k).mean() if len(cc) else np.nan
        rows.append(row)
d = pd.DataFrame(rows); d.to_parquet('events_scar_s.parquet')
print(len(d), 'with scar >=1 ha', (d.scar_ha >= 1).sum()); print(d[d.scar_ha >= 1][['c0', 'c1', 'c2', 'c3', 'c4']].mean().round(3).to_dict())
print(d[d.scar_ha >= 1].scar_ha.describe().round(1).to_dict())
