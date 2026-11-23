"""Run the calibrated spread forecast for any moment.
  python3 forecast.py <issue time UTC, e.g. 2026-03-20T09:00> <out.geojson> [alerts_dir]
Uses only VIIRS points (S-NPP, NOAA-20, NOAA-21) up to the issue time. For every fire seen in the last 36 h, writes 150 m
squares within 2 km with p12 / p24 / p48 = calibrated chance the cell burns within 12 / 24 / 48 h (cells already inside a
detection footprint of this fire are marked burned=1)."""
import pandas as pd, numpy as np, glob, json, sys, pickle, lightgbm as lgb
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from pyproj import Transformer
T_ISSUE = pd.Timestamp(sys.argv[1]); OUT = sys.argv[2]
AD = sys.argv[3] if len(sys.argv) > 3 else '/mnt/project-files/fire-alert-scars/alerts'
M = '/mnt/project-files/research/spread-review/forecast_burn/'
F = ['d_all', 'd_last', 'd_first', 'd_old', 'n_old500', 'proj', 'perp', 'mom_len', 'n_seen', 'n_last', 'looks_seen', 'frp_last', 'frp_max',
     'h_since_first', 'h_since_last', 'silent', 'next_night', 'doy', 'elev_rel', 'slope', 'wc']
LAT, RAD = 150.0, 2000.0
TO = Transformer.from_crs(4326, 32643, always_xy=True); BACK = Transformer.from_crs(32643, 4326, always_xy=True)
yr = T_ISSUE.year
A = pd.concat([pd.read_csv(f) for f in glob.glob(f'{AD}/viirs-*_{yr}.csv')])
A['t'] = pd.to_datetime(A.acq_date) + pd.to_timedelta(A.acq_time // 100, 'h') + pd.to_timedelta(A.acq_time % 100, 'm')
A = A[A.t <= T_ISSUE].sort_values('t').reset_index(drop=True)
A['x'], A['y'] = TO.transform(A.longitude.values, A.latitude.values)
loc = A.t + pd.Timedelta(hours=5.5)
A['look'] = np.where(A.daynight == 'D', loc.dt.strftime('%Y-%m-%d') + 'D', (loc - pd.Timedelta(hours=6)).dt.strftime('%Y-%m-%d') + 'N')
th = (A.t - A.t.min()).dt.total_seconds().values / 3600; Pn = np.c_[A.x, A.y, th * 40.0]
pr = cKDTree(Pn).query_pairs(1200 * np.sqrt(2), output_type='ndarray'); d = np.abs(Pn[pr[:, 0]] - Pn[pr[:, 1]])
pr = pr[(np.hypot(d[:, 0], d[:, 1]) <= 1200) & (d[:, 2] <= 1200)]
_, A['fire'] = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(A), len(A))), directed=False)
looks = sorted(A.look.unique()); li = {l: i for i, l in enumerate(looks)}; A['si'] = A.look.map(li)
# issue slot = last look at or before the issue time; silent looks counted in 12 h steps
G = np.load('/mnt/project-files/ratapani/spread/data_shared/grid20.npz'); TR = G['transform']
def sample(arr, x, y):
    c = ((x - TR[2]) / TR[0]).astype(int); r = ((y - TR[5]) / TR[4]).astype(int)
    ok = (r >= 0) & (r < arr.shape[0]) & (c >= 0) & (c < arr.shape[1]); o = np.full(len(x), np.nan, np.float32); o[ok] = arr[r[ok], c[ok]]; return o
