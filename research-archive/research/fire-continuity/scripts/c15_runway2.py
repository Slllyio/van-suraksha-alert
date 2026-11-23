"""Runway map, attempt 2: rank the 36 directions of each front with a model trained directly on 'which way ran farther'.
Per (front, ray) features from the ground ALONG the ray (static layers only; the scar is never used as input):
  distance to the first road / first forest edge (60 m of non-tree) / first crop / first valley floor (10 m below surroundings),
  tree share, grade, ridge/valley, often-burnt share, fuel, slope over 0-300 m and 300-1000 m, ray vs wind,
  momentum: ray vs bearing from the fire's earlier dots to this front (later fronts only),
  hot side: ray vs the FRP-weighted offset of the front's own dots from their centre; ray vs the dots' long axis.
Label = rank of the true reach within the front. LightGBM LambdaRank and a within-front regression, seasons held out.
Scored exactly like c14 (open 40 deg sector vs stop sector; open half vs other half; chance 50%).
Out: results/runway2.json"""
import os, sys, json, numpy as np, pandas as pd, lightgbm as lgb
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import c0_lib as C
R_ = '/mnt/project-files'; HERE = f'{R_}/research/fire-continuity'; BF = f'{R_}/research/big-fires/results'
P0 = pd.read_parquet(f'{C.SCRATCH}/ray_pred_reach.parquet')
O = pd.read_csv(f'{HERE}/results/ray_origins.csv'); O['reach'] = O.reach.apply(lambda s: np.array(json.loads(s.replace('nan', 'NaN'))))
# Leak-free features: sampled from the front's dot centre along the FULL ray (0-2 km), ignoring where the scar starts and where the
# ray is cut by a neighbouring front (both depend on the outcome). Static layers only.
import rasterio
from scipy.ndimage import uniform_filter, binary_dilation
EL = C.ELEV.astype(float); LOC = EL - uniform_filter(EL, 51); SLOPE = C.G['slope']; TREE = C.WC == 10; CROP = np.isin(C.WC, [40, 50])
ROADN = binary_dilation(C.ROAD, iterations=2)
FUEL = rasterio.open(f'{R_}/fuel-map/ratapani/v3/fuel_total_potential_central_10m.tif'); FUELA = FUEL.read(1).astype(float)
FUELA[FUELA == (FUEL.nodata if FUEL.nodata is not None else -1)] = np.nan
BS = {y: C.G[f'burn_start_{y}'] for y in range(2017, 2027)}; PRI = {}
def prior(season):
    if season not in PRI:
        p = np.zeros(EL.shape, np.float32)
        for y in range(2017, season): p += BS[y] > -999
        PRI[season] = p / max(season - 2017, 1)
    return PRI[season]
W6 = pd.read_csv(f'{R_}/ratapani/ee/era5land_06utc.csv', parse_dates=['time']); W6['date'] = W6.time.dt.normalize(); W6 = W6.set_index('date')
S = np.arange(20, 2001, 20.0); rows = []
for o in O.itertuples():
    PR = prior(int(o.season))
    for j in range(36):
        az = np.radians(j * 10); X = o.x + S * np.sin(az); Y = o.y + S * np.cos(az)
        rr, cc = C.rc_of(X, Y); rr = np.clip(rr, 0, C.NR - 1); cc = np.clip(cc, 0, C.NC - 1)
        tr = TREE[rr, cc]; nt3 = np.r_[[not tr[i:i + 3].any() for i in range(len(S) - 2)], False, False]
        fx = np.floor((X - FUEL.transform.c) / FUEL.transform.a).astype(int); fy = np.floor((Y - FUEL.transform.f) / FUEL.transform.e).astype(int)
        okf = (fy >= 0) & (fy < FUELA.shape[0]) & (fx >= 0) & (fx < FUELA.shape[1]); fu = np.full(len(S), np.nan); fu[okf] = FUELA[fy[okf], fx[okf]]
        el = EL[rr, cc]; gr = np.gradient(el, 20)
        fd = lambda m: float(S[np.argmax(m)]) if m.any() else 4000.0
        rec = dict(origin=o.origin, ray=j, d_road=fd(ROADN[rr, cc]), d_edge=fd(nt3), d_crop=fd(CROP[rr, cc]), d_valley=fd(LOC[rr, cc] < -10))
        for lo, hi in [(0, 300), (300, 1000)]:
            m = (S > lo) & (S <= hi)
            rec.update({f'tree_{lo}_{hi}': tr[m].mean(), f'grade_{lo}_{hi}': gr[m].mean(), f'local_height_{lo}_{hi}': LOC[rr, cc][m].mean(),
                        f'prior_burns_{lo}_{hi}': PR[rr, cc][m].mean(), f'fuel_{lo}_{hi}': np.nanmean(fu[m]) if np.isfinite(fu[m]).any() else np.nan,
                        f'slope_{lo}_{hi}': SLOPE[rr, cc][m].mean()})
        rec['downwind'] = np.cos(az - np.radians(o.wind_to)) if np.isfinite(o.wind_to) else np.nan
        rows.append(rec)
