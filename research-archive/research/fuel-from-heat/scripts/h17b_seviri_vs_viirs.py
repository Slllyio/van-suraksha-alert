"""Can Meteosat see Ratapani fires? Same-moment check against VIIRS.

Every VIIRS pass over Ratapani: detections grouped into fire clusters (DBSCAN, 1.5 km). For each cluster: does Meteosat
report a fire pixel within 5 km in the 15-min slot covering the VIIRS time (slot start in [t-15 min, t])? And how does
Meteosat FRP compare with VIIRS summed FRP when both see it?
Out: results/seviri_vs_viirs.json, results/seviri_vs_viirs.csv
"""
import json, os, glob
import numpy as np, pandas as pd
from sklearn.cluster import DBSCAN
from scipy.spatial import cKDTree
from pyproj import Transformer
from h0_lib import RES

GEO = os.environ.get('GEO_DIR', '/tmp/claude-0/geo')
S = pd.concat([pd.read_csv(f, parse_dates=['slot']) for f in sorted(glob.glob(f'{GEO}/seviri_part_*.csv')) if os.path.getsize(f) > 10])
S['x'], S['y'] = Transformer.from_crs(4326, 32643, always_xy=True).transform(S.lon.values, S.lat.values)
V = pd.read_csv(f'{RES}/viirs_det.csv', parse_dates=['t'])
V = V[(V.t.dt.month.between(2, 6)) & (V.t >= S.slot.min()) & (V.t <= S.slot.max() + pd.Timedelta('15min'))]
rows = []
for (sen, t), g in V.groupby(['sensor', 't']):
    lab = DBSCAN(eps=1500, min_samples=1).fit_predict(g[['x', 'y']].values)
    sl = t.floor('15min')
    cand = S[S.slot == sl]
    tr = cKDTree(cand[['x', 'y']].values) if len(cand) else None
    for c in np.unique(lab):
        h = g[lab == c]; cx, cy = h.x.mean(), h.y.mean()
        hit, mfrp = False, 0.0
        if tr is not None:
            i = tr.query_ball_point([cx, cy], 5000)
            if i: hit, mfrp = True, cand.frp.values[i].sum()
        rows.append(dict(sensor=sen, t=t, n=len(h), viirs_frp=h.frp.sum(), meteosat=hit, meteosat_frp=mfrp,
                         night=h.daynight.iloc[0] == 'N', in_fire=h.fire.notna().any()))
R = pd.DataFrame(rows); R.to_csv(f'{RES}/seviri_vs_viirs.csv', index=False)
bins = [0, 5, 10, 20, 40, 80, 160, 1e5]
b = pd.cut(R.viirs_frp, bins)
T = R.groupby(b, observed=True).agg(clusters=('n', 'size'), seen_pct=('meteosat', 'mean'), share_of_viirs_heat=('viirs_frp', 'sum'))
T['seen_pct'] = (T.seen_pct * 100).round(1); T['share_of_viirs_heat'] = (T.share_of_viirs_heat / R.viirs_frp.sum() * 100).round(1)
print(T)
B = R[R.meteosat]
out = {'viirs_clusters': len(R), 'seen_by_meteosat_pct': round(R.meteosat.mean() * 100, 2),
       'viirs_heat_in_clusters_meteosat_saw_pct': round(B.viirs_frp.sum() / R.viirs_frp.sum() * 100, 1),
       'by_viirs_frp': T.reset_index().astype(str).to_dict('records'),
       'both_seen_n': len(B), 'both_median_meteosat_over_viirs': round(float((B.meteosat_frp / B.viirs_frp).median()), 2),
       'both_rank_corr': round(float(B[['meteosat_frp', 'viirs_frp']].corr('spearman').iloc[0, 1]), 3) if len(B) > 5 else None,
       'seen_pct_day_night': (R.groupby('night').meteosat.mean() * 100).round(1).to_dict()}
print(out)
json.dump(out, open(f'{RES}/seviri_vs_viirs.json', 'w'), indent=1, default=str)
