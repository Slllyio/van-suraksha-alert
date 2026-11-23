"""Leaf-fall curve summary from t4's MODIS NDVI samples (fixes the year wrap in t4's day-of-year medians).
Per pixel-season: hi = max NDVI 15 Oct-31 Dec (prior year); lo = 10th pct NDVI 1 Mar-31 May; loss fraction at date t =
(hi - NDVI_t)/(hi - lo), linearly interpolated between composites. Reports days from 1 Jan (negative = December) at which 50% and
80% of the loss is reached, and the loss fraction reached by 15 Feb, 15 Mar, 15 Apr. Outputs out/leaf_curve_type.csv,
out/leaf_curve_division.csv, out/leaf_curve_type_weekly.csv."""
import numpy as np, pandas as pd
N = pd.read_parquet('out/ndvi_samples.parquet'); S = pd.read_parquet('out/ndvi_sample_points.parquet')
N = N.join(S[['div', 'grp']], on='i')
res = []; curves = []
grid = np.arange(-60, 152, 7)   # days from 1 Jan, weekly, early Nov .. end May
for (i, Y), x in N.groupby(['i', 'season']):
    x = x.sort_values('date')
    t = (x.date - pd.Timestamp(f'{Y}-01-01')).dt.days.values; v = x.ndvi.values
    on = v[(t >= -78) & (t <= 0)]; dry = v[(t >= 59) & (t <= 151)]
    if len(on) < 3 or len(dry) < 6: continue
    hi, lo = on.max(), np.quantile(dry, 0.1)
    if hi - lo < 0.08: continue
    k = t >= -60
    if k.sum() < 10: continue
    # 3-point running median to damp residual cloud
    vv = pd.Series(v[k]).rolling(3, center=True, min_periods=1).median().values; tt = t[k]
    f = np.clip((hi - vv) / (hi - lo), 0, 1.2)
    fi = np.interp(grid, tt, f)
    fm = np.maximum.accumulate(fi)   # leaf loss is treated as monotone for the timing metric
    def first(th):
        j = np.nonzero(fm >= th)[0]; return grid[j[0]] if len(j) else np.nan
    res.append(dict(i=i, season=Y, div=x['div'].iat[0], grp=x.grp.iat[0], hi=hi, lo=lo, amp=hi - lo,
                    d50=first(0.5), d80=first(0.8), f_15feb=np.interp(45, grid, fi), f_15mar=np.interp(73, grid, fi), f_15apr=np.interp(104, grid, fi)))
    curves.append(pd.DataFrame({'grp': x.grp.iat[0], 'day': grid, 'f': fi}))
R = pd.DataFrame(res); R.to_csv('out/leaf_curve_pixels.csv', index=False, float_format='%.4g')
agg = dict(n=('i', 'size'), ndvi_wet=('hi', 'median'), ndvi_dry=('lo', 'median'), amp=('amp', 'median'), d50=('d50', 'median'),
           d80=('d80', 'median'), f_15feb=('f_15feb', 'median'), f_15mar=('f_15mar', 'median'), f_15apr=('f_15apr', 'median'))
ft = R.groupby('grp').agg(**agg); ft.to_csv('out/leaf_curve_type.csv', float_format='%.3g'); print(ft.round(3).to_string())
fs = R.groupby(['grp', 'season']).agg(d50=('d50', 'median'), d80=('d80', 'median')); print(fs.unstack().round(0).to_string())
fd = R.groupby('div').agg(**agg); fd.to_csv('out/leaf_curve_division.csv', float_format='%.3g')
C = pd.concat(curves).groupby(['grp', 'day']).f.median().unstack(0); C.to_csv('out/leaf_curve_type_weekly.csv', float_format='%.3g')
print(C.round(2).to_string())
