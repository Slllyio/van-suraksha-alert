"""Front speed per fire from ALL timed passes fitted together (instead of one noisy pass-to-pass step at a time).
For each pass: front distance = farthest detection of that pass from the fire's start area (centre of the detections in
its first 2 h). Fit front distance against hours since start with a robust line (Theil-Sen), so ~300 m single-pass
errors average out over many passes. Done with VIIRS passes only and with every satellite (VIIRS, MODIS, S2/Landsat).
Out: results/front_speed.csv, printed summary.
"""
import pickle, os
import numpy as np, pandas as pd
from scipy.stats import theilslopes
R = '/mnt/project-files/research/big-fires/results'
P = pd.read_csv(f'{R}/passes.csv', parse_dates=['t'])
A = pd.read_csv(f'{R}/fire_alerts.csv', parse_dates=['t'])
rows = []
for fid, g in P.groupby('fire'):
    if len(g) < 4 or (g.t.max() - g.t.min()) < pd.Timedelta(hours=6): continue
    a = A[A.fire == fid]; t0 = g.t.min()
    st = g[g.t <= t0 + pd.Timedelta(hours=2)]; ox, oy = st.x.mean(), st.y.mean()
    # front distance per pass uses that pass's individual detections where available (alerts), else the pass centre (hot-pixel scenes)
    rec = dict(fire=fid)
    for mode, gg in [('viirs', g[g.sensor.isin(['S-NPP', 'NOAA-20', 'NOAA-21'])]), ('all', g)]:
        hrs, front = [], []
        for _, p in gg.iterrows():
            d = a[(a.t >= p.t) & (a.t <= p.t + pd.Timedelta(minutes=15))]
            dist = np.hypot(d.x - ox, d.y - oy).max() if len(d) and p.sensor not in ('Sentinel-2', 'Landsat') else np.hypot(p.x - ox, p.y - oy)
            hrs.append((p.t - t0).total_seconds() / 3600); front.append(dist)
        hrs, front = np.array(hrs), np.array(front)
        if len(hrs) >= 4 and np.ptp(hrs) > 6:
            s, i, lo, hi = theilslopes(front, hrs)
            rec.update({f'{mode}_passes': len(hrs), f'{mode}_speed_m_per_h': s, f'{mode}_speed_lo': lo, f'{mode}_speed_hi': hi,
                        f'{mode}_ci_width': hi - lo})
    rows.append(rec)
FS = pd.DataFrame(rows); FS.to_csv(f'{R}/front_speed.csv', index=False)
print(FS.describe(percentiles=[.25, .5, .75]).round(1).T[['count', '25%', '50%', '75%']])
both = FS.dropna(subset=['viirs_ci_width', 'all_ci_width'])
print('fires with both:', len(both), '| CI narrower with all sensors in', round((both.all_ci_width < both.viirs_ci_width).mean() * 100), '%',
      '| speed > 0 with CI above 0: viirs', round((FS.viirs_speed_lo > 0).mean() * 100), '% all', round((FS.all_speed_lo > 0).mean() * 100), '%')
