"""Independent test of the chance maps against mid-fire Sentinel-2/Landsat photos (burned-so-far at an exact minute,
fuel thread's chips), which never touch the VIIRS dots used to build the labels.
For each photo: issue a forecast at the last satellite look >= 1 h before the photo (lead <= 24 h), with only the dots seen by then,
using the model trained WITHOUT that season. Score the scar pixels not already inside a seen VIIRS footprint:
did they burn by photo time? Methods: chance map (arrival-label and raw-dot models), 600 m ring, persistence, nearest-latest.
Out: photo_test/scene_scores.parquet, photo_test/summary.json"""
import pandas as pd, numpy as np, glob, os, sys, json, rasterio, lightgbm as lgb
from scipy.spatial import cKDTree
from sklearn.metrics import roc_auc_score
S = sys.argv[1]; OUT = sys.argv[2]; MODE = sys.argv[3] if len(sys.argv) > 3 else 'scar';  # scar = only pixels of the final scar; chip/far = also every pixel of the photo box outside the final scar (counted unburned)
TD = '/mnt/project-files/fuel-map/ratapani/timing/'
F = ['d_all', 'd_last', 'd_first', 'd_old', 'n_old500', 'proj', 'perp', 'mom_len', 'n_seen', 'n_last', 'looks_seen', 'frp_last', 'frp_max',
     'h_since_first', 'h_since_last', 'silent', 'next_night', 'doy', 'elev_rel', 'slope', 'wc']
with rasterio.open('/mnt/project-files/research/ratapani-burn-labels/rasters/burn_2017.tif') as r: TRB = r.transform
G = np.load('/mnt/project-files/ratapani/spread/data_shared/grid20.npz'); TR = G['transform']; ELEV, SLOPE, WC = G['elev'], G['slope'], G['wc']
def sample(arr, x, y):
    c = ((x - TR[2]) / TR[0]).astype(int); r = ((y - TR[5]) / TR[4]).astype(int)
    ok = (r >= 0) & (r < arr.shape[0]) & (c >= 0) & (c < arr.shape[1]); o = np.full(len(x), np.nan, np.float32); o[ok] = arr[r[ok], c[ok]]; return o
A = pd.read_parquet(S + '/tracks.parquet'); P = pd.read_parquet(S + '/passes.parquet')
A['scan'] = A.scan.fillna(0.375).clip(lower=0.3); A['track'] = A.track.fillna(0.375).clip(lower=0.3)
slots = pd.DataFrame({'look': sorted(set(P.look) | set(A.look))})
slots['t'] = slots.look.map(P.groupby('look').t.min()).fillna(slots.look.map(A.groupby('look').t.min()))
slots = slots.sort_values('t').reset_index(drop=True); sidx = dict(zip(slots.look, slots.index))
A['si'] = A.look.map(sidx); A['yr'] = A.t.dt.year; tree = cKDTree(A[['x', 'y']].values)
ms = pd.read_parquet(TD + 'midscar.parquet'); ms = ms[ms.status == 'ok']
MD = {}
def model(tag, y, s):
    k = (tag, y, s)
    if k not in MD: MD[k] = lgb.Booster(model_file=f'{S}/loso_models/{tag}_{y}_{s}.txt')
    return MD[k]
def auc(y, p):
    return roc_auc_score(y, p) if 0 < y.sum() < len(y) else np.nan
