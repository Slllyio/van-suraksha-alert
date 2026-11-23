"""Summary of r5 steps: equal-area hit rates, season-held-out ring radius, by gap."""
import pandas as pd, numpy as np, json, sys
S = sys.argv[1]; X = pd.read_parquet(S + '/r5_steps.parquet')
w = lambda q, c: round(float(np.average(q[c], weights=q.n_new)), 3)
rc = [c for c in X.columns if c.startswith('ring_last_')]
out = {c: w(X, c) for c in ['persist', 'last_only'] + rc + [c for c in X.columns if c.startswith('ring_all_')]}
lo = []
for yr in sorted(X.yr.unique()):
    tr, te = X[X.yr != yr], X[X.yr == yr]
    if len(te) == 0: continue
    best = max(rc, key=lambda c: w(tr, c)); lo.append(te.assign(v=te[best], best=best))
lo = pd.concat(lo); out['ring_last_LOSO'] = w(lo, 'v'); out['LOSO_choices'] = lo.groupby('yr').best.first().to_dict()
for g0, g1 in ((10, 14), (14, 30), (30, 1000)):
    q = X[(X.gap >= g0) & (X.gap < g1)]
    if len(q): out[f'gap_{g0}_{g1}h'] = dict(n=len(q), persist=w(q, 'persist'), ring600=w(q, 'ring_last_600'), ring900=w(q, 'ring_last_900'))
out['n_steps'] = len(X); out['area_ha_med'] = float(X.area_ha.median())
json.dump(out, open(S + '/r5.json', 'w'), indent=1, default=str); print(json.dumps(out, indent=1, default=str))
