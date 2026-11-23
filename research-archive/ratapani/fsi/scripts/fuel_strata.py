"""FSI-style fuel strata test (Surface Fuel Load Mapping deck: forest type x canopy density x slope = 272 strata).
Proxies (no FSI forest-type map here): forest type = 17 k-means clusters of the cell's mean AlphaEarth embedding 2017-24;
canopy density = pre-season (Dec-Jan) median NDVI in 4 classes; slope = FSI classes 0-10, 10-20, 20-30, >30 deg.
Feature = strata burn rate (share of cell-seasons with a first burn), from training seasons only, smoothed.
Test: LOSO 2017-24 stacked LightGBM on logit(lean LOSO pred) with and without strata features; scored on real beats,
main rule and true-lead strict. Out: results/fuel_strata.json"""
import importlib.util, json, os, numpy as np, pandas as pd, lightgbm as lgb
P = '/mnt/project-files/'; O = P + 'ratapani/fsi/'
spec = importlib.util.spec_from_file_location('sb', P + 'ratapani/beats/score_beats.py')
src = open(P + 'ratapani/beats/score_beats.py').read().split('res = {}')[0]   # reuse score() without running it
ns = {}; exec(compile(src, 'score_beats', 'exec'), ns); score = ns['score']; real = ns['real']; ps = ns['ps']
SEAS = list(range(2017, 2025)); n = 3614
# strata
ae = np.mean([pd.read_csv(P + f'ratapani/ee/alphaearth_{y}.csv').sort_values('cell_id').filter(like='A').values for y in SEAS], 0)
rng = np.random.default_rng(0)
def kmeans(X, k, it=50):
    C = X[rng.choice(len(X), k, replace=False)]
    for _ in range(it):
        lab = ((X[:, None] - C[None]) ** 2).sum(-1).argmin(1)
        C = np.array([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
    return lab
ftype = kmeans(ae, 17)
s2 = pd.read_parquet(P + 'research/ratapani-ignition/s2_cells.parquet'); s2['date'] = pd.to_datetime(s2.date)
pre = s2[s2.date.dt.month.isin([12, 1])].groupby('cell_id').ndvi.median().reindex(range(n))
canopy = pd.cut(pre, [-1, pre.quantile(.25), pre.quantile(.5), pre.quantile(.75), 2], labels=False).fillna(1).astype(int).values
slope = pd.read_csv(P + 'ratapani/ee/terrain.csv').set_index('cell_id').slope_deg_mean.reindex(range(n))
scls = np.digitize(slope.fillna(0).values, [10, 20, 30])
strata = ftype * 16 + canopy * 4 + scls
print('strata used', len(np.unique(strata)), 'of 272')
bw = pd.read_csv(P + 'research/ratapani-burn-labels/burn_windows.csv'); bw = bw[(bw.burned == 1) & bw.season.isin(SEAS)]
B = np.zeros((len(SEAS), n)); 
for r in bw[['season', 'cell_id']].drop_duplicates().itertuples(): B[SEAS.index(r.season), r.cell_id] = 1
def srate(train):
    k = [SEAS.index(s) for s in train]; df = pd.DataFrame(dict(s=np.repeat(strata[None], len(k), 0).ravel(), y=B[k].ravel()))
    g = df.groupby('s').y.agg(['sum', 'count']); m = B[k].mean()
    r = (g['sum'] + 20 * m) / (g['count'] + 20); return r.reindex(strata).fillna(m).values
lab = ps.labels(SEAS)
TL = pd.read_parquet(O + 'true_lead_labels.parquet'); TL['date'] = pd.to_datetime(TL.date)
pr = pd.read_parquet(P + 'ratapani/scoring/pipeline_lean_pred_loso_2017_24.parquet'); pr['date'] = pd.to_datetime(pr.date)
X = lab.merge(pr, on=['season', 'date', 'cell_id'])
X['lg'] = np.log(X.pipeline_lean.clip(1e-5, 1 - 1e-5) / (1 - X.pipeline_lean.clip(1e-5, 1 - 1e-5)))
X['ftype'] = ftype[X.cell_id]; X['canopy'] = canopy[X.cell_id]; X['scls'] = scls[X.cell_id]
X['strata_rate'] = 0.0; X['doy'] = X.date.dt.dayofyear
preds = {'strata_only': np.zeros(len(X)), 'stack_base': np.zeros(len(X)), 'stack_strata': np.zeros(len(X))}
for Y in SEAS:
    tr_s = [s for s in SEAS if s != Y]
    for s in SEAS:   # training seasons get a rate built without themselves; test season from all training seasons
        m = (X.season == s).values; X.loc[m, 'strata_rate'] = srate([q for q in tr_s if q != s] if s in tr_s else tr_s)[X.cell_id.values[m]]
    tr = X.season.isin(tr_s).values; te = (X.season == Y).values
    keep = tr & (X.pos.values | (rng.random(len(X)) < 0.25)); wt = np.where(X.pos.values[keep], 1.0, 4.0)
    preds['strata_only'][te] = X.strata_rate.values[te]
    for nm, cols in (('stack_base', ['lg', 'doy']), ('stack_strata', ['lg', 'doy', 'strata_rate', 'ftype', 'canopy', 'scls'])):
        gb = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=15, min_child_samples=200, verbose=-1, n_jobs=4)
        gb.fit(X.loc[keep, cols], X.pos.values[keep], sample_weight=wt, categorical_feature=[c for c in ('ftype',) if c in cols])
        preds[nm][te] = gb.predict_proba(X.loc[te, cols])[:, 1]
    print('fold', Y, flush=True)
for k, v in preds.items(): X[k] = v
cols = ['pipeline_lean', 'strata_only', 'stack_base', 'stack_strata']
pred = X[['season', 'date', 'cell_id'] + cols]
out = {}
for nm, L in (('main', lab), ('truelead_strict', TL[TL.valid_strict][['season', 'date', 'cell_id', 'pos']])):
    m = L.merge(pred, on=['season', 'date', 'cell_id'], how='left'); m['random'] = np.random.default_rng(0).random(len(m))
    out[nm] = {c: score(m, c, real)['recall'] for c in cols + ['random']}
    print(nm, out[nm], flush=True)
# where-only: strata vs burn-history prior per cell (static ranking)
os.makedirs(O + 'results', exist_ok=True); json.dump(out, open(O + 'results/fuel_strata.json', 'w'), indent=1)
