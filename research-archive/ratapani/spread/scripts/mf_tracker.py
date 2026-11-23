"""Multi-front tracker + per-front growth (Oct 17; Akkshay's development order: multi-front tracking first, growth/stop second).
146 big fires, outlines v2, truth = fire-continuity blend map (burn state at any hour). A forecast is issued at every VIIRS look k
(t_k) for the burn state at t_k + 24 h.

Tracker at look k (no future information):
  footprints  = 265 m discs around every dot so far (a 375 m block), all treated as already burned
  fronts      = dots so far linked within LINK m (single linkage); a front is ACTIVE if it has a dot in the latest 2 looks (~14 h)
  new cluster = dots of look k farther than LINK from every earlier dot: 'separate front' if < 3 km, 'independent start' beyond
Stage 1 writes one row per (fire, issue, front) with features and the TRUE new burned area near it in the next 24 h, plus the new
burning that no front could reach (> 1 km from every dot so far). Stage 2 (mf_eval.py) trains the growth model and scores maps.
  FC_SCRATCH=/tmp/claude-0/fronts python3 mf_tracker.py out_prefix
"""
import os, sys, pickle, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts')
import c0_lib as C
from rasterio import features
from rasterio.transform import Affine
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix

OUT = sys.argv[1]
BF = '/mnt/project-files/research/big-fires/results'
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
F = pd.read_csv(f'{BF}/fires.csv').set_index('fire'); L = pd.read_csv(os.environ.get('FIRE_LIST', f'{BF}/big_fires_list.csv'))
SC = pickle.load(open(f"{os.environ['FC_SCRATCH']}/fire_scars.pkl", 'rb'))
LINK = 750.0; FOOT = 265.0; REACH = 1000.0; H = 24.0
WC = C.WC; IST = pd.Timedelta(hours=5, minutes=30)


def clusters(xy):
    if len(xy) == 1:
        return np.zeros(1, int)
    t = cKDTree(xy); p = np.array(list(t.query_pairs(LINK)))
    if len(p) == 0:
        return np.arange(len(xy))
    m = coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy), len(xy)))
    return connected_components(m, directed=False)[1]


rows, issues, maps = [], [], {}
for page, fire in enumerate(L.fire.tolist(), 1):
    d = C.viirs_looks(A[A.fire == fire]).reset_index(drop=True); t0 = d.t.min(); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    poly = SC[fire]
    xs = np.r_[poly.bounds[0], poly.bounds[2], d.x.min(), d.x.max()]; ys = np.r_[poly.bounds[1], poly.bounds[3], d.y.min(), d.y.max()]
    r0, c0 = C.rc_of(xs.min() - 1500, ys.max() + 1500); r1, c1 = C.rc_of(xs.max() + 1500, ys.min() - 1500)
    box = C.Box(max(int(r0), 0), min(int(r1), C.NR - 1) + 1, max(int(c0), 0), min(int(c1), C.NC - 1) + 1)
    tr = Affine(20, 0, C.X0 + box.c0 * 20, 0, -20, C.Y0 - box.r0 * 20)
    dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
    if d.lk.max() == 0:     # seen at one look only: no timing; upper bound = all outline beyond the 375 m blocks burned within the next hour
        dd0 = cKDTree(d[['x', 'y']].values).query(np.c_[box.X.ravel(), box.Y.ravel()])[0].reshape(box.shape)
        Tg = np.where(dom, np.where(dd0 <= FOOT, 0.0, 1.0), np.inf)
    else:
        T, lo, hi, idx, dmin = C.blend_map(box, dom, d, clock=C.Clock(t0), p=4)
        Tg = np.full(box.shape, np.inf); rr, cc = np.where(dom); Tg[rr, cc] = np.where(np.isfinite(T), T, np.inf)
    P = np.c_[box.X.ravel(), box.Y.ravel()]
    wc = WC[box.r0:box.r1, box.c0:box.c1].ravel()
    maps[fire] = dict(box=(box.r0, box.r1, box.c0, box.c1), shape=box.shape, Tg=Tg.astype(np.float32), dom=dom)
    nlk = int(d.lk.max() + 1)
    for k in range(nlk):
        tk = d[d.lk == k].th.max(); known = d[d.lk <= k]; xy = known[['x', 'y']].values
        lab = clusters(xy); known = known.assign(front=lab)
        recent = known[known.lk >= k - 1].front.unique()
        prev = d[d.lk < k][['x', 'y']].values
        burned_now = (Tg.ravel() <= tk)
        new = (Tg.ravel() > tk) & (Tg.ravel() <= tk + H)
        dist_all, near_dot = cKDTree(xy).query(P)
        foot = dist_all <= FOOT
        reach_new = new & (dist_all > REACH)
        I = dict(fire=fire, page=page, season=int(F.season[fire]), k=k, n_looks=nlk, th=round(tk, 2), hour_ist=int(((d[d.lk == k].t.max() + IST).hour)),
                 n_dots=len(xy), n_fronts=int(lab.max() + 1), n_active=len(recent), burned_now_ha=burned_now.sum() * .04,
                 foot_ha=foot.sum() * .04, new24_ha=new.sum() * .04, new24_far1k_ha=reach_new.sum() * .04,
                 later_look=bool((d.th > tk + H).any()) or bool((d.th > tk + 6).any()))
        issues.append(I)
        fr_of_px = lab[near_dot]
        for f in np.unique(lab):
            g = known[known.front == f]; gx = g[['x', 'y']].values
            dprev = cKDTree(prev).query(gx)[0].min() if len(prev) else np.inf
            kind = 'first' if k == 0 else ('old' if g.lk.max() < k else ('continuing' if dprev <= LINK else ('separate' if dprev <= 3000 else 'independent')))
            own = fr_of_px == f
            last2 = g[g.lk >= k - 1]
            grow_prev = np.nan
            if k >= 1:
                gk = g[g.lk <= k - 1]
                grow_prev = len(g) - len(gk)
            fp_ = own & foot
            rows.append(dict(fire=fire, season=I['season'], k=k, front=int(f), kind=kind, active=bool(f in recent), th=I['th'], hour_ist=I['hour_ist'],
                             age_h=round(tk - g.th.min(), 2), n_dots=len(g), n_dots_last=int((g.lk == k).sum()), n_dots_last2=len(last2), dots_added=grow_prev,
                             frp_last=float(g[g.lk == k].frp.sum()) if 'frp' in g else np.nan, frp_all=float(g.frp.sum()) if 'frp' in g else np.nan,
                             night=int(I['hour_ist'] < 6 or I['hour_ist'] >= 18), extent_m=float(np.ptp(gx[:, 0]) + np.ptp(gx[:, 1])),
                             foot_ha=fp_.sum() * .04, forest_share=float(np.isin(wc[fp_], [10]).mean()) if fp_.any() else np.nan,
                             grass_share=float(np.isin(wc[fp_], [30]).mean()) if fp_.any() else np.nan,
                             n_fronts=I['n_fronts'], n_active=I['n_active'], fire_dots=len(xy), doy=int(d.t.min().dayofyear),
                             new24_ha=float((new & own & (dist_all <= REACH)).sum() * .04)))
    if page % 20 == 0:
        print(page, flush=True)
pd.DataFrame(rows).to_parquet(f'{OUT}_fronts.parquet'); pd.DataFrame(issues).to_parquet(f'{OUT}_issues.parquet')
pickle.dump(maps, open(f'{OUT}_maps.pkl', 'wb'))
print('done', len(issues), 'issues', len(rows), 'front rows')
