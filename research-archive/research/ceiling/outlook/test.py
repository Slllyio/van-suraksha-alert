"""Leave-one-season-out test of season outlooks per division. Target: log(season detections + 10), 15 Feb-31 May, S-NPP.
Inputs known by 1 Feb (rain/heat/soil to Jan, last season) and by 15 Feb (+ fires 1 Jan-14 Feb)."""
import numpy as np, pandas as pd, geopandas as gpd
P = '/mnt/project-files/'; O = P + 'research/ceiling/outlook/'
S = pd.read_csv(O + 'div_season.csv'); W = pd.read_csv(O + 'power_monthly.csv')
# early fires 1 Jan - 14 Feb
D = gpd.read_file(P + 'fire-alert-scars/mp/out/mp_divisions.geojson').rename(columns={'Division': 'division'}).dissolve('division').reset_index()
E = []
for y in range(2014, 2027):
    a = pd.read_csv(P + f'fire-alert-scars/alerts_mp/viirs-snpp_{y}.csv', usecols=['latitude', 'longitude', 'acq_date', 'type']); a = a[a.type == 0]
    d = pd.to_datetime(a.acq_date); a = a[(d.dt.month == 1) | ((d.dt.month == 2) & (d.dt.day <= 14))]
    j = gpd.sjoin(gpd.GeoDataFrame(a, geometry=gpd.points_from_xy(a.longitude, a.latitude), crs=4326), D, predicate='within')
    E += [{'division': k, 'year': y, 'early': v} for k, v in j.groupby('division').size().items()]
S = S.merge(pd.DataFrame(E), on=['division', 'year'], how='left').fillna({'early': 0})
S['ly'] = np.log(S.n + 10); S['le'] = np.log(S.early + 3)
def agg(var, months, shift):   # months of year (Y + shift)
    w = W[(W['var'] == var) & W.month.isin(months)].groupby(['division', 'year']).v.mean().reset_index()
    w['year'] = w.year - shift; return w.rename(columns={'v': f'{var}_{months[0]}_{months[-1]}_{shift}'})
F = [agg('PRECTOTCORR', [6, 7, 8, 9], -1), agg('PRECTOTCORR', [10, 11, 12], -1), agg('PRECTOTCORR', [1], 0), agg('T2M_MAX', [1], 0), agg('GWETROOT', [1], 0),
     agg('PRECTOTCORR', [6, 7, 8, 9], -2)]
for f in F: S = S.merge(f, on=['division', 'year'], how='left')
# fix shift sign: agg with shift=-1 means weather year = Y-1 mapped to Y
S = S.sort_values(['division', 'year']); S['ly_last'] = S.groupby('division').ly.shift(1)
wcols = [c for c in S.columns if c.startswith(('PRECT', 'T2M', 'GWET'))]
S = S[S.year >= 2015].dropna(subset=['ly_last'] + wcols).copy()
years = sorted(S.year.unique()); print('years', years, 'rows', len(S))
def zs(df, cols, tr):  # per-division z vs training years
    out = df.copy()
    for c in cols:
        m = tr.groupby('division')[c].mean(); s = tr.groupby('division')[c].std().replace(0, 1)
        out[c + '_z'] = (df[c] - df.division.map(m)) / df.division.map(s)
    return out
SETS = {'normal (division average)': [], '+ last season': ['ly_last'], '+ weather to Jan': wcols, '+ last season + weather': ['ly_last'] + wcols,
        '+ fires 1 Jan-14 Feb': ['le'], '+ all': ['ly_last', 'le'] + wcols}
R = []
for nm, cols in SETS.items():
    pred = []
    for y in years:
        tr, te = S[S.year != y], S[S.year == y]
        base_tr = tr.division.map(tr.groupby('division').ly.mean()); base_te = te.division.map(tr.groupby('division').ly.mean())
        if cols:
            trz, tez = zs(tr, cols, tr), zs(te, cols, tr); Z = [c + '_z' for c in cols]
            X = trz[Z].values; yv = (tr.ly - base_tr).values
            lam = 5.0; b = np.linalg.solve(X.T @ X + lam * np.eye(len(Z)), X.T @ yv)
            p = base_te.values + tez[Z].values @ b
        else: p = base_te.values
        pred.append(pd.DataFrame({'division': te.division, 'year': y, 'pred': p, 'ly': te.ly.values, 'n': te.n.values, 'base': base_te.values}))
    Q = pd.concat(pred)
    an, pa = Q.ly - Q.base, Q.pred - Q.base
    r_div = np.corrcoef(an, pa)[0, 1] if cols else np.nan
    # statewide total by year
    st = Q.groupby('year').apply(lambda g: pd.Series({'act': g.n.sum(), 'pr': (np.exp(g.pred) - 10).clip(0).sum()}))
    r_state = np.corrcoef(np.log(st.act), np.log(st.pr))[0, 1]
    # within-year division ranking: share of the season's fires in the top 20 divisions picked
    cap = Q.groupby('year').apply(lambda g: g.nlargest(20, 'pred').n.sum() / g.n.sum()).mean()
    best = Q.groupby('year').apply(lambda g: g.nlargest(20, 'n').n.sum() / g.n.sum()).mean()
    # mean abs error in log (factor)
    fac = np.exp(np.abs(Q.ly - Q.pred).median())
    R.append({'inputs': nm, 'division anomaly r': round(r_div, 2), 'statewide year r': round(r_state, 2), 'top-20 divisions hold % of fires': round(100 * cap, 1), 'perfect top-20': round(100 * best, 1), 'median error factor': round(fac, 2)})
R = pd.DataFrame(R); print(R.to_string(index=False)); R.to_csv(O + 'outlook_results.csv', index=False)
# simple correlations of statewide anomaly with each input
yr = S.groupby('year').agg(ly=('n', lambda x: np.log(x.sum())), **{c: (c, 'mean') for c in wcols + ['early']})
print(yr.round(2).to_string()); print(yr.corr()['ly'].round(2).to_string())
