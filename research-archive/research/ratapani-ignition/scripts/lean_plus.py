"""Rebuild of the pipeline thread's lean burn-scar model (ratapani/scoring/pipeline_lean_model.py) with the statics
available to this thread, then additions from the scouting note, scored with SCORING.md on the 94 real beats:
  base      : statics + POWER weather + burn prior + S2 dryness before t + scars already seen (nearby/sanctuary)
  +hawkes   : self-exciting features: known scars decayed over time (tau 2/7/21 d) and distance (sigma 1/3/8 km),
              for all scars and for new-ignition scars; ring counts of scars seen in the last 3/7/14 d within 1/3/8 km
  +dry      : dryness slopes (30/60 d), days since NDVI < 0.35, 3x3 / 5x5 neighbour mean-min-max of NDVI and NBR,
              dryness rank within the real beat
  lambdarank: LGBMRanker, query = (real beat, issue day), on beat-days with >= 1 positive; also rank-averaged with the classifier
Usage: python3 lean_plus.py <out_dir> [configs comma-separated]
"""
import os, sys, json, numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree
import scipy.sparse as sp
sys.path.insert(0, os.path.dirname(__file__)); import pipeline_score as ps
RS = '/mnt/project-files/research/'; RP = '/mnt/project-files/ratapani/'
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
CONFIGS = sys.argv[2].split(',') if len(sys.argv) > 2 else ['base', 'hawkes', 'dry', 'hawkes+dry', 'rank:base', 'rank:hawkes+dry']
n = 3614; SEAS = list(range(2017, 2027))
G = json.load(open(RP + 'grid_500m.geojson'))['features']
xy = np.zeros((n, 2))
for f in G: p = f['properties']; xy[p['cell_id']] = (p['x0'] + 250, p['y0'] + 250)
tree = cKDTree(xy)
def adj(r):
    pr = tree.query_pairs(r, output_type='ndarray'); A = sp.coo_matrix((np.ones(len(pr) * 2), (np.r_[pr[:, 0], pr[:, 1]], np.r_[pr[:, 1], pr[:, 0]])), (n, n)); return A.tocsr()
A1, A2 = adj(1001), adj(2001)
real = pd.read_csv(RP + 'beats/cell_beat.csv').set_index('cell_id').beat_uid.reindex(range(n))
beat_code = pd.factorize(real)[0]
lab = ps.labels(SEAS); print('labels', len(lab), 'positives', int(lab.pos.sum()), flush=True)
# ---- statics ----
st = pd.read_csv(RS + 'ratapani-ignition/cells_static.csv').set_index('cell_id')[['elig_ha', 'tree', 'shrub', 'grass', 'crop', 'northness', 'eastness', 'd_built', 'd_crop', 'd_edge', 'd_aoi']]
for f, cols in [('terrain', None), ('proximity', None), ('worldcover', None), ('population', None)]:
    t = pd.read_csv(RP + f'ee/{f}.csv').set_index('cell_id'); st = st.join(t, rsuffix='_' + f)
