"""Part B: does a division-and-phase cut-off for 'burnt square' give a better square ranking than one fixed cut-off?
10 MP regions (Prithvi statewide boxes), seasons 2022-25, three phases: P1 15 Feb-15 Mar, P2 16 Mar-15 Apr, P3 16 Apr on.
Rows: forest square x season x phase (no pre-15 Feb scar). Region held out (10 folds).
Inputs: access/terrain/history controls, frozen Prithvi pre-season tokens (PCA fitted on training regions), phase,
HLS dryness from the 10-day step ending before the phase starts (and change since 1 Feb), share burnt earlier this season.
Targets: fixed 30%; any burn; division-and-phase cut-off (median burnt share of burnt squares in that region and phase, other seasons only); share itself (regression).
Scored the same way for all: flag the top 20% of squares in each region-season-phase; % of burnt hectares inside, % of locally big burns inside.
Out: results/b_summary.json, b_by_region_phase.csv"""
import json, numpy as np, pandas as pd, lightgbm as lgb, warnings
warnings.filterwarnings('ignore')
from sklearn.decomposition import PCA
SP = '/tmp/claude-0/-home-user/d4594ebc-4c67-5b87-9e36-c2f8e01f7c08/scratchpad'; R = '/mnt/project-files/research/dynamic-cutoff/results/'
REGS = list(json.load(open(f'{SP}/mp/regions.json'))); SEAS = [2022, 2023, 2024, 2025]; PH = ['P1', 'P2', 'P3']
st = pd.read_parquet('/mnt/project-files/ratapani/mp_grid/static_gis_v1.parquet')
L = pd.read_parquet(f'{SP}/mp/labels_phase.parquet').merge(st, on='cell'); L = L[(L.lc_forest >= 0.5) & ~L.early].copy()
# season-level history from other seasons (as in the statewide test)
S0 = pd.read_parquet(f'{SP}/mp/labels.parquet'); H = S0.pivot_table(index='cell', columns='season', values='share'); B = (H > 0.02).astype(float)
for Y in SEAS:
    o = [s for s in SEAS if s != Y]; m = L.season == Y
    L.loc[m, 'share_hist'] = H[o].mean(1).reindex(L.cell[m]).values; L.loc[m, 'burn_hist'] = B[o].mean(1).reindex(L.cell[m]).values
# burnt earlier this season (earlier phases)
W = L.pivot_table(index=['region', 'season', 'cell'], columns='phase', values='share')
prior = pd.DataFrame({'P1': 0.0, 'P2': W['P1'], 'P3': W['P1'] + W['P2']}).stack().rename('prior_share')
prior.index.names = ['region', 'season', 'cell', 'phase']; L = L.merge(prior.reset_index(), on=['region', 'season', 'cell', 'phase'], how='left')
L['ph'] = L.phase.str[1].astype(int)
# dryness at phase start (step window ends before phase start): P1 Feb 1, P2 Mar 3, P3 Apr 2; change since Feb 1
SI = {'P1': 3, 'P2': 6, 'P3': 9}; dry = []
for Y in SEAS:
    z = np.load(f'/mnt/project-files/ratapani/mp_grid/dryness/mp_dry_{Y}.npz'); ci = pd.Index(z['cells'])
    for p, k in SI.items():
        m = (L.season == Y) & (L.phase == p); q = ci.get_indexer(L.cell[m]); ok = q >= 0
        A = np.full((m.sum(), 8), np.nan, np.float32); A[ok, :4] = z['X'][k][q[ok]]; A[ok, 4:] = z['X'][k][q[ok]].astype(np.float32) - z['X'][3][q[ok]]
        A[A == -32768] = np.nan; dry.append(pd.DataFrame(A, index=L.index[m], columns=[f'dry{i}' for i in range(4)] + [f'ddry{i}' for i in range(4)]))
L = L.join(pd.concat(dry)); DRY = [f'dry{i}' for i in range(4)] + [f'ddry{i}' for i in range(4)]
# local cut-off: median share of burnt squares, same region and phase, other seasons
L['cut'] = np.nan
for r in REGS:
    for p in PH:
        for Y in SEAS:
            o = (L.region == r) & (L.phase == p) & (L.season != Y) & (L.share >= 0.02)
            L.loc[(L.region == r) & (L.phase == p) & (L.season == Y), 'cut'] = L.share[o].median()
L['y30'] = (L.share >= 0.3).astype(int); L['yany'] = (L.share >= 0.02).astype(int); L['ydyn'] = (L.share >= L.cut).astype(int); L['big'] = L.ydyn
# Prithvi tokens (pre-season, per region-season) -> per row
tok = {}
for r in REGS:
    for Y in SEAS:
        z = np.load(f'{SP}/mp/feat/{r}_{Y}.npz'); tok[(r, Y)] = (pd.Index(z['cell']), z['tok'])
CTRL = ['elev', 'slope', 'rugged', 'rough_in', 'tpi5', 'south', 'd_edge_in', 'd_forest_out', 'road_km', 'major_km', 'road_km_5k', 'd_major', 'd_road',
        'd_village', 'villages_5k', 'farm_2k5', 'farm_5k', 'forest_5k', 'settle_5k', 'lc_forest', 'lc_scrub', 'lc_grass', 'lc_farm', 'share_hist', 'burn_hist']
