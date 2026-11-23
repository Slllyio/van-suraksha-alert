"""Does a 70 m ECOSTRESS hot front place the next 24 h of burning better than VIIRS dots alone? (Oct 17, Akkshay: "use 70 m thermal then")
Visible passes (>= 10 K) from big-fires/results/ecostress_pass_stats.csv (hot-pixel centre only; the 70 m clips themselves were in another
session's scratch and are gone). At the ECOSTRESS time t: VIIRS dots seen up to t; real new burning in (t, t+24 h] = blend arrival map
inside outline v2 (built from VIIRS only, so independent of ECOSTRESS). Same added area for every rule (the true new area, then 24 ha):
  dots      : nearest to any VIIRS dot so far (current rule)
  dots+hot  : nearest to dots or the 70 m hot centre (hot centre added as an extra dot)
  hot only  : nearest to the hot centre
Score = overlap of the ADDED ground with the real new burning (Sorensen), plus share of real new burning within 500 m of the hot centre
vs of the latest VIIRS dots.
"""
import sys, pickle, json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts'); import c0_lib as C
X0, Y0 = 737300.0, 2560500.0
S = pd.read_csv('/mnt/project-files/research/big-fires/results/ecostress_pass_stats.csv', parse_dates=['t0'])
S = S[S.visible10 == True].drop_duplicates(['fire', 't0'])
A = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis']
M = {}
for p in ['/tmp/claude-0/fronts/mf', '/tmp/claude-0/unseen/u']:
    M.update(pickle.load(open(f'{p}_maps.pkl', 'rb')))
import os
HP = pd.read_csv('/tmp/claude-0/eco_cache/hot_pixels.csv', parse_dates=['t0']) if os.environ.get('HOTPX') else None
so = lambda a, b: 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)
rows = []
for r in S.itertuples():
    if r.fire not in M:
        rows.append(dict(fire=r.fire, skip='one VIIRS look only')); continue
    mp = M[r.fire]; r0, r1, c0, c1 = mp['box']; Tg = mp['Tg'].ravel(); dom = mp['dom'].ravel()
    rr, cc = np.mgrid[r0:r1, c0:c1]; P = np.c_[(X0 + (cc + .5) * 20).ravel(), (Y0 - (rr + .5) * 20).ravel()]
    d = C.viirs_looks(A[A.fire == r.fire]); t0 = d.t.min(); th = (r.t0 - t0).total_seconds() / 3600
    known = d[d.t <= r.t0]
    if len(known) == 0:
        rows.append(dict(fire=r.fire, skip='before first VIIRS dot')); continue
    xy = known[['x', 'y']].values; hot = np.array([[r.hot_cx, r.hot_cy]])
    if HP is not None:
        hp = HP[(HP.fire == r.fire) & ((HP.t0 - r.t0).abs() <= pd.Timedelta(minutes=2))][['x', 'y']].drop_duplicates().values
        if len(hp): hot = hp
    new = dom & (Tg > th) & (Tg <= th + 24); nn = int(new.sum())
    if nn < 25:
        rows.append(dict(fire=r.fire, skip=f'under 1 ha new burning ({nn * .04:.1f} ha)')); continue
    dd = cKDTree(xy).query(P)[0]; dh = cKDTree(hot).query(P)[0]; foot = dd <= 265
    out = dict(fire=r.fire, t=str(r.t0), big=bool(r.big), n_hot=r.n_hot, new_ha=nn * .04, viirs_dots=len(xy), th=round(th, 1))
    for tag, n in [('true', nn), ('24ha', 600)]:
        for name, score in [('dots', dd), ('dots_hot', np.minimum(dd, dh)), ('hot', dh)]:
            s = np.where(foot, np.inf, score); m = np.zeros(len(s), bool); m[np.argsort(s, kind='stable')[:n]] = True
            out[f'{name}_{tag}'] = so(m, new)
    near = d[(d.t - r.t0).abs() <= pd.Timedelta(hours=1)]           # control: VIIRS look within 1 h of the 70 m pass (same timing, 375 m)
    if len(near):
        vx = near[['x', 'y']].values; dv = cKDTree(vx).query(P)[0]; vc = cKDTree(vx.mean(0, keepdims=True)).query(P)[0]
        for name, score in [('dots_vnear', np.minimum(dd, dv)), ('dots_vcentre', np.minimum(dd, vc))]:
            s = np.where(foot, np.inf, score); m = np.zeros(len(s), bool); m[np.argsort(s, kind='stable')[:nn]] = True
            out[f'{name}_true'] = so(m, new)
    last = known[known.t == known.t.max()][['x', 'y']].values; dl = cKDTree(last).query(P)[0]
    out['new_within500_hot'] = float((dh[new] <= 500).mean()); out['new_within500_lastviirs'] = float((dl[new] <= 500).mean())
    out['new_within500_anydot'] = float((dd[new] <= 500).mean())
    rows.append(out)
R = pd.DataFrame(rows); R.to_csv('/tmp/claude-0/unseen/eco_front_test' + ('_line' if HP is not None else '') + '.csv', index=False)
U = R[R.skip.isna()] if 'skip' in R else R
res = dict(visible_passes=len(S), usable=len(U), skipped=R.skip.value_counts().to_dict() if 'skip' in R else {})
for c in [c for c in U.columns if c.endswith('_true') or c.endswith('_24ha') or c.startswith('new_within')]:
    res[c] = round(float(U[c].median()), 3)
res['dots_hot_beats_dots_true'] = int((U.dots_hot_true > U.dots_true + .01).sum()); res['dots_hot_worse_true'] = int((U.dots_hot_true < U.dots_true - .01).sum())
rng = np.random.default_rng(0); df = (U.dots_hot_true - U.dots_true).values
res['dots_hot_minus_dots_ci'] = [round(float(np.percentile([df[rng.integers(0, len(df), len(df))].mean() for _ in range(4000)], q)), 3) for q in (2.5, 97.5)]
V = U.dropna(subset=['dots_vnear_true']) if 'dots_vnear_true' in U else U.iloc[:0]
res['with_viirs_within_1h'] = dict(n=len(V), dots=round(float(V.dots_true.median()), 3), dots_hot=round(float(V.dots_hot_true.median()), 3), dots_viirs_1h=round(float(V.dots_vnear_true.median()), 3), dots_viirs_1h_centre=round(float(V.dots_vcentre_true.median()), 3), hot_beats_viirs1h=int((V.dots_hot_true > V.dots_vnear_true + .01).sum()), viirs1h_beats_hot=int((V.dots_vnear_true > V.dots_hot_true + .01).sum()))
print(json.dumps(res, indent=1)); json.dump(res, open('/tmp/claude-0/unseen/eco_front_test' + ('_line' if HP is not None else '') + '.json', 'w'), indent=1)
print(U[['fire', 't', 'big', 'new_ha', 'dots_true', 'dots_hot_true', 'hot_true', 'new_within500_hot', 'new_within500_lastviirs']].round(2).to_string())