st = st.reindex(range(n))
# roads v2 (pipeline thread, Microsoft Road Detections + OSM) replaces ee/proximity dist_road and dist_track
_rv = pd.read_parquet(RP + 'scoring/features/roads_features_v2.parquet').set_index('cell_id')
st = st.drop(columns=[c for c in ('dist_road', 'dist_track') if c in st.columns]).join(_rv[['dist_road_km', 'dist_major_road_km', 'road_km_in_cell']])
# ---- weather ----
w = pd.read_csv(RS + 'ratapani-ignition/weather_power_2017_2026.csv', parse_dates=['date']).set_index('date').sort_index()
w['p7'] = w.PRECTOTCORR.rolling(7).sum(); w['p30'] = w.PRECTOTCORR.rolling(30).sum(); w['rh3'] = w.RH2M.rolling(3).mean()
w['tmax3'] = w.T2M_MAX.rolling(3).mean(); w['tmax_anom'] = w.T2M_MAX - w.T2M_MAX.rolling(30).mean(); w['doy'] = w.index.dayofyear
wcols = ['T2M', 'T2M_MAX', 'RH2M', 'WS10M', 'ws_pm', 'p7', 'p30', 'rh3', 'tmax3', 'tmax_anom', 'doy']
# ---- scars seen ----
bw = pd.read_csv(RS + 'ratapani-burn-labels/burn_windows.csv', parse_dates=['window_start', 'window_end'])
bw = bw[bw.burned == 1].sort_values(['season', 'cell_id', 'window_end']).drop_duplicates(['season', 'cell_id'])
burned = {Y: np.zeros(n, bool) for Y in SEAS}
for r in bw.itertuples(): burned[r.season][r.cell_id] = True
# new-ignition scars (patch main cells) from the ignition study
pc = pd.read_csv('/tmp/claude-0/ign/data/patch_cells.csv').rename(columns=lambda c: 'new' if c.startswith('new_') else c)
pat = pd.read_csv(RS + 'ratapani-ignition/patches.csv', parse_dates=['window_end'])
newp = pc[pc.new == 1][['season', 'patch', 'cell_id']].merge(pat[['season', 'patch', 'window_end']], on=['season', 'patch'])
# ---- optical dryness before t ----
sc = pd.read_parquet(RS + 'ratapani-ignition/s2_cells.parquet'); cc = pd.read_parquet(RS + 'ratapani-burn-labels/clear_calendar.parquet')
cc['date'] = pd.to_datetime(cc['date']); cc = cc[cc.clear_frac >= 0.5][['cell_id', 'date']].drop_duplicates()
sc['date'] = pd.to_datetime(sc.date); sc = sc.merge(cc, on=['cell_id', 'date'])
_bw = pd.read_csv(RS + 'ratapani-burn-labels/burn_windows.csv', parse_dates=['window_start', 'window_end']); _bw = _bw[_bw.burned == 1]
_m = _bw[['cell_id', 'window_start', 'window_end']].merge(sc[['cell_id', 'date']], on='cell_id')
_in = _m[(_m.date > _m.window_start) & (_m.date < _m.window_end)][['cell_id', 'date']].drop_duplicates()
sc = sc.merge(_in.assign(_x=1), on=['cell_id', 'date'], how='left'); sc = sc[sc._x.isna()].drop(columns='_x')
cal = pd.date_range('2016-12-01', '2026-06-30')
dyn = {}
for col in ('ndvi', 'ndmi', 'nbr'):
    d = sc.pivot_table(index='date', columns='cell_id', values=col).reindex(index=cal, columns=range(n)).shift(1)
    last = d.ffill(limit=60); dyn[f'{col}_last'] = last; dyn[f'{col}_chg30'] = last - last.shift(30); dyn[f'{col}_mean30'] = d.rolling(30, min_periods=1).mean()
    if col in ('ndvi', 'nbr'):
        dyn[f'{col}_chg60'] = last - last.shift(60)
nd = dyn['ndvi_last']
below = (nd < 0.35).astype(float); below[nd.isna()] = np.nan
# days since NDVI last fell below 0.35: running count of consecutive "below" days (nan treated as carry)
dsb = np.full(nd.shape, np.nan, np.float32); run = np.full(n, np.nan)
bv = below.to_numpy()
for i in range(len(cal)):
    b = bv[i]; run = np.where(np.isnan(b), run, np.where(b == 1, np.nan_to_num(run, nan=0) + 1, 0)); dsb[i] = run