F = pd.DataFrame(rows)
# momentum and hot side from the dots (same origin rules as c10)
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis']
def clusters(xy):
    if len(xy) == 1: return np.zeros(1, int)
    p = np.array(list(cKDTree(xy).query_pairs(750.0)))
    if len(p) == 0: return np.arange(len(xy))
    return connected_components(coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy),) * 2), directed=False)[1]
ext = {}
for fire, d in A.groupby('fire'):
    if fire not in set(O.fire): continue
    d = C.viirs_looks(d).reset_index(drop=True); oi = 0
    for k in sorted(d.lk.unique()):
        g = d[d.lk == k]; prev = d[d.lk < k]
        if k > 0:
            dp = cKDTree(prev[['x', 'y']].values).query(g[['x', 'y']].values)[0]; g = g[dp > 750]
        if not len(g): continue
        lab = clusters(g[['x', 'y']].values)
        for c in np.unique(lab):
            gg = g[lab == c]; cx, cy = gg.x.mean(), gg.y.mean()
            w = gg.frp.clip(lower=.1).values; hx, hy = (w * gg.x).sum() / w.sum() - cx, (w * gg.y).sum() / w.sum() - cy
            mom = np.degrees(np.arctan2(cx - prev.x.mean(), cy - prev.y.mean())) if len(prev) else np.nan
            if len(gg) >= 3:
                Mx = np.cov(np.c_[gg.x - cx, gg.y - cy].T); wv, vv = np.linalg.eigh(Mx); ax = np.degrees(np.arctan2(vv[0, 1], vv[1, 1])); el = np.sqrt(wv[1] / max(wv[0], 1))
            else: ax, el = np.nan, 1.0
            ext[f'{fire}_{oi}'] = dict(mom=mom, hot_b=np.degrees(np.arctan2(hx, hy)), hot_m=np.hypot(hx, hy), ax=ax, el=el); oi += 1
E = pd.DataFrame(ext).T; F = F.join(E, on='origin')
az = F.ray * 10
F['momentum'] = np.cos(np.radians(az - F.mom)); F['hot_side'] = np.cos(np.radians(az - F.hot_b)) * np.minimum(F.hot_m, 300) / 300
F['along_dots'] = np.abs(np.cos(np.radians(az - F.ax))) * np.log(F.el)
F['old_hazard_reach'] = P0.full.reindex(pd.MultiIndex.from_frame(F[['origin', 'ray']])).values
# labels
act = {(o.origin, j): r for o in O.itertuples() for j, r in enumerate(o.reach) if np.isfinite(r)}
O['censored'] = O.censored.apply(lambda s: json.loads(s.lower()))
cen = {(o.origin, j): c for o in O.itertuples() for j, c in enumerate(o.censored)}
F['reach'] = [act.get((o, r), np.nan) for o, r in zip(F.origin, F.ray)]
F['cens'] = [cen.get((o, r), True) for o, r in zip(F.origin, F.ray)]
F = F.merge(O[['origin', 'season', 'fire', 'kind']], on='origin')
F = F[F.groupby('origin').reach.transform('count') >= 30].dropna(subset=['reach']).copy()
F['rel'] = F.groupby('origin').reach.transform(lambda r: pd.qcut(r.rank(method='first'), 5, labels=False))
F['yc'] = np.log1p(F.reach) - F.groupby('origin').reach.transform(lambda r: np.log1p(r).mean())
FEAT_SETS = {'ground along ray': [c for c in F.columns if c.startswith(('d_', 'tree_', 'grade_', 'local_height_', 'prior_burns_', 'fuel_', 'slope_'))] + ['downwind'],
             'dots only (momentum, hot side, dot axis)': ['momentum', 'hot_side', 'along_dots'],
             'ground + dots': None}
