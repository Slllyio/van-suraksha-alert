import pandas as pd, numpy as np
L = '/mnt/project-files/ratapani/labels_v3/'
cv = pd.read_csv('cell_vhr.csv').dropna(subset=['vhr_date']); cv['D'] = pd.to_datetime(cv.vhr_date.astype(int).astype(str))
cv = cv[(cv.D >= '2025-02-01') & (cv.D <= '2025-06-30')]
sw = pd.read_csv(L + 'season_windows.csv', parse_dates=['ws', 'we']); sw = sw[sw.season == 2025]
ew = pd.read_csv(L + 'event_windows.csv', parse_dates=['ws', 'we', 'alert_day']); ew = ew[ew.season == 2025]
dt = pd.read_csv(L + 'dated_cells.csv', parse_dates=['d']); dt = dt[dt.season == 2025].set_index('cell_id').d
cc = pd.read_parquet('/mnt/project-files/research/ratapani-burn-labels/clear_calendar.parquet'); cc['date'] = pd.to_datetime(cc.date)
cc = cc[(cc.season == 2025) & (cc.clear_frac >= 0.5)]
td = pd.Timedelta
rows = []
for r in cv.itertuples():
    c, D = r.cell_id, r.D; s = sw[sw.cell_id == c]; e = ew[ew.cell_id == c]
    s_recent = ((s.we >= D - td(days=20)) & (s.we <= D)).any(); e_recent = ((e.we >= D - td(days=20)) & (e.we <= D)).any()
    any_near = ((s.we >= D - td(days=60)) & (s.ws <= D + td(days=7))).any() or ((e.we >= D - td(days=60)) & (e.ws <= D + td(days=7))).any()
    seen_after = ((cc.cell_id == c) & (cc.date > D) & (cc.date <= D + td(days=15))).any()
    s_any = ((s.we >= D - td(days=30)) & (s.ws <= D + td(days=5))).any()
    cls = 'S' if s_recent else ('A' if e_recent and not s_any else ('N' if (not any_near and seen_after) else None))
    d = dt.get(c); lag = (D - d).days if d is not None else np.nan
    rows.append((c, r.lon, r.lat, D.date(), cls, s_recent, e_recent, lag))
s = pd.DataFrame(rows, columns=['cell_id', 'lon', 'lat', 'D', 'cls', 's_recent', 'e_recent', 'dated_lag'])
s.to_csv('cls_all.csv', index=False)
old = pd.read_csv('vhr_sample.csv')
extra = pd.concat([g[~g.cell_id.isin(old.cell_id)].sample(min(len(g[~g.cell_id.isin(old.cell_id)]), k), random_state=11) for cl, k in (('S', 255), ('A', 181), ('N', 240)) for g in [s[s.cls == cl]]])
extra['blind_id'] = [f'X{i:03d}' for i in range(len(extra))]
allc = pd.concat([old.merge(s[['cell_id', 'dated_lag']], on='cell_id'), extra], ignore_index=True); allc.to_csv('vhr_sample_all.csv', index=False)
print(allc.cls.value_counts())
