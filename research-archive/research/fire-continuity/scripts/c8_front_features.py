"""Why do some fronts run farther than others? Stage 1: features of the ground around each front.
Fronts are the spread thread's (ratapani/spread/scripts/mf_tracker.py, same rules: dots so far linked within 750 m; growth =
new burning within 1 km of the front's own dots in the next 24 h, read from the fire-continuity blend map). This script rebuilds
the same fronts so it can measure the ground each front had in front of it, using ALL ground within 1 km (not only the final
outline, so the outline cannot leak where the fire went):
  cover : tree / grass+shrub / crop+built shares (ESA WorldCover), fuel map v3 total (relative, t/ha)
  terrain: mean slope, uphill = mean height of the ground around minus height at the front's dots, ridge(+)/valley(-) local height
  burn history: share burned earlier this season (burn-label start day < fire start - 2), mean number of earlier seasons burned
  people: share of road pixels, distance to nearest village (500 m grid, OSM)
  wind side: cos(bearing fire-centre -> front, ERA5-Land 06 UTC wind 'toward') = is this front on the downwind side
Out: results/front_features.parquet (one row per active front per look)"""
import os, sys, pickle, json
import numpy as np, pandas as pd, rasterio
from rasterio import features
from rasterio.transform import Affine
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix
from scipy.ndimage import uniform_filter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import c0_lib as C

R = '/mnt/project-files'; BF = f'{R}/research/big-fires/results'; HERE = f'{R}/research/fire-continuity'
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
A['scan'] = A.scan.fillna(.375).clip(lower=.3); A['track'] = A.track.fillna(.375).clip(lower=.3)
F = pd.read_csv(f'{BF}/fires.csv').set_index('fire'); L = pd.read_csv(f'{BF}/big_fires_list.csv')
SC = pickle.load(open(f'{C.SCRATCH}/fire_scars.pkl', 'rb'))
LINK, FOOT, REACH, H = 750.0, 265.0, 1000.0, 24.0
FUEL = rasterio.open(f'{R}/fuel-map/ratapani/v3/fuel_total_potential_central_10m.tif'); FUELA = FUEL.read(1).astype(float)
FUELA[FUELA == (FUEL.nodata if FUEL.nodata is not None else -1)] = np.nan
import json as _j
gj = _j.load(open(f'{R}/ratapani/grid_500m.geojson'))
cells = pd.DataFrame([f['properties'] for f in gj['features']])
prox = pd.read_csv(f'{R}/ratapani/ee/proximity.csv').merge(cells[['cell_id', 'x0', 'y0']], on='cell_id')
VIL = {(int(r.x0), int(r.y0)): r.dist_village for r in prox.itertuples()}
W6 = pd.read_csv(f'{R}/ratapani/ee/era5land_06utc.csv', parse_dates=['time']); W6['date'] = W6.time.dt.normalize()
W6 = W6.set_index('date')

def clusters(xy):
    if len(xy) == 1: return np.zeros(1, int)
    p = np.array(list(cKDTree(xy).query_pairs(LINK)))
    if len(p) == 0: return np.arange(len(xy))
    return connected_components(coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy),) * 2), directed=False)[1]

def fuel_at(X, Y):
    tf = FUEL.transform; c = np.floor((X - tf.c) / tf.a).astype(int); r = np.floor((Y - tf.f) / tf.e).astype(int)
    ok = (r >= 0) & (r < FUELA.shape[0]) & (c >= 0) & (c < FUELA.shape[1]); out = np.full(len(r), np.nan)
    out[ok] = FUELA[r[ok], c[ok]]; return out

