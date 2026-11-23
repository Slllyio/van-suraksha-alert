"""Equal-area 'where will the next look show fire' with pure geometry rules, no learning.
Step = a fire's look k -> its next detecting look (>= 10 h later). Area budget = persistence (475 m around all detections so far).
Hit = a selected 40 m cell within 240 m of a next-look detection (the spread thread's rule, here Euclidean)."""
import pandas as pd, numpy as np, sys, json
from scipy import ndimage
S = sys.argv[1]; RES = 40.0; PERS = 475.0; HIT = 240.0
A = pd.read_parquet(S + '/tracks.parquet'); md = A.t.dt.strftime('%m-%d'); A = A[(md >= '02-15') & (md <= '06-15')].copy()
A['yr'] = A.t.dt.year
rows = []
for f, g in A.groupby('fire'):
    ls = sorted(g.look.unique())
    if len(ls) < 2: continue
    lt = g.groupby('look').t.min()
    yr = g.yr.iloc[0]; t0 = g.t.min()
    old = A[(A.yr == yr) & (A.t < t0 - pd.Timedelta(days=2)) & (abs(A.x - g.x.mean()) < 6000) & (abs(A.y - g.y.mean()) < 6000)]
    x0, y0 = g.x.min() - 4000, g.y.min() - 4000
    nx, ny = int((g.x.max() + 4000 - x0) / RES), int((g.y.max() + 4000 - y0) / RES)
    def grid(pts):
        m = np.ones((ny, nx), bool)
        if len(pts):
            c = ((pts[:, 0] - x0) / RES).astype(int); r = ((pts[:, 1] - y0) / RES).astype(int)
            ok = (c >= 0) & (c < nx) & (r >= 0) & (r < ny); m[r[ok], c[ok]] = False
        return ndimage.distance_transform_edt(m) * RES
    d_old = grid(old[['x', 'y']].values) if len(old) else np.full((ny, nx), 1e5)
    for k in range(1, len(ls)):
        gap = (lt[ls[k]] - lt[ls[k - 1]]).total_seconds() / 3600
        if gap < 10: continue
        prev = g[g.look.isin(ls[:k])]; last = g[g.look == ls[k - 1]]; new = g[g.look == ls[k]]
        d_all = grid(prev[['x', 'y']].values); d_last = grid(last[['x', 'y']].values); d_first = grid(g[g.look == ls[0]][['x', 'y']].values)
        tgt = np.ones((ny, nx), bool)
        c = ((new.x.values - x0) / RES).astype(int); r = ((new.y.values - y0) / RES).astype(int); tgt[r, c] = False
        d_tgt = ndimage.distance_transform_edt(tgt) * RES
        n = int((d_all <= PERS).sum())
        # motion vector first -> last look (only when k >= 2)
        def hitrate(score):
            thr = np.partition(score.ravel(), -n)[-n]; sel = score >= thr
            # each target detection: is a selected cell within HIT of it?
            dsel = ndimage.distance_transform_edt(~sel) * RES
            return float((dsel[r, c] <= HIT).mean())
        res = dict(fire=f, k=k, gap=gap, n_new=len(new), area_ha=n * RES * RES / 1e4, yr=yr)
        res['persist'] = hitrate(-d_all)
        res['last_only'] = hitrate(-d_last)
        for r0 in (300, 450, 600, 750, 900, 1050, 1200):
            res[f'ring_last_{r0}'] = hitrate(-np.abs(d_last - r0))
            res[f'ring_all_{r0}'] = hitrate(-np.abs(d_all - r0))
        res['last_minus_old'] = hitrate(-d_last + 0.5 * np.minimum(1500 - np.minimum(d_old, 1500), 1500))
        if k >= 2:
            # push outward along the first->last direction
            v = np.array([last.x.mean() - g[g.look == ls[0]].x.mean(), last.y.mean() - g[g.look == ls[0]].y.mean()])
            if np.hypot(*v) > 1:
                v = v / np.hypot(*v); yy, xx = np.mgrid[0:ny, 0:nx]
                proj = (xx * RES + x0 - last.x.mean()) * v[0] + (yy * RES + y0 - last.y.mean()) * v[1]
                res['last_plus_momentum'] = hitrate(-d_last + 0.5 * np.clip(proj, -800, 800))
        rows.append(res)
X = pd.DataFrame(rows); X.to_parquet(S + '/r5_steps.parquet')
# leave-one-season-out choice of the ring radius (no tuning on the scored season)
rc = [c for c in X.columns if c.startswith('ring_last_')]
lo = []
for yr in sorted(X.yr.unique()):
    tr = X[X.yr != yr]; te = X[X.yr == yr]
    best = max(rc, key=lambda c: np.average(tr[c], weights=tr.n_new))
    lo.append(pd.DataFrame(dict(v=te[best], w=te.n_new, p=te.persist)))
lo = pd.concat(lo)
cols = [c for c in X.columns if c not in ('fire', 'k', 'gap', 'n_new', 'area_ha', 'yr')]
# weight each next-look detection equally (as the thread does): weight = n_new
out = {c: round(float(np.average(X[c].dropna(), weights=X.loc[X[c].notna(), 'n_new'])), 3) for c in cols}
out['n_steps'] = len(X); out['area_ha_med'] = float(X.area_ha.median())
out['k>=2'] = {c: round(float(np.average(X.loc[X.k >= 2, c].dropna(), weights=X.loc[(X.k >= 2) & X[c].notna(), 'n_new'])), 3) for c in cols}
out['ring_last_LOSO'] = round(float(np.average(lo.v, weights=lo.w)), 3)
for g0, g1 in ((10, 14), (14, 30), (30, 100)):
    q = X[(X.gap >= g0) & (X.gap < g1)]
    out[f'gap_{g0}_{g1}h'] = dict(n=len(q), persist=round(float(np.average(q.persist, weights=q.n_new)), 3), ring600=round(float(np.average(q.ring_last_600, weights=q.n_new)), 3), ring900=round(float(np.average(q.ring_last_900, weights=q.n_new)), 3))
json.dump(out, open(S + '/r5.json', 'w'), indent=1); print(json.dumps(out, indent=1))
