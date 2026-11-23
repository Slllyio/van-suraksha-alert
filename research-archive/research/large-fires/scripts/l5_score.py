"""Step 5. Score each model on LARGE fires only, each fire counted once.
A fire (start 15 Feb-31 May, IST) is caught when one of its first-look squares, or a square next to it (3x3), is flagged on
the day before or two days before it starts. Flags = top q% of each division's square-days in that season (ties broken
at random), q = 1, 2, 5, 10, 20. Ground = share of square-days flagged or next to a flag. Precision = share of flagged
square-days that get a large-fire first look within the 3x3 in the next 2 days. 95% CI by resampling fires.
Out: results/catch_curves.csv, results/catch_by_division.csv, results/catch_by_phase.csv."""
import sys, pickle, numpy as np, pandas as pd
from scipy.ndimage import maximum_filter
import lf_common as L, lf_sr
Fe = lf_sr.Fe
QS = (0.01, 0.02, 0.05, 0.10, 0.20)
MODELS = sys.argv[1].split(',') if len(sys.argv) > 1 else ['ALL', 'ALLS', 'START', 'BIG', 'B100', 'B500', 'TWO', 'HIST', 'BIGH', 'RAND']
import os
YEARS = tuple(int(x) for x in os.environ.get('LF_YEARS', '2022,2023,2024,2025').split(','))
THS = (100, 200, 500)
TAG = os.environ.get('LF_TAG', '')


def main():
    B = Fe.base(); U, ur, uc, home = B['U'], B['ur'], B['uc'], B['home']; nU = len(U); names = B['divnames']
    fires = pickle.load(open(L.SC + os.environ.get('LF_FIRES', 'fires.pkl'), 'rb'))
    rows, drows, prows, ev_all = [], [], [], []
    for y in YEARS:
        days = pd.date_range(f'{y}-02-13', f'{y}-05-30'); di = {d: i for i, d in enumerate(days)}
        F = [f for f in fires if f['year'] == y and f['forest_ha'] >= min(THS) and pd.Timestamp(f'{y}-02-15') <= f['start_day'] <= pd.Timestamp(f'{y}-05-31')]
        # large-start rasters for precision: per threshold, (days, H, W) of first looks on t+1/t+2, dilated 3x3
        LS = {}
        for th in THS:
            A = np.zeros((len(days), L.H, L.W), bool)
            for f in F:
                if f['forest_ha'] < th: continue
                r, c = f['start_cells'] // L.W, f['start_cells'] % L.W
                for dd in (1, 2):
                    t = di.get(f['start_day'] - pd.Timedelta(days=dd))
                    if t is not None: A[t, r, c] = True
            LS[th] = np.stack([maximum_filter(a, 3)[ur, uc] for a in A])
        rng = np.random.default_rng(y)
        for mname in MODELS:
            s = rng.random((len(days), nU)).astype(np.float32) if mname == 'RAND' else np.load(L.SC + f'cube_{mname}_{y}.npy').astype(np.float32)
            s = s + rng.random(s.shape).astype(np.float32) * 1e-6 * (np.nanstd(s) + 1e-9)
            s = np.nan_to_num(s, nan=-1)
            for q in QS:
                flag = np.zeros_like(s, bool)
                for k in range(len(names)):
                    ix = np.nonzero(home == k)[0]
                    if len(ix) == 0: continue
                    v = s[:, ix]; flag[:, ix] = v >= np.quantile(v, 1 - q)
                NEAR = np.zeros_like(flag)
                for t in range(len(days)):
                    g = np.zeros((L.H, L.W), bool); g[ur[flag[t]], uc[flag[t]]] = True; NEAR[t] = maximum_filter(g, 3)[ur, uc]
                ground = NEAR.mean()
                gfull = {}
                for t in range(len(days)):
                    g = np.zeros((L.H, L.W), bool); g[ur[NEAR[t]], uc[NEAR[t]]] = True; gfull[t] = g
                for f in F:
                    r, c = f['start_cells'] // L.W, f['start_cells'] % L.W; hit = False
                    for dd in (1, 2):
                        t = di.get(f['start_day'] - pd.Timedelta(days=dd))
                        if t is not None and gfull[t][r, c].any(): hit = True
                    ev_all.append(dict(model=mname, q=q, season=y, fire=f['fire'], div=f['div'], ha=f['forest_ha'], month=f['start_day'].month,
                                       day=f['start_day'].dayofyear, hit=hit))
                rows.append(dict(model=mname, q=q, season=y, ground=ground, **{f'prec{th}': LS[th][flag].mean() for th in THS},
                                 **{f'base{th}': LS[th].mean() for th in THS}))
            print(y, mname, flush=True)
    E = pd.DataFrame(ev_all); R = pd.DataFrame(rows)
    E.to_parquet(L.SC + f'events_scored{TAG}.parquet'); R.to_csv(L.OUT + f'season_rows{TAG}.csv', index=False)
    out = []
    for (m, q), g in E.groupby(['model', 'q']):
        r = R[(R.model == m) & (R.q == q)]
        for per, ys in (('held 2022-24', (2022, 2023, 2024)), ('fwd 2025', (2025,)), ('fwd 2026', (2026,))):
            if not set(ys) & set(YEARS): continue
            gg = g[g.season.isin(ys)]; rr = r[r.season.isin(ys)]
            for th in THS:
                h = gg.hit[gg.ha >= th].values.astype(float)
                bs = np.random.default_rng(0).integers(0, len(h), (500, len(h)))
                ci = np.percentile(h[bs].mean(1), [2.5, 97.5]) * 100
                out.append(dict(model=m, flag_share=q, period=per, size=f'{th}+', n_fires=len(h), catch=100 * h.mean(), lo=ci[0], hi=ci[1],
                                ground=100 * rr.ground.mean(), precision=100 * rr[f'prec{th}'].mean(), base_rate=100 * rr[f'base{th}'].mean()))
    pd.DataFrame(out).round(2).to_csv(L.OUT + f'catch_curves{TAG}.csv', index=False)


if __name__ == '__main__':
    main()
