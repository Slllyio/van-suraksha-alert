"""Bhoonidhi thread: how many more MP fires get a scene while burning if ResourceSat AWiFS (and LISS-III/IV, EOS-04) are added to Sentinel-2.
Fires and passes exactly as big-fires b18/b19c: VIIRS alerts (mp_alert_event.csv) linked within 750 m and 48 h; day passes on forest
events 06-11 UTC. Sentinel-2 = mp_hotpix_pairs.csv (s2, cloud < 80%, scene 0-3.5 h before the pass). Bhoonidhi scene = catalog footprint
(Img corners) containing the pass point on the same date, pass <= 09:00 UTC (ResourceSat ~05:00-05:30 UTC; EOS-04 is a dawn/dusk SAR, any time
that day). No cloud screen for Bhoonidhi optical (catalog carries none).  python3 coverage.py <catalog dir>"""
import sys, json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely.geometry import Polygon, Point
from shapely.strtree import STRtree
from pyproj import Transformer
CD = sys.argv[1]; R = '/mnt/project-files/research/big-fires/results'; MO = '/mnt/project-files/fire-alert-scars/mp/out'
A = pd.read_csv(f'{MO}/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'instrument', 'satellite', 'event_id'])
A = A[A.instrument == 'VIIRS'].reset_index(drop=True)
A['t'] = pd.to_datetime(A.acq_date + ' ' + A.acq_time.astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
A['x'], A['y'] = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform(A.longitude.values, A.latitude.values)
Z = np.c_[A.x, A.y, (A.t - A.t.min()).dt.total_seconds() / 3600 * 750 / 48]
pr = cKDTree(Z).query_pairs(750, p=np.inf, output_type='ndarray'); n = len(A)
_, A['fire'] = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(n, n)), directed=False)
F = A.groupby('fire').agg(t0=('t', 'min'), t1=('t', 'max'), n_alerts=('t', 'size'))
F['dur_h'] = (F.t1 - F.t0).dt.total_seconds() / 3600
ev2fire = A.groupby('event_id').fire.first()
ev = pd.read_csv(f'{MO}/mp_events.csv', usecols=['event_id', 'forest'])
D = A[A.event_id.isin(ev[ev.forest].event_id) & (A.t.dt.hour >= 6) & (A.t.dt.hour < 11)].copy()
D['pass_id'] = D.event_id + '|' + D.satellite + '|' + D.t.dt.floor('15min').astype(str)
P = D.groupby('pass_id').agg(event_id=('event_id', 'first'), t=('t', 'min'), lon=('longitude', 'mean'), lat=('latitude', 'mean')).reset_index()
P['date'] = P.t.dt.normalize(); P['fire'] = P.event_id.map(ev2fire)
print('day passes', len(P), flush=True)
PR = pd.read_csv(f'{R}/mp_hotpix_pairs.csv', usecols=['pass_id', 'sensor'])
hit = {'s2': set(PR[PR.sensor == 's2'].pass_id), 'landsat': set(PR[PR.sensor == 'ls'].pass_id)}
for s in ['awifs', 'liss3', 'liss4', 'eos04']:
    try: C = pd.read_csv(f'{CD}/cat_{s}.csv')
    except FileNotFoundError: continue
    C['date'] = pd.to_datetime(C.DOP, format='%d-%b-%Y'); hs = set()
    for d, g in C.groupby('date'):
        pp = P[P.date == d]
        if s != 'eos04': pp = pp[pp.t.dt.hour < 9]
        if pp.empty: continue
        polys = [Polygon([(r.ImgCrnNWLon, r.ImgCrnNWLat), (r.ImgCrnNELon, r.ImgCrnNELat), (r.ImgCrnSELon, r.ImgCrnSELat), (r.ImgCrnSWLon, r.ImgCrnSWLat)]) for r in g.itertuples()]
        tree = STRtree(polys)
        for r in pp.itertuples():
            if len(tree.query(Point(r.lon, r.lat), predicate='within')): hs.add(r.pass_id)
    hit[s] = hs; print(s, 'scenes', len(C), 'passes hit', len(hs), flush=True)
for k, v in list(hit.items()): P[k] = P.pass_id.isin(v)
P['s2+awifs'] = P.s2 | P.get('awifs', False)
cols = [c for c in ['s2', 'landsat', 'awifs', 's2+awifs', 'liss3', 'liss4', 'eos04'] if c in P]
Fh = P.groupby('fire')[cols].any(); F = F.join(Fh).fillna(False)
F['band'] = pd.cut(F.dur_h, [-1, 12, 36, 84, 1e9], labels=['seen 1 day', '1-2 days', '2-4 days', '4+ days'])
F['yr'] = F.t0.dt.year
def tab(G): return dict(fires=int(len(G)), **{c: round(float(G[c].mean()), 3) for c in cols})
out = dict(note=__doc__, passes={c: round(float(P[c].mean()), 3) for c in cols}, all=tab(F),
           by_duration={str(k): tab(v) for k, v in F.groupby('band', observed=True)}, by_year={int(k): tab(v) for k, v in F.groupby('yr')})
json.dump(out, open(f'{CD}/coverage.json', 'w'), indent=1); print(json.dumps({k: v for k, v in out.items() if k != 'note'}, indent=1))
