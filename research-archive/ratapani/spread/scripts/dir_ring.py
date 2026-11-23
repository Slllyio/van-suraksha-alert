"""Directional ring (Oct 17; lead from the big-fires thread: the direction of NEW burning between looks persists ~68% of the time).
Dots only, no rasters: at every look k of a multi-look VIIRS fire (S-NPP, NOAA-20, NOAA-21; looks = detections within 90 min), rank a 40 m
lattice within 3 km of the dots so far and keep the top cells for a fixed area; a later dot (within 24 h / 48 h) is caught when a kept cell
lies within 240 m of it (the fair table's 12-pixel box). Momentum = centroid of the latest look's NEW dots (> 375 m from every earlier dot)
minus the centroid of all earlier dots; steps without momentum keep the plain rule.
Rules: pers (-distance to any dot), ring (-|distance to latest look - 600 m|), and each plus a lean w * 600 m * cos(angle between the cell's
bearing from the latest look's centroid and the momentum). w picked leave-one-season-out from {0.1, 0.25, 0.5, 1}.
  python3 dir_ring.py events_viirs.parquet out.json
"""
import sys, json, numpy as np, pandas as pd
EV = sys.argv[1] if len(sys.argv) > 1 else 'events_viirs.parquet'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'dir_ring.json'
D = '/tmp/claude-0/spread/data/'
V = pd.read_parquet(D + EV).sort_values('t')
CELL = 40.0; R = 3000.0; HIT = 240.0; RING = 600.0; NEW = 375.0; PERS = 475.0
WS = [0.0, 0.1, 0.25, 0.5, 1.0]
BUD = {'25ha': int(25e4 / CELL ** 2), '100ha': int(100e4 / CELL ** 2)}


def looks(ev):
    t = ev.t.values; g = np.zeros(len(ev), int)
    for i in range(1, len(ev)):
        g[i] = g[i - 1] + int((t[i] - t[i - 1]) > np.timedelta64(90, 'm'))
    return g


rows = []
for e, ev in V.groupby('event'):
    ev = ev.sort_values('t').reset_index(drop=True); g = looks(ev); n = g.max() + 1
    if n < 3:
        continue
    for k in range(1, n - 1):
        known = ev[g <= k]; last = ev[g == k]; prev = ev[g < k]; t_issue = last.t.max()
        P = prev[['x', 'y']].values; L = last[['x', 'y']].values; K = known[['x', 'y']].values
        dprev = np.sqrt(((L[:, None, :] - P[None, :, :]) ** 2).sum(-1)).min(1)
        newL = L[dprev > NEW]
        mom = newL.mean(0) - P.mean(0) if len(newL) else None
        x0, y0 = K.min(0) - R; x1, y1 = K.max(0) + R
        gx, gy = np.meshgrid(np.arange(x0, x1, CELL), np.arange(y0, y1, CELL)); C = np.c_[gx.ravel(), gy.ravel()]
        dall = np.full(len(C), np.inf); dlast = np.full(len(C), np.inf)
        for p in K: dall = np.minimum(dall, np.hypot(C[:, 0] - p[0], C[:, 1] - p[1]))
        for p in L: dlast = np.minimum(dlast, np.hypot(C[:, 0] - p[0], C[:, 1] - p[1]))
        keep = dall <= R; C, dall, dlast = C[keep], dall[keep], dlast[keep]
        if mom is not None and np.hypot(*mom) > 0:
            v = C - L.mean(0); cosang = (v @ mom) / (np.hypot(v[:, 0], v[:, 1]) * np.hypot(*mom) + 1e-9)
        else:
            cosang = np.zeros(len(C))
        npers = int((dall <= PERS).sum())
        for h in (24, 48):
            fut = ev[(ev.t > t_issue) & (ev.t <= t_issue + pd.Timedelta(hours=h))]
            if not len(fut):
                continue
            T = fut[['x', 'y']].values
            dT = np.sqrt(((T[:, None, :] - K[None, :, :]) ** 2).sum(-1)).min(1); isnew = dT > NEW
            for base in ('pers', 'ring'):
                s0 = -dall if base == 'pers' else -np.abs(dlast - RING)
                for w in WS:
                    sc = s0 + w * RING * cosang
                    for bname, nb in list(BUD.items()) + [('pers', npers)]:
                        top = C[np.argsort(-sc, kind='stable')[:nb]]
                        hit = np.array([(np.maximum(np.abs(top[:, 0] - a), np.abs(top[:, 1] - b)) <= HIT).any() for a, b in T])
                        rows.append(dict(event=e, season=int(ev.season.iloc[0]), k=k, h=h, base=base, w=w, budget=bname, mom=mom is not None,
                                         n=len(T), hit=hit.mean(), n_new=int(isnew.sum()), hitnew=hit[isnew].mean() if isnew.any() else np.nan))
df = pd.DataFrame(rows); df.to_parquet(D + OUT.replace('.json', '.parquet'))
# leave-one-season-out choice of w (by mean hit at the same budget/horizon), then fire-bootstrap vs the plain rule
rng = np.random.default_rng(0); res = {}
for (h, base, b), x in df.groupby(['h', 'base', 'budget']):
    sel = []
    for s in sorted(x.season.unique()):
        tr = x[(x.season != s) & x.mom]; wbest = tr.groupby('w').hit.mean().idxmax()
        sel.append(x[(x.season == s) & (x.w == wbest)].assign(wsel=wbest))
    lo = pd.concat(sel); pl = x[x.w == 0]
    m = lo.merge(pl[['event', 'k', 'hit', 'hitnew']], on=['event', 'k'], suffixes=('', '_plain'))
    f = m.groupby('event')[['hit', 'hit_plain']].mean(); diffs = []
    for _ in range(1000):
        i = rng.integers(0, len(f), len(f)); diffs.append((f.hit.values[i] - f.hit_plain.values[i]).mean())
    mm = m[m.mom]
    res[f'{h}h_{base}_{b}'] = dict(n_steps=len(m), n_fires=len(f), n_mom=int(m.mom.sum()), plain=round(m.hit_plain.mean(), 4), lean=round(m.hit.mean(), 4),
                                    ci=[round(float(np.percentile(diffs, q)), 4) for q in (2.5, 97.5)], w_chosen=lo.wsel.value_counts().to_dict(),
                                    mom_steps_plain=round(mm.hit_plain.mean(), 4), mom_steps_lean=round(mm.hit.mean(), 4),
                                    new_plain=round(mm.hitnew_plain.mean(), 4), new_lean=round(mm.hitnew.mean(), 4))
    print(f'{h}h {base} {b}', res[f'{h}h_{base}_{b}'], flush=True)
json.dump(res, open(D + OUT, 'w'), indent=1, default=str)
