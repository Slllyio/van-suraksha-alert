"""T2b = T2 plus access/contiguity controls (village, track, depth in forest, crops, boundary, forest share 1-2 km, past burnt share).
T2: does a fuel layer say which forest cells burn more of their area in a season (after 15 Feb), beyond canopy and ignition pressure?
Cells with >= 50% forest. Cells already burnt before 15 Feb that season are dropped (they show in the Feb frame).
Held out twice: season left out AND spatial block left out (5 folds of 10 km blocks), so a model can't learn a place.
Targets: share of the cell burnt (0-1), and 'most of the cell burnt' (>= 50%). Metrics averaged over held-out seasons:
Spearman (share), AUC (>=50%)."""
import json, numpy as np, pandas as pd, lightgbm as lgb, warnings
warnings.filterwarnings('ignore')
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
import common as C
cells = pd.read_parquet(f'{C.SP}/cells.parquet')
st = pd.read_parquet('/mnt/project-files/ratapani/scoring/features/static_features.parquet').merge(pd.read_parquet('/mnt/project-files/ratapani/scoring/features/roads_features_v2.parquet'), on='cell_id')
cells = cells.merge(st, on='cell_id')
from scipy.spatial import cKDTree
EE = '/mnt/project-files/ratapani/ee/'
cells = cells.merge(pd.read_csv(EE + 'proximity.csv'), on='cell_id')
_t = cKDTree(cells[['x', 'y']].values)
for r in (1000, 2000):
    nb = _t.query_ball_point(cells[['x', 'y']].values, r + 1); cells[f'forest_{r}'] = [cells.forest_frac.values[n].mean() for n in nb]
cells = cells[cells.forest_frac >= 0.5]
cs = pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/cell_season.csv', parse_dates=['first_window_start'])
SEAS = list(range(2017, 2027))
D = pd.DataFrame([(Y, c) for Y in SEAS for c in cells.cell_id], columns=['season', 'cell_id']).merge(cs, on=['season', 'cell_id'], how='left')
D['burned_ha_total'] = D.burned_ha_total.fillna(0)
early = D.first_window_start.notna() & (D.first_window_start < pd.to_datetime(D.season.astype(str) + '-02-15'))
D = D[~early].copy(); D['share'] = np.clip(D.burned_ha_total / 25, 0, 1); D['most'] = (D.share >= 0.5).astype(int)
B = cs.assign(b=1).pivot_table(index='cell_id', columns='season', values='b', fill_value=0).reindex(index=cells.cell_id, columns=SEAS, fill_value=0)
SH = cs.assign(sh=np.clip(cs.burned_ha_total / 25, 0, 1)).pivot_table(index='cell_id', columns='season', values='sh', fill_value=0).reindex(index=cells.cell_id, columns=SEAS, fill_value=0)
D = D.merge(cells, on='cell_id')
for kind in ('prithvi', 'raw'): D = D.merge(pd.read_parquet(f'{C.SP}/cellfeat_{kind}.parquet'), on=['season', 'cell_id'], how='left')
blk = ((D.x - 739500) // 10000).astype(int) * 7 + ((D.y - 2524000) // 10000).astype(int); D['fold'] = blk.map(dict(zip(sorted(blk.unique()), np.arange(blk.nunique()) % 5)))
IGN = ['prior', 'dist_road_km', 'dist_major_road_km', 'road_km_in_cell', 'dist_edge_km', 'elev_m', 'slope_deg', 'rough_m', 'wc_crop', 'wc_built', 'wc_grass', 'wc_shrub', 'dist_village', 'dist_track', 'depth_in_forest', 'dist_crop_cell', 'dist_boundary', 'forest_1000', 'forest_2000', 'share_hist']
PR = C.NAMES['prithvi']; RAW = C.NAMES['raw']
SETS = {'ignition + access + history only': IGN, 'canopy': IGN + ['canopy'], 'canopy + fuel map v3': IGN + ['canopy', 'litter', 'grass', 'teak'],
        'canopy + raw HLS (same pixels)': IGN + ['canopy'] + RAW, 'canopy + Prithvi': IGN + ['canopy'] + PR, 'canopy + v3 + Prithvi': IGN + ['canopy', 'litter', 'grass', 'teak'] + PR}
out = {'cell_seasons': int(len(D)), 'mean_share': round(float(D.share.mean()), 3), 'most_rate': round(float(D.most.mean()), 3), 'models': {}}
P = {}
for name, f in SETS.items():
    ps, pm = np.full(len(D), np.nan), np.full(len(D), np.nan)
    for Y in SEAS:
        other = [s for s in SEAS if s != Y]
        D['prior'] = np.log((B[other].sum(1) + 0.5) / (len(other) + 1)).reindex(D.cell_id).values   # history from other seasons only
        D['share_hist'] = SH[other].mean(1).reindex(D.cell_id).values
        for k in range(5):
            tr = ((D.season != Y) & (D.fold != k)).values; te = ((D.season == Y) & (D.fold == k)).values
            prm = dict(n_estimators=250, learning_rate=0.04, num_leaves=15, min_child_samples=80, subsample=0.8, subsample_freq=1, colsample_bytree=0.6, n_jobs=4, verbose=-1)
            ps[te] = lgb.LGBMRegressor(**prm).fit(D.loc[tr, f], D.share[tr]).predict(D.loc[te, f])
            pm[te] = lgb.LGBMClassifier(**prm).fit(D.loc[tr, f], D.most[tr]).predict_proba(D.loc[te, f])[:, 1]
    P[name] = (ps, pm)
    sp = [spearmanr(D.share[D.season == Y], ps[(D.season == Y).values])[0] for Y in SEAS]
    au = [roc_auc_score(D.most[D.season == Y], pm[(D.season == Y).values]) for Y in SEAS]
    out['models'][name] = dict(spearman_share=round(float(np.mean(sp)), 3), auc_most=round(float(np.mean(au)), 3), auc_by_season=[round(a, 3) for a in au])
    print(f'{name:35s}', {k: v for k, v in out['models'][name].items() if k != 'auc_by_season'}, flush=True)
def seas_gain(a, b):
    g = [roc_auc_score(D.most[D.season == Y], P[a][1][(D.season == Y).values]) - roc_auc_score(D.most[D.season == Y], P[b][1][(D.season == Y).values]) for Y in SEAS]
    return dict(mean=round(float(np.mean(g)), 4), seasons_better=int(np.sum(np.array(g) > 0)), of=len(g))
out['auc_gain'] = {f'{a} vs {b}': seas_gain(a, b) for a, b in [('canopy + Prithvi', 'canopy'), ('canopy + fuel map v3', 'canopy'), ('canopy + raw HLS (same pixels)', 'canopy'), ('canopy + Prithvi', 'canopy + raw HLS (same pixels)'), ('canopy + v3 + Prithvi', 'canopy + fuel map v3')]}
print(json.dumps(out['auc_gain'], indent=0))
json.dump(out, open(f'{C.SP}/t2b_cells.json', 'w'), indent=1)
