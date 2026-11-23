"""Experiment 3c (detail): hot-pixel density inside the overlap of two near-time footprint sets vs inside each set alone.
Day passes; VIIRS+VIIRS < 2 h; Terra MODIS + VIIRS < 3 h. Hot pixels: same-day Sentinel-2/Landsat (~05:15 UTC)."""
import glob, json
import numpy as np, pandas as pd, pyproj, shapely
from shapely.ops import unary_union
from s_lib import *
rng = np.random.default_rng(0)
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
H = pd.concat([pd.read_csv(f) for f in glob.glob(f'{ROOT}/fire-alert-scars/out/af/af_20*.csv')], ignore_index=True)
H['t'] = pd.to_datetime(H.date + ' ' + H.time_utc); H['x'], H['y'] = tp(H.lon.values, H.lat.values); H = H.drop_duplicates(['x', 'y', 't'])
D = load_det(); D = D[(D.type.fillna(0) != 2) & (D.daynight == 'D')]
rows = []
for day, g in D.groupby(D.t.dt.date):
    h = H[H.t.dt.date == day]
    if not len(h): continue
    pts = shapely.points(h.x.values, h.y.values)
    pt = g.groupby('pass_id').agg(t=('t', 'min'), sensor=('sensor', 'first'), kind=('kind', 'first'))
    U = {k: unary_union([poly(r) for r in g[g.pass_id == k].itertuples()]) for k in pt.index}
    for i in pt.index:
        for j in pt.index:
            if i == j or pt.sensor[i] == pt.sensor[j] or pt.kind[j] != 'viirs': continue
            if pt.kind[i] == 'modis' and pt.sensor[i] != 'Terra MODIS': continue
            if pt.kind[i] == 'viirs' and j < i: continue
            dt = abs((pt.t[j] - pt.t[i]).total_seconds()) / 3600
            if dt > (2 if pt.kind[i] == 'viirs' else 3): continue
            A, B = U[i], U[j]; I = A.intersection(B)
            if I.area < 1e4: continue
            for nm, geom in [('A', A), ('B', B), ('I', I), ('A_only', A.difference(B)), ('B_only', B.difference(A))]:
                pass
            r = dict(day=day, pair='Terra+VIIRS' if pt.kind[i] == 'modis' else 'VIIRS+VIIRS', dt_h=dt)
            for nm, geom in [('A', A), ('B', B), ('I', I), ('AuB', A.union(B))]:
                r['area_' + nm] = geom.area; r['hot_' + nm] = int(shapely.contains(geom, pts).sum())
            rows.append(r)
X = pd.DataFrame(rows); X.to_csv(f'{OUT}/e3c_overlap_detail.csv', index=False)
res = {}
for pair, x in X.groupby('pair'):
    x = x[x.hot_AuB > 0]
    dens = lambda xx, k: xx['hot_' + k].sum() / (xx['area_' + k].sum() / 1e4)    # hot pixels per ha
    r = dict(pass_pairs=len(x), hot_per_ha={k: round(dens(x, k), 3) for k in ['A', 'B', 'I', 'AuB']},
             share_hot_caught={k: round(x['hot_' + k].sum() / x.hot_AuB.sum(), 3) for k in ['A', 'B', 'I']},
             share_area={k: round(x['area_' + k].sum() / x.area_AuB.sum(), 3) for k in ['A', 'B', 'I']})
    bs = []
    for _ in range(1000):
        xx = x.iloc[rng.integers(0, len(x), len(x))]; bs.append(dens(xx, 'I') / dens(xx, 'B'))
    r['overlap_vs_viirs_B_density_ratio'] = [round(dens(x, 'I') / dens(x, 'B'), 2), round(np.quantile(bs, .025), 2), round(np.quantile(bs, .975), 2)]
    r['note'] = 'A = first set (Terra MODIS, or earlier VIIRS), B = VIIRS set'
    res[pair] = r
json.dump(res, open(f'{OUT}/e3c_overlap_summary.json', 'w'), indent=1, default=float); print(json.dumps(res, indent=1, default=float))