rows = []
for page, fire in enumerate(L.fire.tolist(), 1):
    d = C.viirs_looks(A[A.fire == fire]).reset_index(drop=True); t0 = d.t.min(); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    poly = SC[fire]; season = int(F.season[fire]); doy0 = t0.dayofyear
    xs = np.r_[poly.bounds[0], poly.bounds[2], d.x.min(), d.x.max()]; ys = np.r_[poly.bounds[1], poly.bounds[3], d.y.min(), d.y.max()]
    r0, c0 = C.rc_of(xs.min() - 1500, ys.max() + 1500); r1, c1 = C.rc_of(xs.max() + 1500, ys.min() - 1500)
    box = C.Box(max(int(r0), 0), min(int(r1), C.NR - 1) + 1, max(int(c0), 0), min(int(c1), C.NC - 1) + 1)
    tr = Affine(20, 0, C.X0 + box.c0 * 20, 0, -20, C.Y0 - box.r0 * 20)
    dom = features.rasterize([poly], out_shape=box.shape, transform=tr).astype(bool)
    T, lo, hi, idx, dmin = C.blend_map(box, dom, d, clock=C.Clock(t0), p=4)
    Tg = np.full(box.shape, np.inf); rr, cc = np.where(dom); Tg[rr, cc] = np.where(np.isfinite(T), T, np.inf)
    P = np.c_[box.X.ravel(), box.Y.ravel()]
    # static layers on the box
    sl = (slice(box.r0, box.r1), slice(box.c0, box.c1))
    wc = box.wc.ravel(); el = box.elev; loc = (el - uniform_filter(el, 51)).ravel(); elr = el.ravel()
    slope = np.degrees(np.arctan(np.hypot(*np.gradient(el, 20)))).ravel()
    bs = C.G[f'burn_start_{season}'][sl].ravel(); earlier = (bs > -999) & (bs < doy0 - 2)
    prior = np.zeros(len(wc))
    for y in range(2017, season):
        prior += (C.G[f'burn_start_{y}'][sl].ravel() > -999)
    nprior = max(season - 2017, 1)
    road = box.road.ravel(); fuel = fuel_at(P[:, 0], P[:, 1])
    vil = np.array([VIL.get((int(np.floor(x / 500) * 500), int(np.floor(y / 500) * 500)), np.nan) for x, y in P[::1]])
    nlk = int(d.lk.max() + 1)
    for k in range(nlk):
        tk = d[d.lk == k].th.max(); known = d[d.lk <= k]; xy = known[['x', 'y']].values
        lab = clusters(xy); known = known.assign(front=lab); recent = known[known.lk >= k - 1].front.unique()
        prev = d[d.lk < k][['x', 'y']].values
        new = (Tg.ravel() > tk) & (Tg.ravel() <= tk + H)
        dist_all, near_dot = cKDTree(xy).query(P)
        fr_of_px = lab[near_dot]
        date = (t0 + pd.Timedelta(hours=tk)).normalize()
        w = W6.loc[date] if date in W6.index else None
        wtoward = np.degrees(np.arctan2(w.u_component_of_wind_10m, w.v_component_of_wind_10m)) % 360 if w is not None else np.nan
        wspd = float(np.hypot(w.u_component_of_wind_10m, w.v_component_of_wind_10m)) if w is not None else np.nan
        cxy = xy.mean(0)
        for f in recent:
            g = known[known.front == f]; gx = g[['x', 'y']].values
            dprev = cKDTree(prev).query(gx)[0].min() if len(prev) else np.inf
            kind = 'first' if k == 0 else ('old' if g.lk.max() < k else ('continuing' if dprev <= LINK else ('separate' if dprev <= 3000 else 'independent')))
            own = (fr_of_px == f) & (dist_all <= REACH)
            ahead = own & (dist_all > FOOT)          # ground around the front not yet under a block: where it can go
            if ahead.sum() < 20: continue
            fc = gx.mean(0); brg = np.degrees(np.arctan2(fc[0] - cxy[0], fc[1] - cxy[1])) % 360
            el_front = np.nanmean(C.ELEV[C.rc_of(gx[:, 0], gx[:, 1])])
            rows.append(dict(fire=fire, season=season, k=k, front=int(f), kind=kind, th=round(tk, 2), date=date,
                             hour_ist=int((d[d.lk == k].t.max() + pd.Timedelta(hours=5.5)).hour), age_h=round(tk - g.th.min(), 2),
                             n_dots=len(g), n_dots_last=int((g.lk == k).sum()), frp_last=float(g[g.lk == k].frp.sum()),
                             n_active=len(recent), new24_ha=float((new & own).sum() * .04), avail_ha=ahead.sum() * .04,
                             tree=float((wc[ahead] == 10).mean()), grass=float(np.isin(wc[ahead], [20, 30]).mean()),
                             crop=float(np.isin(wc[ahead], [40, 50]).mean()), fuel=float(np.nanmean(fuel[ahead])),
                             slope=float(slope[ahead].mean()), uphill=float(elr[ahead].mean() - el_front), local_height=float(loc[ahead].mean()),
                             burned_earlier=float(earlier[ahead].mean()), prior_burns=float(prior[ahead].mean() / nprior),
                             road=float(road[ahead].mean()), village_km=float(np.nanmean(vil[ahead]) / 1000),
                             downwind=float(np.cos(np.radians(brg - wtoward))) if len(recent) > 1 and np.isfinite(wtoward) else np.nan,
                             wind_ms=wspd))
    if page % 20 == 0: print(page, flush=True)
X = pd.DataFrame(rows); X.to_parquet(f'{HERE}/results/front_features.parquet'); print(len(X), 'front rows')
