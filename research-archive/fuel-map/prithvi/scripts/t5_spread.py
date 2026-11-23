"""T5: which ground around the first alert burns? Can Prithvi tell 'ground like the burning ground' better than distance,
canopy, roads and raw pixels?  Fires first seen on/after 15 Feb (2,388), points every 150 m within 1.5 km of the first-pass dots.
Target: point inside the fire's final scar (scar outlines v2). Held out: leave-one-season-out, LightGBM.
Prithvi used two ways: the point's own features, and how similar the point's token is to the token under the dots
(cosine similarity of the 64-d PCA vectors, 'same stand as the burning ground'). Same for raw HLS.
Metrics: pixel AUC, and per-fire overlap (IoU) when the top-N points are taken, N = true burnt count (shape at true size)."""
import json, numpy as np, pandas as pd, lightgbm as lgb, rasterio, pyproj, warnings
warnings.filterwarnings('ignore')
from shapely.geometry import shape
from shapely.ops import transform, unary_union
import shapely
from scipy.spatial import cKDTree
from sklearn.metrics import roc_auc_score
import common as C
V2 = '/mnt/project-files/fire-alert-scars/reference/v2_2026-10-16/firms_event_scars.geojson'
to_utm = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
ev = {f['properties']['event_id']: transform(to_utm, shape(f['geometry'])).buffer(0) for f in json.load(open(V2))['features']}
F = pd.read_csv('/mnt/project-files/research/big-fires/results/fires.csv')
G = pd.read_parquet(f'{C.SP}/fires.parquet'); G = G[G.doy >= 46]; D = pd.read_parquet(f'{C.SP}/dots.parquet')
G = G.merge(F[['fire', 'events']], on='fire')
with rasterio.open('/mnt/project-files/fuel-map/ratapani/canopy_cover_10m.tif') as r: CAN = r.read(1).astype(np.float32); CT = r.transform
cells = pd.read_parquet(f'{C.SP}/cells.parquet').merge(pd.read_csv('/mnt/project-files/ratapani/ee/proximity.csv'), on='cell_id')
st = pd.read_parquet('/mnt/project-files/ratapani/scoring/features/static_features.parquet'); cells = cells.merge(st, on='cell_id')
ctree = cKDTree(cells[['x', 'y']].values)
off = np.array([(dx, dy) for dx in np.arange(-1500, 1501, 150) for dy in np.arange(-1500, 1501, 150) if dx * dx + dy * dy <= 1500 ** 2], float)
rows = []
for g in G.itertuples():
    d = D[D.fire == g.fire][['x', 'y']].values; c = d.mean(0); P = c + off
    scar = unary_union([ev[e] for e in g.events.split(';') if e in ev])
    dist = cKDTree(d).query(P)[0]
    rows.append(pd.DataFrame({'fire': g.fire, 'season': g.season, 'x': P[:, 0], 'y': P[:, 1], 'dist': dist, 'burnt': shapely.contains_xy(scar, P[:, 0], P[:, 1]).astype(int),
                              'dx': off[:, 0], 'dy': off[:, 1], 'n_dots': len(d), 'doy': g.doy, 'tmax': g.tmax, 'rh': g.rh, 'wind': g.wind, 'cx': c[0], 'cy': c[1]}))
X = pd.concat(rows, ignore_index=True); print('points', len(X), 'burnt share', round(X.burnt.mean(), 3), flush=True)
rr = ((CT.f - X.y) / -CT.e).astype(int).clip(0, CAN.shape[0] - 1); cc = ((X.x - CT.c) / CT.a).astype(int).clip(0, CAN.shape[1] - 1)
X['canopy'] = np.where(CAN[rr, cc] == 65535, np.nan, CAN[rr, cc] * 0.1)
_, ci = ctree.query(X[['x', 'y']].values)
for c in ['dist_road', 'dist_track', 'dist_village', 'depth_in_forest', 'dist_crop_cell', 'forest_frac', 'slope_deg', 'wc_crop', 'wc_tree']: X[c] = cells[c].values[ci]
PR, RAW = C.NAMES['prithvi'], C.NAMES['raw']
for kind, names in (('prithvi', PR), ('raw', RAW)):
    parts = []
    for Y, g in X.groupby('season'):
        v = C.sample(Y, kind, g.x.values, g.y.values)
        dd = D.merge(G[['fire', 'season']], on='fire'); dd = dd[dd.season == Y]
        dv = pd.DataFrame(C.sample(Y, kind, dd.x.values, dd.y.values), index=dd.fire.values).groupby(level=0).mean()
        ref = dv.reindex(g.fire.values).values
        A = np.nan_to_num((v - np.nanmean(v, 0)) / np.nanstd(v, 0)); Bm = np.nan_to_num((ref - np.nanmean(v, 0)) / np.nanstd(v, 0))
        sim = (A * Bm).sum(1) / (np.linalg.norm(A, axis=1) * np.linalg.norm(Bm, axis=1) + 1e-9)
        parts.append(pd.DataFrame(np.c_[v, sim], index=g.index, columns=names + [f'{kind}_sim']))
    X = X.join(pd.concat(parts))
BASE = ['dist', 'dx', 'dy', 'n_dots', 'doy', 'tmax', 'rh', 'wind']
GND = ['canopy', 'dist_road', 'dist_track', 'dist_village', 'depth_in_forest', 'dist_crop_cell', 'forest_frac', 'slope_deg', 'wc_crop', 'wc_tree']
SETS = {'distance only': BASE, '+ ground (canopy, roads, crops...)': BASE + GND, '+ ground + raw HLS': BASE + GND + RAW + ['raw_sim'],
        '+ ground + Prithvi': BASE + GND + PR + ['prithvi_sim'], '+ ground + Prithvi similarity only': BASE + GND + ['prithvi_sim']}
out = {'fires': int(X.fire.nunique()), 'points': int(len(X)), 'burnt_share': round(float(X.burnt.mean()), 3), 'models': {}}
def iou(p):
    s = []
    for f, g in X.assign(p=p).groupby('fire'):
        n = g.burnt.sum()
        if n == 0: continue
        top = g.p.rank(ascending=False, method='first') <= n; s.append((top & (g.burnt == 1)).sum() / (top | (g.burnt == 1)).sum())
    return float(np.mean(s))
for name, f in SETS.items():
    p = np.zeros(len(X))
    for Y in X.season.unique():
        tr, te = (X.season != Y).values, (X.season == Y).values
        m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=200, subsample=0.7, subsample_freq=1, colsample_bytree=0.6, n_jobs=4, verbose=-1).fit(X.loc[tr, f], X.burnt[tr])
        p[te] = m.predict_proba(X.loc[te, f])[:, 1]
    X[f'p_{name}'] = p
    out['models'][name] = dict(auc=round(roc_auc_score(X.burnt, p), 4), iou_true_size=round(iou(p), 4),
                               auc_by_season=[round(roc_auc_score(g.burnt, g[f'p_{name}']), 3) for _, g in X.groupby('season')])
    print(f'{name:40s}', {k: v for k, v in out['models'][name].items() if k != 'auc_by_season'}, flush=True)
json.dump(out, open(f'{C.SP}/t5_spread.json', 'w'), indent=1)