models = {y: (lgb.Booster(model_file=M + f'model_{y}.txt'), pickle.load(open(M + f'iso_{y}.pkl', 'rb'))) for y in ('y12', 'y24', 'y48')}
feats = []
for f, g in A.groupby('fire'):
    h_last = (T_ISSUE - g.t.max()).total_seconds() / 3600
    if h_last > 36: continue
    first = g[g.si == g.si.min()]; last = g[g.si == g.si.max()]
    xs = np.arange(g.x.min() - RAD, g.x.max() + RAD, LAT); ys = np.arange(g.y.min() - RAD, g.y.max() + RAD, LAT)
    X, Y = np.meshgrid(xs, ys); X, Y = X.ravel(), Y.ravel()
    d_all = cKDTree(g[['x', 'y']].values).query(np.c_[X, Y])[0]; k = d_all <= RAD; X, Y, d_all = X[k], Y[k], d_all[k]
    old = A[(A.t < g.t.min() - pd.Timedelta(days=2)) & (A.fire != f)]
    vx, vy = last.x.mean() - first.x.mean(), last.y.mean() - first.y.mean(); vl = np.hypot(vx, vy)
    ux, uy = (vx / vl, vy / vl) if vl > 1 else (0.0, 0.0); dx, dy = X - last.x.mean(), Y - last.y.mean()
    R = pd.DataFrame(dict(fire=f, x=X, y=Y, d_all=d_all, d_last=cKDTree(last[['x', 'y']].values).query(np.c_[X, Y])[0],
        d_first=cKDTree(first[['x', 'y']].values).query(np.c_[X, Y])[0],
        d_old=cKDTree(old[['x', 'y']].values).query(np.c_[X, Y])[0] if len(old) else 6000.0,
        n_old500=[len(v) for v in cKDTree(old[['x', 'y']].values).query_ball_point(np.c_[X, Y], 500)] if len(old) else 0,
        proj=dx * ux + dy * uy, perp=np.abs(-dx * uy + dy * ux) if vl > 1 else np.hypot(dx, dy), mom_len=vl, n_seen=len(g), n_last=len(last),
        looks_seen=g.si.nunique(), frp_last=last.frp.sum(), frp_max=g.frp.max(),
        h_since_first=(T_ISSUE - g.t.min()).total_seconds() / 3600, h_since_last=h_last, silent=int(round(h_last / 12)),
        next_night=int(((T_ISSUE + pd.Timedelta(hours=5.5)).hour >= 14) or ((T_ISSUE + pd.Timedelta(hours=5.5)).hour < 2)),
        doy=T_ISSUE.dayofyear, elev_rel=sample(G['elev'], X, Y) - np.nanmean(sample(G['elev'], last.x.values, last.y.values)),
        slope=sample(G['slope'], X, Y), wc=sample(G['wc'], X, Y)))
    hx = g.scan.fillna(0.375).values * 500 if 'scan' in g else np.full(len(g), 187.5)
    hy = g.track.fillna(0.375).values * 500 if 'track' in g else np.full(len(g), 187.5)
    R['burned'] = ((np.abs(X[:, None] - g.x.values[None]) <= hx[None]) & (np.abs(Y[:, None] - g.y.values[None]) <= hy[None])).any(1).astype(int)
    feats.append(R)
if not feats:
    json.dump({'type': 'FeatureCollection', 'features': []}, open(OUT, 'w')); print('no active fires'); sys.exit()
R = pd.concat(feats)
for y, (b, iso) in models.items():
    R['p' + y[1:]] = np.where(R.burned == 1, np.nan, iso.predict(b.predict(R[F].astype(np.float32))))
R = R[(R.burned == 1) | (R.p48 >= 0.02)]
fs = []
for r in R.itertuples():
    xs_, ys_ = [r.x - 75, r.x + 75, r.x + 75, r.x - 75, r.x - 75], [r.y - 75, r.y - 75, r.y + 75, r.y + 75, r.y - 75]
    lo, la = BACK.transform(xs_, ys_)
    fs.append({'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [list(map(list, zip(np.round(lo, 6), np.round(la, 6))))]},
               'properties': {'fire': int(r.fire), 'burned': int(r.burned), **{k: (None if np.isnan(getattr(r, k)) else round(float(getattr(r, k)), 3)) for k in ('p12', 'p24', 'p48')}}})
json.dump({'type': 'FeatureCollection', 'issue_time_utc': str(T_ISSUE), 'features': fs}, open(OUT, 'w'))
print(len(fs), 'cells for', R.fire.nunique(), 'active fires ->', OUT)
