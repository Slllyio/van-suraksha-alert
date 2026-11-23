"""Step 3: size model at square-day level. E(size) = expected burnt area (ha) IF a fire starts in this square in the next
2 days, from inputs known at issue time:
- the round-22 feature row of the square on the issue day (B0 + static GIS: live fires nearby 0.5-50 km over 1-30 days,
  days since the last fire, 5-season burn history, day of year and division day rate, HLS dryness, division activity,
  terrain, land cover / forest type / forest continuity and edge distance, roads and villages, division id);
- big-fire history (only seasons before the issue season, from 2019 on): the division's share of 200 ha+ fires and median
  log area, and the mean log area of past fires whose first-day squares lie within 5 km.
Training rows: every first-day square of every fire in the training seasons, on issue days -1 and -2 (weight 1/(2 x squares)).
Target: burnt area, scar where it exists, else the VIIRS square-count area. LightGBM gamma (log link), so the output is E(ha).
held model: trained on 2019-21, predicts 2022-24. fwd model: trained on 2019-24, predicts 2025.
Out (scratch r24): size_rows.parquet, Ecube_{period}.pkl; out/size_model_{period}.json, out/size_imp_{period}.csv."""
import sys, os, json, pickle, numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree
import aw_common as A
C, Fe = A.C, A.Fe
sys.path.insert(0, A.SR); import variants
PAR = dict(objective='gamma', learning_rate=0.04, num_leaves=31, min_data_in_leaf=100, feature_fraction=0.8, bagging_fraction=0.8,
           bagging_freq=1, lambda_l2=5.0, verbose=-1, num_threads=4, max_cat_to_onehot=4, cat_smooth=20)
NR = 400


def hist_feats(ev, fd, y, ur, uc, home, divnames):
    """Big-fire history from seasons 2019..y-1 for every union square: division share of 200 ha+ fires, division median
    log area, mean log area of past fires starting within 5 km (NaN where nothing is known)."""
    p = ev[(ev.season < y) & ev.valid]
    out = {}
    dv = p.groupby('division').agg(big=('area_ha', lambda a: (a >= A.BIG).mean()), mlog=('area_ha', lambda a: np.log(a).median()))
    out['div_bigshare'] = dv.big.reindex(divnames).values[home].astype(np.float32) if len(dv) else np.full(len(ur), np.nan, np.float32)
    out['div_mlog'] = dv.mlog.reindex(divnames).values[home].astype(np.float32) if len(dv) else np.full(len(ur), np.nan, np.float32)
    f = fd.merge(p[['division', 'ev', 'season', 'area_ha']], on=['division', 'ev']).drop_duplicates(['division', 'ev', 'season'])
    if len(f):
        tr = cKDTree(np.c_[f.row.values, f.col.values]); la = np.log(f.area_ha.values)
        nb = tr.query_ball_point(np.c_[ur, uc], r=10)
        out['loc_mlog'] = np.array([la[k].mean() if len(k) else np.nan for k in nb], np.float32)
        out['loc_big5k'] = np.array([(la[k] >= np.log(A.BIG)).sum() if len(k) else 0 for k in nb], np.float32)
    else:
        out['loc_mlog'] = np.full(len(ur), np.nan, np.float32); out['loc_big5k'] = np.zeros(len(ur), np.float32)
    return out


