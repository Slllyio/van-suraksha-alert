"""Tracking step 1b: "drizzle" on things that cannot move (FIRMS type 2 industrial hot sources, all MP).
Does combining many passes through the pixel model place a fixed source better than averaging pixel centres, and does the
error fall like 1/sqrt(N passes)? Truth is unknown for the sites, so precision is measured as the disagreement between two
independent halves (even vs odd years): if each half has error e, the halves differ by ~e*sqrt(2).
Per site and half:
  centre   : mean of pass centroids (each pass = mean of its flagged pixel centres), offsets corrected
  drizzle  : maximum likelihood point position: for every pass, log( sum over its flagged pixels of the pixel response
             at x ) (the source lies under the flagged pixels, response = box blurred by the geolocation error and by the
             native-sample trapezoid), summed over passes, on a 10 m grid
  median   : coordinate-wise median of pass centroids (robust to ghosts)
Also for N = 1, 2, 4, 8, 16, 32 random passes per half: the half-vs-half distance (precision vs number of looks).
Out: results/t1b_static_drizzle.json, fig_static_drizzle.png"""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t2_lib import gbox, nagg, axes, OUT, SC, TRACK_SPACING
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
rng = np.random.default_rng(0)
off = json.load(open(f'{OUT}/t1_calib.json'))['offsets']
offs = {}
for k, v in off.items():
    e = v['east_m'] if (v['east_ci'][0] > 0 or v['east_ci'][1] < 0) else 0.0; n = v['north_m'] if (v['north_ci'][0] > 0 or v['north_ci'][1] < 0) else 0.0
    offs[k] = (e, n)
S = pd.read_parquet(f'{SC}/static.parquet'); S = S[S.kind == 'viirs'].copy()
k = S.sensor + '|' + S.daynight; S['xc'] = S.x - k.map(lambda q: offs.get(q, (0, 0))[0]); S['yc'] = S.y - k.map(lambda q: offs.get(q, (0, 0))[1])
S['cell'] = (S.x // 3000).astype(int).astype(str) + '_' + (S.y // 3000).astype(int).astype(str); S['yr'] = S.t.dt.year
GEO = 80.0

def drizzle(g, c0, half=700, step=10):
    a = np.arange(-half, half + step, step); X, Y = np.meshgrid(c0[0] + a, c0[1] + a); X, Y = X.ravel(), Y.ravel(); L = np.zeros(len(X))
    for pk, p in g.groupby('pass_key'):
        us, ut = axes(p.heading.iloc[0]); acc = np.zeros(len(X))
        for q in p.itertuples():
            dx, dy = X - q.xc, Y - q.yc; ss = np.sqrt(GEO ** 2 + (q.scan_m / nagg(q.track_m) / 2) ** 2)
            acc += gbox(dx * us[0] + dy * us[1], q.scan_m, ss) * gbox(dx * ut[0] + dy * ut[1], q.track_m * TRACK_SPACING, GEO)
        L += np.log(acc + 1e-3)
    j = np.argmax(L); return np.array([X[j], Y[j]])

def est(g):
    pc = g.groupby('pass_key')[['xc', 'yc']].mean().values
    return dict(centre=pc.mean(0), median=np.median(pc, 0), drizzle=drizzle(g, pc.mean(0)))

rows, curve = [], []
for cell, g in S.groupby('cell'):
    g = g[np.hypot(g.xc - g.xc.median(), g.yc - g.yc.median()) < 1500]
    A, B = g[g.yr % 2 == 0], g[g.yr % 2 == 1]
    if A.pass_key.nunique() < 40 or B.pass_key.nunique() < 40: continue
    ea, eb = est(A), est(B)
    rows.append(dict(cell=cell, nA=A.pass_key.nunique(), nB=B.pass_key.nunique(), **{f'd_{m}': float(np.hypot(*(ea[m] - eb[m]))) for m in ea}))
    for N in [1, 2, 4, 8, 16, 32]:
        for rep in range(3):
            pa = rng.choice(A.pass_key.unique(), N, replace=False); pb = rng.choice(B.pass_key.unique(), N, replace=False)
            a_, b_ = est(A[A.pass_key.isin(pa)]), est(B[B.pass_key.isin(pb)])
            curve.append(dict(cell=cell, N=N, **{f'd_{m}': float(np.hypot(*(a_[m] - b_[m]))) for m in a_}))
    if len(rows) >= 40: break
R, C = pd.DataFrame(rows), pd.DataFrame(curve); R.to_csv(f'{OUT}/t1b_sites.csv', index=False); C.to_csv(f'{SC}/t1b_curve.csv', index=False)
res = dict(sites=len(R), passes_per_half_median=float(np.median(R[['nA', 'nB']].values)),
           half_vs_half_median_m={m: round(R[f'd_{m}'].median(), 1) for m in ['centre', 'median', 'drizzle']},
           drizzle_minus_centre_median_m=round(float((R.d_drizzle - R.d_centre).median()), 1),
           drizzle_closer_share=round(float((R.d_drizzle < R.d_centre).mean()), 3),
           by_N={int(N): {m: round(g[f'd_{m}'].median(), 1) for m in ['centre', 'median', 'drizzle']} for N, g in C.groupby('N')})
bt = []
for _ in range(1000):
    kk = rng.integers(0, len(R), len(R)); bt.append(np.median(R.d_drizzle.values[kk] - R.d_centre.values[kk]))
res['drizzle_minus_centre_ci'] = [round(float(np.quantile(bt, .025)), 1), round(float(np.quantile(bt, .975)), 1)]
json.dump(res, open(f'{OUT}/t1b_static_drizzle.json', 'w'), indent=1); print(json.dumps(res, indent=1))
fig, ax = plt.subplots(figsize=(5.5, 4))
Ns = sorted(C.N.unique())
for m, lab in [('centre', 'mean of pixel centres'), ('median', 'median of pass centres'), ('drizzle', 'pixel-model fit (drizzle)')]:
    ax.plot(Ns, [C[C.N == n][f'd_{m}'].median() / np.sqrt(2) for n in Ns], 'o-', label=lab)
ax.plot(Ns, [C[C.N == 1].d_centre.median() / np.sqrt(2) / np.sqrt(n) for n in Ns], 'k:', label='1/sqrt(N) from N=1')
ax.set_xscale('log', base=2); ax.set_yscale('log'); ax.set_xlabel('passes combined (N)'); ax.set_ylabel('position error of a fixed source (m)\n(half-vs-half distance / sqrt 2, median)')
ax.set_title('Industrial sources: error vs number of passes', fontsize=9); ax.legend(fontsize=7); plt.tight_layout(); plt.savefig(f'{OUT}/fig_static_drizzle.png', dpi=120)