rows = []; PX = []
for f in sorted(glob.glob(TD + 'chips/*.npz')):
    b = os.path.basename(f); ev = int(b.split('_')[0]); sc = b[len(str(ev)) + 1:-4]
    m = ms[(ms.event == ev) & (ms.scene.str[:40] == sc)]
    if not len(m) or m.iloc[0].season > 2024: continue
    m = m.iloc[0]; z = np.load(f); Sm, bym, ok = z['S'], z['bym'], z['ok']; i0, j0 = int(z['i0']), int(z['j0'])
    rr, cc = np.where((Sm & ok) if MODE == 'scar' else ((Sm & ok) | ~Sm))
    if MODE != 'scar' and len(rr) > 6000: kk = np.random.default_rng(ev).choice(len(rr), 6000, replace=False); rr, cc = rr[kk], cc[kk]
    if len(rr) < 20: continue
    xs, ys = rasterio.transform.xy(TRB, rr + i0, cc + j0); X, Y = np.array(xs), np.array(ys)
    near = np.unique(np.concatenate(tree.query_ball_point(np.c_[X[::5], Y[::5]], 1000)))
    if not len(near): continue
    d = A.iloc[near]; d = d[(d.t >= m.t_first - pd.Timedelta(hours=26)) & (d.t <= m.t_last + pd.Timedelta(hours=26))]
    if not len(d): continue
    fire = d.fire.value_counts().index[0]; g = A[A.fire == fire]; T = m['T']
    cand = [s for s in range(g.si.min(), g.si.max() + 3) if s < len(slots) and slots.t[s] <= T - pd.Timedelta(hours=1)]
    if not cand: continue
    s = max(cand); t_issue = slots.t[s]; lead = (T - t_issue).total_seconds() / 3600
    if lead > 24: continue
    seen = g[g.si <= s]
    if not len(seen): continue
    last = seen[seen.si == seen.si.max()]; first = seen[seen.si == seen.si.min()]
    # drop pixels already inside a footprint seen by issue time (known burning)
    inside = ((np.abs(X[:, None] - seen.x.values[None]) <= seen.scan.values[None] * 500) &
              (np.abs(Y[:, None] - seen.y.values[None]) <= seen.track.values[None] * 500)).any(1)
    ins_n, ins_b = int(inside.sum()), int((bym[rr, cc] & Sm[rr, cc])[inside].sum())
    X, Y, obs = X[~inside], Y[~inside], (bym[rr, cc] & Sm[rr, cc])[~inside]
    if len(X) < 20 or obs.sum() == 0 or obs.all(): continue
    yr = int(g.yr.iloc[0])
    old = A[(A.yr == yr) & (A.si < s - 4) & (A.fire != fire) & (abs(A.x - seen.x.mean()) < 6000) & (abs(A.y - seen.y.mean()) < 6000)]
    vx, vy = last.x.mean() - first.x.mean(), last.y.mean() - first.y.mean(); vl = np.hypot(vx, vy)
    ux, uy = (vx / vl, vy / vl) if vl > 1 else (0.0, 0.0); dx, dy = X - last.x.mean(), Y - last.y.mean()
    R = pd.DataFrame(dict(d_all=cKDTree(seen[['x', 'y']].values).query(np.c_[X, Y])[0], d_last=cKDTree(last[['x', 'y']].values).query(np.c_[X, Y])[0],
        d_first=cKDTree(first[['x', 'y']].values).query(np.c_[X, Y])[0],
        d_old=cKDTree(old[['x', 'y']].values).query(np.c_[X, Y])[0] if len(old) else 6000.0,
        n_old500=[len(v) for v in cKDTree(old[['x', 'y']].values).query_ball_point(np.c_[X, Y], 500)] if len(old) else 0,
        proj=dx * ux + dy * uy, perp=np.abs(-dx * uy + dy * ux) if vl > 1 else np.hypot(dx, dy), mom_len=vl, n_seen=len(seen), n_last=len(last),
        looks_seen=seen.si.nunique(), frp_last=last.frp.sum(), frp_max=seen.frp.max(),
        h_since_first=(t_issue - g.t.min()).total_seconds() / 3600, h_since_last=(t_issue - last.t.max()).total_seconds() / 3600,
        silent=int(s - seen.si.max()), next_night=int(slots.look[min(s + 1, len(slots) - 1)].endswith('N')), doy=t_issue.dayofyear,
        elev_rel=sample(ELEV, X, Y) - np.nanmean(sample(ELEV, last.x.values, last.y.values)), slope=sample(SLOPE, X, Y), wc=sample(WC, X, Y)))
    if MODE == 'far':   # only ground at least 450 m from every dot seen so far: new ground, not ash behind the dots
        kf = R.d_all.values >= 450; R, obs = R[kf].reset_index(drop=True), obs[kf]
        if len(R) < 20 or obs.sum() == 0 or obs.all(): continue
    yh = 'y12' if lead <= 12 else 'y24'
    sc_ = dict(arr=model('arr', yh, yr).predict(R[F].astype(np.float32)), raw=model('raw', yh, yr).predict(R[F].astype(np.float32)),
               ring=-np.abs(R.d_last.values - 600), persist=-R.d_all.values, nearest_latest=-R.d_last.values)
    res = dict(inside_px=ins_n, inside_burned=ins_b, event=ev, scene=sc, season=yr, lead_h=lead, n_px=len(X), share_burned=float(obs.mean()))
    k = int(obs.sum())
    for name, p in sc_.items():
        res['auc_' + name] = auc(obs, p)
        top = np.argsort(-p, kind='stable')[:k]; res['found_' + name] = float(obs[top].mean())   # equal-area: pick as many pixels as truly burned
    rows.append(res)
    if os.environ.get('DUMP'):   # pixel rows for the photo-calibrated map (h3)
        dd = np.hypot(X[:, None] - seen.x.values[None], Y[:, None] - seen.y.values[None]); kern = np.exp(-dd / 400).sum(1)
        prevd = seen[seen.si < seen.si.max()]; cosg = np.zeros(len(X))
        if len(prevd):   # growth bearing: centre of earlier dots -> centre of the latest look's dots
            gx, gy = last.x.mean() - prevd.x.mean(), last.y.mean() - prevd.y.mean(); gl = np.hypot(gx, gy)
            if gl > 100:
                px, py = X - prevd.x.mean(), Y - prevd.y.mean(); cosg = (px * gx + py * gy) / (np.hypot(px, py) * gl + 1e-9)
        PX.append(R.assign(x=X, y=Y, kern=kern, cosg=cosg, has_dir=int(len(prevd) > 0), obs=obs.astype(np.int8), season=yr, event=ev, scene=sc, lead_h=lead, arr=sc_['arr']))
