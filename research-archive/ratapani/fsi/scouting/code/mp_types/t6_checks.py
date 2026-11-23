"""Extra per-division checks: static/industrial sources (FIRMS type 2, persistent cells), January share,
NOAA-20 cross-check of season shares, year-to-year spread of the median fire date, and the share of season fires
that a 15 Feb - 15 Jun window keeps. Inputs: out/viirs_vtm.parquet. Output: out/division_checks.csv"""
import numpy as np, pandas as pd
p = pd.read_parquet('out/viirs_vtm.parquet')
p['cell'] = (np.floor(p.latitude / 0.005).astype(int) * 100000 + np.floor(p.longitude / 0.005).astype(int))
rows = []
for d, x in p.groupby('Division'):
    s = x[x.sat == 'snpp']; n20 = x[(x.sat == 'jpss1') & (x.season >= 2019)]
    r = {'Division': d}
    r['share_type2_static'] = (s['type'] == 2).mean()
    yrs = s.groupby('cell').season.nunique()
    pers = yrs[yrs >= 9].index           # cells with fire in >= 9 of 13 seasons
    r['share_pts_in_cells_burnt_ge9of13yrs'] = s.cell.isin(pers).mean()
    r['n_cells_ge9of13'] = len(pers)
    r['share_jan'] = (s.doy <= 31).mean()
    r['share_in_15feb_15jun'] = ((s.doy >= 46) & (s.doy <= 166)).mean()
    r['n20_share_before_15feb'] = (n20.doy < 46).mean() if len(n20) else np.nan
    r['n20_share_after_15may'] = (n20.doy > 135).mean() if len(n20) else np.nan
    med = s.groupby('season').doy.median()
    r['median_doy_sd_across_years'] = med.std()
    r['median_doy_range'] = med.max() - med.min()
    r['night_share_n20'] = (n20.daynight == 'N').mean() if len(n20) else np.nan
    rows.append(r)
c = pd.DataFrame(rows).set_index('Division')
c.to_csv('out/division_checks.csv', float_format='%.4g')
print(c.sort_values('share_type2_static', ascending=False).round(3).head(15).to_string())
print(c.sort_values('share_in_15feb_15jun').round(3).head(15).to_string())
print(c.round(3).describe().to_string())
