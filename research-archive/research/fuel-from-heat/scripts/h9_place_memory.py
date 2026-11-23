"""Second method (Akkshay 17 Oct 07:25Z: "do it again, different methodology, good problem statement").

PROBLEM STATEMENT
  If fuel load drives heat, two things must be true, and neither needs a fuel map to test:
   (1) PLACE MEMORY: a place that burns hot in one year burns hot again in other years (fuel is a lasting property of
       the ground: canopy, species, litter fall). Weather and satellite geometry change every pass; the place does not.
   (2) FUEL RESET: right after a place burns, its fuel is gone, so the next season's fire there should be weaker, and
       heat should climb back with every unburnt year (fuel builds up again).
  The fire is used as its own measuring stick; the fuel map is only used afterwards to explain what we find.

METHOD
  Unit = one VIIRS detection (all 53k in Ratapani 2017-26, every satellite pass separate).
  Relative heat = log FRP compared only with OTHER detections of the SAME satellite pass (same minute, sensor, weather,
  time of day), also allowing for the pixel's size (swath position) and how much of its square burnt that season
  (scar outlines v1 bitmask). What is left = how much hotter or cooler this spot burnt than the rest of that pass.
  Place = 500 m square of the detection centre.
  Test 1: split each place's seasons into two halves; do the halves agree? Baseline: places shuffled.
  Test 2: same place, different seasons: relative heat vs seasons since that ground last burnt (1, 2, 3+).
          Place fixed effects, so canopy and everything else lasting about the place cancels.
  Test 3: what lasting ground property goes with hot places (canopy, teak, grass, slope).
Out: results/place_det.csv, results/place_tests.json
"""
import json
import numpy as np, pandas as pd, rasterio
import statsmodels.formula.api as smf
from scipy.stats import spearmanr
from h0_lib import RES, ROOT, layers, X0, Y0, NR, NC

v = pd.read_csv(f'{RES}/viirs_det.csv', parse_dates=['t'])
v = v[(v.frp > 0)].copy()
v['season'] = v.t.dt.year + (v.t.dt.month >= 11)
v = v[v.season.between(2017, 2026)]
v['pass'] = v.sensor + v.t.dt.strftime('%Y%m%d%H%M')
# burn history at 10 m (bit k = burnt in season 2017+k; scar outlines v1)
with rasterio.open(f'{ROOT}/fuel-map/ratapani/v3/burn_seasons_bitmask_10m.tif') as r:
    B = r.read(1); T = r.transform
