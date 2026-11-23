"""Sanctuary-wide cell ranker for the forecast-driven daily budget. Headroom check showed the day total is near perfect,
so all the gain must come from ranking cells across the whole sanctuary on a given day (not within a beat).
Inputs per valid cell-day (known by end of day t): lean score; distance to nearest VIIRS point (all satellites) in the last
1 / 3 / 7 days; VIIRS points within 1.5 km in last 3 days; share of 1.5 km ring already seen burned this season; scar windows
ended in the ring in the last 7 days; beat's recent VIIRS; cell burn history prior (leave-season-out); static forest/fsi.
Models: (a) lean only, (b) LightGBM classifier on all inputs, (c) lambdarank with the issue day as the query; plus rank-average.
Scored with the main labels under the no-peek forecast-driven daily budget (exp_budget.scale_nopeek) and fixed 5/beat."""
import json, sys, numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts')
import data as D, exp_budget as E
m = E.m.copy()
c = D.cells().set_index('cell_id'); XY = c[['x', 'y']].values; n = len(c); tree = cKDTree(XY)
v = D.viirs(); b = D.burns(); fb = b[b['first']]
fsi = pd.read_csv('/mnt/project-files/research/reframe/results/cell_fsi_prone.csv').set_index('cell_id').fsi_prone.reindex(c.index).fillna(3).values
ring = tree.query_ball_point(XY, 1500 + 1)
R = np.zeros((n, n), np.float32)
for i, r in enumerate(ring): R[i, r] = 1
R /= R.sum(1, keepdims=True)
cb = c.beat_uid.values; beats = {u: k for k, u in enumerate(pd.unique(cb))}; cbi = np.array([beats[u] for u in cb])
# burn history: seasons burned (first burn) per cell, for leave-season-out prior
hist = fb.groupby(['season', 'cell_id']).size().unstack(fill_value=0).reindex(columns=range(n), fill_value=0).clip(upper=1)
feat_rows = []
for Y in D.SEASONS:
    days = pd.date_range(f'{Y}-01-01', f'{Y}-06-30'); T = len(days); d0 = days[0]
    g = v[(v.date >= d0) & (v.date <= days[-1])]; gi = (g.date - d0).dt.days.values; gxy = g[['x', 'y']].values
    f = fb[fb.season == Y]; seen_day = np.full(n, 10 ** 6); seen_day[f.cell_id.values] = (f.we - d0).dt.days.values
    prior = hist.drop(index=Y, errors='ignore'); prior = prior[prior.index.isin([s for s in D.SEASONS if s != Y])].mean(0).values
    for t in np.nonzero((days >= pd.Timestamp(f'{Y}-02-01')) & (days <= pd.Timestamp(f'{Y}-06-20')))[0]:
        out = {}
        for k in (1, 3, 7):
            sel = (gi <= t) & (gi > t - k)
            out[f'd{k}'] = np.minimum(cKDTree(gxy[sel]).query(XY)[0], 20000) if sel.any() else np.full(n, 20000.)
        sel = (gi <= t) & (gi > t - 3)
        out['n3_1500'] = np.array([len(x) for x in cKDTree(gxy[sel]).query_ball_point(XY, 1500)]) if sel.any() else np.zeros(n)
        seen = (seen_day <= t).astype(np.float32); recent = ((seen_day <= t) & (seen_day > t - 7)).astype(np.float32)
        out['ring_seen'] = R @ seen; out['ring_recent7'] = R @ recent
        bv = np.bincount(cbi[g.cell_id.values[sel]], minlength=len(beats)) if sel.any() else np.zeros(len(beats))
        out['beat_v3'] = bv[cbi]; out['prior'] = prior
        feat_rows.append(pd.DataFrame(dict(season=Y, date=days[t], cell_id=np.arange(n), **out)))
    print(Y, flush=True)
F = pd.concat(feat_rows, ignore_index=True)
m = m.merge(F, on=['season', 'date', 'cell_id'], how='left')
m['forest'] = c.forest_frac.values[m.cell_id.values]; m['fsi'] = fsi[m.cell_id.values]; m['doy'] = m.date.dt.dayofyear
FE = ['s', 'd1', 'd3', 'd7', 'n3_1500', 'ring_seen', 'ring_recent7', 'beat_v3', 'prior', 'forest', 'fsi', 'doy']
CV = list(range(2017, 2025)); TEST = [2025, 2026]
P = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8, bagging_fraction=0.7,
         bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=0, num_threads=4)
m = m.sort_values(['season', 'date', 'cell_id']).reset_index(drop=True)
m['p_clf'] = np.nan; m['p_rank'] = np.nan
for hold, train in [([s], [x for x in CV if x != s]) for s in CV] + [(TEST, CV)]:
    tr = m[m.season.isin(train)]; te = m.season.isin(hold)
    clf = lgb.train(P, lgb.Dataset(tr[FE], tr.pos.astype(int)), 300)
    m.loc[te, 'p_clf'] = clf.predict(m.loc[te, FE])
    grp = tr.groupby(['season', 'date'], sort=False).size().values
    rk = lgb.train(dict(P, objective='lambdarank', lambdarank_truncation_level=600, eval_at=[470]), lgb.Dataset(tr[FE], tr.pos.astype(int), group=grp), 300)
    m.loc[te, 'p_rank'] = rk.predict(m.loc[te, FE]); print('fold', hold, flush=True)
for col in ('s', 'p_clf', 'p_rank'): m[f'r_{col}'] = m.groupby(['season', 'date'])[col].rank(pct=True)
m['p_avg'] = (m.r_p_clf + m.r_p_rank) / 2
m.to_parquet(D.OUT + 'pooled_full.parquet')
res = {}
for split, sel in (('loso_2017_24', m.season < 2025), ('test_2025_26', m.season >= 2025)):
    d = m[sel].reset_index(drop=True); sc = E.scale_nopeek(d, 'mu_N2'); r = {}
    for col in ('s', 'p_clf', 'p_rank', 'p_avg'):
        r[f'{col}_dayvarying'] = round(float(d.pos[E.pick(d, col, 'day_varying', sc)].sum() / d.pos.sum()), 4)
        r[f'{col}_fixed5'] = round(float(d.pos[E.pick(d, col, 'fixed5')].sum() / d.pos.sum()), 4)
        r[f'{col}_by_season_dayvarying'] = {int(s): round(float(g.pos.values[E.pick(g, col, 'day_varying', E.scale_nopeek(g, 'mu_N2')).values].sum() / g.pos.sum()), 3) for s, g in ((s, g.reset_index(drop=True)) for s, g in d.groupby('season'))}
    res[split] = r; print(split, {k: v for k, v in r.items() if 'by_season' not in k}, flush=True)
imp = pd.Series(clf.feature_importance('gain'), index=FE).sort_values(ascending=False); res['importance_gain_test_model'] = imp.round(0).to_dict(); print(imp)
json.dump(res, open('/mnt/project-files/research/reframe/results/pooled_ranker.json', 'w'), indent=1)
m[['season', 'date', 'cell_id', 'p_clf', 'p_rank', 'p_avg']].to_parquet(D.OUT + 'pooled_preds.parquet'); print('DONE')
