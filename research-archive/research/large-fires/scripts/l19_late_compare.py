"""Step 19. Late-season fixes side by side, each fire once, top 1% / 2% per division (season rule), paired with BIG.
Variants: BIG (now), BIG_a05 (rank s / day mean^0.5, l17), BIGW (late rows x3, l18), BIGS (late-only model from 16 Apr, l18), BIGW_a05.
Out: results/late_fixes.csv, scratch late_fix_events.parquet."""
import pickle, numpy as np, pandas as pd
from scipy.ndimage import maximum_filter
import lf_common as L, lf_sr
from l16_flag_timing import ph
B = lf_sr.Fe.base(); U, ur, uc, home = B['U'], B['ur'], B['uc'], B['home']
F = pickle.load(open(L.SC + 'fires.pkl', 'rb')) + pickle.load(open(L.SC + 'fires_2026.pkl', 'rb'))
V = {'BIG': ('BIG', 0), 'BIG_a05': ('BIG', .5), 'BIGW': ('BIGW', 0), 'BIGS': ('BIGS', 0), 'BIGW_a05': ('BIGW', .5)}
ev = []
for y in (2022, 2023, 2024, 2025, 2026):
    days = pd.date_range(f'{y}-02-13', f'{y}-05-30')
    Fy = [f for f in F if f['year'] == y and f['forest_ha'] >= 200 and pd.Timestamp(f'{y}-02-15') <= f['start_day'] <= pd.Timestamp(f'{y}-05-31')]
    for nm, (cube, a) in V.items():
        c = np.clip(np.nan_to_num(np.load(L.SC + f'cube_{cube}_{y}.npy').astype(np.float32), nan=0), 1e-7, None)
        c = c + np.random.default_rng(y).random(c.shape).astype(np.float32) * 1e-9
        for q in (0.01, 0.02):
            flag = np.zeros_like(c, bool)
            for k in np.unique(home[home >= 0]):
                ix = np.nonzero(home == k)[0]; v = c[:, ix] / c[:, ix].mean(1, keepdims=True) ** a; flag[:, ix] = v >= np.quantile(v, 1 - q)
            G = np.zeros((len(days), L.H, L.W), bool)
            for t in range(len(days)): g = np.zeros((L.H, L.W), bool); g[ur[flag[t]], uc[flag[t]]] = True; G[t] = maximum_filter(g, 3)
            for f in Fy:
                r, cc = f['start_cells'] // L.W, f['start_cells'] % L.W
                hit = any(G[t][r, cc].any() for t in [(f['start_day'] - pd.Timedelta(days=dd) - days[0]).days for dd in (1, 2)] if 0 <= t < len(days))
                ev.append(dict(year=y, v=nm, q=q, fire=f['fire'], ha=f['forest_ha'], phase=ph(f['start_day']), hit=hit))
    print(y, flush=True)
E = pd.DataFrame(ev); E.to_parquet(L.SC + 'late_fix_events.parquet')
E['period'] = np.where(E.year <= 2024, 'held 2022-24', E.year.astype(str)); E['late'] = np.where(E.phase >= 'c', 'from 16 Apr', 'to 15 Apr')
out = []
for th in (200, 500):
    for (p, q), g in E[E.ha >= th].groupby(['period', 'q']):
        base = g[g.v == 'BIG'].set_index('fire')
        for nm in V:
            h = g[g.v == nm].set_index('fire').hit.reindex(base.index)
            for part, idx in (('all', base.index), ('from 16 Apr', base.index[base.late == 'from 16 Apr']), ('to 15 Apr', base.index[base.late == 'to 15 Apr'])):
                d = (h[idx].astype(float) - base.hit[idx].astype(float)).values
                bs = d[np.random.default_rng(0).integers(0, len(d), (1000, len(d)))].mean(1) * 100
                out.append(dict(size=f'{th}+', period=p, q=q, variant=nm, part=part, n=len(d), catch=round(100 * h[idx].mean(), 1),
                                gain=round(100 * d.mean(), 1), lo=round(np.percentile(bs, 2.5), 1), hi=round(np.percentile(bs, 97.5), 1)))
R = pd.DataFrame(out); R.to_csv(L.OUT + 'late_fixes.csv', index=False)
print(R[(R['size'] == '200+') & (R.q == 0.01)].to_string())
