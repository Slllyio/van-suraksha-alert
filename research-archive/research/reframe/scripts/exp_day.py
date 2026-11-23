"""Experiment B: is the next 2 days a big fire day for Ratapani? Sanctuary-level daily forecast.
Targets over (t, t+2]: N2 = first-burned cells (VIIRS-dated where possible), F2 = S-NPP VIIRS points.
Big = above the 80th percentile of training-season days (so ~20% of days are big). Also a count forecast with intervals."""
import json, sys, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts')
import data as D, common as C
import lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from scipy import stats

bd = pd.read_parquet(D.OUT + 'beat_day.parquet')
v = D.viirs(); v = v[v.satellite == 'N']; vc = v.groupby('date').size()
g = bd.groupby(['season', 'date']).agg(N2=('n2', 'sum'), N7=('n7', 'sum'), san_l1=('san_l1', 'first'), san_l3=('san_l3', 'first'),
                                       san_l7=('san_l7', 'first'), san_seen=('san_seen', 'first'), lean_sum=('lean_sum', 'sum'),
                                       lean_n=('lean_n', 'sum'), v_season=('v_season', 'sum'), doy=('doy', 'first')).reset_index()
g['F2'] = [vc.reindex(pd.date_range(d + pd.Timedelta(days=1), periods=2)).fillna(0).sum() for d in g.date]
w = D.weather(); g = g.merge(w, on='date', how='left')
g['lean_rate'] = g.lean_sum / g.lean_n.clip(lower=1)
CV = list(range(2017, 2025)); TEST = [2025, 2026]
FE = {'climatology': ['doy'],
      'persistence': ['doy', 'san_l1', 'san_l3', 'san_l7'],
      'weather': ['doy', 'T2M_MAX', 'RH2M', 'days_since_rain', 'rh_min7', 'rh7', 'tmax7', 'rain30', 'vpd7', 'WS10M'],
      'full': ['doy', 'san_l1', 'san_l3', 'san_l7', 'san_seen', 'v_season', 'T2M_MAX', 'RH2M', 'days_since_rain', 'rh_min7', 'rh7', 'tmax7', 'rain30', 'vpd7', 'lean_sum', 'lean_rate'],
      'full_no_lean': ['doy', 'san_l1', 'san_l3', 'san_l7', 'san_seen', 'v_season', 'T2M_MAX', 'RH2M', 'days_since_rain', 'rh_min7', 'rh7', 'tmax7', 'rain30', 'vpd7']}
PB = dict(num_leaves=4, min_data_in_leaf=30, learning_rate=0.03)

def fold_list():
    return [([s], [x for x in CV if x != s]) for s in CV] + [(TEST, CV)]

def run_big(target, feats):
    p = pd.Series(np.nan, index=g.index); ybig = pd.Series(0, index=g.index)
    for hold, train in fold_list():
        tr = g[g.season.isin(train)].copy(); te = g[g.season.isin(hold)].copy()
        thr = tr[target].quantile(0.8); tr['y'] = (tr[target] > thr).astype(int); te['y'] = (te[target] > thr).astype(int)
        ybig.loc[te.index] = te.y
        pr, _ = C.fit_predict(tr, te, feats, 'y', 300, PB)
        inner = pd.Series(np.nan, index=tr.index)
        for s in train:
            a, b = tr[tr.season != s], tr[tr.season == s]; inner.loc[b.index], _ = C.fit_predict(a, b, feats, 'y', 300, PB)
        iso = IsotonicRegression(out_of_bounds='clip', y_min=1e-3, y_max=1 - 1e-3).fit(inner, tr.y)
        p.loc[te.index] = iso.predict(pr)
    return p, ybig

