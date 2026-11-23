"""Step 16. Fix A: spread the watch list's flags by day. 'season' = top q% of each division's square-days over the season
(current rule); 'daily' = top q% of each division's squares every day (same total ground). Each 200 ha+ / 500 ha+ scar fire
once, first-look square or a neighbour flagged 1-2 days before. 2022-24 held out, 2025 and 2026 forward.
Out: results/flag_timing.csv."""
import pickle, numpy as np, pandas as pd
from scipy.ndimage import maximum_filter
import lf_common as L, lf_sr
B = lf_sr.Fe.base(); U, ur, uc, home = B['U'], B['ur'], B['uc'], B['home']
F = pickle.load(open(L.SC + 'fires.pkl', 'rb')) + pickle.load(open(L.SC + 'fires_2026.pkl', 'rb'))
ph = lambda d: 'a <=15 Mar' if (d.month, d.day) <= (3, 15) else 'b 16 Mar-15 Apr' if (d.month, d.day) <= (4, 15) else 'c 16-30 Apr' if d.month == 4 else 'd May'
ev = []
for y in (2022, 2023, 2024, 2025, 2026):
    days = pd.date_range(f'{y}-02-13', f'{y}-05-30')
    Fy = [f for f in F if f['year'] == y and f['forest_ha'] >= 200 and pd.Timestamp(f'{y}-02-15') <= f['start_day'] <= pd.Timestamp(f'{y}-05-31')]
    for m in ('ALL', 'BIG'):
        c = np.nan_to_num(np.load(L.SC + f'cube_{m}_{y}.npy').astype(np.float32), nan=-1)
        c = c + np.random.default_rng(y).random(c.shape).astype(np.float32) * 1e-7
        for q in (0.01, 0.02):
            for mode in ('season', 'daily'):
                flag = np.zeros_like(c, bool)
                for k in np.unique(home[home >= 0]):
                    ix = np.nonzero(home == k)[0]; v = c[:, ix]
                    flag[:, ix] = v >= (np.quantile(v, 1 - q) if mode == 'season' else np.quantile(v, 1 - q, axis=1, keepdims=True))
                G = np.zeros((len(days), L.H, L.W), bool)
                for t in range(len(days)): g = np.zeros((L.H, L.W), bool); g[ur[flag[t]], uc[flag[t]]] = True; G[t] = maximum_filter(g, 3)
                for f in Fy:
                    r, cc = f['start_cells'] // L.W, f['start_cells'] % L.W
                    hit = any(G[t][r, cc].any() for t in [(f['start_day'] - pd.Timedelta(days=dd) - days[0]).days for dd in (1, 2)] if 0 <= t < len(days))
                    ev.append(dict(year=y, model=m, q=q, mode=mode, fire=f['fire'], ha=f['forest_ha'], phase=ph(f['start_day']), hit=hit))
        print(y, m, flush=True)
E = pd.DataFrame(ev); E.to_parquet(L.SC + 'flag_timing_events.parquet')
E['period'] = np.where(E.year <= 2024, 'held 2022-24', E.year.astype(str))
out = []
for th in (200, 500):
    e = E[E.ha >= th]
    for keys, g in list(e.groupby(['period', 'model', 'q', 'mode'])) + list(e.groupby(['period', 'model', 'q', 'mode', 'phase'])):
        out.append(dict(size=f'{th}+', period=keys[0], model=keys[1], q=keys[2], mode=keys[3], phase=keys[4] if len(keys) > 4 else 'all', n=len(g), catch=round(100 * g.hit.mean(), 1)))
R = pd.DataFrame(out); R.to_csv(L.OUT + 'flag_timing.csv', index=False)
print(R[(R['size'] == '200+') & (R.q == 0.01)].pivot_table(index=['period', 'phase'], columns=['model', 'mode'], values='catch').to_string())
