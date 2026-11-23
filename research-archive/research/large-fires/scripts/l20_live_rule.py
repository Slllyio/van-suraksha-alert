"""Step 20. Live-rule check on 2026. A live engine sees one day at a time, so 'top 1% of the season' must come from a fixed
per-division score cut set on an earlier season. Rules (all per division, 200 ha+ / 500 ha+ scar fires, 2026):
  daily   : top q% of squares every day (what watch/big_watch.py does now: rank_in_division per day)
  cut25   : score >= the division's 2025 season (1-q) quantile of BIG
  cut25a  : same with s / day-mean^0.5 (the late-season fix), cut from 2025
  season  : 2026's own season quantile (hindsight, the research number)
Out: results/live_rule_2026.csv, results/live_cuts_2025.json (cuts per division for the engine)."""
import json, pickle, numpy as np, pandas as pd
from scipy.ndimage import maximum_filter
import lf_common as L, lf_sr
from l16_flag_timing import ph
B = lf_sr.Fe.base(); U, ur, uc, home = B['U'], B['ur'], B['uc'], B['home']; names = B['divnames']
F = [f for f in pickle.load(open(L.SC + 'fires_2026.pkl', 'rb')) if f['forest_ha'] >= 200 and pd.Timestamp('2026-02-15') <= f['start_day'] <= pd.Timestamp('2026-05-31')]
days = pd.date_range('2026-02-13', '2026-05-30')
ld = lambda y: np.clip(np.nan_to_num(np.load(L.SC + f'cube_BIG_{y}.npy').astype(np.float32), nan=0), 1e-7, None)
c25, c26 = ld(2025), ld(2026); divs = np.unique(home[home >= 0]); out = []; cuts = {}
for q in (0.01, 0.02):
    for rule in ('daily', 'cut25', 'cut25a', 'season'):
        flag = np.zeros_like(c26, bool)
        for k in divs:
            ix = np.nonzero(home == k)[0]; v = c26[:, ix]
            if rule == 'daily': flag[:, ix] = v >= np.quantile(v, 1 - q, axis=1, keepdims=True)
            elif rule == 'season': flag[:, ix] = v >= np.quantile(v, 1 - q)
            elif rule == 'cut25': t = np.quantile(c25[:, ix], 1 - q); flag[:, ix] = v >= t; cuts.setdefault(f'top{int(q*100)}', {})[str(names[k])] = float(t)
            else:
                w = c25[:, ix]; t = np.quantile(w / w.mean(1, keepdims=True) ** .5, 1 - q); flag[:, ix] = v / v.mean(1, keepdims=True) ** .5 >= t
                cuts.setdefault(f'top{int(q*100)}_dayadj', {})[str(names[k])] = float(t)
        G = np.zeros((len(days), L.H, L.W), bool)
        for t in range(len(days)): g = np.zeros((L.H, L.W), bool); g[ur[flag[t]], uc[flag[t]]] = True; G[t] = maximum_filter(g, 3)
        ground = 100 * np.mean([G[t][ur, uc].mean() for t in range(len(days))])
        hits = [(f['forest_ha'], ph(f['start_day']), any(G[t][f['start_cells'] // L.W, f['start_cells'] % L.W].any() for t in [(f['start_day'] - pd.Timedelta(days=dd) - days[0]).days for dd in (1, 2)] if 0 <= t < len(days))) for f in F]
        H = pd.DataFrame(hits, columns=['ha', 'phase', 'hit'])
        for th in (200, 500):
            h = H[H.ha >= th]; bs = h.hit.values[np.random.default_rng(0).integers(0, len(h), (1000, len(h)))].mean(1) * 100
            out.append(dict(q=q, rule=rule, size=f'{th}+', n=len(h), catch=round(100 * h.hit.mean(), 1), lo=round(np.percentile(bs, 2.5), 1), hi=round(np.percentile(bs, 97.5), 1),
                            late=round(100 * h[h.phase >= 'c'].hit.mean(), 1), ground=round(ground, 2), flags_per_day=round(flag.sum(1).mean())))
R = pd.DataFrame(out); R.to_csv(L.OUT + 'live_rule_2026.csv', index=False); json.dump(cuts, open(L.OUT + 'live_cuts_2025.json', 'w'))
print(R.to_string())
