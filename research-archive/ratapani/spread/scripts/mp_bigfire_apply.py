"""Apply the final 24 h burn-scar map to big UNSEEN fires across Madhya Pradesh (Akkshay Oct 19 09:30Z).
Fires: day-events with a history scar >= 200 ha (status scar / scar_faint), outside Ratapani (+5 km); VIIRS alerts within 3 km and
-3..+10 days of the seed event, single-linked at 750 m, cluster holding the seed; >= 4 VIIRS looks and >= 10 alerts. Each event used once.
Outline = union of the cluster's history scars (read_hist_geom). Timing truth = straight-line blend of VIIRS looks (as s2_statewide).
Forecast at every VIIRS look: blocks (265 m) + area, nearest-first.
  rule    : 24.1 ha x active fronts
  learned : learned 24 h area (section 17 model, trained on ALL Ratapani forecasts, never on these fires)
(Prithvi grids cover Ratapani only, so the order here is nearest-first; scene days are scored separately in section 16.)
  python3 mp_bigfire_apply.py [NFIRES]
"""
import os, sys, json, pickle, numpy as np, pandas as pd, lightgbm as lgb
from rasterio.transform import from_origin
from rasterio import features
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely import wkt
from shapely.geometry import shape, mapping
from shapely.ops import unary_union, transform as stransform
from pyproj import Transformer
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, '/mnt/project-files/fire-alert-scars/mp/scripts'); from read_geom import read_hist_geom
NF = int(sys.argv[1]) if len(sys.argv) > 1 else 600; MO = '/mnt/project-files/fire-alert-scars/mp/out'; OUT = os.environ.get('OUT', '/tmp/claude-0/mpbig'); os.makedirs(OUT, exist_ok=True)
MED = 24.1; LINK = 750.0; RES = 20.0
to43 = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True).transform
so = lambda a, b: 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)
def clusters(xy):
    if len(xy) == 1: return np.zeros(1, int)
    p = np.array(list(cKDTree(xy).query_pairs(LINK)))
    if len(p) == 0: return np.arange(len(xy))
    return connected_components(coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy), len(xy))), directed=False)[1]