dyn['ndvi_days_dry'] = pd.DataFrame(dsb, index=cal, columns=range(n))
# ---- Hawkes kernels ----
D = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(-1))
K = {s: np.exp(-0.5 * (D / (s * 1000.0)) ** 2).astype(np.float32) for s in (1, 3, 8)}
R = {s: (D <= s * 1000.0).astype(np.float32) for s in (1, 3, 8)}
frames = []
for Y in SEAS:
    days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); T = len(days)
    full = pd.date_range(f'{Y - 1}-12-01', f'{Y}-06-30'); d0 = full[0]
    ev = np.zeros((len(full), n), np.float32); evn = np.zeros((len(full), n), np.float32)
    for r in bw[bw.season == Y].itertuples(): ev[(r.window_end - d0).days, r.cell_id] = 1
    for r in newp[newp.season == Y].itertuples(): evn[(r.window_end - d0).days, r.cell_id] = 1
    cum = np.cumsum(ev, 0); off = (days[0] - d0).days
    known = cum[off - 1: off - 1 + T]; k7 = known - cum[off - 8: off - 8 + T]
    f = {'aoi_new7': np.repeat(k7.sum(1, keepdims=True), n, 1), 'aoi_season': np.repeat(known.sum(1, keepdims=True) / n, n, 1),
         'nb1_new7': (A1 @ k7.T).T, 'nb2_new7': (A2 @ k7.T).T, 'nb2_season': (A2 @ known.T).T, 'nb1_season': (A1 @ known.T).T}
    # hawkes: H_t = exp(-1/tau) H_{t-1} + K @ ev[t-1]   (events seen on images up to t-1)
    for tag, E in (('all', ev), ('new', evn)):
        for tau in (2, 7, 21):
            dec = np.exp(-1.0 / tau)
            for s in (1, 3, 8):
                H = np.zeros((len(full), n), np.float32); h = np.zeros(n, np.float32)
                for i in range(1, len(full)):
                    h = dec * h + K[s] @ E[i - 1]; H[i] = h
                f[f'hx_{tag}_t{tau}_s{s}'] = H[off: off + T]
    for L in (3, 7, 14):
        kL = known - cum[off - 1 - L: off - 1 - L + T]
        for s in (1, 3, 8):
            f[f'ring_{L}d_{s}km'] = (R[s] @ kL.T).T
    di = cal.get_indexer(days)
    for k, v in dyn.items(): f['s2d_' + k] = v.to_numpy(np.float32)[di]
    for k in ('ndvi_last', 'ndmi_last', 'nbr_last'): f['s2d_' + k + '_spanom'] = f['s2d_' + k] - np.nanmedian(f['s2d_' + k], 1, keepdims=True)
    # neighbour stats of dryness (3x3 ~ 1 km ring, 5x5 ~ 2 km ring)
    for k in ('ndvi_last', 'nbr_last'):
        v = f['s2d_' + k]; vz = np.nan_to_num(v, nan=0.0); ok = (~np.isnan(v)).astype(np.float32)
        for tag, A in (('n1', A1), ('n2', A2)):
            cnt = (A @ ok.T).T; f[f'nb_{tag}_{k}_mean'] = np.where(cnt > 0, (A @ vz.T).T / np.maximum(cnt, 1), np.nan)
        # beat rank (fraction of cells in the beat drier than this one)
        dfk = pd.DataFrame(v); rk = dfk.T.groupby(beat_code).rank(pct=True).T.to_numpy(np.float32); f[f'beat_rank_{k}'] = rk
    tt, cc_ = np.meshgrid(np.arange(T), np.arange(n), indexing='ij')
    df = pd.DataFrame({k: np.asarray(v, np.float32).reshape(-1) for k, v in f.items()}); df['season'] = Y; df['date'] = days[tt.reshape(-1)]; df['cell_id'] = cc_.reshape(-1)
    frames.append(df); print('built', Y, flush=True)
X = pd.concat(frames, ignore_index=True); del frames
X = lab.merge(X, on=['season', 'date', 'cell_id'], how='left')
X = X.join(st, on='cell_id'); X = X.join(w[wcols], on='date'); X['beat'] = beat_code[X.cell_id.values]
HAWKES = [c for c in X.columns if c.startswith('hx_') or c.startswith('ring_')]
DRY = [c for c in X.columns if c.endswith('_chg60') or c.endswith('days_dry') or c.startswith('nb_n') or c.startswith('beat_rank_')]
BASE = [c for c in X.columns if c not in ('season', 'date', 'cell_id', 'pos', 'beat') and c not in HAWKES and c not in DRY] + ['prior']
print('rows', len(X), 'base', len(BASE), 'hawkes', len(HAWKES), 'dry', len(DRY), flush=True)
B = np.stack([burned[Y] for Y in SEAS]).astype(float)
def prior(train_seasons):
    k = [SEAS.index(s) for s in train_seasons]; return np.log((B[k].sum(0) + 0.5) / (len(k) + 1))
def set_prior(tr_seasons):
    X['prior'] = 0.0
    for Y in SEAS:
        p = prior([s for s in tr_seasons if s != Y]) if Y in tr_seasons else prior(tr_seasons)
        m = (X.season == Y).values; X.loc[m, 'prior'] = p[X.cell_id.values[m]]
