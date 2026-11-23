"""Item 1+4+5: training/scoring rows for calibrated 'fire here within 12/24/48 h' chances.
Issue time = every satellite slot (13:30 / 01:30 IST look) from a fire's first detection to 2 slots after its last one,
using ONLY detections up to that slot. Cells: 150 m lattice within 2 km of the fire's detections so far.
Label h = a VIIRS detection (any satellite, any fire) within 300 m of the cell centre in the next 1/2/4 slots (12/24/48 h).
Out: rows.parquet (features + y12/y24/y48 + weight; far negatives subsampled 1 in 3 with weight 3)."""
import pandas as pd, numpy as np, sys
from scipy.spatial import cKDTree
S = sys.argv[1]; OUT = sys.argv[2]
LAT, RAD, TOL = 150.0, 2000.0, 300.0
A = pd.read_parquet(S + '/tracks.parquet'); md = A.t.dt.strftime('%m-%d'); A = A[(md >= '02-10') & (md <= '06-20')].copy()
P = pd.read_parquet(S + '/passes.parquet')
slots = pd.DataFrame({'look': sorted(set(P.look) | set(A.look))})
slots['t'] = slots.look.map(P.groupby('look').t.min()).fillna(slots.look.map(A.groupby('look').t.min()))
slots = slots.sort_values('t').reset_index(drop=True); sidx = dict(zip(slots.look, slots.index))
A['si'] = A.look.map(sidx); A['yr'] = A.t.dt.year
G = np.load('/mnt/project-files/ratapani/spread/data_shared/grid20.npz')
TR = G['transform']; ELEV, SLOPE, WC = G['elev'], G['slope'], G['wc']
def sample(arr, x, y):
    c = ((x - TR[2]) / TR[0]).astype(int); r = ((y - TR[5]) / TR[4]).astype(int)
    ok = (r >= 0) & (r < arr.shape[0]) & (c >= 0) & (c < arr.shape[1])
    out = np.full(len(x), np.nan, np.float32); out[ok] = arr[r[ok], c[ok]]; return out
treeA = cKDTree(A[['x', 'y']].values); At = A.si.values
rng = np.random.default_rng(0); rows = []
for f, g in A.groupby('fire'):
    md0 = g.t.min().strftime('%m-%d')
    if not ('02-15' <= md0 <= '06-15'): continue
    s0, s1 = g.si.min(), g.si.max(); yr = g.yr.iloc[0]
    first = g[g.si == s0]
    for s in range(s0, s1 + 3):
        seen = g[g.si <= s]; last_si = seen.si.max(); last = seen[seen.si == last_si]
        cx, cy = seen.x.mean(), seen.y.mean()
        xs = np.arange(seen.x.min() - RAD, seen.x.max() + RAD, LAT); ys = np.arange(seen.y.min() - RAD, seen.y.max() + RAD, LAT)
        X, Y = np.meshgrid(xs, ys); X, Y = X.ravel(), Y.ravel()
        d_all, _ = cKDTree(seen[['x', 'y']].values).query(np.c_[X, Y])
        keep = d_all <= RAD; X, Y, d_all = X[keep], Y[keep], d_all[keep]
        d_last, _ = cKDTree(last[['x', 'y']].values).query(np.c_[X, Y])
        d_first, _ = cKDTree(first[['x', 'y']].values).query(np.c_[X, Y])
        # earlier burning this season (other fires, > 2 days before issue): ground likely already burned
        old = A[(A.yr == yr) & (A.si < s - 4) & (A.fire != f) & (abs(A.x - cx) < 6000) & (abs(A.y - cy) < 6000)]
        d_old = cKDTree(old[['x', 'y']].values).query(np.c_[X, Y])[0] if len(old) else np.full(len(X), 6000.0)
        n_old500 = np.array([len(v) for v in cKDTree(old[['x', 'y']].values).query_ball_point(np.c_[X, Y], 500)]) if len(old) else np.zeros(len(X))
        # momentum (item 5): first-look centroid -> last-look centroid
        vx, vy = last.x.mean() - first.x.mean(), last.y.mean() - first.y.mean(); vl = np.hypot(vx, vy)
        ux, uy = (vx / vl, vy / vl) if vl > 1 else (0.0, 0.0)
        dx, dy = X - last.x.mean(), Y - last.y.mean()
        proj = dx * ux + dy * uy; perp = np.abs(-dx * uy + dy * ux) if vl > 1 else np.hypot(dx, dy)
        # labels: detections in the next 1/2/4 slots within TOL
        lab = {}
        for h, k in ((12, 1), (24, 2), (48, 4)):
            idx = np.where((At > s) & (At <= s + k))[0]
            if len(idx):
                d = cKDTree(A[['x', 'y']].values[idx]).query(np.c_[X, Y], distance_upper_bound=TOL)[0]
                lab[h] = np.isfinite(d)
            else:
                lab[h] = np.zeros(len(X), bool)
        el = sample(ELEV, X, Y); el0 = np.nanmean(sample(ELEV, last.x.values, last.y.values))
        t_issue = slots.t[s]
        R = pd.DataFrame(dict(
            fire=f, yr=yr, s=s, x=X, y=Y, d_all=d_all, d_last=d_last, d_first=d_first, d_old=d_old, n_old500=n_old500,
            proj=proj, perp=perp, mom_len=vl, n_seen=len(seen), n_last=len(last), looks_seen=seen.si.nunique(),
            frp_last=last.frp.sum(), frp_max=seen.frp.max(),
            h_since_first=(t_issue - g.t.min()).total_seconds() / 3600, h_since_last=(t_issue - last.t.max()).total_seconds() / 3600,
            silent=int(s - last_si), next_night=int(slots.look[min(s + 1, len(slots) - 1)].endswith('N')),
            doy=t_issue.dayofyear, elev_rel=el - el0, slope=sample(SLOPE, X, Y), wc=sample(WC, X, Y),
            y12=lab[12], y24=lab[24], y48=lab[48]))
        pos = R.y48.values; far = (R.d_all.values > 800) & ~pos
        sub = ~far | (rng.random(len(R)) < 1 / 3)
        R['w'] = np.where(far, 3.0, 1.0)
        rows.append(R[sub])
D = pd.concat(rows, ignore_index=True)
for c in D.columns:
    if D[c].dtype == np.float64: D[c] = D[c].astype(np.float32)
D.to_parquet(OUT)
print(len(D), 'rows', D.groupby(['fire', 's']).ngroups, 'issues', D[['y12', 'y24', 'y48']].mean().round(4).to_dict())