TIME = ['ph', 'prior_share'] + DRY
PRN = [f'pm{i}' for i in range(32)] + [f'pd{i}' for i in range(16)] + [f'pl{i}' for i in range(16)]
L = L.reset_index(drop=True); rng = np.random.default_rng(0)
print('rows', len(L), L.groupby('phase').agg(rate30=('y30', 'mean'), rateany=('yany', 'mean'), cut=('cut', 'median')).round(3).to_dict(), flush=True)
prm = dict(n_estimators=250, learning_rate=0.05, num_leaves=31, min_child_samples=200, subsample=0.7, subsample_freq=1, colsample_bytree=0.5, n_jobs=4, verbose=-1)
MODELS = {'fixed 30%': ('y30', True), 'any burn': ('yany', True), 'division+phase cut-off': ('ydyn', True), 'share (no cut-off)': ('share', True),
          'division+phase cut-off, no Prithvi': ('ydyn', False), 'share (no cut-off), no Prithvi': ('share', False)}
P = {k: np.full(len(L), np.nan) for k in MODELS}
for r in REGS:
    tr = L.index[L.region != r]; te = L.index[L.region == r]
    segs = [(0, 1024), (1024, 2048), (2048, 3072)]
    X = np.concatenate([v[1][rng.choice(len(v[1]), 1000, replace=False)] for (rr, Y), v in tok.items() if rr != r]).astype(np.float32); X = X[~np.isnan(X).any(1)]
    pcs = [PCA(n, random_state=0).fit(X[:, a:b]) for (a, b), n in zip(segs, (32, 16, 16))]; del X
    fr = []
    for (rr, Y), (ci, T) in tok.items():
        T = T.astype(np.float32); nan = np.isnan(T).any(1); T = np.nan_to_num(T)
        F = np.concatenate([p.transform(T[:, a:b]) for p, (a, b) in zip(pcs, segs)], 1).astype(np.float32); F[nan] = np.nan
        fr.append(pd.DataFrame(F, columns=PRN).assign(region=rr, season=Y, cell=ci.values))
    F = L[['region', 'season', 'cell']].merge(pd.concat(fr), on=['region', 'season', 'cell'], how='left'); F.index = L.index; F = F[PRN]; del fr
    Ftr, Fte = F.loc[tr], F.loc[te]
    for k, (y, usep) in MODELS.items():
        f = CTRL + TIME + (PRN if usep else []); Xtr = L.loc[tr, CTRL + TIME].join(Ftr); Xte = L.loc[te, CTRL + TIME].join(Fte)
        if y == 'share': P[k][te] = lgb.LGBMRegressor(**prm).fit(Xtr[f], L.share[tr]).predict(Xte[f])
        else: P[k][te] = lgb.LGBMClassifier(**prm).fit(Xtr[f], L[y][tr]).predict_proba(Xte[f])[:, 1]
    print(r, flush=True)
rows = []
for k in MODELS:
    L['p'] = P[k]
    for (r, Y, p), g in L.groupby(['region', 'season', 'phase']):
        if g.share.sum() < 1 or g.big.sum() < 5: continue
        top = g.p.rank(ascending=False, method='first') <= 0.2 * len(g)
        rows.append(dict(model=k, region=r, season=Y, phase=p, ha_burnt=float(g.share.sum() * 25), ha_caught=float(g.share[top].sum() / g.share.sum()),
                         big_caught=float(g.big[top].mean() / max(g.big.mean(), 1e-9) * 0.2) if False else float(g.big[top].sum() / g.big.sum()),
                         fixed30_caught=float(g.y30[top].sum() / max(g.y30.sum(), 1)), any_caught=float(g.yany[top].sum() / g.yany.sum()), cut=float(g.cut.iloc[0])))
T = pd.DataFrame(rows); T.to_csv(R + 'b_by_region_phase.csv', index=False)
def summ(d): return d.groupby('model')[['ha_caught', 'big_caught', 'any_caught']].mean().round(4)
out = dict(cuts=L.groupby(['region', 'phase']).cut.median().unstack().round(3).to_dict('index'), overall=summ(T).to_dict('index'),
           by_phase={p: summ(T[T.phase == p]).to_dict('index') for p in PH},
           by_region={r: summ(T[T.region == r]).to_dict('index') for r in REGS})
a, b = 'division+phase cut-off', 'fixed 30%'
g = T[T.model == a].set_index(['region', 'season', 'phase']).ha_caught - T[T.model == b].set_index(['region', 'season', 'phase']).ha_caught
gr = g.groupby(level=0).mean(); bs = [gr.values[rng.integers(0, len(gr), len(gr))].mean() for _ in range(4000)]
out['dyn_vs_fixed_ha'] = dict(mean=round(float(gr.mean()), 4), regions_better=int((gr > 0).sum()), ci=[round(float(np.percentile(bs, q)), 4) for q in (2.5, 97.5)])
for a, b, nm in [('share (no cut-off)', 'fixed 30%', 'share_vs_fixed_ha'), ('division+phase cut-off', 'division+phase cut-off, no Prithvi', 'prithvi_gain_dyn_ha'), ('share (no cut-off)', 'share (no cut-off), no Prithvi', 'prithvi_gain_share_ha')]:
    g = (T[T.model == a].set_index(['region', 'season', 'phase']).ha_caught - T[T.model == b].set_index(['region', 'season', 'phase']).ha_caught)
    out[nm] = dict(mean=round(float(g.mean()), 4), by_phase=g.groupby(level=2).mean().round(4).to_dict(), by_region=g.groupby(level=0).mean().round(4).to_dict())
json.dump(out, open(R + 'b_summary.json', 'w'), indent=1); print(json.dumps(out, indent=1))