# ---- area model trained on all Ratapani forecasts
R = pd.read_csv('/tmp/claude-0/unseen/area_model.csv')
FEAT = ['doy', 'hour', 'n_dots', 'n_last', 'n_prev', 'n_fronts', 'n_act', 'age_h', 'gap_h', 'frp_last', 'frp_max', 'frp_all', 'ext_x', 'ext_y', 'foot_ha', 'day', 'sats_last']
AM = lgb.LGBMRegressor(n_estimators=300, learning_rate=.03, num_leaves=15, min_child_samples=30, n_jobs=1, verbose=-1).fit(R[FEAT], np.log1p(R.extra_true_ha))
# ---- alerts and seeds
A = pd.read_csv(f'{MO}/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'instrument', 'frp', 'daynight', 'sensor', 'event_id'])
A = A[A.instrument == 'VIIRS'].copy()
A['t'] = pd.to_datetime(A.acq_date + ' ' + A.acq_time.astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
A['x'], A['y'] = to43(A.longitude.values, A.latitude.values); A = A.reset_index(drop=True); AT = cKDTree(A[['x', 'y']].values)
aoi = unary_union([shape(f['geometry']) for f in json.load(open('/mnt/project-files/ratapani/ratapani_aoi.geojson'))['features']])
aoi = stransform(lambda x, y, z=None: to43(x, y), aoi).buffer(5000)
S = pd.read_csv(f'{MO}/scars_mp_hist.csv', usecols=['event_id', 'status', 'scar_ha']); S = S[S.status.isin(['scar', 'scar_faint'])]
SMIN, SMAX = float(os.environ.get('SMIN', 200)), float(os.environ.get('SMAX', 1e9)); MINLK, MINAL = int(os.environ.get('MINLK', 4)), int(os.environ.get('MINAL', 10))
big = S[(S.scar_ha >= SMIN) & (S.scar_ha < SMAX)].event_id   # small-fire pass: SMIN=20 SMAX=200 MINLK=2 MINAL=3
ev = A[A.event_id.isin(big)].groupby('event_id').agg(x=('x', 'mean'), y=('y', 'mean'), t0=('t', 'min'), n=('t', 'size')).reset_index()
import shapely; ev = ev[~shapely.contains_xy(aoi, ev.x.values, ev.y.values)]
ev = ev.sample(frac=1, random_state=0).reset_index(drop=True)
print('big seed events outside Ratapani', len(ev), flush=True)
G = read_hist_geom(); G = G[G.event_id.isin(S.event_id)].set_index('event_id').geometry
used = set(); fires = []
for r in ev.itertuples():
    if r.event_id in used: continue
    near = A.iloc[AT.query_ball_point([r.x, r.y], 3000)]
    near = near[(near.t >= r.t0 - pd.Timedelta(days=3)) & (near.t <= r.t0 + pd.Timedelta(days=10))].reset_index(drop=True)
    lab = clusters(near[['x', 'y']].values); keep = set(lab[(near.event_id == r.event_id).values])
    d = near[np.isin(lab, list(keep))].sort_values('t').reset_index(drop=True)
    evs = set(d.event_id.unique())
    if evs & used: continue
    d['lk'] = (d.t.diff().dt.total_seconds().fillna(1e9) > 7200).cumsum() - 1
    if d.lk.max() + 1 < MINLK or len(d) < MINAL: continue
    used |= evs; fires.append((r.event_id, d, [e for e in evs if e in G.index]))
    if len(fires) >= NF: break
print('fires', len(fires), flush=True)
pickle.dump(fires, open(f'{OUT}/fires_list.pkl', 'wb'))
GEO = {e: G[e] for _, _, es in fires for e in es}


def one(arg):
    seed, d, es = arg
    try:
        geoms = [wkt.loads(GEO[e]) for e in es]
        poly = stransform(lambda x, y, z=None: to43(x, y), unary_union(geoms))
        xs = np.r_[d.x, poly.bounds[0], poly.bounds[2]]; ys = np.r_[d.y, poly.bounds[1], poly.bounds[3]]
        x0, x1, y0, y1 = xs.min() - 800, xs.max() + 800, ys.min() - 800, ys.max() + 800
        if x1 - x0 > 15000 or y1 - y0 > 15000: return [dict(seed=seed, skip='too big')]
        W, H = int((x1 - x0) / RES), int((y1 - y0) / RES); tr = from_origin(x0, y1, RES, RES)
        dom = features.rasterize([(mapping(poly), 1)], out_shape=(H, W), transform=tr).astype(bool).ravel()
        rr, cc = np.mgrid[0:H, 0:W]; Px = np.c_[(x0 + (cc + .5) * RES).ravel(), (y1 - (rr + .5) * RES).ravel()]
        tl = d.groupby('lk').t.min(); T0 = tl.iloc[0]; th = ((tl - T0).dt.total_seconds() / 3600).values
        Dk = np.stack([np.maximum(cKDTree(d[d.lk == k][['x', 'y']].values).query(Px[dom])[0] - 265, 0) for k in tl.index], 1)
        w = 1 / (Dk + 50) ** 4; w /= w.sum(1, keepdims=True); Tg = np.full(len(Px), np.inf); Tg[dom] = (w * th[None]).sum(1)
        out = []
        for k in tl.index[:-1]:            # forecasts at every look that has a later look
            kn = d[d.lk <= k]; xy = kn[['x', 'y']].values; lab = clusters(xy); last = kn[kn.lk == k]; prev = kn[kn.lk == k - 1]; tk = kn.t.max()
            act = set(lab[(kn.lk >= k - 1).values]); nact = len(act); truth = dom & (Tg <= th[k] + 24)
            dd = cKDTree(xy).query(Px)[0]; foot = dd <= 265; ext = xy.max(0) - xy.min(0)
            f = dict(doy=tk.dayofyear, hour=tk.hour, n_dots=len(xy), n_last=len(last), n_prev=len(prev), n_fronts=len(set(lab)), n_act=nact,
                     age_h=(tk - kn.t.min()).total_seconds() / 3600, gap_h=(tk - prev.t.max()).total_seconds() / 3600 if len(prev) else -1,
                     frp_last=last.frp.sum(), frp_max=last.frp.max(), frp_all=kn.frp.sum(), ext_x=ext[0], ext_y=ext[1], foot_ha=foot.sum() * .04,
                     day=int((last.daynight == 'D').any()), sats_last=last.sensor.nunique())
            la = float(np.expm1(AM.predict(pd.DataFrame([f])[FEAT]))[0])
            order = np.argsort(np.where(foot, -1, dd), kind='stable')
            def m(ha): s = np.zeros(len(Px), bool); s[order[:int(foot.sum() + ha / .04)]] = True; return s
            mR, mL = m(MED * nact), m(la); mO = m((truth & ~foot).sum() * .04)
            out.append(dict(seed=seed, k=int(k), n_looks=len(tl), t=str(tk), x=float(xy[:, 0].mean()), y=float(xy[:, 1].mean()), scar_ha=dom.sum() * .04,
                            truth_ha=truth.sum() * .04, rule_ha=MED * nact, learned_ha=la, true_extra_ha=(truth & ~foot).sum() * .04,
                            rule=so(mR, truth), learned=so(mL, truth), oracle=so(mO, truth), blocks_only=so(foot, truth), **f))
        pickle.dump(dict(seed=seed, box=(x0, y1, W, H), dom=dom.reshape(H, W), Tg=Tg.reshape(H, W).astype(np.float32), th=th, d=d, poly=poly),
                    open(f'{OUT}/fire_{seed}.pkl', 'wb'))
        return out
    except Exception as e:
        return [dict(seed=seed, skip='error ' + str(e)[:80])]


rows = []
with ThreadPoolExecutor(8) as ex:     # threads: LightGBM hangs in forked workers
    for i, o in enumerate(ex.map(one, fires)):
        rows += o
        if i % 50 == 0: print(i, len(fires), flush=True)
Rr = pd.DataFrame(rows); Rr.to_csv(f'{OUT}/mp_bigfire_rows.csv', index=False)
U = Rr[Rr.skip.isna()] if 'skip' in Rr else Rr
fm = U.groupby('seed')[['rule', 'learned', 'oracle', 'blocks_only']].mean()
rng = np.random.default_rng(0); dl = (fm.learned - fm.rule).values
res = dict(fires=int(U.seed.nunique()), forecasts=len(U), skipped=Rr.skip.value_counts().to_dict() if 'skip' in Rr else {},
           mean_by_fire=fm.mean().round(4).to_dict(), median_forecast=U[['rule', 'learned', 'oracle']].median().round(4).to_dict(),
           learned_minus_rule_ci=[round(float(np.percentile([dl[rng.integers(0, len(dl), len(dl))].mean() for _ in range(2000)], q)), 4) for q in (2.5, 97.5)],
           better_worse=[int((dl > .005).sum()), int((dl < -.005).sum())],
           median_ha=dict(rule=float(U.rule_ha.median()), learned=float(U.learned_ha.median()), true=float(U.true_extra_ha.median())),
           by_year=U.assign(yr=U.t.str[:4]).groupby('yr')[['rule', 'learned']].mean().round(3).to_dict('index'))
json.dump(res, open(f'{OUT}/mp_bigfire.json', 'w'), indent=1); print(json.dumps(res, indent=1))