H, W = B.shape
L = layers()
recs = []
for rr in v.itertuples():
    hx, hy = rr.scan_m / 2, rr.track_m / 2
    c0, c1 = int((rr.x - hx - T.c) // 10), int((rr.x + hx - T.c) // 10) + 1
    r0, r1 = int((T.f - rr.y - hy) // 10), int((T.f - rr.y + hy) // 10) + 1
    c0, r0, c1, r1 = max(c0, 0), max(r0, 0), min(c1, W), min(r1, H)
    if c1 <= c0 or r1 <= r0:
        recs.append({}); continue
    b = B[r0:r1, c0:c1].astype(np.int32); k = rr.season - 2017
    now = ((b >> k) & 1).mean()
    # seasons since this ground last burnt, per 10 m pixel, before this season (cap: unknown before 2017)
    since = np.full(b.shape, 99)
    for j in range(1, k + 1):
        hit = ((b >> (k - j)) & 1).astype(bool) & (since == 99); since[hit] = j
    # use the pixels that burnt this season (the burning ground), else the whole square
    m = ((b >> k) & 1).astype(bool)
    s = since[m] if m.any() else since.ravel()
    g0, g1 = (r0 + 100 * 0) // 2, (r1) // 2   # 10 m -> 20 m grid of layers (10 m raster sits 100 rows/cols inside)
    R20 = slice(r0 // 2 + 100, (r1 + 1) // 2 + 100); C20 = slice(c0 // 2 + 100, (c1 + 1) // 2 + 100)
    rec = dict(burnt_now=now, since1=(s == 1).mean(), since2=(s == 2).mean(), since3p=((s >= 3) & (s < 99)).mean(),
               since_unknown=(s == 99).mean(), hist_years=k)
    for n in ['canopy', 'teak', 'grass', 'slope', 'litter']:
        rec[n] = np.nanmean(L[n][R20, C20])
    recs.append(rec)
X = pd.DataFrame(recs, index=v.index); v = v.join(X).dropna(subset=['burnt_now', 'canopy'])
v['lf'] = np.log(v.frp); v['lpix'] = np.log(v.scan_m * v.track_m / 1e6)
v['place'] = (v.x // 500).astype(int).astype(str) + '_' + (v.y // 500).astype(int).astype(str)
# relative heat: within-pass, allowing for pixel size and burnt share of the square
v = v[v.groupby('pass').lf.transform('size') >= 3]
for c in ['lf', 'lpix', 'burnt_now']:
    v[c + '_d'] = v[c] - v.groupby('pass')[c].transform('mean')
m0 = smf.ols('lf_d ~ lpix_d + burnt_now_d - 1', v).fit()
v['rel'] = m0.resid
out = {'detections': len(v), 'passes': v['pass'].nunique(), 'places': v.place.nunique(),
       'adjust_coefs': m0.params.round(3).to_dict(), 'rel_sd': round(v.rel.std(), 3)}
print(out)

# TEST 1: place memory across seasons
P = v.groupby(['place', 'season']).rel.agg(['mean', 'size']).reset_index()
multi = P.groupby('place').season.nunique(); P = P[P.place.isin(multi[multi >= 2].index)]
rng = np.random.default_rng(0); rhos, rhos0 = [], []
for it in range(30):
    a, b_ = [], []
    for pl, g in P.groupby('place'):
        s = rng.permutation(g.season.values); h = len(s) // 2
        A = g[g.season.isin(s[:h])]; Bm = g[g.season.isin(s[h:])]
        a.append(np.average(A['mean'], weights=A['size'])); b_.append(np.average(Bm['mean'], weights=Bm['size']))
    a, b_ = np.array(a), np.array(b_)
    rhos.append(spearmanr(a, b_)[0]); rhos0.append(spearmanr(a, rng.permutation(b_))[0])
out['T1_places'] = int(P.place.nunique()); out['T1_rho_halves'] = round(float(np.median(rhos)), 3)
out['T1_rho_shuffled'] = round(float(np.median(rhos0)), 3)
# how big: hot vs cool places (by half A), heat in half B
qa = pd.qcut(a, 5, labels=False)
out['T1_quintile_halfB_factor'] = [round(float(np.exp(b_[qa == q].mean())), 3) for q in range(5)]
# share of variance that belongs to the place (between-season, one-way ANOVA on place-season means)
ps = P.copy(); grand = ps['mean'].mean()
msb = (ps.groupby('place')['mean'].agg(['mean', 'size']).pipe(lambda d: (d['size'] * (d['mean'] - grand) ** 2).sum() / (len(d) - 1)))
msw = ps.groupby('place')['mean'].apply(lambda s: ((s - s.mean()) ** 2).sum()).sum() / (len(ps) - ps.place.nunique())
n0 = ps.groupby('place').size().mean()
out['T1_place_share_of_variance'] = round(float(max((msb - msw) / (msb + (n0 - 1) * msw), 0)), 3)
print('TEST 1', {k: out[k] for k in out if k.startswith('T1')})
# same test inside one season, for contrast (two different passes, same place, same season)
Q = v.groupby(['place', 'season', 'pass']).rel.mean().reset_index()
pr = []
for (pl, s), g in Q.groupby(['place', 'season']):
    if len(g) >= 2:
        i = rng.permutation(len(g))[:2]; pr.append(g.rel.values[i])
pr = np.array(pr); out['T1b_same_season_two_passes_rho'] = round(spearmanr(pr[:, 0], pr[:, 1])[0], 3); out['T1b_n'] = len(pr)
print('same place, same season, two passes:', out['T1b_same_season_two_passes_rho'], len(pr))

# TEST 2: fuel reset, place fixed effects, seasons with >= 3 years of history
w = v[v.hist_years >= 3].copy()
w['since_cls'] = np.select([w.since1 >= .5, w.since2 >= .5, w.since3p >= .5], ['1 season', '2 seasons', '3+ seasons'], 'not since 2017')
w = w[w.place.isin(w.groupby('place').since_cls.nunique().loc[lambda s: s >= 2].index)]
m2 = smf.ols('rel ~ C(since_cls, Treatment("1 season")) + C(place)', w).fit(cov_type='cluster', cov_kwds={'groups': pd.factorize(w.place)[0]})
co = {k.split('T.')[1].rstrip(']'): (round(float(np.exp(m2.params[k])), 3), [round(float(np.exp(x)), 3) for x in m2.conf_int().loc[k]])
      for k in m2.params.index if 'since_cls' in k}
out['T2_n'] = len(w); out['T2_places'] = int(w.place.nunique())
out['T2_heat_vs_burnt_1_season_ago'] = co
out['T2_raw_counts'] = w.since_cls.value_counts().to_dict()
print('TEST 2 (heat factor vs ground burnt 1 season before, same place):', co)
# continuous version: share of burning ground that burnt last season
m3 = smf.ols('rel ~ since1 + C(place)', w).fit(cov_type='cluster', cov_kwds={'groups': pd.factorize(w.place)[0]})
out['T2_since1_share_coef'] = [round(float(m3.params.since1), 3), m3.conf_int().loc['since1'].round(3).tolist()]

# TEST 3: lasting ground of hot places
pl = v.groupby('place').agg(rel=('rel', 'mean'), n=('rel', 'size'), seasons=('season', 'nunique'), canopy=('canopy', 'mean'),
                            teak=('teak', 'mean'), grass=('grass', 'mean'), slope=('slope', 'mean'), litter=('litter', 'mean'))
pl = pl[pl.seasons >= 2]
out['T3_place_rho'] = {c: round(spearmanr(pl.rel, pl[c], nan_policy='omit')[0], 3) for c in ['canopy', 'teak', 'grass', 'slope', 'litter']}
out['T3_n_places'] = len(pl)
print('TEST 3', out['T3_place_rho'])
v.drop(columns=['lf_d', 'lpix_d', 'burnt_now_d']).to_csv(f'{RES}/place_det.csv', index=False)
json.dump(out, open(f'{RES}/place_tests.json', 'w'), indent=1, default=float)
