"""Statewide test of the Ratapani burn-share result: does Prithvi rank which forest cells burn most of their area in a season
(fires on/after 15 Feb, 2022-25) better than access/terrain/history controls, a forest-type map, and the raw HLS pixels it saw?
Cells: >= 50% forest (static_gis_v1 lc_forest), no scar from a fire before 15 Feb that season.
A) region held out: train on the other 9 regions AND other seasons, score the held-out region-season (spatial transfer across MP).
B) block held out: train on all regions but other seasons and other 10 km blocks (like the Ratapani test).
PCA of Prithvi tokens is fitted inside each fold on training regions only. Out: mp/mp_stack.json"""
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
for v in ('raw','frozen','finetune'):
    sc = pd.read_parquet(f'/home/user/vanagni/prithvi_finetune/out/scores_{v}.parquet').rename(columns={'score': 'gpu_'+v})
    D = D.reset_index().merge(sc, on=['region','season','cell'], how='left').set_index('index')
print('gpu score coverage', D[['gpu_raw','gpu_frozen','gpu_finetune']].notna().mean().round(4).to_dict(), flush=True)
CTRL = ['elev', 'slope', 'rugged', 'rough_in', 'tpi5', 'south', 'd_edge_in', 'd_forest_out', 'road_km', 'major_km', 'road_km_5k', 'd_major', 'd_road',
        'd_village', 'villages_5k', 'farm_2k5', 'farm_5k', 'forest_5k', 'settle_5k', 'lc_forest', 'lc_scrub', 'lc_grass', 'lc_farm', 'share_hist', 'burn_hist']
FT = ['lc_sal', 'lc_teak', 'lc_drymix', 'lc_moistmix', 'lc_bamboo', 'lc_degraded']
PRN = [f'pm{i}' for i in range(32)] + [f'pd{i}' for i in range(16)] + [f'pl{i}' for i in range(16)]
SETS = {'controls + Prithvi': CTRL + PRN, 'controls + Prithvi + GPU frozen': CTRL + PRN + ['gpu_frozen'],
        'controls + Prithvi + GPU finetune': CTRL + PRN + ['gpu_finetune'], 'controls + GPU finetune': CTRL + ['gpu_finetune'],
        'controls + GPU raw': CTRL + ['gpu_raw']}
_old = {'controls only': CTRL, 'controls + forest type map': CTRL + FT, 'controls + raw HLS': CTRL + RAWN, 'controls + Prithvi': CTRL + PRN,
        'controls + raw HLS + Prithvi': CTRL + RAWN + PRN}
D['block'] = ((D.cell % 1829) // 20).astype(str) + '_' + ((D.cell // 1829) // 20).astype(str)
ub = D.block.unique(); rng = np.random.default_rng(0); D['fold'] = D.block.map(dict(zip(ub, rng.permutation(len(ub)) % 5)))
def pca_feats(train_idx, all_idx):
    pos = TKI.get_indexer(train_idx); pos = pos[pos >= 0]
    s = rng.choice(pos, min(30000, len(pos)), replace=False); X = TK[s]; ok = ~np.isnan(X).any(1); X = X[ok]
    P = [PCA(n, random_state=0).fit(X[:, a:b]) for (a, b), n in zip([(0, 1024), (1024, 2048), (2048, 3072)], (32, 16, 16))]
    q = TKI.get_indexer(all_idx); A = TK[q]; nan = np.isnan(A).any(1); A = np.nan_to_num(A)
    F = np.concatenate([p.transform(A[:, a:b]) for p, (a, b) in zip(P, [(0, 1024), (1024, 2048), (2048, 3072)])], 1); F[nan] = np.nan
    return pd.DataFrame(F, index=all_idx, columns=PRN)
prm = dict(n_estimators=300, learning_rate=0.04, num_leaves=31, min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.6, n_jobs=4, verbose=-1)
out = {'cells': int(len(D)), 'most_rate': round(float(D.most.mean()), 4), 'by_region_rate': D.groupby('region').most.mean().round(3).to_dict()}
for design in ('A_region_held_out',):
    P = {n: pd.Series(np.nan, index=D.index) for n in SETS}
    folds = [(r, Y) for r in REGS for Y in SEAS] if design[0] == 'A' else [(k, Y) for k in range(5) for Y in SEAS]
    for a, Y in folds:
        if design[0] == 'A': tr = (D.region != a) & (D.season != Y); te = (D.region == a) & (D.season == Y)
        else: tr = (D.fold != a) & (D.season != Y); te = (D.fold == a) & (D.season == Y)
        if te.sum() == 0 or D.most[te].nunique() < 2: continue
        idx = D.index[tr | te]; pf = pca_feats(D.index[tr], idx); X = D.loc[idx].join(pf)
        for n, f in SETS.items():
            mdl = lgb.LGBMClassifier(**prm).fit(X.loc[D.index[tr], f], D.most[tr])
            P[n][te] = mdl.predict_proba(X.loc[D.index[te], f])[:, 1]
        print(design, a, Y, flush=True)
    res = {}
    for n in SETS:
        au = {}
        for r in REGS:
            v = [roc_auc_score(D.most[m], P[n][m]) for Y in SEAS for m in [(D.region == r) & (D.season == Y)] if P[n][m].notna().all() and D.most[m].nunique() == 2 and D.most[m].sum() >= 10]
            au[r] = round(float(np.mean(v)), 3) if v else None
        res[n] = dict(mean_auc=round(float(np.mean([v for v in au.values() if v])), 4), by_region=au)
    def gain(a, b):
        g = [res[a]['by_region'][r] - res[b]['by_region'][r] for r in REGS if res[a]['by_region'][r] and res[b]['by_region'][r]]
        return dict(mean=round(float(np.mean(g)), 4), regions_better=int(np.sum(np.array(g) > 0)), of=len(g))
    res['gains'] = {f'{a} vs {b}': gain(a, b) for a, b in [('controls + Prithvi + GPU finetune', 'controls + Prithvi'), ('controls + Prithvi + GPU frozen', 'controls + Prithvi'),
                    ('controls + Prithvi + GPU finetune', 'controls + Prithvi + GPU frozen'), ('controls + GPU finetune', 'controls + Prithvi'), ('controls + GPU finetune', 'controls + GPU raw')]}
    import itertools
    rb = np.random.default_rng(1); a, b = 'controls + Prithvi + GPU finetune', 'controls + Prithvi'
    g = np.array([res[a]['by_region'][r] - res[b]['by_region'][r] for r in REGS]); bs = [g[rb.integers(0, 10, 10)].mean() for _ in range(5000)]
    res['gains']['ci_finetune_stack'] = [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]
    res['gains'] = {**res['gains']}
    out[design] = res; print(design, json.dumps({n: res[n]['mean_auc'] for n in SETS}), json.dumps(res['gains']), flush=True)
    json.dump(out, open(f'{SP}/mp/mp_stack.json', 'w'), indent=1)
