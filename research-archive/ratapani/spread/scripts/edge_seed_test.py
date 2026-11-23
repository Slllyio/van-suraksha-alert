"""Seed the 24 h growth from block EDGES instead of block centres (Oct 17; big-fires 14c: real hot pixels sit in the outer half of
their VIIRS block or just outside it, rarely at the centre). Same unseen fires, issues and truth as uv_apply.py; same added area as
the "dots + 24 ha per active front" rule (0.477). Variants, all with the 375 m blocks counted as burned:
  centre      : added ground nearest to dot centres (the 0.477 rule)
  out_fire    : each dot moved 190 m (half a block) away from the centre of ALL dots so far
  out_latest  : dots of the latest look moved 190 m away from the centre of the earlier dots (first look: from its own centre)
  hull_edge   : added ground nearest to the outer boundary of the block cluster (convex hull of all blocks)
  python3 edge_seed_test.py prefix
"""
import sys, pickle, json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry import MultiPoint
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts'); import c0_lib as C
PRE = sys.argv[1]; X0, Y0 = 737300.0, 2560500.0; MED = 24.1; SH = float(__import__("os").environ.get("SH", 190))
I = pd.read_parquet(f'{PRE}_issues.parquet'); M = pickle.load(open(f'{PRE}_maps.pkl', 'rb'))
A = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis']
so = lambda a, b: 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)


def push(p, c):
    v = p - c; n = np.hypot(v[:, 0], v[:, 1]); n[n == 0] = 1
    return p + v / n[:, None] * SH


rows = []
for fire, g in I.groupby('fire'):
    mp = M[fire]; r0, r1, c0, c1 = mp['box']; Tg = mp['Tg'].ravel(); dom = mp['dom'].ravel()
    rr, cc = np.mgrid[r0:r1, c0:c1]; P = np.c_[(X0 + (cc + .5) * 20).ravel(), (Y0 - (rr + .5) * 20).ravel()]
    d = C.viirs_looks(A[A.fire == fire]).reset_index(drop=True)
    for it in g.itertuples():
        kn = d[d.lk <= it.k]; xy = kn[['x', 'y']].values; truth = dom & (Tg <= it.th + 24)
        dd = cKDTree(xy).query(P)[0]; foot = dd <= 265; n = int(foot.sum() + MED * it.n_active / .04)
        lat = kn[kn.lk == it.k][['x', 'y']].values; prev = kn[kn.lk < it.k][['x', 'y']].values
        seeds = dict(centre=xy, out_fire=push(xy, xy.mean(0)),
                     out_latest=np.r_[prev, push(lat, prev.mean(0) if len(prev) else lat.mean(0))])
        out = dict(fire=fire, k=it.k, n_dots=len(xy))
        for name, s in seeds.items():
            sc = np.where(foot, -1, cKDTree(s).query(P)[0]); m = np.zeros(len(sc), bool); m[np.argsort(sc, kind='stable')[:n]] = True
            out[name] = so(m, truth)
        hull = MultiPoint([tuple(p) for p in xy]).convex_hull.buffer(265).exterior
        hp = np.array(hull.interpolate(np.linspace(0, hull.length, max(int(hull.length / 20), 8))).coords) if False else np.array([hull.interpolate(t).coords[0] for t in np.linspace(0, hull.length, max(int(hull.length / 40), 8))])
        sc = np.where(foot, -1, cKDTree(hp).query(P)[0]); m = np.zeros(len(sc), bool); m[np.argsort(sc, kind='stable')[:n]] = True
        out['hull_edge'] = so(m, truth); rows.append(out)
R = pd.DataFrame(rows); R.to_csv(f'{PRE}_edge_seed'+__import__('os').environ.get('SH','')+'.csv', index=False)
rng = np.random.default_rng(0); res = dict(issues=len(R), fires=int(R.fire.nunique()))
f = R.groupby('fire')[['centre', 'out_fire', 'out_latest', 'hull_edge']].mean()
for c in ['centre', 'out_fire', 'out_latest', 'hull_edge']:
    res[c] = round(float(R[c].median()), 4)
    if c != 'centre':
        dlt = (f[c] - f.centre).values
        res[f'{c}_minus_centre_ci'] = [round(float(np.percentile([dlt[rng.integers(0, len(dlt), len(dlt))].mean() for _ in range(2000)], q)), 4) for q in (2.5, 97.5)]
        res[f'{c}_better_fires'] = int((dlt > .005).sum()); res[f'{c}_worse_fires'] = int((dlt < -.005).sum())
json.dump(res, open(f'{PRE}_edge_seed'+__import__('os').environ.get('SH','')+'.json', 'w'), indent=1); print(json.dumps(res, indent=1))
