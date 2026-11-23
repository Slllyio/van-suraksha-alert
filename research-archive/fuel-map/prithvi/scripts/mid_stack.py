"""Mid-season check inside the full model. Target = PC's mid-season target: squares (>=50% forest) not burnt by 15 Mar that burn >=4 ha (16%)
after 15 Mar; late = >=4 ha after 15 Apr. Region held out (train other 9 regions and other seasons). Inputs: controls (access, terrain,
burn history from other seasons) + Feb Prithvi tokens (PCA in fold), then add the PC GPU score (Feb-only 'pre' or 5-frame '+Mar'),
or mid-March HLS dryness (cloud). Out: results/mid_stack.json"""
import json, numpy as np, pandas as pd, lightgbm as lgb, warnings
warnings.filterwarnings('ignore')
from sklearn.decomposition import PCA
from sklearn.metrics import roc_auc_score
SP = '/tmp/claude-0/-home-user/d4594ebc-4c67-5b87-9e36-c2f8e01f7c08/scratchpad'; V = '/home/user/vanagni/prithvi_finetune/'
REGS = list(json.load(open(f'{SP}/mp/regions.json'))); SEAS = [2022, 2023, 2024, 2025]
st = pd.read_parquet('/mnt/project-files/ratapani/mp_grid/static_gis_v1.parquet')
LP = pd.read_parquet(f'{SP}/mp/labels_phase.parquet')
W = LP.pivot_table(index=['region', 'season', 'cell'], columns='phase', values='share', aggfunc='sum').fillna(0).reset_index()
W['s1'] = W['P1']; W['s23'] = W[[c for c in ('P2', 'P3', 'P4') if c in W]].sum(1); W['s3'] = W[[c for c in ('P3', 'P4') if c in W]].sum(1)
ear = LP.groupby(['region', 'season', 'cell']).early.max().reset_index()
D = W.merge(ear, on=['region', 'season', 'cell']).merge(st, on='cell'); D = D[(D.lc_forest >= 0.5) & ~D.early & (D.s1 < 0.02)].copy()
D['y'] = (D.s23 >= 0.16).astype(int); D['ylate'] = (D.s3 >= 0.16).astype(int)
S0 = pd.read_parquet(f'{SP}/mp/labels.parquet'); H = S0.pivot_table(index='cell', columns='season', values='share'); B = (H > 0.02).astype(float)
for Y in SEAS:
    o = [s for s in SEAS if s != Y]; m = D.season == Y
    D.loc[m, 'share_hist'] = H[o].mean(1).reindex(D.cell[m]).values; D.loc[m, 'burn_hist'] = B[o].mean(1).reindex(D.cell[m]).values
for v, n in (('out_mid_pre', 'gpu_feb'), ('out_mid_all5', 'gpu_mar')):
    D = D.merge(pd.read_parquet(V + v + '/scores_frozen.parquet').rename(columns={'score': n}), on=['region', 'season', 'cell'], how='left')
dry = []
for Y in SEAS:
    z = np.load(f'/mnt/project-files/ratapani/mp_grid/dryness/mp_dry_{Y}.npz'); ci = pd.Index(z['cells']); m = D.season == Y; q = ci.get_indexer(D.cell[m]); ok = q >= 0
    A = np.full((m.sum(), 8), np.nan, np.float32); A[ok, :4] = z['X'][6][q[ok]]; A[ok, 4:] = z['X'][6][q[ok]].astype(np.float32) - z['X'][3][q[ok]]
    A[A == -32768] = np.nan; dry.append(pd.DataFrame(A, index=D.index[m], columns=[f'mdry{i}' for i in range(4)] + [f'mddry{i}' for i in range(4)]))
D = D.join(pd.concat(dry)); MD = [f'mdry{i}' for i in range(4)] + [f'mddry{i}' for i in range(4)]
print('rows', len(D), 'y', D.y.mean().round(3), 'late', D.ylate.mean().round(3), 'gpu cover', D[['gpu_feb', 'gpu_mar']].notna().mean().round(3).to_dict(), flush=True)
tok = {}
for r in REGS:
    for Y in SEAS:
        z = np.load(f'{SP}/mp/feat/{r}_{Y}.npz'); i = pd.Index(z['cell']); m = (D.region == r) & (D.season == Y)
        tok[(r, Y)] = (D.index[m], z['tok'][i.get_indexer(D.cell[m])])
