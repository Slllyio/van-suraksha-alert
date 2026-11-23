"""Crown effect, stricter version: SAME 500 m place on different dates. Relative heat (h9: vs the rest of the same pass)
against leafy crown cover on that date. Place fixed effects remove species, site moisture, canopy structure: only the
leaves present overhead change between dates. Out: results/crown_same_place.json"""
import json, numpy as np, pandas as pd, rasterio
import statsmodels.formula.api as smf
from h0_lib import RES, ROOT
v = pd.read_csv(f'{RES}/place_det.csv', parse_dates=['t']); v = v[v.t.dt.month.isin([1, 2, 3, 4, 5])].copy()
with rasterio.open(f'{ROOT}/fuel-map/ratapani/leaf_fall_fraction_10m.tif') as r:
    LF = r.read().astype(float); T = r.transform; nd = r.nodata
if nd is not None: LF[LF == nd] = np.nan
H, W = LF.shape[1:]; xa = np.array([-31, 0, 31, 59, 90, 120, 151]); fl = []
for rr in v.itertuples():
    hx, hy = rr.scan_m / 2, rr.track_m / 2
    c0, c1 = max(int((rr.x - hx - T.c) // 10), 0), min(int((rr.x + hx - T.c) // 10) + 1, W)
    r0, r1 = max(int((T.f - rr.y - hy) // 10), 0), min(int((T.f - rr.y + hy) // 10) + 1, H)
    row = np.nanmean(LF[:, r0:r1, c0:c1].reshape(5, -1), axis=1) if (c1 > c0 and r1 > r0) else np.full(5, np.nan)
    fl.append(np.interp(rr.t.dayofyear, xa, np.r_[0, row, 100]) / 100 if np.isfinite(row).all() else np.nan)
v['leafy'] = v.canopy / 100 * (1 - np.array(fl)); v = v.dropna(subset=['leafy'])
out = {}
for name, d in [('all', v), ('night', v[v.daynight == 'N']), ('day', v[v.daynight == 'D'])]:
    d = d[d.groupby('place').leafy.transform('std') > 0.02]
    d = d[d.groupby('place').rel.transform('size') >= 2]
    m = smf.ols('rel ~ leafy + C(place)', d).fit(cov_type='cluster', cov_kwds={'groups': pd.factorize(d.place)[0]})
    out[name] = dict(n=int(m.nobs), places=int(d.place.nunique()), frp_factor_full_leafy=round(float(np.exp(m.params.leafy)), 3),
                     ci=[round(float(np.exp(x)), 3) for x in m.conf_int().loc['leafy']], p=round(float(m.pvalues.leafy), 4),
                     leafy_range_within_place_median=round(float(d.groupby('place').leafy.agg(lambda s: s.max() - s.min()).median()), 3))
    print(name, out[name])
json.dump(out, open(f'{RES}/crown_same_place.json', 'w'), indent=1)
