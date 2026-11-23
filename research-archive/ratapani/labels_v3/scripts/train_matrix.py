"""Train the lean ensemble (classifier + lambdarank rank-average, SCORING.md baseline) on each label variant and score it on
every label key, on the 94 real beats at 5 picks per beat per day. Features = lean_plus.py BASE set (no Hawkes / extra dryness).
LOSO 2017-24 and train 2017-24 -> test 2025-26.  Usage: python3 train_matrix.py OUTDIR [train_variants]"""
import os, sys, json, numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree
import scipy.sparse as sp
RS = '/mnt/project-files/research/'; RP = '/mnt/project-files/ratapani/'
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
TRAIN = sys.argv[2].split(',') if len(sys.argv) > 2 else ['main', 'union', 'dlenient', 'dstrict', 'truelead']
n = 3614; SEAS = list(range(2017, 2027))
G = json.load(open(RP + 'grid_500m.geojson'))['features']
xy = np.zeros((n, 2))
for f in G: p = f['properties']; xy[p['cell_id']] = (p['x0'] + 250, p['y0'] + 250)
tree = cKDTree(xy)
def adj(r):
    pr = tree.query_pairs(r, output_type='ndarray'); A = sp.coo_matrix((np.ones(len(pr) * 2), (np.r_[pr[:, 0], pr[:, 1]], np.r_[pr[:, 1], pr[:, 0]])), (n, n)); return A.tocsr()
A1, A2 = adj(1001), adj(2001)
beat_code = pd.factorize(pd.read_csv(RP + 'beats/cell_beat.csv').set_index('cell_id').beat_uid.reindex(range(n)))[0]
# ---- labels: all variants on one row set ----
lab = pd.read_parquet(RP + 'labels_v3/labels_v3.parquet'); lab['date'] = pd.to_datetime(lab.date)
tl = pd.read_parquet(RP + 'fsi/true_lead_labels.parquet')[['season', 'date', 'cell_id', 'pos', 'valid_strict']]
tl['date'] = pd.to_datetime(tl.date); tl = tl.rename(columns={'pos': 'pos_truelead', 'valid_strict': 'valid_truelead'})
lab = lab.merge(tl, on=['season', 'date', 'cell_id'], how='left')
for c in ('pos_truelead', 'valid_truelead'): lab[c] = lab[c].fillna(False).astype(bool)
lab['pos_truelead'] &= lab.valid_truelead
af = pd.read_parquet(RP + 'labels_v3/labels_v3_af.parquet'); af['date'] = pd.to_datetime(af.date)
lab = lab.merge(af, on=['season', 'date', 'cell_id'], how='left')
AFV = [c[4:] for c in af.columns if c.startswith('pos_')]
for v in AFV:
    lab['valid_' + v] = lab['valid_' + v].fillna(False).astype(bool); lab['pos_' + v] = lab['pos_' + v].fillna(False).astype(bool) & lab['valid_' + v]
if os.path.exists(RP + 'labels_v3/labels_v3_soft.parquet'):
    so = pd.read_parquet(RP + 'labels_v3/labels_v3_soft.parquet'); so['date'] = pd.to_datetime(so.date)
    lab = lab.merge(so, on=['season', 'date', 'cell_id'], how='left'); SOV = [c[4:] for c in so.columns if c.startswith('pos_')]
    for v in SOV:
        lab['valid_' + v] = lab['valid_' + v].fillna(False).astype(bool); lab['pos_' + v] = lab['pos_' + v].fillna(False).astype(bool) & lab['valid_' + v]
    AFV = AFV + SOV
VARS = ['main', 'union', 'dlenient', 'dstrict', 'truelead'] + AFV
print('label rows', len(lab), {v: int((lab['pos_' + v] & lab['valid_' + v]).sum()) for v in VARS}, flush=True)
# ---- statics ----
st = pd.read_csv(RS + 'ratapani-ignition/cells_static.csv').set_index('cell_id')[['elig_ha', 'tree', 'shrub', 'grass', 'crop', 'northness', 'eastness', 'd_built', 'd_crop', 'd_edge', 'd_aoi']]
for f in ('terrain', 'proximity', 'worldcover', 'population'):
    t = pd.read_csv(RP + f'ee/{f}.csv').set_index('cell_id'); st = st.join(t, rsuffix='_' + f)
