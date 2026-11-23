"""REVIEW COPY of ratapani/scoring/lag_check.py, honest arm only (seen scars from window_end + 25 d, all clear looks kept),
predicting EVERY cell-day Feb 1-Jun 20 (not only scorer-valid ones) so the review can score a live candidate pool and calibration.
Original docstring: Burn-scar model that only uses inputs available for 2017-2026, scored with the shared rule (ratapani/scoring/SCORING.md)
via the research thread's scorer, so the two threads can be compared both ways.
Inputs: static landscape, NASA POWER sanctuary weather (research thread's file), burn-history prior from training seasons,
per-cell Sentinel-2/Landsat dryness from clear looks before the issue day, and scars already seen before the issue day
(nearby and sanctuary-wide) in place of VIIRS recent fire, which has no 2025-26 data here.
Runs: (1) leave-one-season-out 2017-2024, (2) train 2017-2024, score 2025-2026.  Usage: python3 scr/score2526.py"""
import sys, json, importlib.util, numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree
import scipy.sparse as sp
RS = '/mnt/project-files/research/'; SC = '/mnt/project-files/ratapani/scoring/'
spec = importlib.util.spec_from_file_location('ps', RS + 'ratapani-ignition/scripts/pipeline_score.py'); ps = importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)
n = 3614; SEAS = list(range(2017, 2027))
G = json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']
xy = np.zeros((n, 2))
for f in G: p = f['properties']; xy[p['cell_id']] = (p['x0'] + 250, p['y0'] + 250)
tree = cKDTree(xy)
def adj(r):
    pr = tree.query_pairs(r, output_type='ndarray'); A = sp.coo_matrix((np.ones(len(pr) * 2), (np.r_[pr[:, 0], pr[:, 1]], np.r_[pr[:, 1], pr[:, 0]])), (n, n)); return A.tocsr()
A1, A2 = adj(1001), adj(2001)
lab = ps.labels(SEAS); print('labels', len(lab), 'positives', int(lab.pos.sum()), flush=True)
# ── static ──
st = pd.read_parquet(SC + 'features/static_features.parquet').merge(pd.read_parquet(SC + 'features/roads_features_v2.parquet'), on='cell_id').set_index('cell_id').sort_index()
# ── weather ──
w = pd.read_csv(RS + 'ratapani-ignition/weather_power_2017_2026.csv', parse_dates=['date']).set_index('date').sort_index()
w['p7'] = w.PRECTOTCORR.rolling(7).sum(); w['p30'] = w.PRECTOTCORR.rolling(30).sum(); w['rh3'] = w.RH2M.rolling(3).mean()
w['tmax3'] = w.T2M_MAX.rolling(3).mean(); w['tmax_anom'] = w.T2M_MAX - w.T2M_MAX.rolling(30).mean(); w['doy'] = w.index.dayofyear
wcols = ['T2M', 'T2M_MAX', 'RH2M', 'WS10M', 'ws_pm', 'p7', 'p30', 'rh3', 'tmax3', 'tmax_anom', 'doy']
# ── scars already seen (first burn per cell-season, image date we <= t-1) ──
bw = pd.read_csv(RS + 'ratapani-burn-labels/burn_windows.csv', parse_dates=['window_start', 'window_end'])
bw = bw[bw.burned == 1].sort_values(['season', 'cell_id', 'window_end']).drop_duplicates(['season', 'cell_id'])
burned = {Y: np.zeros(n, bool) for Y in SEAS}
for r in bw.itertuples(): burned[r.season][r.cell_id] = True
# ── per-cell optical dryness from clear looks before t ──
sc = pd.read_parquet(RS + 'ratapani-ignition/s2_cells.parquet'); cc = pd.read_parquet(RS + 'ratapani-burn-labels/clear_calendar.parquet')
cc['date'] = pd.to_datetime(cc['date']); cc = cc[cc.clear_frac >= 0.5][['cell_id', 'date']].drop_duplicates()
sc = sc.merge(cc, on=['cell_id', 'date'])
_bw = pd.read_csv(RS + 'ratapani-burn-labels/burn_windows.csv', parse_dates=['window_start', 'window_end']); _bw = _bw[_bw.burned == 1]
_m = _bw[['cell_id', 'window_start', 'window_end']].merge(sc[['cell_id', 'date']], on='cell_id')
_in = _m[(_m.date > _m.window_start) & (_m.date < _m.window_end)][['cell_id', 'date']].drop_duplicates()
sc_all = sc.copy(); sc = sc.merge(_in.assign(_x=1), on=['cell_id', 'date'], how='left'); sc = sc[sc._x.isna()].drop(columns='_x')   # drop looks inside a burn window (pixel-level windows can leave a clear-enough look mid-burn)
cal = pd.date_range('2016-12-01', '2026-06-30')
dyn = {}
for col in ('ndvi', 'ndmi', 'nbr'):
    d = sc_all.pivot_table(index='date', columns='cell_id', values=col).reindex(index=cal, columns=range(n)).shift(1)
    last = d.ffill(limit=60); dyn[f'{col}_last_K'] = last; dyn[f'{col}_chg30_K'] = last - last.shift(30); dyn[f'{col}_mean30_K'] = d.rolling(30, min_periods=1).mean()
    d = sc.pivot_table(index='date', columns='cell_id', values=col).reindex(index=cal, columns=range(n)).shift(1)
    last = d.ffill(limit=60); dyn[f'{col}_last'] = last; dyn[f'{col}_chg30'] = last - last.shift(30); dyn[f'{col}_mean30'] = d.rolling(30, min_periods=1).mean()
