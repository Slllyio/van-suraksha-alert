"""Daily 2-day model, trained by fire-timing regime (Akkshay 20 Oct: 'some divisions burn early, some late; use and train accordingly').
Lean cloud stand-in for the PC daily model (no weather: weather for 2019-24 is only on the PC). All MP beat squares (500 m), 15 Feb-15 Jun.
Target: VIIRS type-0 fire in the square on day t+1 or t+2 (field-system/pc_models/fire_celldays). Train 2019-24 (all positives + 2% others),
test 2025 and 2026 every second day, all squares.
Models: (A) one model per division; (B) one statewide model; (C) one model per regime (early/mid/late division calendar from 2017-24);
(D) statewide + timing inputs (division's usual median fire day, days since its usual start, division activity last 3 days); (E) per regime + timing inputs.
Score: each day, flag the top 10% of each division's squares; % of next-2-day fire squares inside flags (all, and 'new' = no fire within 3 km in 7 days).
Out: results/d1_*"""
import json, sys, time, numpy as np, pandas as pd, lightgbm as lgb, warnings
from scipy.ndimage import uniform_filter
warnings.filterwarnings('ignore')
R = '/mnt/project-files/research/fire-timing/results/'; NC, NR = 1829, 1332
cells = pd.read_parquet('/mnt/project-files/ratapani/mp_grid/mp_cells.parquet', columns=['cell', 'row', 'col'])
dv = pd.read_parquet('/mnt/project-files/field-system/pc_models/static_inputs.parquet', columns=['cell', 'division']).drop_duplicates('cell')
cells = cells.merge(dv, on='cell', how='inner').reset_index(drop=True); N = len(cells)
st = pd.read_parquet('/mnt/project-files/ratapani/mp_grid/static_gis_v1.parquet')
GIS = ['elev', 'slope', 'rugged', 'tpi5', 'south', 'd_edge_in', 'd_forest_out', 'road_km_5k', 'd_major', 'd_road', 'd_village', 'villages_5k', 'farm_5k', 'forest_5k', 'lc_forest']
G = cells[['cell']].merge(st[['cell'] + GIS], on='cell', how='left')[GIS].to_numpy(np.float32)
f = pd.read_parquet('/mnt/project-files/field-system/pc_models/fire_celldays.parquet'); f['cell'] = f.row * NC + f.col
ci = pd.Series(np.arange(N), index=cells.cell); f = f[f.cell.isin(ci.index)]; f['i'] = ci.reindex(f.cell).values
DIVS = sorted(cells.division.unique()); dcode = cells.division.map({d: k for k, d in enumerate(DIVS)}).to_numpy()
print('squares', N, 'divisions', len(DIVS), flush=True)
def season_days(Y): return pd.date_range(f'{Y}-02-15', f'{Y}-06-15')
# division calendar from 2017-24 fire squares in window: median day of season (d50) and 20% day (onset)
w = f[(f.date.dt.year.between(2017, 2024))].copy(); w['doy'] = (w.date - pd.to_datetime(w.date.dt.year.astype(str) + '-02-15')).dt.days
w = w[w.doy.between(0, 120)]; w['div'] = cells.division.values[w.i]
cal = w.groupby('div').doy.quantile([.2, .5]).unstack(); cal.columns = ['onset', 'd50']; cal = cal.reindex(DIVS).fillna(cal.median())
reg = pd.cut(cal.d50, [-1, 38, 52, 200], labels=['early', 'mid', 'late']).astype(str)  # half of fire squares by ~25 Mar / ~8 Apr
cal['regime'] = reg; cal.to_csv(R + 'd1_division_calendar.csv'); print(cal.regime.value_counts().to_dict(), flush=True)
ONS = cal.onset.to_numpy()[dcode].astype(np.float32); D50 = cal.d50.to_numpy()[dcode].astype(np.float32); REG = cal.regime.to_numpy()[dcode]
# climatology: fire-day rate of the square in the window over the 5 seasons before (per season, rolling)
fy = f.assign(Y=f.date.dt.year, doy=(f.date - pd.to_datetime(f.date.dt.year.astype(str) + '-02-15')).dt.days); fy = fy[fy.doy.between(0, 120)]
cnt = {Y: np.bincount(fy.i[fy.Y == Y], minlength=N).astype(np.float32) for Y in range(2014, 2027)}
FEAT = ['c1', 'c3', 'c7', 'c30', 'n3_3', 'n3_7', 'n7_7', 'n15_7', 'dsl', 'clim', 'doy'] + GIS + ['ddiv3']
TFEAT = ['d50', 'onset', 'since_onset', 'rel_d50']
def season_features(Y, step=1, keep=None):
    days = season_days(Y); start = days[0] - pd.Timedelta(days=400)
    ff = f[(f.date >= start) & (f.date <= days[-1] + pd.Timedelta(days=2))]
    idx = {d: g.i.to_numpy() for d, g in ff.groupby('date')}
    last = np.full(N, -999, np.int32); hist = []  # rolling daily fire vectors
    clim = sum(cnt[y] for y in range(Y - 5, Y)) / 5 / 121
    rows_r, rows_c = cells.row.to_numpy(), cells.col.to_numpy()
    out = []
    for k, d in enumerate(pd.date_range(start, days[-1])):
        v = np.zeros(N, np.uint8); v[idx.get(d, [])] = 1
        last[v == 1] = k; hist.append(v)
        if len(hist) > 30: hist.pop(0)
        if d < days[0] or (d - days[0]).days % step: continue
        H = np.array(hist[::-1])  # 0 = today
        c1, c3, c7, c30 = H[0], H[:3].sum(0), H[:7].sum(0), H.sum(0)
        def nb(sz, nd):
            g = np.zeros((NR, NC), np.float32); np.add.at(g, (rows_r, rows_c), H[:nd].max(0).astype(np.float32))
            return (uniform_filter(g, sz, mode='constant') * sz * sz)[rows_r, rows_c]
        y = np.zeros(N, np.uint8)
        for j in (1, 2): y[idx.get(d + pd.Timedelta(days=j), [])] = 1
        doy = (d - days[0]).days
        ddiv = np.bincount(dcode, weights=H[:3].max(0), minlength=len(DIVS))[dcode].astype(np.float32)
        X = np.column_stack([c1, c3, c7, c30, nb(3, 3), nb(3, 7), nb(7, 7), nb(15, 7), np.minimum(k - last, 400), clim, np.full(N, doy), G, ddiv,
                             D50, ONS, doy - ONS, doy - D50]).astype(np.float32)
        n7 = X[:, FEAT.index('n7_7')]
        sel = np.arange(N) if keep is None else keep(y)
        out.append((d, sel, X[sel], y[sel], (n7[sel] == 0)))
    return out
