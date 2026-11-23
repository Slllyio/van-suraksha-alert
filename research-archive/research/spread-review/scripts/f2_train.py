"""Train + score calibrated chances (f1_build rows). Leave-one-season-out on 2017-24; forward test: train 2017-24, score 2025-26.
Models: ring = distance-only chances (empirical rate per d_last x silent-looks bin, from training seasons only);
        full = LightGBM on all features; cal = full + isotonic calibration cross-fitted on the other held-out seasons.
Out: preds.parquet, metrics.json, reliability.csv, importance.csv"""
import pandas as pd, numpy as np, sys, json, lightgbm as lgb
from sklearn.metrics import roc_auc_score, log_loss
from sklearn.isotonic import IsotonicRegression
D = pd.read_parquet(sys.argv[1]); OUT = sys.argv[2]
F = ['d_all', 'd_last', 'd_first', 'd_old', 'n_old500', 'proj', 'perp', 'mom_len', 'n_seen', 'n_last', 'looks_seen', 'frp_last', 'frp_max',
     'h_since_first', 'h_since_last', 'silent', 'next_night', 'doy', 'elev_rel', 'slope', 'wc']
H = ['y12', 'y24', 'y48']
D['dbin'] = np.minimum(D.d_last // 150, 13).astype(int); D['sbin'] = np.minimum(D.silent, 2)
def ring_fit(tr, y):
    t = tr.groupby(['dbin', 'sbin']).apply(lambda q: np.average(q[y], weights=q.w), include_groups=False)
    return t
P = []
splits = [(y, D.yr.between(2017, 2024) & (D.yr != y), D.yr == y) for y in range(2017, 2025)] + [('fwd', D.yr <= 2024, D.yr >= 2025)]
imp = {}
for name, trm, tem in splits:
    tr, te = D[trm], D[tem]
    out = te[['fire', 'yr', 's', 'x', 'y', 'w', 'd_all', 'd_last'] + H].copy(); out['split'] = str(name)
    for y in H:
        rt = ring_fit(tr, y)
        out['ring_' + y] = [rt.get((a, b), np.nan) for a, b in zip(te.dbin, te.sbin)]
        m = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=63, min_child_samples=200, subsample=0.8,
                               subsample_freq=1, colsample_bytree=0.8, verbose=-1)
        m.fit(tr[F], tr[y], sample_weight=tr.w)
        out['full_' + y] = m.predict_proba(te[F])[:, 1]
        if name == 'fwd': imp[y] = dict(zip(F, m.booster_.feature_importance('gain')))
    P.append(out)
P = pd.concat(P, ignore_index=True)
# cross-fitted isotonic: for each held-out season, calibrate on the other LOSO seasons' out-of-fold predictions
for y in H:
    P['cal_' + y] = np.nan
    lo = P[P.split != 'fwd']
    for sp in P.split.unique():
        ref = lo[lo.split != sp] if sp != 'fwd' else lo
        iso = IsotonicRegression(out_of_bounds='clip', y_min=0, y_max=1).fit(ref['full_' + y], ref[y], sample_weight=ref.w)
        k = P.split == sp; P.loc[k, 'cal_' + y] = iso.predict(P.loc[k, 'full_' + y])
P.to_parquet(OUT + '/preds.parquet')
def metrics(q, y, m):
    p = q[f'{m}_{y}'].fillna(q[y].mean()).clip(1e-4, 1 - 1e-4); w = q.w
    base = np.average(q[y], weights=w)
    bs = np.average((p - q[y]) ** 2, weights=w); bs0 = np.average((base - q[y]) ** 2, weights=w)
    # equal-area recall: per issue, top-N cells with N = cells within 475 m of detections so far
    rec = []
    for _, g in q.groupby(['fire', 's']):
        if not g[y].any(): continue
        n = int((g.d_all <= 475).sum()); sel = g[f'{m}_{y}'].fillna(0).rank(ascending=False, method='first') <= n
        rec.append((g[y] & sel).sum() / g[y].sum())
    return dict(brier_skill=round(1 - bs / bs0, 3), logloss=round(log_loss(q[y], p, sample_weight=w), 4),
                auc=round(roc_auc_score(q[y], p, sample_weight=w), 3), recall_at_persistence_area=round(float(np.mean(rec)), 3), base_rate=round(base, 4))
M = {}
for part, q in (('LOSO_2017_24', P[P.split != 'fwd']), ('forward_2025_26', P[P.split == 'fwd'])):
    M[part] = {y: {m: metrics(q, y, m) for m in ('ring', 'full', 'cal')} for y in H}
    # persistence as a 0/1 rule for the recall comparison
    for y in H:
        rec = []
        for _, g in q.groupby(['fire', 's']):
            if g[y].any(): rec.append((g[y] & (g.d_all <= 475)).sum() / g[y].sum())
        M[part][y]['persistence_recall'] = round(float(np.mean(rec)), 3)
rel = []
for part, q in (('LOSO', P[P.split != 'fwd']), ('forward', P[P.split == 'fwd'])):
    for y in H:
        b = pd.cut(q['cal_' + y], [-.01, .02, .05, .1, .2, .3, .4, .5, .6, .7, .8, 1.01])
        t = q.groupby(b, observed=True).apply(lambda g: pd.Series(dict(pred=np.average(g['cal_' + y], weights=g.w), obs=np.average(g[y], weights=g.w), n=len(g))), include_groups=False)
        t['part'], t['h'] = part, y; rel.append(t.reset_index())
pd.concat(rel).to_csv(OUT + '/reliability.csv', index=False)
pd.DataFrame(imp).sort_values('y24', ascending=False).to_csv(OUT + '/importance.csv')
json.dump(M, open(OUT + '/metrics.json', 'w'), indent=1); print(json.dumps(M, indent=1))
