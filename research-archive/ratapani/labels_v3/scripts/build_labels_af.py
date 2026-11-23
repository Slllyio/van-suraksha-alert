"""Dated variants from the burn-scar thread's multi-sensor dating (fire-alert-scars/out/af/dated_first_burns.csv):
same frame as SCORING.md main (season windows, first burn only, valid = t+2 <= last clear look). Fire day = earliest dated day
for the cell's first window among sources of the given confidence. Dated: positive t = d-2, d-1, rest of window masked.
  af_high_s : conf high only (S2/Landsat active fire, VIIRS <= 400 m); undated windows masked
  af_hm_s   : conf high + med (VIIRS 400-750 m); undated masked
  af_all_s  : + low (MODIS); undated masked
  af_hm_l   : as af_hm_s but undated windows keep the main window rule
Output labels_v3_af.parquet (season, date, cell_id, pos_*, valid_*)."""
import numpy as np, pandas as pd
LAB = '/mnt/project-files/research/ratapani-burn-labels/'; OUT = '/mnt/project-files/ratapani/labels_v3/'
H = 2; n = 3614; SEAS = list(range(2017, 2027))
af = pd.read_csv('/mnt/project-files/fire-alert-scars/out/af/dated_first_burns.csv', parse_dates=['fire_day', 'window_start', 'window_end'])
cc = pd.read_parquet(LAB + 'clear_calendar.parquet'); cc['date'] = pd.to_datetime(cc['date'])
VARS = {'af_high_s': ({'high'}, False), 'af_hm_s': ({'high', 'med'}, False), 'af_all_s': ({'high', 'med', 'low'}, False), 'af_hm_l': ({'high', 'med'}, True)}
frames = []
for Y in SEAS:
    days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); T = len(days); d0 = days[0]
    last = cc[(cc.season == Y) & (cc.clear_frac >= 0.5)].groupby('cell_id').date.max().reindex(range(n))
    lim = ((last - d0).dt.days - H).values; bv = np.zeros((T, n), bool)
    for c in range(n):
        if np.isfinite(lim[c]) and lim[c] >= 0: bv[:int(min(lim[c], T - 1)) + 1, c] = True
    V = {v: bv.copy() for v in VARS}; P = {v: np.zeros((T, n), bool) for v in VARS}
    g = af[af.season == Y]
    for c, gc in g.groupby('cell_id'):
        s, e = gc.window_start.iloc[0], gc.window_end.iloc[0]
        a, b = max((s - d0).days - H + 1, 0), min((e - d0).days - 1, T - 1); ei = (e - d0).days
        for v, (confs, lenient) in VARS.items():
            dd = gc[gc.conf.isin(confs) & gc.fire_day.notna()].fire_day
            if ei <= T - 1: V[v][max(ei, 0):, c] = False
            if len(dd):
                d = dd.min(); fi = (d - d0).days
                if b >= a: V[v][a:b + 1, c] = False
                V[v][max(fi, 0):, c] = False
                a0, b0 = max(fi - H, 0), min(fi - 1, T - 1)
                if b0 >= a0: P[v][a0:b0 + 1, c] = True; V[v][a0:b0 + 1, c] = True
            elif b >= a:
                P[v][a:b + 1, c] = lenient; V[v][a:b + 1, c] = lenient
    allv = np.zeros((T, n), bool)
    for v in V: allv |= V[v]
    ti, ci = np.nonzero(allv); df = pd.DataFrame(dict(season=Y, date=days[ti], cell_id=ci))
    for v in V: df['pos_' + v] = P[v][ti, ci]; df['valid_' + v] = V[v][ti, ci]
    frames.append(df); print(Y, {v: int((P[v] & V[v]).sum()) for v in V}, flush=True)
pd.concat(frames, ignore_index=True).to_parquet(OUT + 'labels_v3_af.parquet', index=False); print('saved')
