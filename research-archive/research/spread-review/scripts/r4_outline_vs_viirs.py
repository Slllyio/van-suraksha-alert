"""Does the truth outline match what VIIRS saw of the same fire? Matches r1 fires to scar outlines v1 through the alert lookup."""
import pandas as pd, numpy as np, geopandas as gpd, sys, json
from shapely.ops import unary_union
from shapely.geometry import Point
S = sys.argv[1]
A = pd.read_parquet(S + '/tracks.parquet'); md = A.t.dt.strftime('%m-%d'); A = A[(md >= '02-15') & (md <= '06-15')]
L = pd.read_csv(S + '/d/firms_alert_scar_lookup.csv', usecols=['event_id', 'latitude', 'longitude', 'acq_date', 'acq_time', 'sensor'])
key = lambda d: d.latitude.round(4).astype(str) + '_' + d.longitude.round(4).astype(str) + '_' + d.acq_date.astype(str) + '_' + d.acq_time.fillna(-1).astype(int).astype(str)
L['key'] = key(L); A['key'] = key(A)
M = A[['fire', 'key']].merge(L[['key', 'event_id']], on='key')
print('detections matched to lookup', M.key.nunique(), 'of', len(A))
G = gpd.read_parquet(S + '/d/evgeom.parquet').to_crs(32643).set_index('event_id')
E = pd.read_parquet(S + '/d/ev.parquet').set_index('event_id')
rows = []
for f, g in M.groupby('fire'):
    eids = [e for e in g.event_id.unique() if e in G.index]
    if not eids: continue
    det = A[A.fire == f]
    poly = unary_union(list(G.loc[eids].geometry)).buffer(0)
    if poly.is_empty: continue
    pts = [Point(x, y) for x, y in zip(det.x, det.y)]
    near = unary_union([p.buffer(600) for p in pts])
    hours = (det.t.max() - det.t.min()).total_seconds() / 3600
    ee = E.loc[eids]
    rows.append(dict(fire=f, season=det.t.dt.year.iloc[0], n_det=len(det), n_look=det.look.nunique(), hours=hours, n_events=len(eids),
                     area_ha=poly.area / 1e4, share_beyond_600=poly.difference(near).area / poly.area,
                     share_beyond_1000=poly.difference(unary_union([p.buffer(1000) for p in pts])).area / poly.area,
                     edge=bool(ee.touches_chip_edge.any()), grew_large=bool(ee.grew_into_large_burn.any()),
                     win_days=float((pd.to_datetime(ee.check_date.fillna(ee.post_date)).max() - pd.to_datetime(ee.pre_date).min()).days),
                     faint=bool((ee.status == 'scar_faint').all())))
X = pd.DataFrame(rows); X.to_parquet(S + '/r4_fires.parquet')
X['req'] = np.sqrt(X.area_ha * 1e4 / np.pi)
R = dict(n_fires=len(X), area_med=X.area_ha.median(), edge_share=X.edge.mean(),
         share_beyond_600_med=X.share_beyond_600.median(), share_beyond_1000_med=X.share_beyond_1000.median(),
         window_days_med=X.win_days.median(), window_days_q=X.win_days.quantile([.25, .75, .9]).tolist())
for c, g in X.groupby(pd.cut(X.n_look, [0, 1, 2, 4, 100])):
    R[f'nlook_{c}'] = dict(n=len(g), area_med=round(g.area_ha.median(), 1), beyond600=round(g.share_beyond_600.median(), 2),
                           beyond1000=round(g.share_beyond_1000.median(), 2), edge=round(g.edge.mean(), 2), hours_med=round(g.hours.median(), 1))
# implied speed if the fire burned the whole outline between ignition (3 h before first det) and last det + 6 h, from a point
X['v_implied'] = X.req / (X.hours + 9)
R['implied_radial_speed_mph_q'] = X.v_implied.quantile([.25, .5, .75]).round(1).tolist()
R['implied_speed_multi_look_q'] = X[X.n_look >= 2].v_implied.quantile([.25, .5, .75]).round(1).tolist()
R = json.loads(json.dumps({str(k): v for k, v in R.items()}, default=float)); json.dump(R, open(S + '/r4.json', 'w'), indent=1)
print(json.dumps(R, indent=1))
