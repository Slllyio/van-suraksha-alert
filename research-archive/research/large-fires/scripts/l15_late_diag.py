"""Step 15. Why are late-season (16 Apr-31 May) big fires missed? Per 200 ha+ fire, 2022-26 scar truth:
caught at top 1% (BIG, same rule as l5), the start square's BIG percentile within its division that day (day -1),
season-to-date burnt share (earlier scar fires this season) within 0.5 and 2.5 km of the start, scar fires active within
10 km in the 3 days before, and the start square's past burning (bf_all_r3 proxy: earlier-season scar cells nearby).
Out: results/late_diag.csv (one row per fire)."""
import pickle, numpy as np, pandas as pd
from scipy.ndimage import uniform_filter, maximum_filter
import lf_common as L, lf_sr
B = lf_sr.Fe.base(); U, ur, uc, home = B['U'], B['ur'], B['uc'], B['home']
pos = np.full(L.H * L.W, -1); pos[U] = np.arange(len(U))
F = pickle.load(open(L.SC + 'fires.pkl', 'rb')) + pickle.load(open(L.SC + 'fires_2026.pkl', 'rb'))
rows = []
for y in (2022, 2023, 2024, 2025, 2026):
    days = pd.date_range(f'{y}-02-13', f'{y}-05-30')
    c = np.nan_to_num(np.load(L.SC + f'cube_BIG_{y}.npy').astype(np.float32), nan=-1)
    pct = np.zeros_like(c)
    flag = np.zeros_like(c, bool)
    for k in np.unique(home[home >= 0]):
        ix = np.nonzero(home == k)[0]; v = c[:, ix]; flag[:, ix] = v >= np.quantile(v, .99)
        pct[:, ix] = (np.argsort(np.argsort(v, 1), 1) + .5) / len(ix)
    Fy = sorted([f for f in F if f['year'] == y], key=lambda f: f['start_day'])
    burnt = np.zeros((L.H, L.W), np.float32); j = 0
    starts = [(f['start_day'], f['start_cells']) for f in Fy]
    for f in Fy:
        if not (pd.Timestamp(f'{y}-02-15') <= f['start_day'] <= pd.Timestamp(f'{y}-05-31')): continue
        if f['forest_ha'] < 200: continue
        # season-to-date burnt: fires ending before this start
        g = np.zeros(L.H * L.W, np.float32)
        for h in Fy:
            if h['last_day'] < f['start_day']: np.maximum.at(g, h['cells'], h['frac'])
        g = g.reshape(L.H, L.W); r, cc = f['start_cells'] // L.W, f['start_cells'] % L.W
        b1 = uniform_filter(g, 3)[r, cc].mean(); b5 = uniform_filter(g, 11)[r, cc].mean()
        act = sum(1 for h in Fy if 0 < (f['start_day'] - h['start_day']).days <= 3 and np.hypot(*(np.array([h['start_cells'][0] // L.W, h['start_cells'][0] % L.W]) - [r[0], cc[0]])) * .5 <= 10)
        t = (f['start_day'] - pd.Timedelta(days=1) - days[0]).days; p = pos[f['start_cells']]; p = p[p >= 0]
        hit = False
        for dd in (1, 2):
            tt = (f['start_day'] - pd.Timedelta(days=dd) - days[0]).days
            if 0 <= tt < len(days):
                G = np.zeros((L.H, L.W), bool); G[ur[flag[tt]], uc[flag[tt]]] = True
                if maximum_filter(G, 3)[r, cc].any(): hit = True
        rows.append(dict(year=y, fire=f['fire'], div=f['div'], day=f['start_day'], ha=f['forest_ha'], hit=hit,
                         pct=float(pct[t, p].max()) if len(p) and t >= 0 else np.nan, burnt_05km=b1, burnt_25km=b5, active10km_3d=act))
    print(y, flush=True)
D = pd.DataFrame(rows); D.to_csv(L.OUT + 'late_diag.csv', index=False)
D['phase'] = np.where(D.day.dt.month * 100 + D.day.dt.day >= 416, 'late', 'early')
print(D.groupby(['phase', 'hit'])[['pct', 'burnt_05km', 'burnt_25km', 'active10km_3d', 'ha']].median().round(3))
print(D.groupby('phase').hit.agg(['mean', 'size']))