def run_count(target, feats):
    """Poisson GBM mean + negative-binomial dispersion fitted on inner LOSO residuals -> 80% and 95% intervals."""
    mu = pd.Series(np.nan, index=g.index); lo80 = mu.copy(); hi80 = mu.copy(); lo95 = mu.copy(); hi95 = mu.copy()
    for hold, train in fold_list():
        tr = g[g.season.isin(train)]; te = g[g.season.isin(hold)]
        par = dict(C.P, objective='poisson', **PB)
        m = lgb.train(par, lgb.Dataset(tr[feats], tr[target]), 300); mt = m.predict(te[feats])
        inner = []
        for s in train:
            a, b = tr[tr.season != s], tr[tr.season == s]
            mi = lgb.train(par, lgb.Dataset(a[feats], a[target]), 300).predict(b[feats]); inner.append((b[target].values, mi))
        yy = np.concatenate([x[0] for x in inner]); mm = np.concatenate([x[1] for x in inner])
        # NB2 alpha by moments: Var = mu + alpha mu^2
        alpha = max(np.sum((yy - mm) ** 2 - mm) / np.sum(mm ** 2), 1e-3)
        n = 1 / alpha; pnb = n / (n + mt)
        mu.loc[te.index] = mt
        lo80.loc[te.index], hi80.loc[te.index] = stats.nbinom.ppf(0.1, n, pnb), stats.nbinom.ppf(0.9, n, pnb)
        lo95.loc[te.index], hi95.loc[te.index] = stats.nbinom.ppf(0.025, n, pnb), stats.nbinom.ppf(0.975, n, pnb)
    return mu, lo80, hi80, lo95, hi95

res = {}
for target in ('N2', 'F2'):
    res[target] = {}
    P = {}; YB = None
    for k, f in FE.items(): P[k], YB = run_big(target, f)
    g[f'big_{target}'] = YB;
    for split, m in (('loso_2017_24', g.season.isin(CV)), ('test_2025_26', g.season.isin(TEST))):
        d = g[m]; r = {}
        for k in FE:
            r[k] = C.skill(d[f'big_{target}'], P[k][m], ref=P['climatology'][m] if k != 'climatology' else None)
            # share of the period's burning that falls on the days ranked in the model's top 20%
            rk = P[k][m].rank(pct=True, method='first'); r[k]['share_of_burning_on_top20pct_days'] = round(float(d[target][rk > 0.8].sum() / d[target].sum()), 4)
            r[k]['auc_by_season'] = {int(s): round(float(C.roc_auc_score(gg[f'big_{target}'], P[k][gg.index])), 3) if gg[f'big_{target}'].nunique() > 1 else None for s, gg in d.groupby('season')}
        rk = d[target].rank(pct=True, method='first'); r['ceiling_share_top20pct_days'] = round(float(d[target][rk > 0.8].sum() / d[target].sum()), 4)
        r['reliability_full'] = C.reliability(d[f'big_{target}'], P['full'][m], bins=(0, .05, .1, .2, .35, .5, .65, .8, 1.0001))
        res[target][split] = r
        print(target, split, {k: (r[k]['auc'], r[k].get('bss_vs_ref'), r[k]['share_of_burning_on_top20pct_days']) for k in FE}, r['ceiling_share_top20pct_days'], flush=True)
    g[f'p_big_{target}'] = P['full']
    # count forecast
    for k in ('climatology', 'full'):
        mu, l8, h8, l9, h9 = run_count(target, FE[k])
        for split, m in (('loso_2017_24', g.season.isin(CV)), ('test_2025_26', g.season.isin(TEST))):
            y = g.loc[m, target]
            res[target][split][f'count_{k}'] = dict(
                spearman=round(float(stats.spearmanr(y, mu[m]).correlation), 3),
                mae=round(float(np.abs(y - mu[m]).mean()), 2),
                cover80=round(float(((y >= l8[m]) & (y <= h8[m])).mean()), 3), cover95=round(float(((y >= l9[m]) & (y <= h9[m])).mean()), 3),
                mean_width80=round(float((h8[m] - l8[m]).mean()), 1))
            print(target, k, split, res[target][split][f'count_{k}'], flush=True)
        if k == 'full': g[f'mu_{target}'] = mu
json.dump(res, open('/mnt/project-files/research/reframe/results/big_day.json', 'w'), indent=1)
g.to_parquet(D.OUT + 'day_preds.parquet'); print('DONE')
