"""[big-fires b19c, 18 Oct] How often would the 30 m direction arrow (15f) be available in live use, statewide 2017-25?
Fires = all-MP VIIRS alerts (mp_alert_event.csv) linked when within 750 m (x and y) and 48 h of each other (event ids split per day).
Scene = a Sentinel-2 / Landsat 8-9 scene 0-3.5 h before a VIIRS day pass of the fire, low cloud (mp_hotpix_pairs.csv, b18 matching).
Chance the scene shows the hot line (>= 3 hot pixels) = b18 sample rate by sensor and block count (mp_hotpix_passes.csv); a fire's
chance of >= 1 arrow = 1 - prod(1 - p) over its distinct scenes. Burnt patch assumed found when the hot line is (234 of 235 in 15f).
Output results/arrow_coverage.json"""
import os, json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from pyproj import Transformer
R = '/mnt/project-files/research/big-fires/results'; MO = '/mnt/project-files/fire-alert-scars/mp/out'
A = pd.read_csv(f'{MO}/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'instrument', 'daynight', 'event_id'])
A = A[A.instrument == 'VIIRS'].reset_index(drop=True)
A['t'] = pd.to_datetime(A.acq_date + ' ' + A.acq_time.astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
A['x'], A['y'] = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform(A.longitude.values, A.latitude.values)
Z = np.c_[A.x, A.y, (A.t - A.t.min()).dt.total_seconds() / 3600 * 750 / 48]
pr = cKDTree(Z).query_pairs(750, p=np.inf, output_type='ndarray')
n = len(A); _, A['fire'] = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(n, n)), directed=False)
F = A.groupby('fire').agg(t0=('t', 'min'), t1=('t', 'max'), n_alerts=('t', 'size'), days=('acq_date', 'nunique'))
F['dur_h'] = (F.t1 - F.t0).dt.total_seconds() / 3600
ev2fire = A.groupby('event_id').fire.first()
P = pd.read_csv(f'{R}/mp_hotpix_passes.csv'); PR = pd.read_csv(f'{R}/mp_hotpix_pairs.csv', parse_dates=['t', 't_scene'])
P['kind'] = np.where(P.n_blocks == 1, 1, np.where(P.n_blocks == 2, 2, 3)); PR['kind'] = np.where(PR.n_blocks == 1, 1, np.where(PR.n_blocks == 2, 2, 3))
rate = P.groupby(['sensor', 'kind']).visible.mean()
PR['p'] = [rate.get((s, k), P.visible.mean()) for s, k in zip(PR.sensor, PR.kind)]
PR['fire'] = PR.event_id.map(ev2fire)
ONLY = os.environ.get('SENSOR')  # SENSOR=s2: Sentinel-2 only (Landsat L2 reaches Planetary Computer ~40 days late)
if ONLY: PR = PR[PR.sensor == ONLY]
PR = PR.dropna(subset=['fire']).sort_values('p', ascending=False).drop_duplicates(['fire', 'scene'])
PR['h_after_first'] = (PR.t_scene - PR.fire.map(F.t0)).dt.total_seconds() / 3600
g = PR.groupby('fire')
F['n_scenes'] = g.size(); F['p_arrow'] = g.p.apply(lambda v: 1 - np.prod(1 - v.values))
F['first_scene_h'] = g.h_after_first.min(); F = F.fillna({'n_scenes': 0, 'p_arrow': 0})
F['band'] = pd.cut(F.dur_h, [-1, 12, 36, 84, 1e9], labels=['seen 1 day (<12 h)', '1-2 days', '2-4 days', '4+ days'])
F['size'] = pd.cut(F.n_alerts, [0, 2, 9, 49, 1e9], labels=['1-2 dots', '3-9', '10-49', '50+ dots'])
def tab(G):
    return dict(fires=int(len(G)), share_with_clear_scene=round(float((G.n_scenes > 0).mean()), 3),
                expected_share_with_arrow=round(float(G.p_arrow.mean()), 3),
                median_hours_first_alert_to_scene=round(float(G.first_scene_h.median()), 1) if G.first_scene_h.notna().any() else None)
out = dict(note='fires 2017-25 all MP from VIIRS alerts; scene = low-cloud S2/Landsat 0-3.5 h before a VIIRS day pass; arrow = expected chance the scene shows the hot line',
           all=tab(F), by_duration={str(k): tab(v) for k, v in F.groupby('band', observed=True)},
           by_size={str(k): tab(v) for k, v in F.groupby('size', observed=True)},
           by_year={int(k): tab(v) for k, v in F.groupby(F.t0.dt.year)},
           arrows_per_season_expected={int(k): round(float(v.p_arrow.sum())) for k, v in F.groupby(F.t0.dt.year)})
S = F[F.n_scenes > 0]; out['when_scene_comes'] = dict(first_day=round(float((S.first_scene_h < 24).mean()), 3), day_2=round(float(S.first_scene_h.between(24, 48).mean()), 3), later=round(float((S.first_scene_h >= 48).mean()), 3))
json.dump(out, open(f'{R}/arrow_coverage' + (f'_{ONLY}' if ONLY else '') + '.json', 'w'), indent=1); print(json.dumps(out, indent=1))
