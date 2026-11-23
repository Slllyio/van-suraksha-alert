"""Step 9. Package the tested big-fire model (BIG, trained 2018-24, tested on 2025) for daily use -> research/large-fires/watch/:
  big_model.txt          LightGBM model; features.json = its input order
  calibration.json       isotonic map score -> % chance a 200 ha+ fire's first look lands in the square or next to it
                         in the next 2 days, fitted on 2025 (the held-out season)
  squares.npz            the 418,642 squares (U, mp_grid cell ids), their home division and division names
  scar_hist_<S>.npz      the scar-history inputs for season S (from earlier seasons' scar fires), S = 2025, 2026"""
import json, pickle, numpy as np, pandas as pd
from scipy.ndimage import maximum_filter
from sklearn.isotonic import IsotonicRegression
import lf_common as L, l2_samples as S2, lf_sr
W = L.HERE + 'watch/'
B = lf_sr.Fe.base(); U, ur, uc = B['U'], B['ur'], B['uc']
s, f = pickle.load(open(L.SC + 'models_fwd.pkl', 'rb'))['BIG']
open(W + 'big_model.txt', 'w').write(s); json.dump(f, open(W + 'features.json', 'w'))
np.savez_compressed(W + 'squares.npz', cells=U, home=B['home'], divnames=np.array(B['divnames']))
for y in (2025, 2026):
    sh = S2.scar_hist(y); np.savez_compressed(W + f'scar_hist_{y}.npz', **sh)
# calibration on 2025
cube = np.load(L.SC + 'cube_BIG_2025.npy').astype(np.float32)
days = pd.date_range('2025-02-13', '2025-05-30'); di = {d: i for i, d in enumerate(days)}
fires = [x for x in pickle.load(open(L.SC + 'fires.pkl', 'rb')) if x['year'] == 2025 and x['forest_ha'] >= 200]
A = np.zeros((len(days), L.H, L.W), bool)
for x in fires:
    r, c = x['start_cells'] // L.W, x['start_cells'] % L.W
    for dd in (1, 2):
        t = di.get(x['start_day'] - pd.Timedelta(days=dd))
        if t is not None: A[t, r, c] = True
Y = np.stack([maximum_filter(a, 3)[ur, uc] for a in A])
rng = np.random.default_rng(0); pos = np.nonzero(Y.ravel())[0]; neg = rng.choice(np.nonzero(~Y.ravel())[0], 3_000_000, replace=False)
idx = np.r_[pos, neg]; w = np.r_[np.ones(len(pos)), np.full(len(neg), (~Y).sum() / len(neg))]
iso = IsotonicRegression(out_of_bounds='clip', y_min=0).fit(cube.ravel()[idx], Y.ravel()[idx], sample_weight=w)
x = np.quantile(cube.ravel(), np.linspace(0, 1, 401)); x = np.unique(x)
json.dump(dict(x=x.tolist(), y=(100 * iso.predict(x)).tolist(), note='pct = numpy.interp(score, x, y); fitted on 2025, BIG model trained 2018-24'), open(W + 'calibration.json', 'w'))
pct = 100 * iso.predict(cube.ravel())
for lo, hi in ((0, 0.1), (0.1, 0.5), (0.5, 1), (1, 2), (2, 100)):
    m = (pct >= lo) & (pct < hi); print(f'said {lo}-{hi}%: squares {m.sum()}, happened {100 * Y.ravel()[m].mean():.2f}%')
