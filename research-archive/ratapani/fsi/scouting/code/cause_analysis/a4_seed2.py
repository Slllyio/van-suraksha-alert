"""Burn-scar model that only uses inputs available for 2017-2026, scored with the shared rule (ratapani/scoring/SCORING.md)
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
EE = '/mnt/project-files/ratapani/ee/'
st = pd.read_csv(EE + 'terrain.csv')
for f_ in ('population.csv', 'proximity.csv', 'worldcover.csv'): st = st.merge(pd.read_csv(EE + f_), on='cell_id')
st = st.merge(pd.read_csv(RS + 'ratapani-ignition/cells_static.csv').drop(columns=['beat']), on='cell_id').set_index('cell_id').sort_index()
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
sc = sc.merge(_in.assign(_x=1), on=['cell_id', 'date'], how='left'); sc = sc[sc._x.isna()].drop(columns='_x')   # drop looks inside a burn window (pixel-level windows can leave a clear-enough look mid-burn)
cal = pd.date_range('2016-12-01', '2026-06-30')
dyn = {}
for col in ('ndvi', 'ndmi', 'nbr'):
    d = sc.pivot_table(index='date', columns='cell_id', values=col).reindex(index=cal, columns=range(n)).shift(1)
    last = d.ffill(limit=60); dyn[f'{col}_last'] = last; dyn[f'{col}_chg30'] = last - last.shift(30); dyn[f'{col}_mean30'] = d.rolling(30, min_periods=1).mean()
frames = []
for Y in SEAS:
    days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); T = len(days)
    g = bw[bw.season == Y]; ev = np.zeros((len(pd.date_range(f'{Y - 1}-12-01', f'{Y}-06-30')), n), np.float32)
    d0 = pd.Timestamp(f'{Y - 1}-12-01')
    for r in g.itertuples(): ev[(r.window_end - d0).days, r.cell_id] = 1
    cum = np.cumsum(ev, 0); off = (days[0] - d0).days
    known = cum[off - 1: off - 1 + T]                            # seen by t-1
    k7 = known - cum[off - 8: off - 8 + T]                        # seen in [t-7, t-1]
    f = {'aoi_new7': np.repeat(k7.sum(1, keepdims=True), n, 1), 'aoi_season': np.repeat(known.sum(1, keepdims=True) / n, n, 1),
         'nb1_new7': (A1 @ k7.T).T, 'nb2_new7': (A2 @ k7.T).T, 'nb2_season': (A2 @ known.T).T, 'nb1_season': (A1 @ known.T).T}
    di = cal.get_indexer(days)
    for k, v in dyn.items(): f['s2d_' + k] = v.to_numpy(np.float32)[di]
    for k in ('ndvi_last', 'ndmi_last', 'nbr_last'): f['s2d_' + k + '_spanom'] = f['s2d_' + k] - np.nanmedian(f['s2d_' + k], 1, keepdims=True)
    tt, cc_ = np.meshgrid(np.arange(T), np.arange(n), indexing='ij')
    df = pd.DataFrame({k: np.asarray(v, np.float32).reshape(-1) for k, v in f.items()}); df['season'] = Y; df['date'] = days[tt.reshape(-1)]; df['cell_id'] = cc_.reshape(-1)
    frames.append(df)
X = pd.concat(frames, ignore_index=True)
X = lab.merge(X, on=['season', 'date', 'cell_id'], how='left')
X = X.join(st, on='cell_id'); X = X.join(w[wcols], on='date')
feat = [c for c in X.columns if c not in ('season', 'date', 'cell_id', 'pos')] + ['prior']
print('rows', len(X), 'features', len(feat), flush=True)
B = np.stack([burned[Y] for Y in SEAS]).astype(float)
def prior(train_seasons):
    k = [SEAS.index(s) for s in train_seasons]; return np.log((B[k].sum(0) + 0.5) / (len(k) + 1))
def fit_pred(tr_seasons, te_seasons):
    X['prior'] = 0.0
    for Y in SEAS:   # each training season sees a prior built without itself; test seasons see the prior from all training seasons
        p = prior([s for s in tr_seasons if s != Y]) if Y in tr_seasons else prior(tr_seasons)
        m = (X.season == Y).values; X.loc[m, 'prior'] = p[X.cell_id.values[m]]
    tr = X.season.isin(tr_seasons).values; te = X.season.isin(te_seasons).values
    rs = np.random.default_rng(0); keep = tr & (X.pos.values | (rs.random(len(X)) < 0.25))
    wt = np.where(X.pos.values[keep], 1.0, 4.0)
    gb = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.7, n_jobs=4, verbose=-1)
    gb.fit(X.loc[keep, feat], X.pos.values[keep], sample_weight=wt)
    return gb.predict_proba(X.loc[te, feat])[:, 1], te, dict(zip(feat, gb.booster_.feature_importance('gain').round().tolist()))

OUT = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/cause_an/'
A = pd.read_parquet(OUT + 'pos_attrs.parquet')
A['mgd'] = A.managed_proxy | A.linear
X = X.merge(A[['season', 'cell_id', 'mgd', 'cropedge', 'night', 'we']], on=['season', 'cell_id'], how='left')
X['mgd'] = X.mgd.fillna(False).astype(bool); X['cropedge_c'] = X.cell_id.map(A.drop_duplicates('cell_id').set_index('cell_id').cropedge) if False else 0
px = pd.read_csv('/mnt/project-files/ratapani/ee/proximity.csv').set_index('cell_id'); wc = pd.read_csv('/mnt/project-files/ratapani/ee/worldcover.csv').set_index('cell_id')
ce = ((wc.wc_40 >= 0.2) | (px.dist_crop_cell <= 500)).reindex(range(n)).fillna(False).values
X['ce'] = ce[X.cell_id.values]
# per-cell timing / type priors from other seasons
fbA = A.set_index(['season', 'cell_id'])
doyA = (A.we - pd.to_datetime(A.season.astype(str) + '-01-01')).dt.days
A['doy'] = doyA; A['early'] = A.we <= pd.to_datetime(A.season.astype(str) + '-02-28')
pb = pd.read_csv(SC + 'pseudo_beats_pipeline.csv').set_index('cell_id').pseudo_beat
def tprior(seasons):
    a = A[A.season.isin(seasons)].groupby('cell_id')
    med = a.doy.median().reindex(range(n)); er = a.early.mean().reindex(range(n)); ni = a.night.mean().reindex(range(n))
    return med.values, er.values, ni.values
def set_t(tr_seasons):
    for nm in ('tp_doy', 'tp_early', 'tp_night'): X[nm] = np.nan
    for Y in SEAS:
        ss = [s for s in tr_seasons if s != Y] if Y in tr_seasons else tr_seasons
        md, er, ni = tprior(ss); msk = (X.season == Y).values; c = X.cell_id.values[msk]
        X.loc[msk, 'tp_doy'] = md[c]; X.loc[msk, 'tp_early'] = er[c]; X.loc[msk, 'tp_night'] = ni[c]
    X['tp_gap'] = X.doy - X.tp_doy
def fit(tr_seasons, te_mask, feats, train_extra=None):
    X['prior'] = 0.0
    for Y in SEAS:
        p = prior([s for s in tr_seasons if s != Y]) if Y in tr_seasons else prior(tr_seasons)
        m = (X.season == Y).values; X.loc[m, 'prior'] = p[X.cell_id.values[m]]
    tr = X.season.isin(tr_seasons).values
    if train_extra is not None: tr = tr & train_extra
    rs = np.random.default_rng(11); keep = tr & (X.pos.values | (rs.random(len(X)) < 0.25))
    wt = np.where(X.pos.values[keep], 1.0, 4.0)
    gb = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.7, n_jobs=4, verbose=-1, random_state=7)
    gb.fit(X.loc[keep, feats], X.pos.values[keep], sample_weight=wt)
    return gb.predict_proba(X.loc[te_mask, feats])[:, 1]
X['pb'] = X.cell_id.map(pb).values
def rec(col, mask=None):
    r = X[col].fillna(-np.inf).groupby([X.season, X.date, X.pb]).rank('first', ascending=False)
    hit = X.pos.values & (r.values <= 5) & (X.season.values <= 2024); pos = X.pos.values & (X.season.values <= 2024)
    if mask is not None: hit = hit & mask; pos = pos & mask
    return round(float(hit.sum() / pos.sum()), 4)
base_feat = feat; tfeat = feat + ['tp_doy', 'tp_early', 'tp_night', 'tp_gap']
res = {}
L = list(range(2017, 2025))
for name in ['base']:
    X[name] = np.nan
    for Y in L:
        trs = [s for s in L if s != Y]; te = (X.season == Y).values
        if name.startswith('timing'): set_t(trs)
        fe = tfeat if name.startswith('timing') else base_feat
        extra = ~(X.pos.values & X.mgd.values) if 'drop_mgd' in name else None
        if name == 'split_ce':
            p = np.full(len(X), np.nan)
            for g in (True, False):
                gm = X.ce.values == g
                p[te & gm] = fit(trs, te & gm, fe, train_extra=gm)
            X.loc[te, name] = p[te]
        else:
            X.loc[te, name] = fit(trs, te, fe, train_extra=extra)
    res[name] = dict(all=rec(name), non_mgd=rec(name, ~X.mgd.values), mgd=rec(name, X.mgd.values), ce=rec(name, X.ce.values), interior=rec(name, ~X.ce.values),
                     per_season={int(y): rec(name, (X.season == y).values) for y in L})
    print(name, json.dumps(res[name]), flush=True)
json.dump(res, open(OUT + 'exp_results_seed2.json', 'w'), indent=1); X.loc[X.season <= 2024, ['season', 'date', 'cell_id', 'pos', 'mgd', 'ce', 'base']].rename(columns={'base': 'base_seed2'}).to_parquet(OUT + 'exp_preds_seed2.parquet'); print('DONE')
