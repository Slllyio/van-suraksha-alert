"""Check of the pilot's ignition-stream rule against the FSI thread's fire-level ignition points (ratapani/fsi/scouting/data/ignition_points.csv).
(a) Share of true first-day fires (event_role) whose ignition cell had a VIIRS point within 1.5 km in the 3 days before -> excluded by
the 'no nearby recent VIIRS' rule; and share of later-day events the rule would call new. (b) 2025-26, 15 Feb-15 Jun: share of first-day
fires whose ignition cell was on an ignition-stream list issued 1 or 2 days before (fixed5 vs calendar vs forecast, dryness model,
sanctuary-wide, season total unchanged)."""
import json, sys, numpy as np, pandas as pd
from pyproj import Transformer
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts')
import data as D, exp_budget as E
ip = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/ignition_points.csv', parse_dates=['date']).dropna(subset=['ign_lat', 'ign_lon'])
c = D.cells(); key = {(int(x // 500), int(y // 500)): i for i, x, y in zip(c.cell_id, c.x, c.y)}
X, Y = Transformer.from_crs(4326, 32643, always_xy=True).transform(ip.ign_lon.values, ip.ign_lat.values)
ip['cell_id'] = [key.get((int(x // 500), int(y // 500)), -1) for x, y in zip(X, Y)]; ip = ip[ip.cell_id >= 0]
v = D.viirs(); cxy = c.set_index('cell_id')[['x', 'y']]
from scipy.spatial import cKDTree
near = []
for _, r in ip.iterrows():
    w = v[(v.date < r.date) & (v.date >= r.date - pd.Timedelta(days=3))]
    near.append(bool(len(w)) and cKDTree(w[['x', 'y']].values).query(cxy.loc[r.cell_id].values)[0] <= 1500)
ip['near'] = near; first = ip.event_role == 'first_day_of_fire'
res = dict(first_day_fires=int(first.sum()), first_day_excluded_by_rule=round(float(ip.near[first].mean()), 3),
           later_day_events=int((~first).sum()), later_day_called_new_by_rule=round(float((~ip.near[~first]).mean()), 3))
m = pd.read_parquet(D.OUT + 'pooled_full.parquet')
m = m[(m.season >= 2025) & (m.date.dt.strftime('%m%d') >= '0213') & (m.date.dt.strftime('%m%d') <= '0615')]
m = m[m.d3 > 1500].reset_index(drop=True)
f = ip[first & (ip.date.dt.year >= 2025) & (ip.date.dt.strftime('%m%d') >= '0215') & (ip.date.dt.strftime('%m%d') <= '0615')]
for name, rule, sc in (('fixed5', 'fixed5', None), ('calendar_total', 'day_varying', E.scale_nopeek(m, 'mu_N2', clim=True)),
                       ('forecast_total', 'day_varying', E.scale_nopeek(m, 'mu_N2'))):
    p = E.pick(m, 's', rule, sc); P = set(zip(m.date[p], m.cell_id[p]))
    hit = [any((r.date - pd.Timedelta(days=k), r.cell_id) in P for k in (1, 2)) for _, r in f.iterrows()]
    res[f'{name}_first_day_fires_listed'] = round(float(np.mean(hit)), 3)
res['first_day_fires_2025_26'] = len(f)
print(res); json.dump(res, open('/mnt/project-files/research/reframe/results/ignition_check.json', 'w'), indent=1)
