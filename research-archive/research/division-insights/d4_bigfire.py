# Does a division's own habit (fires still burning next day; typical scar size) improve the app's big-fire points?
# Traits use only seasons before the test season. Test = the app's replay of 2025 and 2026 (docs/big_fire_replay),
# VIIRS truth 200 ha+. Weight fitted on one season, scored on the other. Null: traits shuffled across divisions.
import numpy as np, pandas as pd, json
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
E = pd.read_parquet('events.parquet')
R = {y: pd.read_csv(f'/mnt/project-files/field-system/docs/big_fire_replay/season_{y}.csv') for y in (2025, 2026)}
def traits(upto, m=50):
    e = E[(E.year <= upto) & E.forest]
    n = e[e.new_start]
    st = n.next_day.mean()
    g = n.groupby('Division').next_day.agg(['sum', 'count'])
    sb = (g['sum'] + m * st) / (g['count'] + m)                       # shrunk to the MP rate
    s = e[e.scar_ha.notna()].groupby('Division').scar_ha.agg(['median', 'count'])
    med = np.log((s['median'] * s['count'] + m * e.scar_ha.median()) / (s['count'] + m))
    return pd.DataFrame({'still': sb, 'size': med})
def table(y, T, shuffle=None):
    r = R[y].copy(); t = T.copy()
    if shuffle is not None:
        t.index = shuffle.permutation(t.index.values)
    r = r.join(t, on='division')
    for c in ('still', 'size'):
        r[c] = r[c].fillna(t[c].median())
    return r
def run(shuffle=None):
    out = {}
    D = {y: table(y, traits(y - 1), shuffle) for y in (2025, 2026)}
    for tr, te in ((2025, 2026), (2026, 2025)):
        a, b = D[tr], D[te]
        for name, cols in (('points', ['points']), ('+still', ['points', 'still']), ('+size', ['points', 'size']), ('+both', ['points', 'still', 'size'])):
            mu, sd = a[cols].mean(), a[cols].std()
            lr = LogisticRegression(C=1.0).fit((a[cols] - mu) / sd, a.big)
            out[(te, name)] = roc_auc_score(b.big, lr.decision_function((b[cols] - mu) / sd))
    return out
real = run()
print({f'{k[0]} {k[1]}': round(v, 4) for k, v in real.items()})
rng = np.random.default_rng(0)
nulls = [run(rng) for _ in range(200)]
res = {}
for te in (2025, 2026):
    for name in ('+still', '+size', '+both'):
        gain = real[(te, name)] - real[(te, 'points')]
        ng = np.array([n[(te, name)] - n[(te, 'points')] for n in nulls])
        res[f'{te} {name}'] = dict(auc=round(real[(te, name)], 4), points=round(real[(te, 'points')], 4), gain=round(gain, 4),
                                   null_95=round(float(np.quantile(ng, 0.95)), 4), p=round(float((ng >= gain).mean()), 3))
        print(te, name, res[f'{te} {name}'])
# daily top-10 statewide catch, points vs +both
def topn(y, cols_fit, n=10):
    a, b = (table(2026, traits(2025)), table(2025, traits(2024))) if y == 2025 else (table(2025, traits(2024)), table(2026, traits(2025)))
    mu, sd = a[cols_fit].mean(), a[cols_fit].std()
    b['s'] = LogisticRegression().fit((a[cols_fit] - mu) / sd, a.big).decision_function((b[cols_fit] - mu) / sd)
    b['day'] = b.first_look_utc.str[:10]
    top = b.sort_values('s', ascending=False).groupby('day').head(n)
    return round(100 * top.big.sum() / b.big.sum(), 1)
for y in (2025, 2026):
    res[f'{y} top10/day'] = {c: topn(y, cols) for c, cols in (('points', ['points']), ('+still', ['points', 'still']), ('+both', ['points', 'still', 'size']))}
    print(y, 'big fires in top 10 a day %', res[f'{y} top10/day'])
json.dump(res, open('results_bigfire.json', 'w'), indent=1)
