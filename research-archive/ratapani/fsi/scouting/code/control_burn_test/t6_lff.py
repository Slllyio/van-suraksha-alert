"""t6: FSI Large Forest Fire events (lff_mp.csv, MP 2019-2025) as a set of KNOWN real wildfires. For each LFF, take our VIIRS
cluster(s) on its first-detection fire-day within 1.5 km of its inside point or box; report the share whose first-day cluster carries
the live (day-0) tag and the final tag. Output: out/lff_tag.csv"""
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
S = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/'
O = '/mnt/project-files/ratapani/fsi/scouting/code/control_burn_test/out/'
L = pd.read_csv('/mnt/project-files/ratapani/fsi/fsi_portal/lff_mp.csv')
t = pd.to_datetime(L.F_T_D, format='%Y%m%d_%H%M')   # stamps are IST (day passes read 12-14 h)
L['date'] = (t - pd.to_timedelta((t.dt.hour < 6).astype(int), unit='D')).dt.normalize()
c = pd.read_parquet(S + 'r21_cb/clusters_t1.parquet', columns=['cid', 'season', 'fday', 'date', 'lat', 'lon', 'fn', 'n'])
c = c.merge(pd.read_parquet(S + 'r21_cb/cluster_flags.parquet')[['cid', 'flag_cur', 'flag_live']], on='cid')
c['d0'] = c.date.dt.normalize()
xy = lambda la, lo: np.c_[np.radians(lo) * 6371000 * np.cos(np.radians(23.5)), np.radians(la) * 6371000]
rows = []
by = c.groupby('d0').indices
for i, r in L.iterrows():
    best = None
    for dd in (0, 1, -1):
        ix = by.get(r.date + pd.Timedelta(days=dd))
        if ix is None: continue
        q = c.iloc[ix]; dist = np.hypot(*(xy(q.lat.values, q.lon.values) - xy(np.array([r.INSIDE_Y]), np.array([r.INSIDE_X]))).T)
        inbox = (q.lat.between(r.EXT_MIN_Y - .01, r.EXT_MAX_Y + .01) & q.lon.between(r.EXT_MIN_X - .01, r.EXT_MAX_X + .01)).values
        ok = (dist <= 1500) | inbox
        if ok.any(): best = q[ok]; break
    if best is None: continue
    rows.append(dict(lff=i, date=r.date, fn=best.fn.iloc[0], live=bool(best.flag_live.any()), final=bool(best.flag_cur.any()),
                     days=(pd.to_datetime(r.L_T_D, format='%Y%m%d_%H%M') - pd.to_datetime(r.F_T_D, format='%Y%m%d_%H%M')).total_seconds() / 86400))
R = pd.DataFrame(rows)
print('LFF', len(L), 'matched', len(R))
T = R.groupby('fn').agg(lff=('lff', 'size'), live_tag=('live', 'mean'), final_tag=('final', 'mean'))
T.to_csv(O + 'lff_tag.csv'); print(T.round(3))
