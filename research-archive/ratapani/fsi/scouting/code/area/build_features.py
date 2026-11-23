"""Area-from-active-fire test, Ratapani. Builds per-scar features from VIIRS points.
For each event scar: seed = the event's own VIIRS alerts; chain-grow (FEDS-like) with VIIRS points
(S-NPP, NOAA-20, NOAA-21) within LINK_M of any cluster point and within 1 day of the cluster's latest
detection, up to the scar's post_date. Features computed for several 'as-of' cut-offs (day 0, day 0-1, full).
Output: features.parquet in scratch dir.
"""
import glob, sys
import numpy as np, pandas as pd, geopandas as gpd
import shapely
from shapely.geometry import box
from scipy.spatial import cKDTree

BASE = '/mnt/project-files/fire-alert-scars'
OUT = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r12_area_code/'
LINK_M = float(sys.argv[1]) if len(sys.argv) > 1 else 750.0
CRS = 32643

# --- VIIRS points
fr = []
for f in glob.glob(BASE + '/alerts/viirs-*.csv'):
    d = pd.read_csv(f)
    d['sensor'] = f.split('/')[-1].split('_')[0]
    fr.append(d)
v = pd.concat(fr, ignore_index=True)
v['acq_time'] = v.acq_time.astype(int)
v['date'] = pd.to_datetime(v.acq_date)
v['dn'] = (v.date - pd.Timestamp('2017-01-01')).dt.days
v['overpass'] = v.sensor + '_' + v.acq_date + '_' + (v.acq_time // 100).astype(str)
g = gpd.GeoSeries(gpd.points_from_xy(v.longitude, v.latitude), crs=4326).to_crs(CRS)
v['x'] = g.x.values; v['y'] = g.y.values
# 2026 rows have no scan/track: use nominal 0.375 km
for c in ['scan', 'track']:
    v[c] = v[c].fillna(0.375) if c in v else 0.375
v = v.drop_duplicates(['x', 'y', 'overpass']).reset_index(drop=True)
print('viirs points', len(v))
tree = cKDTree(v[['x', 'y']].values)

# --- lookup: event -> its VIIRS alerts
lk = pd.read_csv(BASE + '/alert_scar_lookup.csv')
lk = lk[lk.sensor.str.startswith('viirs')]
lg = gpd.GeoSeries(gpd.points_from_xy(lk.longitude, lk.latitude), crs=4326).to_crs(CRS)
lk['x'] = lg.x.values; lk['y'] = lg.y.values

sc = gpd.read_file(BASE + '/event_scars.geojson').to_crs(CRS)
sc = sc[sc.sensor == 'viirs']
print('viirs-seeded scars', len(sc))


def feats(P, prefix):
    out = {}
    if len(P) == 0:
        return {prefix + k: 0.0 for k in ['n', 'nop', 'ndays', 'frp_sum', 'frp_max', 'fp_union_ha', 'hull_ha', 'concave_ha', 'span_m']}
    out['n'] = len(P)
    out['nop'] = P.overpass.nunique()
    out['ndays'] = P.dn.nunique()
    out['frp_sum'] = P.frp.sum()
    out['frp_max'] = P.frp.max()
    # pixel footprints (scan x track km) as boxes
    boxes = [box(x - s * 500, y - t * 500, x + s * 500, y + t * 500) for x, y, s, t in zip(P.x, P.y, P.scan, P.track)]
    u = shapely.union_all(boxes)
    out['fp_union_ha'] = u.area / 1e4
    pts = shapely.multipoints(P[['x', 'y']].values)
    hull = pts.convex_hull.buffer(187.5)
    out['hull_ha'] = hull.area / 1e4
    if len(P) >= 3:
        ch = shapely.concave_hull(pts, ratio=0.3).buffer(187.5)
    else:
        ch = hull
    out['concave_ha'] = ch.area / 1e4
    xy = P[['x', 'y']].values
    out['span_m'] = float(np.hypot(*(xy.max(0) - xy.min(0))))
    return {prefix + k: float(val) for k, val in out.items()}


rows = []
for _, s in sc.iterrows():
    seeds = lk[lk.event_id == s.event_id]
    if len(seeds) == 0:
        continue
    d0 = (pd.Timestamp(s.date) - pd.Timestamp('2017-01-01')).days
    dend = (pd.Timestamp(s.post_date) - pd.Timestamp('2017-01-01')).days
    # seed indices in v
    _, idx = tree.query(seeds[['x', 'y']].values, k=1)
    idx = [i for i in set(idx) if v.dn[i] == d0]
    if not idx:
        continue
    clus = set(idx); frontier = list(idx)
    while frontier:
        new = []
        for i in frontier:
            for j in tree.query_ball_point((v.x[i], v.y[i]), LINK_M):
                if j in clus:
                    continue
                dj = v.dn[j]
                if dj < d0 - 1 or dj > dend:
                    continue
                if abs(dj - v.dn[i]) > 1:
                    continue
                clus.add(j); new.append(j)
        frontier = new
    P = v.loc[sorted(clus)]
    r = dict(event_id=s.event_id, year=pd.Timestamp(s.date).year, month=pd.Timestamp(s.date).month, scar_ha=s.scar_ha,
             scar_ha_post=s.scar_ha_post, edge=bool(s.touches_chip_edge), gap_days=s.gap_days,
             days_after=int(dend - d0), grew_large=bool(s.grew_into_large_burn))
    r.update(feats(P[P.dn <= d0], 'd0_'))
    r.update(feats(P[P.dn <= d0 + 1], 'd1_'))
    r.update(feats(P, 'all_'))
    # fraction of cluster points inside the scar (sanity)
    inside = shapely.contains_xy(s.geometry.buffer(200), P.x.values, P.y.values)
    r['frac_inside'] = inside.mean()
    rows.append(r)

F = pd.DataFrame(rows)
F.to_parquet(OUT + f'features_{int(LINK_M)}.parquet')
print(F.describe().T.to_string())
