"""Step 11. Second forward season with no scars: score the 2-day lists on 2025 and 2026 against VIIRS-truth big fires
(field-system/docs/big_fire_replay/season_<S>.csv: new-fire first looks, viirs_ha = distinct 375 m cells within 7 days x 10.9 ha).
Same rule as l5 (top q% per division, first-look square or a neighbour flagged 1-2 days before, each fire once), but one
first-look square per fire (the replay's lat/lon). Models trained 2018-24, so 2025 and 2026 are both unseen.
Out: results/catch_curves_viirs_truth.csv."""
import numpy as np, pandas as pd
from scipy.ndimage import maximum_filter
from pyproj import Transformer
import lf_common as L, lf_sr
B = lf_sr.Fe.base(); U, ur, uc, home = B['U'], B['ur'], B['uc'], B['home']
QS = (0.01, 0.02, 0.05, 0.10); MODELS = ['ALL', 'BIG', 'B500', 'START', 'HIST', 'RAND']
tr = Transformer.from_crs(4326, 32643, always_xy=True); out = []
for y in (2025, 2026):
    days = pd.date_range(f'{y}-02-13', f'{y}-05-30')
    R = pd.read_csv(L.P + f'field-system/docs/big_fire_replay/season_{y}.csv')
    x, yy = tr.transform(R.lon.values, R.lat.values)
    R['r'] = ((L.Y1 - yy) // 500).astype(int); R['c'] = ((x - L.X0) // 500).astype(int)
    R['day'] = pd.to_datetime(R.first_look_utc).dt.tz_convert('Asia/Kolkata').dt.tz_localize(None).dt.normalize()
    R = R[(R.day >= f'{y}-02-15') & (R.day <= f'{y}-05-31') & (R.viirs_ha >= 200)]
    rng = np.random.default_rng(y)
    for m in MODELS:
        s = rng.random((len(days), len(U))).astype(np.float32) if m == 'RAND' else np.load(L.SC + f'cube_{m}_{y}.npy').astype(np.float32)
        s = np.nan_to_num(s + rng.random(s.shape).astype(np.float32) * 1e-6 * (np.nanstd(s) + 1e-9), nan=-1)
        for q in QS:
            flag = np.zeros_like(s, bool)
            for k in np.unique(home[home >= 0]):
                ix = np.nonzero(home == k)[0]; v = s[:, ix]; flag[:, ix] = v >= np.quantile(v, 1 - q)
            G = np.zeros((len(days), L.H, L.W), bool)
            for t in range(len(days)): g = np.zeros((L.H, L.W), bool); g[ur[flag[t]], uc[flag[t]]] = True; G[t] = maximum_filter(g, 3)
            ground = np.mean([G[t][ur, uc].mean() for t in range(len(days))])
            hit = []
            for _, f in R.iterrows():
                h = False
                for dd in (1, 2):
                    t = (f.day - pd.Timedelta(days=dd) - days[0]).days
                    if 0 <= t < len(days) and 0 <= f.r < L.H and 0 <= f.c < L.W and G[t][f.r, f.c]: h = True
                hit.append(h)
            hit = np.array(hit)
            for th in (200, 500):
                hh = hit[R.viirs_ha.values >= th].astype(float); bs = np.random.default_rng(0).integers(0, len(hh), (500, len(hh)))
                lo, hi = np.percentile(hh[bs].mean(1), [2.5, 97.5]) * 100
                out.append(dict(season=y, model=m, flag_share=q, size=f'{th}+', n_fires=len(hh), catch=100 * hh.mean(), lo=lo, hi=hi, ground=100 * ground))
        print(y, m, flush=True)
D = pd.DataFrame(out); D[['catch', 'lo', 'hi', 'ground']] = D[['catch', 'lo', 'hi', 'ground']].round(1); D.to_csv(L.OUT + 'catch_curves_viirs_truth.csv', index=False)
print(D.pivot_table(index=['season', 'size', 'flag_share'], columns='model', values='catch').to_string()); print(D[D.model.isin(['ALL', 'BIG'])].pivot_table(index=['season', 'size', 'flag_share'], columns='model', values=['lo', 'hi', 'ground']).to_string())