def collect_rows():
    fn = A.S24 + 'size_rows.parquet'
    if os.path.exists(fn): return pd.read_parquet(fn)
    ev = pd.read_parquet(A.S24 + 'events.parquet'); fd = pd.read_parquet(A.S24 + 'fd_cells.parquet')
    B = Fe.base(); U = B['U']; V = C.load_det(); rows = []
    for y in range(2019, 2026):
        e = ev[(ev.season == y) & ev.valid]
        f = fd.merge(e[['division', 'ev', 'nfd', 'area_ha']], on=['division', 'ev'])
        f['u'] = np.searchsorted(U, f.row.values * C.W + f.col.values)
        want = {}
        for lag in (1, 2):
            iss = f.day - pd.Timedelta(days=lag)
            for k, g in f.assign(iss=iss).groupby('iss'): want.setdefault(pd.Timestamp(k), []).append(g)
        H = hist_feats(ev, fd, y, B['ur'], B['uc'], B['home'], B['divnames'])
        for it in Fe.season_iter(y, {}, V, **variants.ex_static(y)):
            if it['t'] not in want: continue
            g = pd.concat(want[it['t']]); X = it['X'][g.u.values]
            r = pd.DataFrame(X, columns=it['names'])
            for k, a in H.items(): r[k] = a[g.u.values]
            r['division'] = g.division.values; r['ev'] = g.ev.values; r['season'] = y; r['w'] = 1.0 / (2 * g.nfd.values); r['area_ha'] = g.area_ha.values
            rows.append(r)
        print('rows', y, sum(len(r) for r in rows), flush=True)
    R = pd.concat(rows, ignore_index=True); R.to_parquet(fn, index=False); return R


def feats(R): return [c for c in R.columns if c not in ('division', 'ev', 'season', 'w', 'area_ha')]


def train(R, seasons):
    tr = R[R.season.isin(seasons)]; F = feats(R)
    ds = lgb.Dataset(tr[F].values, tr.area_ha.values, weight=tr.w.values, feature_name=F, categorical_feature=['div'])
    m = lgb.train(PAR, ds, NR); return m, F


def evaluate(m, F, R, seasons, ev):
    te = R[R.season.isin(seasons)].copy(); te['E'] = m.predict(te[F].values)
    e = te.groupby(['division', 'ev', 'season']).agg(E=('E', 'mean')).reset_index().merge(ev, on=['division', 'ev', 'season'])
    out = {}
    for nm, s in (('all', e), ('scar', e[e.area_src == 'scar'])):
        top = s.E >= s.E.quantile(0.9)
        out[nm] = dict(n=len(s), spearman=float(s.E.corr(s.area_ha, method='spearman')),
                       ha_share_top10pct_pred=float(s.area_ha[top].sum() / s.area_ha.sum()),
                       big_share_top10pct_pred=float(((s.area_ha >= A.BIG) & top).sum() / max(1, (s.area_ha >= A.BIG).sum())),
                       big_rate_top10=float((s.area_ha[top] >= A.BIG).mean()), big_rate_all=float((s.area_ha >= A.BIG).mean()))
    e[['division', 'ev', 'season', 'E']].to_parquet(A.S24 + f'Eev_{"".join(map(str, seasons))}.parquet', index=False)
    return out


def predict_cube(m, F, seasons):
    ev = pd.read_parquet(A.S24 + 'events.parquet'); fd = pd.read_parquet(A.S24 + 'fd_cells.parquet')
    B = Fe.base(); V = C.load_det(); cube = {}
    for y in seasons:
        H = hist_feats(ev, fd, y, B['ur'], B['uc'], B['home'], B['divnames']); out = []
        for it in Fe.season_iter(y, {}, V, **variants.ex_static(y)):
            X = np.column_stack([it['X']] + [H[k] for k in F[len(it['names']):]])
            out.append(m.predict(X, num_threads=4).astype(np.float32))
        cube[y] = np.stack(out); print('E cube', y, cube[y].shape, flush=True)
    return cube


if __name__ == '__main__':
    R = collect_rows(); ev = pd.read_parquet(A.S24 + 'events.parquet')
    for per in sys.argv[1:] or ('held', 'fwd'):
        m, F = train(R, A.TRAIN[per])
        res = evaluate(m, F, R, A.TEST[per], ev); print(per, json.dumps(res, indent=1), flush=True)
        json.dump(res, open(A.OUT + f'size_model_{per}.json', 'w'), indent=1)
        imp = pd.DataFrame(dict(feat=F, gain=m.feature_importance('gain'))).sort_values('gain', ascending=False); imp['share'] = imp.gain / imp.gain.sum()
        imp.to_csv(A.OUT + f'size_imp_{per}.csv', index=False)
        cube = predict_cube(m, F, A.TEST[per]); pickle.dump(cube, open(A.S24 + f'Ecube_{per}.pkl', 'wb'), protocol=4)
