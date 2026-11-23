"""COMBINED (Akkshay Oct 19 07:41Z "yes"): learned 24 h area (section 17, area_model.csv) x learned fill order with Prithvi (section 15).
Based on: Prithvi ground features in the 24 h spread map (coordinator relay Oct 18 06:29Z, after the Prithvi thread's t5: 'which ground around the
first dots burns' AUC 0.795 ground / 0.808 + raw HLS / 0.821 + Prithvi). Unseen 818 fires, same truth and area as the 0.477 rule.
Instead of filling 24.1 ha per active front nearest-first, fill it in order of a learned chance of burning by +24 h
(LightGBM, leave-one-season-out on these issues; candidates = pixels outside the 265 m blocks within 1.5 km of the dots).
  rule      : nearest-first (today)
  dist      : model on distance features only (dist to any dot, to last-look dots, dx/dy of the fire, n dots, day of year)
  ground    : + canopy, roads, tracks, villages, forest depth, crops, slope, land cover
  hls       : + raw HLS (Prithvi's own input, 240 m grid) + similarity to the ground under the dots
  prithvi   : + frozen Prithvi PCA + similarity
  GRID=/mnt/project-files/fuel-map/prithvi/feats python3 prithvi_footprint_test.py
"""
import os, sys, pickle, json, numpy as np, pandas as pd, lightgbm as lgb, rasterio
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.metrics import roc_auc_score
from shapely.geometry import shape
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts'); import c0_lib as C
GRID = os.environ.get('GRID', '/mnt/project-files/fuel-map/prithvi/feats'); GX0, GY1, STEP = 739500.0, 2558520.0, 240.0
NAMES = json.load(open(f'{GRID}/names.json'))
X0, Y0 = 737300.0, 2560500.0; MED = 24.1; LINK = 750.0; CAP = int(os.environ.get("CAP", 500))
I = pd.read_parquet('/tmp/claude-0/unseen/u_issues.parquet'); M = pickle.load(open('/tmp/claude-0/unseen/u_maps.pkl', 'rb'))
A = pd.read_csv('/mnt/project-files/research/big-fires/results/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis']
so = lambda a, b: 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)
_g = {}
def sample(Y, kind, x, y):
    if (Y, kind) not in _g: _g[(Y, kind)] = np.load(f'{GRID}/{Y}_{kind}.npy')
    F = _g[(Y, kind)]; R_, C_, K = F.shape
    fx = (x - GX0) / STEP; fy = (GY1 - y) / STEP
    c0 = np.clip(np.floor(fx).astype(int), 0, C_ - 2); r0 = np.clip(np.floor(fy).astype(int), 0, R_ - 2)
    wx = np.clip(fx - c0, 0, 1)[:, None]; wy = np.clip(fy - r0, 0, 1)[:, None]
    v = [F[r0, c0], F[r0, c0 + 1], F[r0 + 1, c0], F[r0 + 1, c0 + 1]]; w = [(1 - wx) * (1 - wy), wx * (1 - wy), (1 - wx) * wy, wx * wy]
    num = sum(np.nan_to_num(a) * b * ~np.isnan(a) for a, b in zip(v, w)); den = sum(b * ~np.isnan(a) for a, b in zip(v, w))
    return np.where(den > 0, num / np.maximum(den, 1e-9), np.nan)
def clusters(xy):
    if len(xy) == 1: return np.zeros(1, int)
    p = np.array(list(cKDTree(xy).query_pairs(LINK)))
    if len(p) == 0: return np.arange(len(xy))
    return connected_components(coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy), len(xy))), directed=False)[1]
# ground
with rasterio.open('/mnt/project-files/fuel-map/ratapani/canopy_cover_10m.tif') as r: CAN = r.read(1).astype(np.float32); CT = r.transform
gj = json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))
cells = pd.DataFrame([dict(cell_id=f['properties']['cell_id'], x=shape(f['geometry']).centroid.x, y=shape(f['geometry']).centroid.y) for f in gj['features']])
if cells.x.abs().max() < 180:
    import pyproj; t = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform; cells['x'], cells['y'] = t(cells.x.values, cells.y.values)
