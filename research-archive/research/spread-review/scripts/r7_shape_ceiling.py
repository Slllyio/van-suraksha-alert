"""How much of a footprint score is 'where' vs 'shape'? Sorensen against outlines v1 of simple references, all at the true area."""
import pandas as pd, numpy as np, geopandas as gpd, sys, json
from shapely.ops import unary_union
from shapely.geometry import Point
S = sys.argv[1]
A = pd.read_parquet(S + '/tracks.parquet'); md = A.t.dt.strftime('%m-%d'); A = A[(md >= '02-15') & (md <= '06-15')]
L = pd.read_csv(S + '/d/firms_alert_scar_lookup.csv', usecols=['event_id', 'latitude', 'longitude', 'acq_date', 'acq_time'])
key = lambda d: d.latitude.round(4).astype(str) + '_' + d.longitude.round(4).astype(str) + '_' + d.acq_date.astype(str) + '_' + d.acq_time.fillna(-1).astype(int).astype(str)
L['key'] = key(L); A['key'] = key(A)
M = A[['fire', 'key']].merge(L[['key', 'event_id']], on='key')
G = gpd.read_parquet(S + '/d/evgeom.parquet').to_crs(32643).set_index('event_id')
sor = lambda a, b: 2 * a.intersection(b).area / (a.area + b.area)
def at_area(geom_fn, target, lo=1, hi=5000):
    for _ in range(25):
        mid = (lo + hi) / 2
        if geom_fn(mid).area < target: lo = mid
        else: hi = mid
    return geom_fn((lo + hi) / 2)
rows = []
fires = M.groupby('fire').event_id.apply(lambda s: [e for e in s.unique() if e in G.index])
for f, eids in fires.items():
    if not eids: continue
    det = A[A.fire == f]; nl = det.look.nunique()
    if nl < 2: continue
    T = unary_union(list(G.loc[eids].geometry)).buffer(0); a = T.area
    if a < 2e4: continue
    first = det[det.look == det.look.min()]
    c1 = Point(first.x.mean(), first.y.mean()); r = np.sqrt(a / np.pi)
    pts = [Point(x, y) for x, y in zip(det.x, det.y)]
    fpts = [Point(x, y) for x, y in zip(first.x, first.y)]
    rows.append(dict(fire=f, n_look=nl, area_ha=a / 1e4,
        circle_first=sor(c1.buffer(r), T),
        circle_truecentre=sor(T.centroid.buffer(r), T),
        buf_first_pass=sor(at_area(lambda b: unary_union([p.buffer(b) for p in fpts]), a), T),
        buf_all_dets=sor(at_area(lambda b: unary_union([p.buffer(b) for p in pts]), a), T)))
X = pd.DataFrame(rows); X.to_parquet(S + '/r7_fires.parquet')
R = {c: round(float(X[c].median()), 3) for c in ['circle_first', 'circle_truecentre', 'buf_first_pass', 'buf_all_dets']}
R['mean'] = {c: round(float(X[c].mean()), 3) for c in ['circle_first', 'circle_truecentre', 'buf_first_pass', 'buf_all_dets']}
R['n'] = len(X)
json.dump(R, open(S + '/r7.json', 'w'), indent=1); print(json.dumps(R, indent=1))