def fit_pred(tr_seasons, te_seasons, feat, rank=False):
    set_prior(tr_seasons)
    tr = X.season.isin(tr_seasons).values; te = X.season.isin(te_seasons).values
    if not rank:
        rs = np.random.default_rng(0); keep = tr & (X.pos.values | (rs.random(len(X)) < 0.25))
        wt = np.where(X.pos.values[keep], 1.0, 4.0)
        gb = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.7, n_jobs=4, verbose=-1)
        gb.fit(X.loc[keep, feat], X.pos.values[keep], sample_weight=wt)
        return gb.predict_proba(X.loc[te, feat])[:, 1], te, gb
    # ranker: queries = (season, date, beat) with >= 1 positive
    q = X.loc[tr, ['season', 'date', 'beat', 'pos']].copy(); q['qid'] = pd.factorize(pd.MultiIndex.from_frame(q[['season', 'date', 'beat']]))[0]
    haspos = q.groupby('qid').pos.transform('max').values > 0
    sub = q[haspos].sort_values('qid'); idx = sub.index.values
    groups = sub.groupby('qid').size().values
    rk = lgb.LGBMRanker(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.7, lambdarank_truncation_level=8, n_jobs=4, verbose=-1)
    rk.fit(X.loc[idx, feat], X.pos.values[idx].astype(int), group=groups)
    return rk.predict(X.loc[te, feat]), te, rk
def score_pred(pred_col, seasons):
    m = X.loc[X.season.isin(seasons), ['season', 'date', 'cell_id', 'pos', 'beat', pred_col]]
    out = {}
    for bn, bcol in (('real94', 'beat'),):
        s = m[pred_col].fillna(-1e9); r = s.groupby([m.season, m.date, m[bcol]]).rank('first', ascending=False)
        out[f'{bn}_recall@5'] = round(float(m.pos[r <= 5].sum() / m.pos.sum()), 4); out[f'{bn}_recall@10'] = round(float(m.pos[r <= 10].sum() / m.pos.sum()), 4)
        for y, g in m.groupby('season'):
            rr = g[pred_col].fillna(-1e9).groupby([g.date, g[bcol]]).rank('first', ascending=False); out[f'{bn}_recall@5_{y}'] = round(float(g.pos[rr <= 5].sum() / g.pos.sum()), 4)
    return out
res = {}
def run(name, feat, rank=False):
    P = np.full(len(X), np.nan)
    for Y in range(2017, 2025):
        p, te, _ = fit_pred([s for s in range(2017, 2025) if s != Y], [Y], feat, rank); P[te] = p
    X[name] = P
    p, te, mdl = fit_pred(list(range(2017, 2025)), [2025, 2026], feat, rank); X.loc[te, name] = p
    r = {'loso': score_pred(name, range(2017, 2025)), 'test': score_pred(name, [2025, 2026])}
    if not rank:
        imp = dict(zip(feat, mdl.booster_.feature_importance('gain').round().tolist())); r['top_gain'] = dict(sorted(imp.items(), key=lambda kv: -kv[1])[:15])
    res[name] = r; print(name, 'LOSO', r['loso']['real94_recall@5'], 'TEST', r['test']['real94_recall@5'], flush=True)
    json.dump(res, open(os.path.join(OUT, 'lean_plus_results.json'), 'w'), indent=1)
FEATS = {'base': BASE, 'hawkes': BASE + HAWKES, 'dry': BASE + DRY, 'hawkes+dry': BASE + HAWKES + DRY}
for cfg in CONFIGS:
    if cfg.startswith('rank:'):
        base_name = cfg[5:]; run('rank_' + base_name, FEATS[base_name], rank=True)
        if base_name in X.columns:
            # rank-average with the classifier of the same features
            m = X[['season', 'date', 'beat']]
            ra = X[base_name].groupby([m.season, m.date, m.beat]).rank(pct=True) + X['rank_' + base_name].groupby([m.season, m.date, m.beat]).rank(pct=True)
            X['rankavg_' + base_name] = ra
            res['rankavg_' + base_name] = {'loso': score_pred('rankavg_' + base_name, range(2017, 2025)), 'test': score_pred('rankavg_' + base_name, [2025, 2026])}
            print('rankavg_' + base_name, res['rankavg_' + base_name]['loso']['real94_recall@5'], res['rankavg_' + base_name]['test']['real94_recall@5'], flush=True)
            json.dump(res, open(os.path.join(OUT, 'lean_plus_results.json'), 'w'), indent=1)
    else:
        run(cfg, FEATS[cfg])
keep = ['season', 'date', 'cell_id'] + [c for c in X.columns if c in res or c.startswith('rank')]
X[keep].to_parquet(os.path.join(OUT, 'lean_plus_pred.parquet'), index=False)
print('LEAN_PLUS_DONE', flush=True)
