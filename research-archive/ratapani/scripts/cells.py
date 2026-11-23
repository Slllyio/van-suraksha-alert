"""Ratapani cell x day fire model at several grid resolutions, leave-one-season-out."""
import sys, json, time, pickle, numpy as np, pandas as pd
sys.path.insert(0, '/home/user/vanagni')
from src.analysis import fire_occurrence as FO
from src.analysis.fwi_observed import roll_fwi
from shapely.geometry import box
from shapely.ops import transform as shp_transform
from shapely import STRtree
from pyproj import Transformer
import scipy.sparse as sp
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, average_precision_score
import lightgbm as lgb

RES = [int(a) for a in sys.argv[1:]] or [4000, 2000, 1000, 500]
K = 'Ratapani'
TR = pickle.load(open('tr.pkl', 'rb'))
poly_ll = TR[K]
fwd = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
poly = shp_transform(fwd, poly_ll)
det = pd.read_parquet('det_Ratapani.parquet')
dx, dy = fwd(det.longitude.values, det.latitude.values)
det['x'], det['y'] = dx, dy

# ── weather, as before (NASA POWER, rolled FWI) ────────────────────────────────
W = pd.read_parquet('weather_power.parquet'); w = W[W.reserve == K].copy(); w['date'] = w.date.dt.date
w = roll_fwi(w, unit_col='reserve')
w = w[pd.to_datetime(w.date) >= pd.Timestamp('2012-10-01')].reset_index(drop=True)
DAYS = pd.to_datetime(w.date)                      # full calendar 2012-10-01 .. 2024-12-31
T = len(DAYS); day_index = {d.date(): i for i, d in enumerate(DAYS)}
w = FO.build_features(w)                           # doy terms, derived
tot = det.groupby(det.date.dt.date).size()
w['n_forest'] = [tot.get(d, 0) for d in w.date]
w = FO.build_features(w)                           # division memory log_nf_prev{1,3,7,14}
season = np.array([d.month in (2, 3, 4, 5, 6) and d.year >= 2013 for d in DAYS])
years = DAYS.dt.year.values
DIV_FEATS = ['ffmc', 'rh_pct', 'temp_c', 'dmc', 'dc', 'wind_kmh', 'precip_mm', 'rh_min_7d', 'days_since_rain',
             'doy_sin', 'doy_cos', 'log_nf_prev1', 'log_nf_prev7', 'log_nf_prev14']
DIV = w[DIV_FEATS].to_numpy(dtype=np.float32)

def trailing(M, k, lag=1):
    """sum over the k days ending `lag` days before each row (row 0 = day 0)."""
    c = np.vstack([np.zeros((1, M.shape[1])), np.cumsum(M, axis=0)])
    out = np.full(M.shape, np.nan)
    for t in range(M.shape[0]):
        hi = t - lag + 1; lo = hi - k
        if lo >= 0: out[t] = c[hi] - c[lo]
    return out

def budget_metrics(P, L, area, days_mask, budgets):
    """Per-day ranking: recall over burning cells, precision over listed cells, pooled over days."""
    res = {}
    idx = np.where(days_mask)[0]
    order = np.argsort(-P[idx], axis=1)
    cum_area = np.cumsum(area[order], axis=1)
    burn = L[idx]
    for B in budgets:
        inlist = cum_area <= B
        n_list = inlist.sum(1)
        hit = np.take_along_axis(burn, order, axis=1) & inlist
        fire_days = burn.sum(1) > 0
        res[str(B)] = dict(
            recall=float(hit[fire_days].sum() / max(burn[fire_days].sum(), 1)),
            precision=float(hit.sum() / max(n_list.sum(), 1)),
            cells_per_day=float(n_list.mean()),
            precision_fire_days=float(hit[fire_days].sum() / max(n_list[fire_days].sum(), 1)),
        )
    return res

def where_auc(P, L, days_mask):
    out = []
    for t in np.where(days_mask)[0]:
        y = L[t]
        if 0 < y.sum() < len(y): out.append(roc_auc_score(y, P[t]))
    return float(np.mean(out)), float(np.median(out))

