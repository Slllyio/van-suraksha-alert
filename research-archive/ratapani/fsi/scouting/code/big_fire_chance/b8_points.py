"""Step 8: a points table officials can read. Logistic regression on a few binned alert-time items, coefficients turned into
whole points (1 point = 0.25 on the log-odds scale, i.e. odds x1.28), and a chance per points total read off the training
seasons. Fitted and scored held out by season (LOSO 2017-24) and forward (2017-24 -> 2025/26), like the models.
Out: out/points_table_<target>.csv (fitted on 2017-24), out/points_scores.csv, out/points_chance_<target>.csv"""
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r21_big'
OUT = '/mnt/project-files/ratapani/fsi/scouting/code/big_fire_chance/out'
A = pd.read_parquet(f'{SC}/ds.parquet').reset_index(drop=True)
TAB = A.groupby(['Division', 'season']).yV200.agg(['sum', 'count']).reset_index()
def div_hist(trs, m=50):
    T = TAB[TAB.season.isin(trs)]; tot = T.groupby('Division')[['sum', 'count']].sum(); prior = T['sum'].sum() / T['count'].sum()
    own = TAB.set_index(['Division', 'season']).reindex(pd.MultiIndex.from_arrays([A.Division, A.season])).fillna(0).values
    t_ = tot.reindex(A.Division).fillna(0).values; it = A.season.isin(trs).values
    return (t_[:, 0] - np.where(it, own[:, 0], 0) + m * prior) / (t_[:, 1] - np.where(it, own[:, 1], 0) + m)
def items(dh, cut):
    d = pd.DataFrame(index=A.index)
    n = A.n1
    d['2 dots'] = (n == 2); d['3-4 dots'] = n.between(3, 4); d['5-8 dots'] = n.between(5, 8); d['9+ dots'] = n >= 9
    d['dots spread over 1 km or more'] = A.ext1 >= 1000
    d['hottest dot 20 MW or more'] = A.frp_max1 >= 20
    d['first seen at night'] = A.night > 0
    ds = A.days_since_15feb
    d['first seen 15 Mar - 15 Apr'] = ds.between(28, 59); d['first seen 16 Apr - 15 May'] = ds.between(60, 89); d['first seen after 15 May'] = ds >= 90
    d['division with many big fires (top third)'] = dh >= cut[1]; d['division with few big fires (bottom third)'] = dh < cut[0]
    d['10+ VIIRS dots within 10 km in last 3 days'] = A.near10_3d >= 10
    d['mostly farmland around (>50% within 1 km)'] = A.agri_1km > 0.5
    d['steep or broken ground (slope 8 deg+)'] = A.slope1 >= 8
    return d.astype(int)
UNIT = 0.25
def fit(trs, tgt):
    dh = div_hist(trs); trm = A.season.isin(trs).values
    cut = np.quantile(dh[trm], [1 / 3, 2 / 3]); X = items(dh, cut)
    y = A[f'y{tgt}']; ok = trm & y.notna().values
    lr = LogisticRegression(C=1.0, max_iter=2000).fit(X[ok], y[ok].astype(int))
    pts = np.round(lr.coef_[0] / UNIT).astype(int)
    tot = X.values @ pts
    # chance per points total: logistic on the total (training seasons), so sparse totals are smoothed
    l2 = LogisticRegression(C=100).fit(tot[ok][:, None], y[ok].astype(int))
    return X, pts, tot, l2, ok
rows = []
for tgt in ('S200', 'V200'):
    for name, trs, tes in [(f'loso{s}', [t for t in range(2017, 2025) if t != s], [s]) for s in range(2017, 2025)] + [('forward', list(range(2017, 2025)), [2025, 2026])]:
        X, pts, tot, l2, ok = fit(trs, tgt)
        te = A.season.isin(tes).values
        rows.append(pd.DataFrame(dict(alert=A.alert[te], season=A.season[te], target=tgt, split=name, points=tot[te], p=l2.predict_proba(tot[te][:, None])[:, 1])))
        if name == 'forward':
            pd.DataFrame(dict(item=X.columns, points=pts)).to_csv(f'{OUT}/points_table_{tgt}.csv', index=False)
            y = A[f'y{tgt}']; tr = ok
            ch = pd.DataFrame(dict(points=tot[tr], y=y[tr])).groupby('points').agg(alerts=('y', 'size'), happened=('y', 'mean')).reset_index()
            ch['chance_said'] = l2.predict_proba(ch.points.values[:, None])[:, 1]
            ch.to_csv(f'{OUT}/points_chance_{tgt}.csv', index=False, float_format='%.3f')
            print(tgt, dict(zip(X.columns, pts))); print(ch.to_string())
R = pd.concat(rows).merge(A[['alert', 'yS200', 'yV200']], on='alert')
R['set'] = np.where(R.split == 'forward', 'fwd' + R.season.astype(str), 'loso')
R.to_parquet(f'{SC}/points_preds.parquet')
sc = []
for (tgt, st), g in R.groupby(['target', 'set']):
    for truth in ('yS200', 'yV200'):
        h = g[g[truth].notna()]
        if h[truth].sum() < 5: continue
        sc.append(dict(fitted_on=tgt, set=st, truth=truth[1:], alerts=len(h), auc=roc_auc_score(h[truth], h.points), prauc=average_precision_score(h[truth], h.p),
                       said=h.p.mean(), happened=h[truth].mean()))
S = pd.DataFrame(sc); S.to_csv(f'{OUT}/points_scores.csv', index=False, float_format='%.3f'); print(S.round(3).to_string())
# division list for the table (2017-24 seasons; VIIRS-footprint 200 ha share, shrunk toward the MP share with 50 pseudo-alerts)
T = TAB[TAB.season.between(2017, 2024)].groupby('Division')[['sum', 'count']].sum(); pr = T['sum'].sum() / T['count'].sum()
T['big_share'] = (T['sum'] + 50 * pr) / (T['count'] + 50)
dh = div_hist(list(range(2017, 2025))); cut = np.quantile(dh[A.season.between(2017, 2024).values], [1 / 3, 2 / 3])
T['group'] = np.where(T.big_share >= cut[1], 'many big fires (+3)', np.where(T.big_share < cut[0], 'few big fires (-3)', 'middle (0)'))
T.rename(columns={'sum': 'big_alerts', 'count': 'alerts'}).sort_values('big_share', ascending=False).to_csv(f'{OUT}/division_history_groups.csv', float_format='%.4f')