COLS = FEAT + TFEAT
t0 = time.time(); rng = np.random.default_rng(0); TR = []
for Y in range(2019, 2025):
    for d, sel, X, y, new in season_features(Y, step=1, keep=lambda y: np.where((y == 1) | (rng.random(len(y)) < 0.02))[0]):
        TR.append(pd.DataFrame(X, columns=COLS).assign(y=y, dc=dcode[sel], w=np.where(y == 1, 1.0, 50.0)))
    print('train season', Y, round(time.time() - t0), flush=True)
TR = pd.concat(TR, ignore_index=True); TR['reg'] = cal.regime.to_numpy()[TR.dc]
print('train rows', len(TR), 'pos', int(TR.y.sum()), flush=True)
prm = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=200, subsample=0.8, subsample_freq=1, colsample_bytree=0.7, n_jobs=3, verbose=-1)
fit = lambda d, cols: lgb.LGBMClassifier(**prm).fit(d[cols], d.y, sample_weight=d.w)
M = {}
M['B statewide'] = fit(TR, FEAT); M['D statewide + timing'] = fit(TR, COLS)
for g in ('early', 'mid', 'late'):
    M[f'C regime {g}'] = fit(TR[TR.reg == g], FEAT); M[f'E regime+timing {g}'] = fit(TR[TR.reg == g], COLS)
