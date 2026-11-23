"""Statewide test set for the 'which side runs farther' hint (fire-continuity c10/c15 rules, rebuilt on all 9 MP tiger reserves).
Fires: tiger-reserve burn scars 2017-25 (fire-alert-scars/mp/out/scars_tiger_reserves.csv, status 'scar', >= 10 ha, not cut by the
chip edge). Dots: the event's VIIRS alerts (mp_alert_event.csv). Fronts ('origins') exactly as c10: looks split by > 2 h gaps; the
first look's dot groups (linked within 750 m), then later groups > 750 m from every earlier dot.
Out: $RW_SCRATCH/events.pkl  [dict(event, season, reserve, scar (EPSG:32643 shapely), dots DataFrame, origins list)]"""
import json, os, pickle, sys
import numpy as np, pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely.geometry import shape, Point
from shapely.ops import transform as stf
from shapely.prepared import prep
R = '/mnt/project-files'; MO = f'{R}/fire-alert-scars/mp/out'; SCR = os.environ.get('RW_SCRATCH', '.')
to43 = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
S = pd.read_csv(f'{MO}/scars_tiger_reserves.csv')
S = S[(S.status == 'scar') & (S.scar_ha >= 10) & (S.touches_chip_edge != True) & S.geometry.notna()]
A = pd.read_csv(f'{MO}/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'satellite', 'instrument', 'frp', 'scan', 'track', 'daynight', 'event_id'])
A = A[(A.instrument == 'VIIRS') & A.event_id.isin(S.event_id)].copy()
A['t'] = pd.to_datetime(A.acq_date + ' ' + A.acq_time.astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
A['x'], A['y'] = to43(A.longitude.values, A.latitude.values)
RES = [(f['properties']['reserve'], prep(shape(f['geometry']).buffer(0.05))) for f in json.load(open(f'{R}/ratapani/mp_grid/reserves.geojson'))['features']]

def clusters(xy):
    if len(xy) == 1: return np.zeros(1, int)
    p = np.array(list(cKDTree(xy).query_pairs(750.0)))
    if len(p) == 0: return np.arange(len(xy))
    return connected_components(coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy),) * 2), directed=False)[1]

out = []
G = A.groupby('event_id')
for n, s in enumerate(S.itertuples()):
    if s.event_id not in G.groups: continue
    d = G.get_group(s.event_id).sort_values('t').reset_index(drop=True)
    d['lk'] = (d.t.diff().dt.total_seconds().fillna(1e9) > 7200).cumsum() - 1
    t0 = d.t.min(); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    poly = stf(to43, shape(json.loads(s.geometry))).buffer(0)
    org = []
    for k in sorted(d.lk.unique()):
        g = d[d.lk == k]; prev = d[d.lk < k]; dp = None
        if k > 0:
            dp = cKDTree(prev[['x', 'y']].values).query(g[['x', 'y']].values)[0]; g = g[dp > 750]; dp = dp[dp > 750]
        if not len(g): continue
        lab = clusters(g[['x', 'y']].values)
        for c in np.unique(lab):
            gg = g[lab == c]
            kind = 'first' if k == 0 else ('separate' if dp[lab == c].min() <= 3000 else 'independent')
            cx, cy = gg.x.mean(), gg.y.mean(); w = gg.frp.clip(lower=.1).values
            hx, hy = (w * gg.x).sum() / w.sum() - cx, (w * gg.y).sum() / w.sum() - cy
            mom = float(np.degrees(np.arctan2(cx - prev.x.mean(), cy - prev.y.mean()))) if len(prev) else np.nan
            if len(gg) >= 3:
                wv, vv = np.linalg.eigh(np.cov(np.c_[gg.x - cx, gg.y - cy].T)); ax = float(np.degrees(np.arctan2(vv[0, 1], vv[1, 1]))); el = float(np.sqrt(wv[1] / max(wv[0], 1)))
            else: ax, el = np.nan, 1.0
            org.append(dict(origin=f'{s.event_id}_{len(org)}', look=int(k), kind=kind, x=cx, y=cy, th=float(gg.th.min()), n_dots=len(gg),
                            frp=float(gg.frp.sum()), hot_b=float(np.degrees(np.arctan2(hx, hy))), hot_m=float(np.hypot(hx, hy)), mom=mom, ax=ax, el=el,
                            night=bool((gg.daynight == 'N').any()), t=str(gg.t.min())))
    lon, lat = d.longitude.mean(), d.latitude.mean()
    res = next((r for r, p in RES if p.contains(Point(lon, lat))), 'other')
    out.append(dict(event=s.event_id, season=int(s.event_id[1:5]), reserve=res, scar_ha=float(s.scar_ha), scar=poly,
                    dots=d[['t', 'x', 'y', 'frp', 'satellite', 'lk']], origins=org))
    if n % 1000 == 0: print(n, len(out), flush=True)
pickle.dump(out, open(f'{SCR}/events.pkl', 'wb'))
print(len(out), 'events', sum(len(e['origins']) for e in out), 'fronts', pd.Series([e['reserve'] for e in out]).value_counts().to_dict())
