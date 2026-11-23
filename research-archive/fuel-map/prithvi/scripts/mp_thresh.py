"""Statewide test of the Ratapani burn-share result: does Prithvi rank which forest cells burn most of their area in a season
(fires on/after 15 Feb, 2022-25) better than access/terrain/history controls, a forest-type map, and the raw HLS pixels it saw?
Cells: >= 50% forest (static_gis_v1 lc_forest), no scar from a fire before 15 Feb that season.
A) region held out: train on the other 9 regions AND other seasons, score the held-out region-season (spatial transfer across MP).
B) block held out: train on all regions but other seasons and other 10 km blocks (like the Ratapani test).
PCA of Prithvi tokens is fitted inside each fold on training regions only. Out: mp/mp_test.json"""
import json, sys, numpy as np, pandas as pd, lightgbm as lgb, warnings
warnings.filterwarnings('ignore')
from sklearn.decomposition import PCA
from sklearn.metrics import roc_auc_score
SP = '/tmp/claude-0/-home-user/d4594ebc-4c67-5b87-9e36-c2f8e01f7c08/scratchpad'
REGS = list(json.load(open(f'{SP}/mp/regions.json'))); SEAS = [2022, 2023, 2024, 2025]
lab = pd.read_parquet(f'{SP}/mp/labels.parquet')
st = pd.read_parquet('/mnt/project-files/ratapani/mp_grid/static_gis_v1.parquet')
D = lab.merge(st, on='cell'); D = D[(D.lc_forest >= 0.5)]
H = D.pivot_table(index='cell', columns='season', values='share')
B = (H > 0.02).astype(float)
for Y in SEAS:
    o = [s for s in SEAS if s != Y]; m = D.season == Y
    D.loc[m, 'share_hist'] = H[o].mean(1).reindex(D.cell[m]).values; D.loc[m, 'burn_hist'] = B[o].mean(1).reindex(D.cell[m]).values
D = D[~D.early].copy(); D['most'] = (D.share >= 0.5).astype(int)
tok, raw = {}, {}
for r in REGS:
    for Y in SEAS:
        z = np.load(f'{SP}/mp/feat/{r}_{Y}.npz'); i = pd.Index(z['cell'])
        m = (D.region == r) & (D.season == Y); k = i.get_indexer(D.cell[m])
        tok[(r, Y)] = (D.index[m], z['tok'][k].astype(np.float32)); raw[(r, Y)] = (D.index[m], z['raw'][k])
