# Check app/direction.py against the Big fires statewide test (research/big-fires/scripts/b19b_statewide_direction.py):
# on research passes that had an arrow, rebuild the fire's VIIRS dots, let the app find the scene itself (scenes up to the
# research scene's time), and score the arrow against where the statewide scar grew next (scar not yet burnt).
#   python scripts/direction_check.py [N]   (needs Planetary Computer access; ~20-40 s a fire)
import csv, gzip, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from pyproj import Transformer
from rasterio import features
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely import wkt
from shapely.geometry import shape, mapping
from shapely.ops import unary_union, transform as stransform
from app import direction

N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
R = '/mnt/project-files/research/big-fires/results'; MO = '/mnt/project-files/fire-alert-scars/mp/out'
to43 = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
U = pd.read_csv(f'{R}/statewide_direction_rows.csv')
U = U[U.ang_arrow_scar.notna()].sample(frac=1, random_state=1).head(N)
U['t_scene'] = pd.to_datetime(U.t_scene)
A = pd.read_csv(f'{MO}/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'instrument', 'event_id'])
A = A[A.instrument == 'VIIRS'].copy()
A['t'] = pd.to_datetime(A.acq_date + ' ' + A.acq_time.astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
A['x'], A['y'] = to43(A.longitude.values, A.latitude.values); A = A.reset_index(drop=True); AT = cKDTree(A[['x', 'y']].values)
EV = A.groupby('event_id')[['x', 'y']].mean()
need = set()
rows = []
for r in U.itertuples():
    ex, ey = EV.loc[r.event_id]
    near = A.iloc[AT.query_ball_point([ex, ey], 3000)]
    near = near[(near.t >= r.t_scene - pd.Timedelta(hours=72)) & (near.t <= r.t_scene + pd.Timedelta(hours=30))].reset_index(drop=True)
    xy = near[['x', 'y']].values
    p = np.array(list(cKDTree(xy).query_pairs(750.0))) if len(xy) > 1 else np.zeros((0, 2), int)
    lab = connected_components(coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy),) * 2), directed=False)[1] if len(p) else np.arange(len(xy))
    d = near[np.isin(lab, list(set(lab[(near.event_id == r.event_id).values])))]
    need |= set(d.event_id)
    rows.append((r, d))
G = {}
csv.field_size_limit(10 ** 9)
try:
    with gzip.open(f'{MO}/scars_mp_hist_geom.csv.gz', 'rt') as fh:
        rd = csv.reader(fh); next(rd)
        for row in rd:
            if len(row) == 2 and row[0] in need:
                try: G[row[0]] = wkt.loads(row[1])
                except Exception: pass
except Exception as e:
    print('history geometry file read partly:', str(e)[:60])
for f in ['scars_rest_of_mp.csv', 'scars_tiger_reserves.csv']:
    g = pd.read_csv(f'{MO}/{f}', usecols=['event_id', 'status', 'geometry'])
    g = g[g.event_id.isin(need) & g.status.isin(['scar', 'scar_faint']) & g.geometry.notna()]
    for x in g.itertuples():
        G.setdefault(x.event_id, shape(json.loads(x.geometry)))
out = []
for r, d in rows:
    t_scene = r.t_scene.tz_localize('UTC')
    dots = [(a.latitude, a.longitude, a.t.tz_localize('UTC').to_pydatetime()) for a in d.itertuples() if a.t.tz_localize('UTC') <= t_scene + pd.Timedelta(hours=4)]
    try:
        res = direction.arrow(dots, (t_scene + pd.Timedelta(minutes=5)).to_pydatetime(), debug=True)
    except Exception as e:
        import traceback; traceback.print_exc(); res = {'status': 'error ' + str(e)[:60]}
    o = dict(pass_id=r.pass_id, research_angle=r.ang_arrow_scar, research_scene=r.scene, status=res['status'])
    geoms = [G[e] for e in d.event_id.unique() if e in G]
    if res['status'] == 'found' and geoms:
        tr, W, H = res['_grid']
        poly = stransform(lambda x, y, z=None: to43(x, y), unary_union(geoms))
        dom = features.rasterize([(mapping(poly), 1)], out_shape=(H, W), transform=tr).astype(bool).ravel()
        rest = dom & ~res['_burnt']
        if rest.sum() >= 50:
            rr, cc = np.mgrid[0:H, 0:W]
            Px = np.c_[(tr.c + (cc + .5) * 20).ravel(), (tr.f - (rr + .5) * 20).ravel()]
            tv = Px[rest].mean(0) - res['_cb']; v = res['_vec']
            o['angle'] = float(np.degrees(np.abs(np.arctan2(v[0] * tv[1] - v[1] * tv[0], v @ tv))))
        o.update(scene=res['scene'], same_scene=res['scene'] == r.scene, heading=res['heading'])
    out.append(o); print(o, flush=True)
Z = pd.DataFrame(out); Z.to_csv('/mnt/project-files/field-system/docs/direction_check_rows.csv', index=False)
s = Z.dropna(subset=['angle']) if 'angle' in Z else Z.iloc[:0]
print('\npasses', len(Z), 'status', Z.status.value_counts().to_dict())
if len(s):
    print(f"app arrow within 45 deg: {(s.angle <= 45).mean():.0%} of {len(s)}  (research on the same passes: {(s.research_angle <= 45).mean():.0%}); same scene {s.same_scene.mean():.0%}")
