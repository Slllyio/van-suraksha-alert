"""Answer keys from the FSI thread's soft burn dates (fsi/scouting/data/daily_dating/soft_dates.csv: Sentinel-3 300 m daily,
Landsat 7, MCD64A1 narrowing of each cell-season's FIRST burned window; date_lo..date_hi inclusive, burn on one of those days).
Same frame as SCORING.md main (Feb 1 - Jun 20 issue days, first burn only, valid = t+2 <= last clear look).
Burn day d in [lo, hi]; positive t = lo-2 .. hi-1 (some d in t+1..t+2); days after that masked; earlier days negative.
  soft_all : every row (window rows keep their original interval) -> like main with sharper dates
  soft_n   : narrowed rows only (s3/l7/mcd64); window rows masked over their interval and after
  soft_s3  : s3 rows only (2019-23, 2026); others masked over their interval and after
Output labels_v3_soft.parquet (season, date, cell_id, pos_*, valid_*)."""
import numpy as np, pandas as pd
LAB = '/mnt/project-files/research/ratapani-burn-labels/'; OUT = '/mnt/project-files/ratapani/labels_v3/'
H = 2; n = 3614; SEAS = list(range(2017, 2027))
sd = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/daily_dating/soft_dates.csv', parse_dates=['date_lo', 'date_hi', 'orig_lo', 'orig_hi'])
cc = pd.read_parquet(LAB + 'clear_calendar.parquet'); cc['date'] = pd.to_datetime(cc['date'])
VARS = {'soft_all': None, 'soft_n': {'s3', 'l7', 'mcd64'}, 'soft_s3': {'s3'}}
frames = []
for Y in SEAS:
    days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); T = len(days); d0 = days[0]
    last = cc[(cc.season == Y) & (cc.clear_frac >= 0.5)].groupby('cell_id').date.max().reindex(range(n))
    lim = ((last - d0).dt.days - H).values; bv = np.zeros((T, n), bool)
    for c in range(n):
        if np.isfinite(lim[c]) and lim[c] >= 0: bv[:int(min(lim[c], T - 1)) + 1, c] = True
    V = {v: bv.copy() for v in VARS}; P = {v: np.zeros((T, n), bool) for v in VARS}
    for r in sd[sd.season == Y].itertuples():
        c = r.cell_id
        for v, meth in VARS.items():
            use = meth is None or r.method in meth
            lo, hi = (r.date_lo, r.date_hi) if use else (r.orig_lo, r.orig_hi)
            a, b = (lo - d0).days - H, (hi - d0).days - 1
            V[v][max(b + 1, 0):, c] = False
            a0, b0 = max(a, 0), min(b, T - 1)
            if b0 >= a0:
                if use: P[v][a0:b0 + 1, c] = V[v][a0:b0 + 1, c]
                else: V[v][a0:b0 + 1, c] = False
    allv = np.zeros((T, n), bool)
    for v in V: allv |= V[v]
    ti, ci = np.nonzero(allv); df = pd.DataFrame(dict(season=Y, date=days[ti], cell_id=ci))
    for v in V: df['pos_' + v] = P[v][ti, ci]; df['valid_' + v] = V[v][ti, ci]
    frames.append(df); print(Y, {v: int((P[v] & V[v]).sum()) for v in V}, flush=True)
pd.concat(frames, ignore_index=True).to_parquet(OUT + 'labels_v3_soft.parquet', index=False); print('saved')
