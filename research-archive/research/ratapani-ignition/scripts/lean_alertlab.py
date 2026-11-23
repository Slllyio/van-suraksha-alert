"""Alert-dated scars (fire-alert-scars thread) as labels, alone and merged with the season scar labels.
Label sets on one union row set:
  scar   : SCORING.md rule (first burn per season from season scar windows)
  alert  : first alert-dated scar per cell-season (cell overlap >= 0.5 ha); positive on t = fire_day-2, fire_day-1; censored from fire_day
  merged : positive if either; censored at the earlier of the two
Train on one set, score (recall@5, real beats) on each. Lean base features + lambdarank rank-average.
Usage: python3 lean_alertlab.py OUTDIR
"""
import sys, os, json, numpy as np, pandas as pd, lightgbm as lgb
from shapely.geometry import shape, box
from shapely.ops import transform as stransform
import pyproj
RP_ = '/mnt/project-files/ratapani/'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import pipeline_score as ps
H = 2; SEAS_ = list(range(2017, 2027)); n_ = 3614
G_ = json.load(open(RP_ + 'grid_500m.geojson'))['features']
cells = {f['properties']['cell_id']: box(f['properties']['x0'], f['properties']['y0'], f['properties']['x0'] + 500, f['properties']['y0'] + 500) for f in G_}
from shapely.strtree import STRtree
ids = np.array(list(cells)); tree = STRtree([cells[i] for i in ids])
ev = json.load(open('/mnt/project-files/fire-alert-scars/event_scars.geojson'))['features']
to_utm = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
rows = []
for f in ev:
    p = f['properties']
    if p.get('status') not in ('scar', 'scar_faint'): continue
    g = stransform(to_utm, shape(f['geometry']))
    for j in tree.query(g):
        a = g.intersection(cells[ids[j]]).area / 1e4
        if a >= 0.5: rows.append((pd.Timestamp(p['date']), int(ids[j]), a, p['status']))
al = pd.DataFrame(rows, columns=['fire_day', 'cell_id', 'ha', 'status'])
al['season'] = np.where(al.fire_day.dt.month >= 8, al.fire_day.dt.year + 1, al.fire_day.dt.year)
al = al.sort_values(['season', 'cell_id', 'fire_day']).drop_duplicates(['season', 'cell_id'])
print('alert-scar cell-seasons', len(al), al.groupby('season').size().to_dict(), flush=True)
def alert_labels(seasons):
    out = []
    for Y in seasons:
        days = pd.date_range(f'{Y}-02-01', f'{Y}-06-20'); T = len(days)
        valid = np.ones((T, n_), bool); pos = np.zeros((T, n_), bool)
        for r in al[al.season == Y].itertuples():
            fi = (r.fire_day - days[0]).days
            a0, b0 = max(fi - H, 0), min(fi - 1, T - 1)
            if b0 >= a0: pos[a0:b0 + 1, r.cell_id] = True
            if fi <= T - 1: valid[max(fi, 0):, r.cell_id] = False
        ti, ci = np.nonzero(valid); out.append(pd.DataFrame(dict(season=Y, date=days[ti], cell_id=ci, pos=pos[ti, ci])))
    return pd.concat(out, ignore_index=True)
def ALT_LABELS(seasons):
    s = ps.labels(seasons).rename(columns={'pos': 'pos_scar'}); s['valid_scar'] = True
    a = alert_labels(seasons).rename(columns={'pos': 'pos_alert'}); a['valid_alert'] = True
    u = s.merge(a, on=['season', 'date', 'cell_id'], how='outer')
    for c in ('pos_scar', 'pos_alert', 'valid_scar', 'valid_alert'): u[c] = u[c].fillna(False).astype(bool)
    # merged: censor at the earlier censoring point = valid only where both still valid, or where one is valid and the other never censored this cell-season
    u['pos_merged'] = u.pos_scar | u.pos_alert
    u['valid_merged'] = u.valid_scar & u.valid_alert
    u['pos'] = u.pos_scar
    return u
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lean_plus.py')).read()
src = src[:src.index('for cfg in CONFIGS:')].replace('lab = ps.labels(SEAS)', 'lab = ALT_LABELS(SEAS)')
sys.argv = [sys.argv[0], sys.argv[1], 'none']
exec(compile(src, 'lean_plus.py', 'exec'))
OUT = sys.argv[1]
for L in ('scar', 'alert', 'merged'):
    print(L, 'valid rows', int(X['valid_' + L].sum()), 'positives', int((X['pos_' + L] & X['valid_' + L]).sum()), flush=True)
def fit_L(tr_seasons, te_seasons, L, rank):
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
def score_L(col, L, seasons):
    m = X.loc[X.season.isin(seasons) & X['valid_' + L], ['season', 'date', 'beat', 'pos_' + L, col]]
    r = m[col].fillna(-1e9).groupby([m.season, m.date, m.beat]).rank('first', ascending=False)
    p = m['pos_' + L]; o = {'recall@5': round(float(p[r <= 5].sum() / p.sum()), 4), 'recall@10': round(float(p[r <= 10].sum() / p.sum()), 4)}
    for y, g in m.groupby('season'):
        rr = g[col].fillna(-1e9).groupby([g.date, g.beat]).rank('first', ascending=False); o[f'recall@5_{y}'] = round(float(g['pos_' + L][rr <= 5].sum() / g['pos_' + L].sum()), 4)
    return o
res = {}
TEST = [2025, 2026]
for L in ('scar', 'alert', 'merged'):
    for rank in (False, True):
        name = ('rank_' if rank else 'clf_') + L; P = np.full(len(X), np.nan)
        for Y in range(2017, 2025):
            p, te = fit_L([s for s in range(2017, 2025) if s != Y], [Y], L, rank); P[te] = p
        X[name] = P; p, te = fit_L(list(range(2017, 2025)), TEST, L, rank); X.loc[te, name] = p
        print(name, 'fitted', flush=True)
    m = X[['season', 'date', 'beat']]
    X['ra_' + L] = X['clf_' + L].groupby([m.season, m.date, m.beat]).rank(pct=True) + X['rank_' + L].groupby([m.season, m.date, m.beat]).rank(pct=True)
    for col in ('clf_' + L, 'ra_' + L):
        res[col] = {}
        for S in ('scar', 'alert', 'merged'):
            res[col]['score_on_' + S] = {'loso': score_L(col, S, range(2017, 2025)), 'test': score_L(col, S, TEST)}
            print(col, 'scored on', S, res[col]['score_on_' + S]['loso']['recall@5'], res[col]['score_on_' + S]['test']['recall@5'], flush=True)
    json.dump(res, open(os.path.join(OUT, 'lean_alertlab_results.json'), 'w'), indent=1)
# random baseline per label set
rs = np.random.default_rng(1); X['rnd'] = rs.random(len(X))
for S in ('scar', 'alert', 'merged'):
    res['random_' + S] = {'loso': score_L('rnd', S, range(2017, 2025)), 'test': score_L('rnd', S, TEST)}
json.dump(res, open(os.path.join(OUT, 'lean_alertlab_results.json'), 'w'), indent=1)
print('ALERTLAB_DONE', flush=True)