cells = cells.merge(pd.read_csv('/mnt/project-files/ratapani/ee/proximity.csv'), on='cell_id').merge(pd.read_parquet('/mnt/project-files/ratapani/scoring/features/static_features.parquet'), on='cell_id')
ctree = cKDTree(cells[['x', 'y']].values)
GND = ['canopy', 'dist_road', 'dist_track', 'dist_village', 'depth_in_forest', 'dist_crop_cell', 'slope_deg', 'rough_m', 'wc_crop', 'wc_tree', 'wc_grass', 'dist_edge_km']
DIST = ['d_any', 'd_last', 'rx', 'ry', 'n_dots', 'n_act', 'doy', 'hrs_since_last']
rng = np.random.default_rng(0)
def issues():     # yields one forecast at a time (keeps memory small; run twice: once to train, once to score)
    for fire, g in I.groupby('fire'):
        mp = M[fire]; r0, r1, c0, c1 = mp['box']; Tg = mp['Tg'].ravel(); dom = mp['dom'].ravel()
        rr, cc = np.mgrid[r0:r1, c0:c1]; P = np.c_[(X0 + (cc + .5) * 20).ravel(), (Y0 - (rr + .5) * 20).ravel()]
        d = C.viirs_looks(A[A.fire == fire]).reset_index(drop=True)
        if d.t.min().dayofyear < 46: continue          # Prithvi's Feb frame covers 1-14 Feb: score fires first seen from 15 Feb only
        for it in g.itertuples():
            kn = d[d.lk <= it.k].reset_index(drop=True); xy = kn[['x', 'y']].values; lab = clusters(xy); tk = kn.t.max()
            nact = len(set(lab[(kn.lk >= it.k - 1).values])); truth = dom & (Tg <= it.th + 24)
            dd = cKDTree(xy).query(P)[0]; foot = dd <= 265; cand = (~foot) & (dd <= 1500)
            dl = cKDTree(kn[kn.lk == it.k][['x', 'y']].values).query(P)[0]
            idx = np.flatnonzero(cand); cen = xy.mean(0)
            f = pd.DataFrame(dict(d_any=dd[idx], d_last=dl[idx], rx=P[idx, 0] - cen[0], ry=P[idx, 1] - cen[1], n_dots=len(xy), n_act=nact, doy=tk.dayofyear,
                                  hrs_since_last=(tk - kn[kn.lk < it.k].t.max()).total_seconds() / 3600 if it.k > 0 else 99, y=truth[idx].astype(int),
                                  x_=P[idx, 0], y_=P[idx, 1], dotx=cen[0], doty=cen[1]))
            f['fire'] = fire; f['season'] = tk.year
            yield dict(issue=f'{fire}|{it.k}', fire=fire, season=tk.year, n_extra=int(MED * nact / .04), nfoot=int(foot.sum()),
                       tfoot=int((foot & truth).sum()), T=int(truth.sum()), F=f)
TR = []
for e in issues():
    f = e['F']; TR.append(f.sample(min(CAP, len(f)), random_state=0) if len(f) else f)
X = pd.concat(TR, ignore_index=True); del TR; print('train points', len(X), flush=True)
def ground(df):
    rr_ = ((CT.f - df.y_) / -CT.e).astype(int).clip(0, CAN.shape[0] - 1); cc_ = ((df.x_ - CT.c) / CT.a).astype(int).clip(0, CAN.shape[1] - 1)
    v = CAN[rr_, cc_]; df['canopy'] = np.where(v == 65535, np.nan, v * .1)
    _, ci = ctree.query(df[['x_', 'y_']].values)
    for c in GND[1:]: df[c] = cells[c].values[ci]
    for kind in ('raw', 'prithvi'):
        parts = []
        for Y, gg in df.groupby('season'):
            v = sample(Y, kind, gg.x_.values, gg.y_.values); ref = sample(Y, kind, gg.dotx.values, gg.doty.values)
            mu, sd = np.nanmean(v, 0), np.nanstd(v, 0) + 1e-9
            Av = np.nan_to_num((v - mu) / sd); Bv = np.nan_to_num((ref - mu) / sd)
            sim = (Av * Bv).sum(1) / (np.linalg.norm(Av, axis=1) * np.linalg.norm(Bv, axis=1) + 1e-9)
            parts.append(pd.DataFrame(np.c_[v, sim], index=gg.index, columns=NAMES[kind] + [f'{kind}_sim']))
        df = df.join(pd.concat(parts))
    return df
