"""Weight each front's 24 ha by the fire-continuity thread's calibrated 'still burning' chance (c18, by hours since its last dot:
6-12 h 62%, 12-24 h 33%, 24-48 h 16%, 48 h+ 9%; < 6 h = 1, the front is live). Unseen 818 fires, same truth and placement as the 0.477 rule.
  rule      : 24.1 ha per active front (dots in the last 2 looks)
  weighted  : 24.1 ha x chance, for every front seen so far (older fronts can come back)
  weighted_active : 24.1 ha x chance, active fronts only
  python3 still_burning_test.py
"""
import sys, pickle, json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts'); import c0_lib as C
X0, Y0 = 737300.0, 2560500.0; MED = 24.1; LINK = 750.0
I = pd.read_parquet('/tmp/claude-0/unseen/u_issues.parquet'); M = pickle.load(open('/tmp/claude-0/unseen/u_maps.pkl', 'rb'))
A = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis']
so = lambda a, b: 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)
chance = lambda h: 1.0 if h < 6 else .62 if h < 12 else .33 if h < 24 else .16 if h < 48 else .09


def clusters(xy):
    if len(xy) == 1: return np.zeros(1, int)
    p = np.array(list(cKDTree(xy).query_pairs(LINK)))
    if len(p) == 0: return np.arange(len(xy))
    return connected_components(coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy), len(xy))), directed=False)[1]


rows = []
for fire, g in I.groupby('fire'):
    mp = M[fire]; r0, r1, c0, c1 = mp['box']; Tg = mp['Tg'].ravel(); dom = mp['dom'].ravel()
    rr, cc = np.mgrid[r0:r1, c0:c1]; P = np.c_[(X0 + (cc + .5) * 20).ravel(), (Y0 - (rr + .5) * 20).ravel()]
    d = C.viirs_looks(A[A.fire == fire]).reset_index(drop=True)
    for it in g.itertuples():
        kn = d[d.lk <= it.k].reset_index(drop=True); tk = kn.t.max(); xy = kn[['x', 'y']].values; lab = clusters(xy)
        truth = dom & (Tg <= it.th + 24); dd = cKDTree(xy).query(P)[0]; foot = dd <= 265
        act = set(lab[(kn.lk >= it.k - 1).values]); w_all = w_act = 0.0
        for f in np.unique(lab):
            h = (tk - kn[lab == f].t.max()).total_seconds() / 3600; c = chance(h)
            w_all += c; w_act += c if f in act else 0
        def place(ha):
            s = np.where(foot, -1, dd); m = np.zeros(len(s), bool); m[np.argsort(s, kind='stable')[:int(foot.sum() + ha / .04)]] = True; return m
        rows.append(dict(fire=fire, k=it.k, n_act=len(act), w_all=w_all, w_act=w_act, rule=so(place(MED * len(act)), truth),
                         weighted=so(place(MED * w_all), truth), weighted_active=so(place(MED * w_act), truth)))
R = pd.DataFrame(rows); R.to_csv('/tmp/claude-0/unseen/still_burning.csv', index=False)
rng = np.random.default_rng(0); res = dict(issues=len(R), fires=int(R.fire.nunique()))
f = R.groupby('fire')[['rule', 'weighted', 'weighted_active']].mean()
for c in ['rule', 'weighted', 'weighted_active']: res[c] = round(float(R[c].median()), 4)
for c in ['weighted', 'weighted_active']:
    dl = (f[c] - f.rule).values
    res[f'{c}_minus_rule_ci'] = [round(float(np.percentile([dl[rng.integers(0, len(dl), len(dl))].mean() for _ in range(2000)], q)), 4) for q in (2.5, 97.5)]
    res[f'{c}_better/worse'] = [int((dl > .005).sum()), int((dl < -.005).sum())]
res['mean_fronts_rule_vs_weighted_all_vs_weighted_active'] = [round(float(R.n_act.mean()), 2), round(float(R.w_all.mean()), 2), round(float(R.w_act.mean()), 2)]
json.dump(res, open('/tmp/claude-0/unseen/still_burning.json', 'w'), indent=1); print(json.dumps(res, indent=1))
