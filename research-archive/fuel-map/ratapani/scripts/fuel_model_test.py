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
F = pd.read_csv('/tmp/claude-0/fuel/out/fuel_cells_static.csv').set_index('cell_id')
FS = pd.read_csv('/tmp/claude-0/fuel/out/fuel_cells_season.csv')
rng = np.random.default_rng(0)
lab = ps.labels(SEAS)
TL = pd.read_parquet(O + 'true_lead_labels.parquet'); TL['date'] = pd.to_datetime(TL.date)
pr = pd.read_parquet(P + 'ratapani/scoring/pipeline_lean_pred_loso_2017_24.parquet'); pr['date'] = pd.to_datetime(pr.date)
X = lab.merge(pr, on=['season', 'date', 'cell_id'])
X['lg'] = np.log(X.pipeline_lean.clip(1e-5, 1 - 1e-5) / (1 - X.pipeline_lean.clip(1e-5, 1 - 1e-5)))
X = X.join(F, on='cell_id').merge(FS, on=['season', 'cell_id'], how='left'); X['doy'] = X.date.dt.dayofyear
FE = {'stack_base': ['lg', 'doy'], 'stack_fsi': ['lg', 'doy', 'fuel_fsi'], 'stack_cont': ['lg', 'doy', 'fuel_cont', 'fuel_cont_modplus', 'fuel_cont_sd', 'fuel_season']}
preds = {k: np.zeros(len(X)) for k in ['fuel_only_fsi', 'fuel_only_cont', 'fuel_only_season'] + list(FE)}
for Y in SEAS:
    tr_s = [s for s in SEAS if s != Y]
    tr = X.season.isin(tr_s).values; te = (X.season == Y).values
    keep = tr & (X.pos.values | (rng.random(len(X)) < 0.25)); wt = np.where(X.pos.values[keep], 1.0, 4.0)
    preds['fuel_only_fsi'][te] = X.fuel_fsi.values[te]; preds['fuel_only_cont'][te] = X.fuel_cont.values[te]; preds['fuel_only_season'][te] = X.fuel_season.values[te]
    for nm, cols in FE.items():
        gb = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=15, min_child_samples=200, verbose=-1, n_jobs=4)
        gb.fit(X.loc[keep, cols], X.pos.values[keep], sample_weight=wt, )
        preds[nm][te] = gb.predict_proba(X.loc[te, cols])[:, 1]
    print('fold', Y, flush=True)
for k, v in preds.items(): X[k] = v
cols = ['pipeline_lean'] + list(preds)
pred = X[['season', 'date', 'cell_id'] + cols]
out = {}
for nm, L in (('main', lab), ('truelead_strict', TL[TL.valid_strict][['season', 'date', 'cell_id', 'pos']])):
    m = L.merge(pred, on=['season', 'date', 'cell_id'], how='left'); m['random'] = np.random.default_rng(0).random(len(m))
    out[nm] = {c: score(m, c, real)['recall'] for c in cols + ['random']}
    print(nm, out[nm], flush=True)
# where-only: strata vs burn-history prior per cell (static ranking)
json.dump(out, open('/tmp/claude-0/fuel/out/fuel_model_test.json', 'w'), indent=1)
