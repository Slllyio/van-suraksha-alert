"""Share of a fire's own VIIRS detections that sit well outside its truth outline (truncation / under-mapping check)."""
import pandas as pd, numpy as np, geopandas as gpd, sys, json
from shapely.ops import unary_union
import shapely
S = sys.argv[1]
A = pd.read_parquet(S + '/tracks.parquet'); md = A.t.dt.strftime('%m-%d'); A = A[(md >= '02-15') & (md <= '06-15')]
L = pd.read_csv(S + '/d/firms_alert_scar_lookup.csv', usecols=['event_id', 'latitude', 'longitude', 'acq_date', 'acq_time'])
key = lambda d: d.latitude.round(4).astype(str) + '_' + d.longitude.round(4).astype(str) + '_' + d.acq_date.astype(str) + '_' + d.acq_time.fillna(-1).astype(int).astype(str)
L['key'] = key(L); A['key'] = key(A)
M = A[['fire', 'key']].merge(L[['key', 'event_id']], on='key')
G = gpd.read_parquet(S + '/d/evgeom.parquet').to_crs(32643).set_index('event_id')
F = pd.read_parquet(S + '/r4_fires.parquet').set_index('fire')
out = []
for f, g in M.groupby('fire'):
    eids = [e for e in g.event_id.unique() if e in G.index]
    if not eids or f not in F.index: continue
    poly = unary_union(list(G.loc[eids].geometry)).buffer(0)
    det = A[A.fire == f]
    d = shapely.distance(poly, shapely.points(det.x.values, det.y.values))
    # chip-edge boundary share: length of outline boundary lying on straight 3 km chip edges is hard; use edge flag from r4
    out.append(dict(fire=f, n_look=F.loc[f, 'n_look'], edge=F.loc[f, 'edge'], share_out_400=float((d > 400).mean()), share_out_800=float((d > 800).mean()), n=len(det)))
X = pd.DataFrame(out)
R = {}
for c, g in X.groupby(pd.cut(X.n_look, [0, 1, 2, 4, 100])):
    R[str(c)] = dict(n=len(g), det_out_400=round(float(np.average(g.share_out_400, weights=g.n)), 3), det_out_800=round(float(np.average(g.share_out_800, weights=g.n)), 3))
for e, g in X[X.n_look >= 3].groupby('edge'):
    R[f'nlook>=3 edge={e}'] = dict(n=len(g), det_out_400=round(float(np.average(g.share_out_400, weights=g.n)), 3))
json.dump(R, open(S + '/r6.json', 'w'), indent=1); print(json.dumps(R, indent=1))