TK = np.concatenate([v[1] for v in tok.values()]); TKI = pd.Index(np.concatenate([v[0] for v in tok.values()]))
CTRL = ['elev', 'slope', 'rugged', 'rough_in', 'tpi5', 'south', 'd_edge_in', 'd_forest_out', 'road_km', 'major_km', 'road_km_5k', 'd_major', 'd_road',
        'd_village', 'villages_5k', 'farm_2k5', 'farm_5k', 'forest_5k', 'settle_5k', 'lc_forest', 'lc_scrub', 'lc_grass', 'lc_farm', 'share_hist', 'burn_hist']
PRN = [f'pm{i}' for i in range(32)] + [f'pd{i}' for i in range(16)] + [f'pl{i}' for i in range(16)]
SETS = {'full (Feb Prithvi)': CTRL + PRN, '+ GPU Feb score': CTRL + PRN + ['gpu_feb'], '+ GPU March score': CTRL + PRN + ['gpu_mar'],
        '+ mid-March dryness': CTRL + PRN + MD, '+ mid-March dryness + GPU March': CTRL + PRN + MD + ['gpu_mar']}
rng = np.random.default_rng(0); BL = [(0, 1024), (1024, 2048), (2048, 3072)]
def pca_feats(tr_idx, all_idx):
    pos = TKI.get_indexer(tr_idx); s = rng.choice(pos, min(30000, len(pos)), replace=False); X = TK[s].astype(np.float32); X = X[~np.isnan(X).any(1)]
    P = [PCA(n, random_state=0).fit(X[:, a:b]) for (a, b), n in zip(BL, (32, 16, 16))]
    A = np.nan_to_num(TK[TKI.get_indexer(all_idx)].astype(np.float32))
    return pd.DataFrame(np.concatenate([p.transform(A[:, a:b]) for p, (a, b) in zip(P, BL)], 1), index=all_idx, columns=PRN)
prm = dict(n_estimators=300, learning_rate=0.04, num_leaves=31, min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.6, n_jobs=4, verbose=-1)
P = {(n, t): pd.Series(np.nan, index=D.index) for n in SETS for t in ('y', 'ylate')}
for r in REGS:
    for Y in SEAS:
        tr = (D.region != r) & (D.season != Y); te = (D.region == r) & (D.season == Y)
        if te.sum() == 0: continue
        idx = D.index[tr | te]; X = D.loc[idx].join(pca_feats(D.index[tr], idx))
        for n, f in SETS.items():
            for t in ('y', 'ylate'):
                m = lgb.LGBMClassifier(**prm).fit(X.loc[D.index[tr], f], D[t][tr]); P[(n, t)][te] = m.predict_proba(X.loc[D.index[te], f])[:, 1]
        print(r, Y, flush=True)
out = {'rows': int(len(D))}
for t in ('y', 'ylate'):
    res = {}
    for n in SETS:
        au = {}
        for r in REGS:
            v = [roc_auc_score(D[t][m], P[(n, t)][m]) for Y in SEAS for m in [(D.region == r) & (D.season == Y)] if D[t][m].sum() >= 10 and D[t][m].nunique() == 2]
            au[r] = round(float(np.mean(v)), 3) if v else None
        res[n] = dict(mean=round(float(np.mean([a for a in au.values() if a])), 4), by_region=au)
    base = res['+ GPU Feb score']['by_region']
    for n in ('+ GPU March score', '+ mid-March dryness', '+ mid-March dryness + GPU March'):
        g = np.array([res[n]['by_region'][r] - base[r] for r in REGS if base[r] and res[n]['by_region'][r]])
        bs = [g[np.random.default_rng(i).integers(0, len(g), len(g))].mean() for i in range(3000)]
        res[n]['gain_vs_GPU_Feb'] = dict(mean=round(float(g.mean()), 4), better=int((g > 0).sum()), of=len(g), ci95=[round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)])
    out['after 15 Mar' if t == 'y' else 'late (after 15 Apr)'] = res
    print(t, json.dumps({n: res[n]['mean'] for n in SETS}), flush=True)
json.dump(out, open('/mnt/project-files/fuel-map/prithvi/results/mid_stack.json', 'w'), indent=1)