st = st.reindex(range(n))
# ---- weather ----
w = pd.read_csv(RS + 'ratapani-ignition/weather_power_2017_2026.csv', parse_dates=['date']).set_index('date').sort_index()
w['p7'] = w.PRECTOTCORR.rolling(7).sum(); w['p30'] = w.PRECTOTCORR.rolling(30).sum(); w['rh3'] = w.RH2M.rolling(3).mean()
w['tmax3'] = w.T2M_MAX.rolling(3).mean(); w['tmax_anom'] = w.T2M_MAX - w.T2M_MAX.rolling(30).mean(); w['doy'] = w.index.dayofyear
wcols = ['T2M', 'T2M_MAX', 'RH2M', 'WS10M', 'ws_pm', 'p7', 'p30', 'rh3', 'tmax3', 'tmax_anom', 'doy']
# ---- scars seen (season maps, as in the lean model; same inputs for every label variant) ----
bwa = pd.read_csv(RS + 'ratapani-burn-labels/burn_windows.csv', parse_dates=['window_start', 'window_end']); bwa = bwa[bwa.burned == 1]
bw = bwa.sort_values(['season', 'cell_id', 'window_end']).drop_duplicates(['season', 'cell_id'])
burned = {Y: np.zeros(n, bool) for Y in SEAS}
for r in bw.itertuples(): burned[r.season][r.cell_id] = True
# ---- optical dryness before t ----
sc = pd.read_parquet(RS + 'ratapani-ignition/s2_cells.parquet'); cc = pd.read_parquet(RS + 'ratapani-burn-labels/clear_calendar.parquet')
cc['date'] = pd.to_datetime(cc['date']); cc = cc[cc.clear_frac >= 0.5][['cell_id', 'date']].drop_duplicates()
sc['date'] = pd.to_datetime(sc.date); sc = sc.merge(cc, on=['cell_id', 'date'])
_m = bwa[['cell_id', 'window_start', 'window_end']].merge(sc[['cell_id', 'date']], on='cell_id')
_in = _m[(_m.date > _m.window_start) & (_m.date < _m.window_end)][['cell_id', 'date']].drop_duplicates()
sc = sc.merge(_in.assign(_x=1), on=['cell_id', 'date'], how='left'); sc = sc[sc._x.isna()].drop(columns='_x')
cal = pd.date_range('2016-12-01', '2026-06-30'); dyn = {}
for col in ('ndvi', 'ndmi', 'nbr'):
    d = sc.pivot_table(index='date', columns='cell_id', values=col).reindex(index=cal, columns=range(n)).shift(1)
    last = d.ffill(limit=60); dyn[f'{col}_last'] = last; dyn[f'{col}_chg30'] = last - last.shift(30); dyn[f'{col}_mean30'] = d.rolling(30, min_periods=1).mean()
frames = []
for Y in SEAS:
    days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); T = len(days)
    full = pd.date_range(f'{Y - 1}-12-01', f'{Y}-06-30'); d0 = full[0]
    ev = np.zeros((len(full), n), np.float32)
    for r in bw[bw.season == Y].itertuples(): ev[(r.window_end - d0).days, r.cell_id] = 1
    cum = np.cumsum(ev, 0); off = (days[0] - d0).days
    known = cum[off - 1: off - 1 + T]; k7 = known - cum[off - 8: off - 8 + T]
    f = {'aoi_new7': np.repeat(k7.sum(1, keepdims=True), n, 1), 'aoi_season': np.repeat(known.sum(1, keepdims=True) / n, n, 1),
         'nb1_new7': (A1 @ k7.T).T, 'nb2_new7': (A2 @ k7.T).T, 'nb2_season': (A2 @ known.T).T, 'nb1_season': (A1 @ known.T).T}
    di = cal.get_indexer(days)
    for k, v in dyn.items(): f['s2d_' + k] = v.to_numpy(np.float32)[di]
    for k in ('ndvi_last', 'ndmi_last', 'nbr_last'): f['s2d_' + k + '_spanom'] = f['s2d_' + k] - np.nanmedian(f['s2d_' + k], 1, keepdims=True)
    tt, cc_ = np.meshgrid(np.arange(T), np.arange(n), indexing='ij')
    df = pd.DataFrame({k: np.asarray(v, np.float32).reshape(-1) for k, v in f.items()}); df['season'] = Y; df['date'] = days[tt.reshape(-1)]; df['cell_id'] = cc_.reshape(-1)
    frames.append(df)