X = ground(X)
SETS = {'dist': DIST, 'ground': DIST + GND, 'hls': DIST + GND + NAMES['raw'] + ['raw_sim'], 'prithvi': DIST + GND + NAMES['prithvi'] + ['prithvi_sim']}
prm = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=200, subsample=0.7, subsample_freq=1, colsample_bytree=0.6, n_jobs=8, verbose=-1)
models = {s: {} for s in SETS}
for Y in sorted(X.season.unique()):
    tr = X.season != Y
    for s, cols in SETS.items(): models[s][Y] = lgb.LGBMClassifier(**prm).fit(X.loc[tr, cols], X.y[tr])
print('models trained', flush=True)
AR = pd.read_csv('/tmp/claude-0/unseen/area_model.csv').set_index(['fire', 'k'])['mean']
rows = []; AU = []
def dice(e, score):          # blocks always in; then the n_extra lowest-score candidates (score = distance or -chance)
    y = e['F'].y.values; top = np.argsort(score, kind='stable')[:e['n_extra']]; hit = e['tfoot'] + y[top].sum()
    return 2 * hit / max(e['nfoot'] + len(top) + e['T'], 1)
for i, e in enumerate(issues()):
    F = ground(e['F']) if len(e['F']) else e['F']; o = dict(issue=e['issue'], fire=e['fire'], season=e['season'])
    o['rule'] = dice(e, F.d_any.values) if len(F) else 2 * e['tfoot'] / max(e['nfoot'] + e['T'], 1)
    keep = F[['y']].copy(); keep['d'] = -F.d_any if len(F) else []
    for s_, cols in SETS.items():
        p = models[s_][e['season']].predict_proba(F[cols])[:, 1] if len(F) else np.array([])
        o[s_] = dice(e, -p) if len(F) else o['rule']; keep[f'p_{s_}'] = p; F[f'p_{s_}'] = p
    fire_, k_ = e['issue'].split('|'); ea = dict(e, n_extra=int(AR.loc[(int(fire_), int(k_))] / .04))
    if len(F):
        o['area_rule_order'] = dice(ea, F.d_any.values); o['area_prithvi'] = dice(ea, -F['p_prithvi'].values); o['area_hls'] = dice(ea, -F['p_hls'].values)
    else: o['area_rule_order'] = o['area_prithvi'] = o['area_hls'] = 2 * e['tfoot'] / max(e['nfoot'] + e['T'], 1)
    rows.append(o); AU.append(keep.sample(min(2000, len(keep)), random_state=0) if len(keep) else keep)
    if i % 200 == 0: print('scored', i, flush=True)
R = pd.DataFrame(rows); R.to_csv('/tmp/claude-0/unseen/combined.csv', index=False)
Z = pd.concat(AU); res = dict(issues=len(R), fires=int(R.fire.nunique()))
res['pixel_auc'] = {s: round(float(roc_auc_score(Z.y, Z[f'p_{s}'])), 4) for s in SETS}; res['pixel_auc']['nearest'] = round(float(roc_auc_score(Z.y, Z.d)), 4)
fm = R.groupby('fire')[['rule'] + list(SETS) + ['area_rule_order', 'area_hls', 'area_prithvi']].mean(); res['overlap_mean_by_fire'] = fm.mean().round(4).to_dict()
for a, b in [('area_prithvi', 'rule'), ('area_prithvi', 'prithvi'), ('area_prithvi', 'area_rule_order'), ('prithvi', 'hls'), ('prithvi', 'ground'), ('hls', 'ground'), ('ground', 'rule'), ('prithvi', 'rule'), ('dist', 'rule')]:
    dl = (fm[a] - fm[b]).values
    res[f'{a}_minus_{b}_ci'] = [round(float(np.percentile([dl[rng.integers(0, len(dl), len(dl))].mean() for _ in range(2000)], q)), 4) for q in (2.5, 97.5)]
    res[f'{a}_vs_{b}_better/worse'] = [int((dl > .005).sum()), int((dl < -.005).sum())]
res['by_season'] = R.groupby('season')[['rule', 'prithvi', 'area_rule_order', 'area_prithvi']].mean().round(3).to_dict('index')
json.dump(res, open('/tmp/claude-0/unseen/combined.json', 'w'), indent=1, default=str); print(json.dumps(res, indent=1, default=str))
