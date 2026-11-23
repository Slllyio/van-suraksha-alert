"""Fire jumps / new fires near an active fire: how often does new fire appear 1-5 km from a burning fire within 24 h,
how much above the normal background, and can anything say where?
Issue = each detecting look of each fire (Feb 15-Jun 15). Cells: 300 m lattice, 1-5 km from the fire's dots so far.
Label: any VIIRS dot (any fire) within 300 m in the next 2 looks (24 h).
Background: the same cell's chance of a dot in any random 24 h of that season (other seasons' rate, held out).
Model: LightGBM, season held out (2017-24) and forward (2025-26); baseline = distance-only rate.
Out: jumps/summary.json, jumps/rows.parquet"""
import pandas as pd, numpy as np, sys, json, lightgbm as lgb
from scipy.spatial import cKDTree
from sklearn.metrics import roc_auc_score
S = sys.argv[1]; OUT = sys.argv[2]; LAT = 300.0
A = pd.read_parquet(S + '/tracks.parquet'); md = A.t.dt.strftime('%m-%d'); A = A[(md >= '02-10') & (md <= '06-20')].copy()
P = pd.read_parquet(S + '/passes.parquet')
slots = pd.DataFrame({'look': sorted(set(P.look) | set(A.look))})
slots['t'] = slots.look.map(P.groupby('look').t.min()).fillna(slots.look.map(A.groupby('look').t.min()))
slots = slots.sort_values('t').reset_index(drop=True); sidx = dict(zip(slots.look, slots.index))
A['si'] = A.look.map(sidx); A['yr'] = A.t.dt.year; At = A.si.values; AX = A[['x', 'y']].values
G = np.load('/mnt/project-files/ratapani/spread/data_shared/grid20.npz'); TR = G['transform']
def sample(arr, x, y):
    c = ((x - TR[2]) / TR[0]).astype(int); r = ((y - TR[5]) / TR[4]).astype(int)
    ok = (r >= 0) & (r < arr.shape[0]) & (c >= 0) & (c < arr.shape[1]); o = np.full(len(x), np.nan, np.float32); o[ok] = arr[r[ok], c[ok]]; return o
# history: dots per season per 500 m neighbourhood (for held-out "how fire-prone is this spot")
seasons = sorted(A.yr.unique()); trees = {y: cKDTree(A[A.yr == y][['x', 'y']].values) for y in seasons}
nslots = {y: ((slots.t.dt.year == y) & slots.t.dt.strftime('%m-%d').between('02-15', '06-15')).sum() for y in seasons}
rows = []; rng = np.random.default_rng(1)
for f, g in A.groupby('fire'):
    if not ('02-15' <= g.t.min().strftime('%m-%d') <= '06-15'): continue
    yr = g.yr.iloc[0]
    for s in sorted(g.si.unique()):
        seen = g[g.si <= s]; last = seen[seen.si == s]
        xs = np.arange(seen.x.min() - 5000, seen.x.max() + 5000, LAT); ys = np.arange(seen.y.min() - 5000, seen.y.max() + 5000, LAT)
        X, Y = np.meshgrid(xs, ys); X, Y = X.ravel(), Y.ravel()
        d = cKDTree(seen[['x', 'y']].values).query(np.c_[X, Y])[0]; k = (d >= 1000) & (d <= 5000); X, Y, d = X[k], Y[k], d[k]
        if rng.random() > 0.5: continue          # half the issues are enough
        idx = np.where((At > s) & (At <= s + 2))[0]
        y24 = np.isfinite(cKDTree(AX[idx]).query(np.c_[X, Y], distance_upper_bound=300)[0]) if len(idx) else np.zeros(len(X), bool)
        hist = np.zeros(len(X)); nh = 0
        for yy in seasons:
            if yy == yr: continue
            hist += np.array([len(v) for v in trees[yy].query_ball_point(np.c_[X, Y], 500)]) / max(nslots[yy], 1); nh += 1
        old = A[(A.yr == yr) & (A.si < s - 4)]
        rows.append(pd.DataFrame(dict(fire=f, yr=yr, s=s, x=X, y=Y, d=d, d_last=cKDTree(last[['x', 'y']].values).query(np.c_[X, Y])[0],
            hist_rate=hist / nh, d_old=cKDTree(old[['x', 'y']].values).query(np.c_[X, Y])[0] if len(old) else 9000.0,
            frp_last=last.frp.sum(), n_seen=len(seen), looks_seen=seen.si.nunique(), doy=slots.t[s].dayofyear,
            night=int(slots.look[s].endswith('N')), elev=sample(G['elev'], X, Y), wc=sample(G['wc'], X, Y), y24=y24)))
D = pd.concat(rows, ignore_index=True); D.to_parquet(OUT + '/rows.parquet')
# how much above background? background chance of a dot within 300 m in 24 h ~ 2 x hist_rate x (300/500)^2
D['bg'] = 1 - np.exp(-2 * D.hist_rate * (300 / 500) ** 2)
R = dict(n_rows=len(D), n_issues=int(D.groupby(['fire', 's']).ngroups))
for lo, hi in ((1000, 2000), (2000, 3000), (3000, 5000)):
    q = D[(D.d >= lo) & (D.d < hi)]
    R[f'{lo}-{hi} m'] = dict(rate=round(float(q.y24.mean()), 4), background=round(float(q.bg.mean()), 4), ratio=round(float(q.y24.mean() / q.bg.mean()), 1),
                            share_issues_with_any=round(float(q.groupby(['fire', 's']).y24.any().mean()), 3))
F = ['d', 'd_last', 'hist_rate', 'd_old', 'frp_last', 'n_seen', 'looks_seen', 'doy', 'night', 'elev', 'wc']
pr = []
for name, trm, tem in [(y, (D.yr <= 2024) & (D.yr != y), D.yr == y) for y in range(2017, 2025)] + [('fwd', D.yr <= 2024, D.yr >= 2025)]:
    tr, te = D[trm], D[tem]
    m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=300, verbose=-1).fit(tr[F], tr.y24)
    base = tr.groupby((tr.d // 500).astype(int)).y24.mean()
    pr.append(te[['fire', 's', 'y24', 'd']].assign(split=str(name), p=m.predict_proba(te[F])[:, 1], p_dist=(te.d // 500).astype(int).map(base).values,
                                                p_hist=te.hist_rate.values))
pr = pd.concat(pr)
for part, q in (('LOSO_2017_24', pr[pr.split != 'fwd']), ('forward_2025_26', pr[pr.split == 'fwd'])):
    out = {}
    for c in ('p', 'p_dist', 'p_hist'):
        top = q.sort_values(c, ascending=False)
        n10 = int(len(q) * 0.10)
        out[c] = dict(auc=round(roc_auc_score(q.y24, q[c]), 3), caught_in_top10pct=round(float(top.y24.iloc[:n10].sum() / q.y24.sum()), 3))
    R[part] = out
json.dump(R, open(OUT + '/summary.json', 'w'), indent=1); print(json.dumps(R, indent=1))