X_ = pd.DataFrame(rows); X_.to_parquet(OUT + '/scene_scores.parquet')
if PX: pd.concat(PX, ignore_index=True).to_parquet(OUT + '/pixels.parquet')
meths = ['arr', 'raw', 'ring', 'persist', 'nearest_latest']
R = dict(n_scenes=len(X_), lead_h_median=float(X_.lead_h.median()), share_burned_median=float(X_.share_burned.median()),
         mean_auc={m_: round(float(X_['auc_' + m_].mean()), 3) for m_ in meths},
         mean_share_found_equal_area={m_: round(float(X_['found_' + m_].mean()), 3) for m_ in meths},
         scenes_where_beats_ring={m_: round(float((X_['auc_' + m_] > X_.auc_ring).mean()), 3) for m_ in ['arr', 'raw', 'persist', 'nearest_latest']})
rng = np.random.default_rng(0); bs = []
for _ in range(1000):
    q = X_.sample(len(X_), replace=True, random_state=int(rng.integers(1e9)))
    bs.append([q.auc_arr.mean() - q.auc_ring.mean(), q.auc_raw.mean() - q.auc_ring.mean()])
bs = np.array(bs); R['auc_gain_vs_ring_95ci'] = dict(arr=np.percentile(bs[:, 0], [2.5, 97.5]).round(3).tolist(), raw=np.percentile(bs[:, 1], [2.5, 97.5]).round(3).tolist())
json.dump(R, open(OUT + '/summary.json', 'w'), indent=1); print(json.dumps(R, indent=1))
