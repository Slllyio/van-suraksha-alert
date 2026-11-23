"""Step 7. Paired comparison BIG vs ALL (same fires), by season phase, by division and by year; precision lift.
Out: results/paired.csv, results/by_phase.csv, results/by_division.csv, results/by_year.csv."""
import numpy as np, pandas as pd
import lf_common as L
E = pd.read_parquet(L.SC + 'events_scored.parquet'); E['period'] = np.where(E.season >= 2025, 'fwd 2025', 'held 2022-24')
R = pd.read_csv(L.OUT + 'season_rows.csv')
W = E.pivot_table(index=['season', 'fire', 'div', 'ha', 'month', 'day', 'period', 'q'], columns='model', values='hit').reset_index()
rows = []
for (per, q), g in W.groupby(['period', 'q']):
    for th in (100, 200, 500):
        x = g[g.ha >= th]
        for a, b in (('ALL', 'BIG'), ('ALL', 'TWO'), ('START', 'BIG'), ('ALLS', 'BIG')):
            d = x[b].astype(float).values - x[a].astype(float).values
            bs = d[np.random.default_rng(0).integers(0, len(d), (2000, len(d)))].mean(1)
            rows.append(dict(period=per, flag_share=q, size=f'{th}+', a=a, b=b, n=len(d), a_catch=100 * x[a].mean(), b_catch=100 * x[b].mean(),
                             diff=100 * d.mean(), lo=100 * np.percentile(bs, 2.5), hi=100 * np.percentile(bs, 97.5),
                             only_b=int((x[b].astype(bool) & ~x[a].astype(bool)).sum()), only_a=int((x[a].astype(bool) & ~x[b].astype(bool)).sum())))
pd.DataFrame(rows).round(2).to_csv(L.OUT + 'paired.csv', index=False)
X = W[(W.ha >= 200)].copy()
X['phase'] = pd.cut(X.day, [0, 74, 105, 121, 200], labels=['15 Feb-15 Mar', '16 Mar-15 Apr', '16-30 Apr', 'May'])
X['sizeband'] = pd.cut(X.ha, [200, 500, 1000, 1e9], right=False, labels=['200-500', '500-1000', '1000+'])
for key, fn in (('phase', 'by_phase'), ('season', 'by_year'), ('sizeband', 'by_size')):
    t = X[X.q.isin([0.01, 0.05, 0.10])].groupby(['q', key], observed=True).agg(n=('fire', 'size'), ALL=('ALL', 'mean'), BIG=('BIG', 'mean'), START=('START', 'mean'), HIST=('HIST', 'mean')).reset_index()
    for c in ('ALL', 'BIG', 'START', 'HIST'): t[c] = (100 * t[c]).round(1)
    t['gain'] = (t.BIG - t.ALL).round(1); t.to_csv(L.OUT + f'{fn}.csv', index=False)
t = X[X.q == 0.01].groupby('div').agg(n=('fire', 'size'), ALL=('ALL', 'mean'), BIG=('BIG', 'mean')).reset_index()
t['ALL'] = (100 * t.ALL).round(1); t['BIG'] = (100 * t.BIG).round(1); t['gain'] = t.BIG - t.ALL
t.sort_values('n', ascending=False).to_csv(L.OUT + 'by_division.csv', index=False)
print(pd.read_csv(L.OUT + 'paired.csv').query("a=='ALL' and b=='BIG'").to_string())
for fn in ('by_phase', 'by_year', 'by_size'): print(pd.read_csv(L.OUT + f'{fn}.csv').to_string())
d = pd.read_csv(L.OUT + 'by_division.csv'); d = d[d.n >= 15]
print('divisions >=15 fires:', len(d), 'BIG better', (d.gain > 0).sum(), 'worse', (d.gain < 0).sum(), 'median gain', d.gain.median())
print(d.head(20).to_string())