small = dict(prm, n_estimators=200, num_leaves=31, min_child_samples=50)
for k in range(len(DIVS)):
    s = TR[TR.dc == k]
    if s.y.sum() >= 20: M[f'A {k}'] = lgb.LGBMClassifier(**small).fit(s[FEAT], s.y, sample_weight=s.w)
print('models fitted', len(M), round(time.time() - t0), flush=True); del TR
NAMES = ['A per division', 'B statewide', 'C per regime', 'D statewide + timing', 'E per regime + timing']
res = []
for Y in (2025, 2026):
    for d, sel, X, y, new in season_features(Y, step=2):
        if y.sum() == 0: continue
        Xd = pd.DataFrame(X, columns=COLS); S = {}
        S['B statewide'] = M['B statewide'].predict_proba(Xd[FEAT])[:, 1]; S['D statewide + timing'] = M['D statewide + timing'].predict_proba(Xd[COLS])[:, 1]
        S['C per regime'] = np.zeros(N); S['E per regime + timing'] = np.zeros(N); S['A per division'] = S['B statewide'].copy()
        for g in ('early', 'mid', 'late'):
            m = REG == g; S['C per regime'][m] = M[f'C regime {g}'].predict_proba(Xd[FEAT][m])[:, 1]; S['E per regime + timing'][m] = M[f'E regime+timing {g}'].predict_proba(Xd[COLS][m])[:, 1]
        for k in range(len(DIVS)):
            m = dcode == k
            if f'A {k}' in M and m.any(): S['A per division'][m] = M[f'A {k}'].predict_proba(Xd[FEAT][m])[:, 1]
        df = pd.DataFrame({'dc': dcode, 'y': y, 'new': new})
        for n in NAMES:
            df['s'] = S[n]; df['flag'] = df.groupby('dc').s.rank(ascending=False, method='first') <= np.ceil(0.1 * df.groupby('dc').s.transform('size'))
            g = df[df.y == 1].groupby('dc').agg(pos=('y', 'size'), hit=('flag', 'sum'))
            gn = df[(df.y == 1) & df.new].groupby('dc').agg(npos=('y', 'size'), nhit=('flag', 'sum'))
            res.append(g.join(gn, how='left').fillna(0).assign(model=n, season=Y, date=d).reset_index())
    print('test season', Y, round(time.time() - t0), flush=True)
Rr = pd.concat(res); Rr['division'] = np.array(DIVS)[Rr.dc]; Rr['regime'] = cal.regime.reindex(Rr.division).values
Rr['month'] = pd.to_datetime(Rr.date).dt.month; Rr.to_parquet(R + 'd1_daily_hits.parquet')
def rate(g): return pd.Series({'caught': round(g.hit.sum() / g.pos.sum() * 100, 1), 'new_caught': round(g.nhit.sum() / max(g.npos.sum(), 1) * 100, 1)})
out = {'regimes': cal.regime.value_counts().to_dict(), 'regime_members': {g: list(cal.index[cal.regime == g]) for g in ('early', 'late')},
       'overall': Rr.groupby('model').apply(rate).to_dict('index'),
       'by_season': Rr.groupby(['model', 'season']).apply(rate).caught.unstack().to_dict('index'),
       'by_regime': Rr.groupby(['model', 'regime']).apply(rate).caught.unstack().to_dict('index'),
       'by_month': Rr.groupby(['model', 'month']).apply(rate).caught.unstack().to_dict('index')}
dvr = Rr.groupby(['model', 'division']).apply(lambda g: g.hit.sum() / g.pos.sum()).unstack(0)
for a in NAMES[2:] + ['B statewide']:
    if a == 'A per division': continue
    g = (dvr[a] - dvr['A per division']).dropna(); out[f'{a} vs per division, divisions better'] = [int((g > 0.005).sum()), int((g < -0.005).sum()), len(g)]
dvr.round(4).to_csv(R + 'd1_by_division.csv')
json.dump(out, open(R + 'd1_summary.json', 'w'), indent=1, default=str); print(json.dumps(out, indent=1, default=str))
