"""Day/night burning rhythm, from MODIS detection counts in Ratapani, Feb-Jun 2017-26 (same sensor at four hours:
Terra ~11:00 and ~22:30 IST, Aqua ~13:45 and ~02:15 IST). Never uses the photos.
Fit: activity(h) = b + (1-b) * exp(-(h - peak)^2 / (2 s^2)) on the 24 h circle, relative to the peak.
Out: results/diurnal.json"""
import glob, json, numpy as np, pandas as pd
from scipy.optimize import least_squares
ROOT = '/mnt/project-files'
a = pd.concat([pd.read_csv(f) for f in glob.glob(f'{ROOT}/fire-alert-scars/alerts/modis_*.csv')])
a = a[pd.to_datetime(a.acq_date).dt.month.between(2, 6)]
a['h'] = (a.acq_time // 100 + (a.acq_time % 100) / 60 + 5.5) % 24
g = a.groupby(['satellite', 'daynight']).agg(n=('h', 'size'), h=('h', 'median')).reset_index()
g['rel'] = g.n / g.n.max(); print(g)
def act(p, h):
    b, pk, s = p; dh = (h - pk + 12) % 24 - 12
    return b + (1 - b) * np.exp(-dh ** 2 / (2 * s ** 2))
fit = least_squares(lambda p: act(p, g.h.values) / act(p, pk_h := p[1]) - g.rel.values, [0.1, 14.5, 3], bounds=([0, 12, 1], [0.5, 17, 8]))
b, pk, s = fit.x
out = dict(base=round(b, 3), peak_ist=round(pk, 2), width_h=round(s, 2), points=g[['satellite', 'daynight', 'h', 'n', 'rel']].round(3).to_dict('records'),
           share_of_day_activity_01_30_to_10_30=None)
hh = np.arange(0, 24, 1 / 60); r = act(fit.x, hh)
out['share_of_day_activity_01_30_to_10_30'] = round(r[(hh >= 1.5) & (hh < 10.5)].sum() / r.sum(), 3)
out['share_01_30_to_13_30'] = round(r[(hh >= 1.5) & (hh < 13.5)].sum() / r.sum(), 3)
print(out); json.dump(out, open(f'{ROOT}/research/fire-continuity/results/diurnal.json', 'w'), indent=1)