frames = []
for Y in SEAS:
    days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); T = len(days)
    g = bw[bw.season == Y]; ev = np.zeros((len(pd.date_range(f'{Y - 1}-12-01', f'{Y}-06-30')), n), np.float32)
    d0 = pd.Timestamp(f'{Y - 1}-12-01')
    f = {}
    for LAG in (25,):
        ev = np.zeros((len(pd.date_range(f'{Y - 1}-12-01', f'{Y}-06-30')) + 40, n), np.float32)
        for r in g.itertuples(): ev[(r.window_end - d0).days + LAG, r.cell_id] = 1
        cum = np.cumsum(ev, 0); off = (days[0] - d0).days
        known = cum[off - 1: off - 1 + T]; k7 = known - cum[off - 8: off - 8 + T]; sfx = f'_L{LAG}'
        f.update({'aoi_new7' + sfx: np.repeat(k7.sum(1, keepdims=True), n, 1), 'aoi_season' + sfx: np.repeat(known.sum(1, keepdims=True) / n, n, 1),
         'nb1_new7' + sfx: (A1 @ k7.T).T, 'nb2_new7' + sfx: (A2 @ k7.T).T, 'nb2_season' + sfx: (A2 @ known.T).T, 'nb1_season' + sfx: (A1 @ known.T).T})
    di = cal.get_indexer(days)
    for k, v in dyn.items(): f['s2d_' + k] = v.to_numpy(np.float32)[di]
    for k in ('ndvi_last', 'ndmi_last', 'nbr_last'):
        for K in ('', '_K'): f['s2d_' + k + K + '_spanom'] = f['s2d_' + k + K] - np.nanmedian(f['s2d_' + k + K], 1, keepdims=True)
    tt, cc_ = np.meshgrid(np.arange(T), np.arange(n), indexing='ij')
    df = pd.DataFrame({k: np.asarray(v, np.float32).reshape(-1) for k, v in f.items()}); df['season'] = Y; df['date'] = days[tt.reshape(-1)]; df['cell_id'] = cc_.reshape(-1)
    frames.append(df)
X = pd.concat(frames, ignore_index=True)
X = X.merge(lab, on=['season', 'date', 'cell_id'], how='left'); X['valid'] = X.pos.notna(); X['pos'] = X.pos.fillna(False).astype(bool)
X = X.join(st, on='cell_id'); X = X.join(w[wcols], on='date')

B = np.stack([burned[Y] for Y in SEAS]).astype(float)
def prior(train_seasons):
    k = [SEAS.index(s) for s in train_seasons]; return np.log((B[k].sum(0) + 0.5) / (len(k) + 1))
def fit_pred(tr_seasons, te_seasons, feat):
    X['prior'] = 0.0
    for Y in SEAS:
        p = prior([s for s in tr_seasons if s != Y]) if Y in tr_seasons else prior(tr_seasons)
        m = (X.season == Y).values; X.loc[m, 'prior'] = p[X.cell_id.values[m]]
    tr = X.season.isin(tr_seasons).values; te = X.season.isin(te_seasons).values
    rs = np.random.default_rng(0); keep = tr & X.valid.values & (X.pos.values | (rs.random(len(X)) < 0.25))
    wt = np.where(X.pos.values[keep], 1.0, 4.0)
    gb = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.7, n_jobs=3, verbose=-1)
    gb.fit(X.loc[keep, feat], X.pos.values[keep], sample_weight=wt)
    return gb.predict_proba(X.loc[te, feat])[:, 1], te, dict(zip(feat, gb.booster_.feature_importance('gain').round().tolist()))
allc = [c for c in X.columns if c not in ('season', 'date', 'cell_id', 'pos', 'valid')]
seen = lambda L: [c for c in allc if c.endswith(f'_L{L}')]
dryK = [c for c in allc if c.startswith('s2d_') and '_K' in c]; dryD = [c for c in allc if c.startswith('s2d_') and '_K' not in c]
other = [c for c in allc if c not in dryK + dryD and '_L' not in c]
arms = {'honest': other + dryK + seen(25) + ['prior'], 'honest_nodry': other + seen(25) + ['prior']}
print('arms', {k: len(v) for k, v in arms.items()}, flush=True)
out = {}
for arm, feat in arms.items():
    P = np.full(len(X), np.nan)
    for Y in range(2017, 2025):
        p, te, _ = fit_pred([s for s in range(2017, 2025) if s != Y], [Y], feat); P[te] = p; print(arm, 'loso', Y, flush=True)
    p, te, imp = fit_pred(list(range(2017, 2025)), [2025, 2026], feat); P[te] = p
    X[arm] = P
    pr = X[['season', 'date', 'cell_id', 'valid', 'pos', arm]]; pr.to_parquet(f'/mnt/project-files/research/prediction-review/results/pred_allcells_{arm}.parquet')
    out[arm + '_top_gain'] = dict(sorted(imp.items(), key=lambda kv: -kv[1])[:12])
json.dump(out, open('/mnt/project-files/research/prediction-review/results/check3_gain.json', 'w'), indent=1); print('CHECK3_DONE')
