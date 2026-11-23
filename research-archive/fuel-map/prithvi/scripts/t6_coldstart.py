"""T6: cold start. For ground with no fire history (a new division), can images alone say where fires keep coming back?
Target: seasons burnt out of 10 (2017-26) per 500 m cell with >= 30% forest; 'fire-prone' = top quarter.
Held out by 10 km spatial block (5 folds): the model never sees the area it predicts.
Feature sets: maps (terrain, land cover, roads/villages/crops/edge), + canopy, + raw HLS, + Prithvi, and images alone.
Images: one season (2024, as a new division would have) and all 10 seasons averaged."""
import json, numpy as np, pandas as pd, lightgbm as lgb, warnings
warnings.filterwarnings('ignore')
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
import common as C
cells = pd.read_parquet(f'{C.SP}/cells.parquet')
EE = '/mnt/project-files/ratapani/ee/'
cells = cells.merge(pd.read_csv(EE + 'proximity.csv'), on='cell_id').merge(pd.read_csv(EE + 'terrain.csv'), on='cell_id').merge(pd.read_csv(EE + 'worldcover.csv'), on='cell_id')
cs = pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/cell_season.csv')
cells['freq'] = cells.cell_id.map(cs.groupby('cell_id').season.nunique()).fillna(0)
cells = cells[cells.forest_frac >= 0.3].reset_index(drop=True)
cells['prone'] = (cells.freq >= cells.freq.quantile(0.75)).astype(int)
blk = ((cells.x - 739500) // 10000).astype(int) * 7 + ((cells.y - 2524000) // 10000).astype(int); cells['fold'] = blk.map(dict(zip(sorted(blk.unique()), np.arange(blk.nunique()) % 5)))
PR, RAW = C.NAMES['prithvi'], C.NAMES['raw']
for kind in ('prithvi', 'raw'):
    f = pd.read_parquet(f'{C.SP}/cellfeat_{kind}.parquet')
    cells = cells.merge(f[f.season == 2024].drop(columns='season').add_suffix('_1y').rename(columns={'cell_id_1y': 'cell_id'}), on='cell_id')
    cells = cells.merge(f.drop(columns='season').groupby('cell_id').mean().add_suffix('_10y').reset_index(), on='cell_id')
MAPS = ['elev_m_mean', 'elev_m_stdDev', 'slope_deg_mean', 'dist_road', 'dist_track', 'dist_village', 'dist_boundary', 'depth_in_forest', 'dist_crop_cell'] + [c for c in cells if c.startswith('wc_')]
SETS = {'maps (terrain, land cover, access)': MAPS, 'maps + canopy': MAPS + ['canopy'], 'maps + fuel map v3': MAPS + ['canopy', 'litter', 'grass', 'teak'],
        'maps + canopy + raw HLS, 1 season': MAPS + ['canopy'] + [c + '_1y' for c in RAW], 'maps + canopy + Prithvi, 1 season': MAPS + ['canopy'] + [c + '_1y' for c in PR],
        'maps + canopy + raw HLS, 10 seasons': MAPS + ['canopy'] + [c + '_10y' for c in RAW], 'maps + canopy + Prithvi, 10 seasons': MAPS + ['canopy'] + [c + '_10y' for c in PR],
        'raw HLS alone, 10 seasons': [c + '_10y' for c in RAW], 'Prithvi alone, 10 seasons': [c + '_10y' for c in PR]}
out = {'cells': int(len(cells)), 'mean_freq': round(float(cells.freq.mean()), 2), 'models': {}}
for name, f in SETS.items():
    sp, au = [], []
    for rep in range(3):   # 3 different block-to-fold assignments
        fold = ((blk.map(dict(zip(sorted(blk.unique()), np.random.default_rng(rep).permutation(blk.nunique()))))) % 5).values
        pr, pp = np.zeros(len(cells)), np.zeros(len(cells))
        for k in range(5):
            tr, te = fold != k, fold == k
            prm = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=30, subsample=0.8, subsample_freq=1, colsample_bytree=0.6, n_jobs=1, verbose=-1)
            pr[te] = lgb.LGBMRegressor(**prm).fit(cells.loc[tr, f], cells.freq[tr]).predict(cells.loc[te, f])
            pp[te] = lgb.LGBMClassifier(**prm).fit(cells.loc[tr, f], cells.prone[tr]).predict_proba(cells.loc[te, f])[:, 1]
        sp.append(spearmanr(cells.freq, pr)[0]); au.append(roc_auc_score(cells.prone, pp))
    out['models'][name] = dict(spearman_freq=round(float(np.mean(sp)), 3), auc_prone=round(float(np.mean(au)), 3), auc_range=[round(min(au), 3), round(max(au), 3)])
    print(f'{name:42s}', out['models'][name], flush=True)
json.dump(out, open(f'{C.SP}/t6_coldstart.json', 'w'), indent=1)
