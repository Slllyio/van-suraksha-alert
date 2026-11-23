"""New-front risk 1-3 km out from an active fire (Oct 17). At each issue of mf_tracker.py: 100 m cells (5x5 of the 20 m grid) between
1 and 3 km from every dot so far; label = the cell gets new burning in the next 24 h (blend map, inside the fire's outline v2).
Features known at issue time: distance to dots, bearing vs the fire's latest growth direction, distance to roads and built-up,
forest/grass share, seasons burned before (prior seasons only), hour, look number, n active fronts, dots at latest look.
LightGBM, each season held out; compared with distance alone. Scored as AUC and as hit share in the top 5% of cells per issue.
  python3 mf_newfront.py prefix
"""
import sys, pickle, json, numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree
from scipy import ndimage
from sklearn.metrics import roc_auc_score
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts'); import c0_lib as C
import sim, footprint as fp
PRE = sys.argv[1]
I = pd.read_parquet(f'{PRE}_issues.parquet'); M = pickle.load(open(f'{PRE}_maps.pkl', 'rb'))
A = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis']
X0, Y0 = 737300.0, 2560500.0; B = 5
rows = []
for fire, g in I.groupby('fire'):
    mp = M[fire]; r0, r1, c0, c1 = mp['box']; s = int(g.season.iloc[0])
    Tg, dom = mp['Tg'], mp['dom']; h, w = (Tg.shape[0] // B) * B, (Tg.shape[1] // B) * B
    wc = C.WC[r0:r0 + h, c0:c0 + w]; road = sim.BARRIER[r0:r0 + h, c0:c0 + w] if sim.BARRIER is not None else np.zeros((h, w), bool)
    d_road = ndimage.distance_transform_edt(~road) * 20; d_built = ndimage.distance_transform_edt(wc != 50) * 20
    nb = np.zeros((h, w), np.float32)
    for y in range(2017, s):
        nb += (fp.burn_end(y)[r0:r0 + h, c0:c0 + w] > -999)
    agg = lambda a, f=np.mean: f(f(a[:h, :w].reshape(h // B, B, w // B, B), axis=3), axis=1)
    cf = dict(forest=agg((wc == 10).astype(float)), grass=agg((wc == 30).astype(float)), d_road=agg(d_road), d_built=agg(d_built), nburn=agg(nb))
    rr, cc = np.mgrid[0:h // B, 0:w // B]; cx = X0 + (c0 + cc * B + B / 2) * 20; cy = Y0 - (r0 + rr * B + B / 2) * 20
    Pc = np.c_[cx.ravel(), cy.ravel()]
    d = C.viirs_looks(A[A.fire == fire]).reset_index(drop=True); t0 = d.t.min(); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    for it in g.itertuples():
        known = d[d.lk <= it.k]; xy = known[['x', 'y']].values
        new = (Tg[:h, :w] > it.th) & (Tg[:h, :w] <= it.th + 24)
        lab = agg(new.astype(float), np.max).ravel() > 0
        dd = cKDTree(xy).query(Pc)[0]; m = (dd >= 1000) & (dd <= 3000)
        if m.sum() < 20:
            continue
        last = known[known.lk == it.k][['x', 'y']].values.mean(0); prev = known[known.lk < it.k][['x', 'y']].values
        gdir = last - prev.mean(0) if len(prev) else np.array([0., 0.])
        v = Pc - xy.mean(0); cosang = (v @ gdir) / (np.hypot(v[:, 0], v[:, 1]) * max(np.hypot(*gdir), 1e-6))
        df = pd.DataFrame(dict(fire=fire, season=s, k=it.k, y=lab[m].astype(int), dist=dd[m], cos=cosang[m] if np.hypot(*gdir) > 0 else np.nan,
                               **{k_: v_.ravel()[m] for k_, v_ in cf.items()}, hour=it.hour_ist, look=it.k, n_active=it.n_active, n_dots=it.n_dots))
        rows.append(df)
D = pd.concat(rows, ignore_index=True); print(len(D), D.y.mean(), flush=True)
FE = ['dist', 'cos', 'forest', 'grass', 'd_road', 'd_built', 'nburn', 'hour', 'look', 'n_active', 'n_dots']
D['p'] = np.nan
P = dict(objective='binary', learning_rate=.05, num_leaves=15, min_data_in_leaf=200, feature_fraction=.8, verbose=-1, seed=0)
for s in sorted(D.season.unique()):
    tr, te = D[D.season != s], D.season == s
    m = lgb.train(P, lgb.Dataset(tr[FE], tr.y), 300); D.loc[te, 'p'] = m.predict(D.loc[te, FE])
res = dict(cells=len(D), issues=int(D.groupby(['fire', 'k']).ngroups), base_rate=float(D.y.mean()),
           auc_model=float(roc_auc_score(D.y, D.p)), auc_distance=float(roc_auc_score(D.y, -D.dist)))
def top(col, sign=1):
    hits = []
    for _, x in D.groupby(['fire', 'k']):
        if x.y.sum() == 0:
            continue
        n = max(int(.05 * len(x)), 1); t = x.nlargest(n, col) if sign == 1 else x.nsmallest(n, col)
        hits.append(t.y.sum() / x.y.sum())
    return float(np.mean(hits))
res['top5_share_model'] = top('p'); res['top5_share_distance'] = top('dist', -1); res['top5_share_random'] = .05
res['importance'] = {k: float(v) for k, v in sorted(zip(FE, m.feature_importance('gain')), key=lambda x: -x[1])}
json.dump(res, open(f'{PRE}_newfront.json', 'w'), indent=1); print(json.dumps(res, indent=1))
