"""Evaluation helpers shared by the reframe experiments: LOSO training, calibration, skill scores."""
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss
from sklearn.isotonic import IsotonicRegression

P = dict(objective='binary', learning_rate=0.03, num_leaves=15, min_data_in_leaf=100, feature_fraction=0.8,
         bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=0)


def fit_predict(tr, te, feats, y, rounds=400, params=None):
    p = dict(P, **(params or {}))
    m = lgb.train(p, lgb.Dataset(tr[feats], tr[y]), rounds)
    return m.predict(te[feats]), m


def loso(df, feats, y, seasons_cv=range(2017, 2025), test=(2025, 2026), rounds=400, params=None, calibrate=True):
    """Leave-one-season-out over seasons_cv, plus train-on-all-cv -> test seasons. Returns a Series of predictions.
    If calibrate: an isotonic map fitted on inner-LOSO predictions of the training seasons only (no peeking)."""
    out = pd.Series(np.nan, index=df.index)
    folds = [([s], [x for x in seasons_cv if x != s]) for s in seasons_cv] + [(list(test), list(seasons_cv))]
    for hold, train in folds:
        tr = df[df.season.isin(train)]; te = df[df.season.isin(hold)]
        if len(te) == 0: continue
        pr, _ = fit_predict(tr, te, feats, y, rounds, params)
        if calibrate:
            inner = pd.Series(np.nan, index=tr.index)
            for s in train:     # inner LOSO on training seasons for the calibration map (fewer rounds keeps it quick)
                a = tr[tr.season != s]; b = tr[tr.season == s]
                inner.loc[b.index], _ = fit_predict(a, b, feats, y, rounds, params)
            iso = IsotonicRegression(out_of_bounds='clip', y_min=1e-4, y_max=1 - 1e-4).fit(inner.values, tr[y].values)
            pr = iso.predict(pr)
        out.loc[te.index] = pr
    return out


def skill(y, p, ref=None, groups=None):
    y = np.asarray(y).astype(int); p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    r = dict(n=int(len(y)), base_rate=round(float(y.mean()), 4), auc=round(float(roc_auc_score(y, p)), 4),
             brier=round(float(brier_score_loss(y, p)), 5), logloss=round(float(log_loss(y, p)), 4),
             mean_pred=round(float(p.mean()), 4))
    bs_clim = brier_score_loss(y, np.full(len(y), y.mean()))
    r['bss_vs_base_rate'] = round(float(1 - r['brier'] / bs_clim), 4)
    if ref is not None:
        ref = np.clip(np.asarray(ref, float), 1e-4, 1 - 1e-4)
        r['bss_vs_ref'] = round(float(1 - r['brier'] / brier_score_loss(y, ref)), 4)
    return r


def reliability(y, p, bins=(0, .02, .05, .1, .2, .3, .5, .7, 1.0001)):
    d = pd.DataFrame(dict(y=np.asarray(y).astype(int), p=np.asarray(p)))
    d['bin'] = pd.cut(d.p, bins, right=False)
    t = d.groupby('bin', observed=True).agg(n=('y', 'size'), predicted=('p', 'mean'), observed=('y', 'mean'))
    t = t[t.n > 0].round(4); t.index = t.index.astype(str)
    return t.reset_index().to_dict('records')


def topk_recall(df, score, y, group, k, weight=None):
    """Within each group (e.g. issue day), flag the k highest scores; share of positives (or weight) caught."""
    r = df[score].groupby(df[group]).rank('first', ascending=False)
    w = df[weight] if weight else df[y].astype(float)
    return round(float(w[r <= k].sum() / w.sum()), 4)


def topk_ceiling(df, y, group, k, weight=None):
    w = df[weight] if weight else df[y].astype(float)
    r = w.groupby(df[group]).rank('first', ascending=False)
    return round(float(w[r <= k].sum() / w.sum()), 4)