X = pd.concat(frames, ignore_index=True); del frames
X = lab.merge(X, on=['season', 'date', 'cell_id'], how='left')
X = X.join(st, on='cell_id'); X = X.join(w[wcols], on='date'); X['beat'] = beat_code[X.cell_id.values]
NONF = {'season', 'date', 'cell_id', 'beat', 'first_kind', 'fire_day'} | {c for c in X.columns if c.startswith('pos_') or c.startswith('valid_')}
BASE = [c for c in X.columns if c not in NONF] + ['prior']
print('rows', len(X), 'features', len(BASE), flush=True)
B = np.stack([burned[Y] for Y in SEAS]).astype(float)
def prior(ts): k = [SEAS.index(s) for s in ts]; return np.log((B[k].sum(0) + 0.5) / (len(k) + 1))
def set_prior(tr):
    X['prior'] = 0.0
    for Y in SEAS:
        p = prior([s for s in tr if s != Y]) if Y in tr else prior(tr); m = (X.season == Y).values; X.loc[m, 'prior'] = p[X.cell_id.values[m]]
def fit(tr_seasons, te_seasons, L, rank):
    set_prior(tr_seasons)
    v = X['valid_' + L].values; y = X['pos_' + L].values & v
    tr = X.season.isin(tr_seasons).values & v; te = X.season.isin(te_seasons).values
    if not rank:
        rs = np.random.default_rng(0); keep = tr & (y | (rs.random(len(X)) < 0.25)); wt = np.where(y[keep], 1.0, 4.0)
        gb = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.7, n_jobs=4, verbose=-1)
        gb.fit(X.loc[keep, BASE], y[keep], sample_weight=wt); return gb.predict_proba(X.loc[te, BASE])[:, 1], te
    q = X.loc[tr, ['season', 'date', 'beat']].copy(); q['y'] = y[tr]; q['qid'] = pd.factorize(pd.MultiIndex.from_frame(q[['season', 'date', 'beat']]))[0]
    hp = q.groupby('qid').y.transform('max').values > 0; sub = q[hp].sort_values('qid'); idx = sub.index.values; groups = sub.groupby('qid').size().values
    rk = lgb.LGBMRanker(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.7, lambdarank_truncation_level=8, n_jobs=4, verbose=-1)
    rk.fit(X.loc[idx, BASE], sub.y.values.astype(int), group=groups); return rk.predict(X.loc[te, BASE]), te
def score(col, L, seasons):
    m = X.loc[X.season.isin(seasons) & X['valid_' + L], ['season', 'date', 'beat', 'pos_' + L, col]]
    if not len(m) or m['pos_' + L].sum() == 0: return None
    r = m[col].fillna(-1e9).groupby([m.season, m.date, m.beat]).rank('first', ascending=False); p = m['pos_' + L]
    o = {'recall@5': round(float(p[r <= 5].sum() / p.sum()), 4), 'recall@10': round(float(p[r <= 10].sum() / p.sum()), 4), 'positives': int(p.sum())}
    for y, g in m.groupby('season'):
        rr = g[col].fillna(-1e9).groupby([g.date, g.beat]).rank('first', ascending=False); o[f'r5_{y}'] = round(float(g['pos_' + L][rr <= 5].sum() / max(g['pos_' + L].sum(), 1)), 4)
    return o
TEST = [2025, 2026]; res = {}
rs = np.random.default_rng(1); X['rnd'] = rs.random(len(X))
res['random'] = {S: {'loso': score('rnd', S, range(2017, 2025)), 'test': score('rnd', S, TEST)} for S in VARS}
for L in TRAIN:
    for rank in (False, True):
        name = ('rank_' if rank else 'clf_') + L; P = np.full(len(X), np.nan)
        for Y in range(2017, 2025):
            p, te = fit([s for s in range(2017, 2025) if s != Y], [Y], L, rank); P[te] = p
        X[name] = P
        if L != 'truelead' or True:
            p, te = fit(list(range(2017, 2025)), TEST, L, rank); X.loc[te, name] = p
        print(name, 'fitted', flush=True)
    m = X[['season', 'date', 'beat']]
    X['ens_' + L] = X['clf_' + L].groupby([m.season, m.date, m.beat]).rank(pct=True) + X['rank_' + L].groupby([m.season, m.date, m.beat]).rank(pct=True)
    res['ens_' + L] = {S: {'loso': score('ens_' + L, S, range(2017, 2025)), 'test': score('ens_' + L, S, TEST)} for S in VARS}
    print('ens_' + L, {S: (v['loso'] or {}).get('recall@5') for S, v in res['ens_' + L].items()}, {S: (v['test'] or {}).get('recall@5') for S, v in res['ens_' + L].items()}, flush=True)
    json.dump(res, open(os.path.join(OUT, 'train_matrix_results.json'), 'w'), indent=1)
X[['season', 'date', 'cell_id'] + [c for c in X.columns if c.startswith('ens_') or c.startswith('clf_') or c.startswith('rank_')]].to_parquet(os.path.join(OUT, 'train_matrix_pred.parquet'), index=False)
print('MATRIX_DONE', flush=True)