FEAT_SETS['ground + dots'] = FEAT_SETS['ground along ray'] + FEAT_SETS['dots only (momentum, hot side, dot axis)']
F = F.sort_values(['origin', 'ray']).reset_index(drop=True)
preds = {}
for name, cols in FEAT_SETS.items():
    for kind in ['rank', 'reg']:
        p = np.zeros(len(F))
        for s in sorted(F.season.unique()):
            tr, te = (F.season != s).values, (F.season == s).values
            Xtr = F.loc[tr, cols].astype(float); Xte = F.loc[te, cols].astype(float)
            if kind == 'rank':
                m = lgb.LGBMRanker(n_estimators=300, learning_rate=.03, num_leaves=15, min_child_samples=100, subsample=.8, subsample_freq=1, colsample_bytree=.8, verbose=-1)
                m.fit(Xtr, F.rel[tr], group=F[tr].groupby('origin', sort=False).size().values)
            else:
                m = lgb.LGBMRegressor(n_estimators=300, learning_rate=.03, num_leaves=15, min_child_samples=100, subsample=.8, subsample_freq=1, colsample_bytree=.8, verbose=-1).fit(Xtr, F.yc[tr])
            p[te] = m.predict(Xte)
        preds[f'{name} | {kind}'] = p
preds['old hazard model (c14; ray cut by neighbours and scar entry, so partly leaky)'] = F.old_hazard_reach.values
# tree rule as in c14 = mean tree share over first 500 m: rebuild from ST
preds['most tree cover (c14 rule)'] = F['tree_0_300'].values + F['tree_300_1000'].values   # leak-free version of the c14 rule
rng = np.random.default_rng(0); out = {}
def score(pv, g, real_only=False):
    rows = []
    for oid, gi in g.groupby('origin'):
        if len(gi) < 36: continue
        r = gi.reach.values.astype(float); v = pv[gi.index.values]
        if real_only: r = np.where(gi.cens.values, np.nan, r)   # rays cut by a neighbouring front / window: reach unknown
        if not np.isfinite(v).all() or np.ptp(v) == 0: continue
        import warnings; warnings.simplefilter('ignore')
        sr, sp = np.nanmean(r.reshape(9, 4), 1), v.reshape(9, 4).mean(1); a, b = np.argmax(sp), np.argmin(sp)
        if not (np.isfinite(sr[a]) and np.isfinite(sr[b])): continue
        hv = np.array([v[np.arange(k, k + 18) % 36].mean() for k in range(36)]); k = int(np.argmax(hv))
        rows.append((gi.fire.iloc[0], sr[a] > sr[b], np.nanmean(r[np.arange(k, k + 18) % 36]) > np.nanmean(r[np.arange(k + 18, k + 36) % 36]), sr[a] > 500, sr[b] > 500))
    Rr = pd.DataFrame(rows, columns=['fire', 'sec', 'half', 'o500', 's500']); fr = Rr.fire.values; u = np.unique(fr); bs = []
    for _ in range(1000):
        s = rng.choice(u, len(u)); m = np.concatenate([np.where(fr == f)[0] for f in s]); bs.append(Rr.sec.values[m].mean())
    return dict(n=len(Rr), open_sector_farther=[round(Rr.sec.mean(), 3), round(float(np.quantile(bs, .025)), 3), round(float(np.quantile(bs, .975)), 3)],
                open_half_farther=round(Rr.half.mean(), 3), open_past500=round(Rr.o500.mean(), 3), stop_past500=round(Rr.s500.mean(), 3))
for setn, g in [('all fronts', F), ('first-alert fronts', F[F.kind == 'first'])]:
    out[setn] = {k: score(v, g) for k, v in preds.items()}
    out[setn + ' | real stops only'] = {k: score(v, g, True) for k, v in preds.items()}
print(json.dumps(out, indent=1)); json.dump(out, open(f'{HERE}/results/runway2.json', 'w'), indent=1)
