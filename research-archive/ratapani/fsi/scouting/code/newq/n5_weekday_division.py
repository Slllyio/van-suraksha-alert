"""New question 5. The statewide calendar check (mp_calendar_effects.md) found no weekday effect and Holi eve 1.38x. Market
(haat) days differ from place to place, so a weekday effect could exist per division and cancel statewide. Here: scar-fire start
dates 2017-25 (j2_fires, IST), per division: observed starts per weekday against the expected from a centred 15-day running mean
of the division's own daily series (seasonal shape removed), ratio per weekday, the largest weekday's ratio against 2,000
permutations of weekday labels within each week, Holm across divisions. Out: out/n5_weekday.csv, out/n5_weekday_division.csv"""
import os, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = HERE + '/out/'
F = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/code/joint_plan/out/j2_fires.csv', usecols=['key', 'division', 'year', 't0', 'ha'])
F['d'] = pd.to_datetime(F.t0); F = F[(F.d.dt.month >= 1) & (F.d.dt.month <= 6)]
rng = np.random.default_rng(1)
def table(g):
    """daily series over each season Jan-Jun with expected = centred 15-day mean excluding the day"""
    out = []
    for y, gy in g.groupby('year'):
        idx = pd.date_range(f'{y}-01-01', f'{y}-06-30'); c = gy.groupby('d').size().reindex(idx, fill_value=0).astype(float)
        e = (c.rolling(15, center=True, min_periods=8).sum() - c) / (c.rolling(15, center=True, min_periods=8).count() - 1)
        out.append(pd.DataFrame({'obs': c, 'exp': e, 'wd': idx.dayofweek, 'week': idx.isocalendar().week.values + 100 * y}))
    return pd.concat(out).dropna()
def ratios(wd, obs, exp): return np.bincount(wd, weights=obs, minlength=7) / np.bincount(wd, weights=exp, minlength=7)
def test(T, nperm=2000):
    wd, obs, exp, wk = T.wd.values.astype(int), T.obs.values, T.exp.values, T.week.values
    r = ratios(wd, obs, exp); mx = np.nanmax(r); n = len(wd); pos = np.lexsort((np.arange(n), wk)); null = np.empty(nperm)
    for k in range(nperm):
        perm = np.lexsort((rng.random(n), wk)); w2 = np.empty(n, int); w2[pos] = wd[perm]      # shuffle weekday labels within each week
        null[k] = np.nanmax(ratios(w2, obs, exp))
    return r, mx, (null >= mx).mean()
WD = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
T = table(F); r, mx, p = test(T); print('all MP weekday ratios', dict(zip(WD, r.round(3))), 'max', round(mx, 3), 'perm p', p)
pd.DataFrame({'weekday': WD, 'ratio': r, 'fires': T.groupby('wd').obs.sum().values}).to_csv(OUT + 'n5_weekday.csv', index=False)
rows = []
for key, g in F.groupby('key'):
    if len(g) < 300: continue
    Tg = table(g); r, mx, p = test(Tg, 1000)
    rows.append(dict(key=key, division=g.division.iloc[0], fires=len(g), **{f'r_{w}': v for w, v in zip(WD, r)}, peak_day=WD[int(np.nanargmax(r))], peak_ratio=mx, perm_p=p))
D = pd.DataFrame(rows).sort_values('perm_p'); m = len(D); D['holm_p'] = np.minimum(1, np.maximum.accumulate((D.perm_p.values * (m - np.arange(m)))))
D.to_csv(OUT + 'n5_weekday_division.csv', index=False)
print(D[['division', 'fires', 'peak_day', 'peak_ratio', 'perm_p', 'holm_p']].head(12).round(3).to_string(index=False))
print('divisions tested', m, 'perm p<0.05:', int((D.perm_p < 0.05).sum()), 'expected by chance', round(0.05 * m, 1), 'Holm<0.05:', int((D.holm_p < 0.05).sum()))
print('peak day counts', D.peak_day.value_counts().to_dict())