D = D.reset_index(drop=True) if False else D
RAWN = [f'F{k}_{b}' for k in (1, 2, 3, 4) for b in ['blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'ndvi', 'nbr', 'ndmi']]
RW = pd.DataFrame(np.concatenate([v[1] for v in raw.values()]), index=np.concatenate([v[0] for v in raw.values()]), columns=RAWN)
TK = np.concatenate([v[1] for v in tok.values()]); TKI = pd.Index(np.concatenate([v[0] for v in tok.values()]))
D = D.join(RW)
CTRL = ['elev', 'slope', 'rugged', 'rough_in', 'tpi5', 'south', 'd_edge_in', 'd_forest_out', 'road_km', 'major_km', 'road_km_5k', 'd_major', 'd_road',
        'd_village', 'villages_5k', 'farm_2k5', 'farm_5k', 'forest_5k', 'settle_5k', 'lc_forest', 'lc_scrub', 'lc_grass', 'lc_farm', 'share_hist', 'burn_hist']
FT = ['lc_sal', 'lc_teak', 'lc_drymix', 'lc_moistmix', 'lc_bamboo', 'lc_degraded']
PRN = [f'pm{i}' for i in range(32)] + [f'pd{i}' for i in range(16)] + [f'pl{i}' for i in range(16)]
SETS = {'controls': CTRL, 'controls + raw HLS': CTRL + RAWN, 'controls + Prithvi': CTRL + PRN}
TH = [0.02, 0.1, 0.2, 0.3, 0.5]
for t in TH: D[f'y{t}'] = (D.share >= t).astype(int)
D['block'] = ((D.cell % 1829) // 20).astype(str) + '_' + ((D.cell // 1829) // 20).astype(str)
ub = D.block.unique(); rng = np.random.default_rng(0); D['fold'] = D.block.map(dict(zip(ub, rng.permutation(len(ub)) % 5)))
def pca_feats(train_idx, all_idx):
    pos = TKI.get_indexer(train_idx); pos = pos[pos >= 0]
    s = rng.choice(pos, min(30000, len(pos)), replace=False); X = TK[s]; ok = ~np.isnan(X).any(1); X = X[ok]
    P = [PCA(n, random_state=0).fit(X[:, a:b]) for (a, b), n in zip([(0, 1024), (1024, 2048), (2048, 3072)], (32, 16, 16))]
    q = TKI.get_indexer(all_idx); A = TK[q]; nan = np.isnan(A).any(1); A = np.nan_to_num(A)
    F = np.concatenate([p.transform(A[:, a:b]) for p, (a, b) in zip(P, [(0, 1024), (1024, 2048), (2048, 3072)])], 1); F[nan] = np.nan
    return pd.DataFrame(F, index=all_idx, columns=PRN)
prm = dict(n_estimators=250, learning_rate=0.05, num_leaves=31, min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.6, n_jobs=4, verbose=-1)
P = {(t, n): pd.Series(np.nan, index=D.index) for t in TH for n in SETS}
for a, Y in [(r, Y) for r in REGS for Y in SEAS]:
    tr = (D.region != a) & (D.season != Y); te = (D.region == a) & (D.season == Y)
    idx = D.index[tr | te]; pf = pca_feats(D.index[tr], idx); X = D.loc[idx].join(pf)
    for t in TH:
        for n, f in SETS.items():
            P[(t, n)][te] = lgb.LGBMClassifier(**prm).fit(X.loc[D.index[tr], f], D[f'y{t}'][tr]).predict_proba(X.loc[D.index[te], f])[:, 1]
    print(a, Y, flush=True)
pd.DataFrame({f'{t}|{n}': v for (t, n), v in P.items()}).join(D[['region', 'season', 'cell', 'share']]).to_parquet(f'{SP}/mp/mp_thresh_preds.parquet')
out = {}
rb = np.random.default_rng(1)
for t in TH:
    au = {n: {} for n in SETS}
    for n in SETS:
        for r in REGS:
            v = [roc_auc_score(D[f'y{t}'][m], P[(t, n)][m]) for Y in SEAS for m in [(D.region == r) & (D.season == Y)] if D[f'y{t}'][m].nunique() == 2 and D[f'y{t}'][m].sum() >= 10]
            au[n][r] = round(float(np.mean(v)), 3) if v else None
    g = {k: np.array([au[x][r] - au[y][r] for r in REGS]) for k, (x, y) in {'prithvi_vs_controls': ('controls + Prithvi', 'controls'), 'prithvi_vs_raw': ('controls + Prithvi', 'controls + raw HLS')}.items()}
    out[str(t)] = dict(rate=round(float(D[f'y{t}'].mean()), 3), auc={n: dict(mean=round(float(np.mean(list(au[n].values()))), 4), by_region=au[n]) for n in SETS},
        gains={k: dict(mean=round(float(v.mean()), 4), better=int((v > 0).sum()), ci=[round(float(np.percentile([v[rb.integers(0, 10, 10)].mean() for _ in range(4000)], q)), 4) for q in (2.5, 97.5)], by_region=dict(zip(REGS, v.round(3).tolist()))) for k, v in g.items()})
    print(t, json.dumps({n: out[str(t)]['auc'][n]['mean'] for n in SETS}), json.dumps({k: (v['mean'], v['better'], v['ci']) for k, v in out[str(t)]['gains'].items()}), flush=True)
json.dump(out, open(f'{SP}/mp/mp_thresh.json', 'w'), indent=1)
