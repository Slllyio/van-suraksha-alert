"""Oblique-pass check, step 2: detection factor per look and per fire square-day.
f = detection of a fire relative to straight down (heat thread, research/fuel-from-heat/README.md "Crown blocking measured by
viewing angle", March closed forest): <30 deg 1, 30-45 0.76, 45-56 0.68, >56 0.35 for leafy crowns; bare crowns / open 1.
Applied only to closed canopy (Hansen 2000 tree cover >= 10% in a ~390 m box; on Ratapani detections this matches the
canopy map's >=50% with precision 0.84, recall 0.62) in Feb-Mar.
  WORST = every closed Feb-Mar fire under leafy crowns (f as above).  MIX = 54% leafy at straight down (heat thread), f_mix = 0.54 f + 0.46.
A square-day's chance of being seen is set by its best (most straight-down) look that day, so weight = 1 / max f over its looks.
Out: $VA_OUT/va_cellday.parquet (row, col, ld, f_worst, f_mix, per label set), va_weights_summary.json (shared folder)."""
import os, json, numpy as np, pandas as pd
os.environ.setdefault('MPV', 'season')
import mp_simple_rules as M
OUT = os.environ.get('VA_OUT', '/tmp/claude-0/va'); TCMIN = float(os.environ.get('TCMIN', 10))
v = pd.read_parquet(f'{OUT}/va_det.parquet')
x, y = M.TF.transform(v.longitude.values, v.latitude.values)
v['col'] = np.floor((x - M.X0) / M.S).astype(int); v['row'] = np.floor((M.Y1 - y) / M.S).astype(int)
utc = pd.to_datetime(v.acq_date) + pd.to_timedelta(v.acq_time // 100, 'h') + pd.to_timedelta(v.acq_time % 100, 'm')
v['ld'] = (utc + pd.Timedelta(hours=5, minutes=30)).dt.normalize()
f = np.select([v.theta < 30, v.theta < 45, v.theta < 56], [1.0, 0.76, 0.68], 0.35)
apply = (v.tc >= TCMIN) & v.ld.dt.month.isin([2, 3])
v['f_worst'] = np.where(apply, f, 1.0); v['f_mix'] = np.where(apply, 0.54 * f + 0.46, 1.0); v['closed_fm'] = apply
sm = {'tree_cover_min': TCMIN}
for name, sats in (('3sat', ('snpp', 'jpss1', 'noaa21')), ('snpp_noaa20', ('snpp', 'jpss1')), ('snpp_only', ('snpp',))):
    q = v[v.sat.isin(sats)]
    c = q.groupby(['row', 'col', 'ld']).agg(f_worst=('f_worst', 'max'), f_mix=('f_mix', 'max'), closed_fm=('closed_fm', 'max'), n=('theta', 'size')).reset_index()
    s = c[(c.ld.dt.month * 100 + c.ld.dt.day >= 215) & (c.ld.dt.month * 100 + c.ld.dt.day <= 531) & (c.ld.dt.year >= 2022)]
    cf = s[s.closed_fm]
    sm[name] = {'fire_square_days_season_2022_24': len(s), 'closed_canopy_feb_mar': len(cf), 'closed_share_pct': round(100 * len(cf) / len(s), 1),
                'closed_fm_only_oblique_gt56_pct': round(100 * (cf.f_worst == 0.35).mean(), 1),
                'closed_fm_best_look_ge30_pct': round(100 * (cf.f_worst < 1).mean(), 1),
                'est_missing_closed_fm_worst_pct': round(100 * (1 - len(cf) / (1 / cf.f_worst).sum()), 1),
                'est_missing_closed_fm_mix_pct': round(100 * (1 - len(cf) / (1 / cf.f_mix).sum()), 1),
                'est_missing_all_worst_pct': round(100 * (1 - len(s) / (1 / s.f_worst).sum()), 2),
                'est_missing_all_mix_pct': round(100 * (1 - len(s) / (1 / s.f_mix).sum()), 2)}
    c.to_parquet(f'{OUT}/va_cellday_{name}.parquet')
json.dump(sm, open(M.OUT + 'va_weights_summary.json', 'w'), indent=1); print(json.dumps(sm, indent=1))
