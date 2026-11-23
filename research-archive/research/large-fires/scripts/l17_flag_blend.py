"""Step 17. Middle ground between the season rule and daily flags: rank s / m_d^a, where m_d = mean BIG score of the
division's squares that day (a = 0 season rule, a = 1 close to daily). a chosen on held 2022-24, checked on 2025-26.
Out: results/flag_blend.csv."""
import pickle, numpy as np, pandas as pd
from scipy.ndimage import maximum_filter
import lf_common as L, lf_sr
from l16_flag_timing import ph
B = lf_sr.Fe.base(); U, ur, uc, home = B['U'], B['ur'], B['uc'], B['home']
F = pickle.load(open(L.SC + 'fires.pkl', 'rb')) + pickle.load(open(L.SC + 'fires_2026.pkl', 'rb'))
ev = []
for y in (2022, 2023, 2024, 2025, 2026):
    days = pd.date_range(f'{y}-02-13', f'{y}-05-30')
    Fy = [f for f in F if f['year'] == y and f['forest_ha'] >= 200 and pd.Timestamp(f'{y}-02-15') <= f['start_day'] <= pd.Timestamp(f'{y}-05-31')]
    c = np.clip(np.nan_to_num(np.load(L.SC + f'cube_BIG_{y}.npy').astype(np.float32), nan=0), 1e-7, None)
    for a in (0, 0.25, 0.5, 0.75):
        for q in (0.01, 0.02):
            flag = np.zeros_like(c, bool)
            for k in np.unique(home[home >= 0]):
                ix = np.nonzero(home == k)[0]; v = c[:, ix] / c[:, ix].mean(1, keepdims=True) ** a; flag[:, ix] = v >= np.quantile(v, 1 - q)
            G = np.zeros((len(days), L.H, L.W), bool)
            for t in range(len(days)): g = np.zeros((L.H, L.W), bool); g[ur[flag[t]], uc[flag[t]]] = True; G[t] = maximum_filter(g, 3)
            for f in Fy:
                r, cc = f['start_cells'] // L.W, f['start_cells'] % L.W
                hit = any(G[t][r, cc].any() for t in [(f['start_day'] - pd.Timedelta(days=dd) - days[0]).days for dd in (1, 2)] if 0 <= t < len(days))
                ev.append(dict(year=y, a=a, q=q, fire=f['fire'], ha=f['forest_ha'], phase=ph(f['start_day']), hit=hit))
    print(y, flush=True)
E = pd.DataFrame(ev); E['period'] = np.where(E.year <= 2024, 'held 2022-24', E.year.astype(str))
out = []
for th in (200, 500):
    e = E[E.ha >= th]
    for k, g in list(e.groupby(['period', 'a', 'q'])) + list(e.groupby(['period', 'a', 'q', 'phase'])):
        out.append(dict(size=f'{th}+', period=k[0], a=k[1], q=k[2], phase=k[3] if len(k) > 3 else 'all', n=len(g), catch=round(100 * g.hit.mean(), 1)))
R = pd.DataFrame(out); R.to_csv(L.OUT + 'flag_blend.csv', index=False)
print(R[R.q == 0.01].pivot_table(index=['size', 'period', 'phase'], columns='a', values='catch').to_string())