results = {}
for s in RES:
    t0 = time.time()
    x0, y0, x1, y1 = poly.bounds
    xs = np.arange(np.floor(x0 / s) * s, x1 + s, s); ys = np.arange(np.floor(y0 / s) * s, y1 + s, s)
    cells, ij, area, ffrac = [], [], [], []
    for i, cx in enumerate(xs[:-1]):
        for j, cy in enumerate(ys[:-1]):
            b = box(cx, cy, cx + s, cy + s)
            if b.intersects(poly):
                a = b.intersection(poly).area
                if a / b.area < 0.05: continue
                cells.append(b); ij.append((i, j)); area.append(a / 1e6); ffrac.append(a / b.area)
    n = len(cells); area = np.array(area); ffrac = np.array(ffrac)
    ij = np.array(ij); pos = {tuple(p): k for k, p in enumerate(ij)}
    # detections -> cell
    ci = np.floor((det.x.values - xs[0]) / s).astype(int); cj = np.floor((det.y.values - ys[0]) / s).astype(int)
    cell_of = np.array([pos.get((a, b), -1) for a, b in zip(ci, cj)])
    di = np.array([day_index.get(d, -1) for d in det.date.dt.date])
    ok = (cell_of >= 0) & (di >= 0)
    M = np.zeros((T, n), dtype=np.float32)
    np.add.at(M, (di[ok], cell_of[ok]), 1)
    L = M > 0
    # neighbour adjacency (8-ring) and 2-ring
    rows, cols, rows2, cols2 = [], [], [], []
    for k, (i, j) in enumerate(ij):
        for di_ in range(-2, 3):
            for dj_ in range(-2, 3):
                if di_ == 0 and dj_ == 0: continue
                q = pos.get((i + di_, j + dj_))
                if q is None: continue
                if max(abs(di_), abs(dj_)) == 1: rows.append(k); cols.append(q)
                else: rows2.append(k); cols2.append(q)
    A1 = sp.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    A2 = sp.csr_matrix((np.ones(len(rows2)), (rows2, cols2)), shape=(n, n))
    own1, own7, own14 = trailing(M, 1), trailing(M, 7), trailing(M, 14)
    nbr7 = np.asarray(A1 @ np.nan_to_num(own7).T).T; nbr7[np.isnan(own7)] = np.nan
    ring2_7 = np.asarray(A2 @ np.nan_to_num(own7).T).T; ring2_7[np.isnan(own7)] = np.nan
    dsl = np.full((T, n), 400.0); cur = np.full(n, 400.0)
    for t in range(T):
        dsl[t] = cur; cur = np.where(L[t], 0.0, np.minimum(cur + 1, 400.0))  # days since last fire, as of yesterday
    # leave-year-out baseline risk: fire-days per cell per year (season days only)
    yrs = sorted(set(years[season]))
    C = np.stack([(L[season & (years == y)]).sum(0) for y in yrs]).astype(float)   # years x cells
    D = np.array([(season & (years == y)).sum() for y in yrs], dtype=float)
    yi = {y: k for k, y in enumerate(yrs)}
    sidx = np.where(season)[0]
    n_rows = len(sidx) * n
    feat_names = DIV_FEATS + ['log_own1', 'log_own7', 'log_own14', 'log_nbr7', 'log_ring2_7', 'log_dsl', 'forest_frac', 'baseline_risk']
    X = np.empty((n_rows, len(feat_names)), dtype=np.float32)
    X[:, :len(DIV_FEATS)] = np.repeat(DIV[sidx], n, axis=0)
    cellblock = lambda a: np.log1p(a[sidx]).reshape(-1).astype(np.float32)
    X[:, len(DIV_FEATS) + 0] = cellblock(own1); X[:, len(DIV_FEATS) + 1] = cellblock(own7); X[:, len(DIV_FEATS) + 2] = cellblock(own14)
    X[:, len(DIV_FEATS) + 3] = cellblock(nbr7); X[:, len(DIV_FEATS) + 4] = cellblock(ring2_7); X[:, len(DIV_FEATS) + 5] = cellblock(dsl)
    X[:, len(DIV_FEATS) + 6] = np.tile(ffrac, len(sidx)).astype(np.float32)
    BR = len(feat_names) - 1
    y = L[sidx].reshape(-1); yr_row = np.repeat(years[sidx], n); day_row = np.repeat(np.arange(len(sidx)), n)
    area_row = np.tile(area, len(sidx))
    print(f'{s} m: {n} cells, {n_rows:,} rows, base rate {y.mean():.4%}, build {time.time()-t0:.0f}s', flush=True)
    out = dict(cells=n, rows=int(n_rows), base_rate=float(y.mean()), mean_cell_km2=float(area.mean()),
               burning_cells_per_fire_day=float(L[sidx].sum(1)[L[sidx].sum(1) > 0].mean()), models={})
    budgets = [10, 25, 50, 100, 200]
    Pk = {m: np.zeros(n_rows, dtype=np.float32) for m in ('ridge', 'lgbm', 'baseline_map', 'own_memory')}
    for Y in yrs:
        te = yr_row == Y; tr = ~te
        # baseline risk, leakage-safe
        brt = np.log((C.sum(0) - C[yi[Y]] + 0.5) / (D.sum() - D[yi[Y]] + 1))
        X[te, BR] = np.tile(brt, int(te.sum() // n))
        for yy in yrs:
            if yy == Y: continue
            m = yr_row == yy
            X[m, BR] = np.tile(np.log((C.sum(0) - C[yi[Y]] - C[yi[yy]] + 0.5) / (D.sum() - D[yi[Y]] - D[yi[yy]] + 1)), int(m.sum() // n))
        good = ~np.isnan(X).any(1)
        sc = StandardScaler().fit(X[tr & good])
        lr = LogisticRegression(C=1.0, max_iter=300).fit(sc.transform(X[tr & good]), y[tr & good])
        Pk['ridge'][te & good] = lr.predict_proba(sc.transform(X[te & good]))[:, 1]
        gb = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=200,
                                subsample=0.8, subsample_freq=1, colsample_bytree=0.8, n_jobs=4, verbose=-1)
        gb.fit(X[tr & good], y[tr & good])
        Pk['lgbm'][te & good] = gb.predict_proba(X[te & good])[:, 1]
        Pk['baseline_map'][te] = X[te, BR]
        Pk['own_memory'][te & good] = X[te & good, len(DIV_FEATS) + 1] + 0.3 * X[te & good, len(DIV_FEATS) + 3]
        print(f'  {s} m year {Y} done {time.time()-t0:.0f}s', flush=True)
    good = ~np.isnan(X).any(1)
    fire_day_mask = L[sidx].sum(1) > 0
    for m, P in Pk.items():
        Pm = P.reshape(len(sidx), n).astype(float)
        r = dict(auc=float(roc_auc_score(y[good], P[good])), pr_auc=float(average_precision_score(y[good], P[good])),
                 brier=float(np.mean((P[good] - y[good]) ** 2)), brier_clim=float(np.mean((y[good].mean() - y[good]) ** 2)))
        r['where_auc_mean'], r['where_auc_median'] = where_auc(Pm, L[sidx], fire_day_mask)
        r['budget'] = budget_metrics(Pm, L[sidx], area, np.ones(len(sidx), bool), budgets)
        out['models'][m] = r
        print(f'  {s} m {m}: auc {r["auc"]:.3f} pr {r["pr_auc"]:.3f} where {r["where_auc_mean"]:.3f} '
              + ' '.join(f'B{b}:R{v["recall"]:.2f}/P{v["precision"]:.3f}' for b, v in r['budget'].items()), flush=True)
    imp = dict(zip(feat_names, gb.feature_importances_.tolist()))
    out['lgbm_importance_last_fold'] = imp
    out['ridge_coef_last_fold'] = dict(zip(feat_names, lr.coef_[0].tolist()))
    np.save(f'pred_{s}.npy', np.stack([Pk['ridge'], Pk['lgbm']]).reshape(2, len(sidx), n).astype(np.float16))
    results[s] = out
    json.dump(results, open('results_cells.json', 'w'), indent=1)
print('done')
