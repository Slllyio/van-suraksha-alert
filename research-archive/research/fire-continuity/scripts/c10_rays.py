"""Where and why does a front stop? Pixel-level rays from each front to the burn-scar edge.
Origins = groups of VIIRS dots (linked within 750 m): the first look's groups, and later groups > 750 m from every earlier dot
(new fronts; 'separate' if within 3 km of earlier dots, 'independent' beyond). Each origin owns the ground closer to it than to any
other origin of the fire (Voronoi), so two fronts never share a ray.
From each origin 36 rays (every 10 deg), 20 m steps out to 4 km. The ray starts where it first enters the v2 scar outline (within
500 m, dot position error) and the front 'stops' at the first step after which 3 pixels (60 m) in a row are unburned (shorter gaps
= label noise). Steps beyond the stop are kept (flag after_stop) so a model can predict how far each ray should have gone.
Every step records what the candidate pixel is: cover, fuel map, grade along the ray, ridge/valley, road, village distance,
burned earlier this season, past-season burn share, ray direction vs wind, forest-edge transition.
Out: $FC_SCRATCH/rays.parquet (steps), results/ray_origins.csv"""
import os, sys, pickle
import numpy as np, pandas as pd, rasterio, json
from rasterio import features
from rasterio.transform import Affine
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import connected_components
from scipy.sparse import coo_matrix
from scipy.ndimage import uniform_filter, binary_dilation
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import c0_lib as C
R = '/mnt/project-files'; BF = f'{R}/research/big-fires/results'; HERE = f'{R}/research/fire-continuity'
A = pd.read_csv(f'{BF}/fire_alerts.csv', parse_dates=['t']); A = A[A.sat != 'modis'].copy()
F = pd.read_csv(f'{BF}/fires.csv').set_index('fire'); L = pd.read_csv(f'{BF}/big_fires_list.csv')
SC = pickle.load(open(f'{C.SCRATCH}/fire_scars.pkl', 'rb'))
LINK, STEP, MAXS, NRAY = 750.0, 20.0, 4000.0, 36
SLOPE = C.G['slope']; BS = {y: C.G[f'burn_start_{y}'] for y in range(2017, 2027)}  # npz members reload on every access: cache
EL = C.ELEV.astype(float); LOC = EL - uniform_filter(EL, 51)
TREE = C.WC == 10; GRASS = np.isin(C.WC, [20, 30]); CROP = np.isin(C.WC, [40, 50]); WATER = C.WC == 80
ROADN = binary_dilation(C.ROAD, iterations=2)       # road within 40 m
FUEL = rasterio.open(f'{R}/fuel-map/ratapani/v3/fuel_total_potential_central_10m.tif'); FUELA = FUEL.read(1).astype(float)
FUELA[FUELA == (FUEL.nodata if FUEL.nodata is not None else -1)] = np.nan
gj = json.load(open(f'{R}/ratapani/grid_500m.geojson')); cells = pd.DataFrame([f['properties'] for f in gj['features']])
prox = pd.read_csv(f'{R}/ratapani/ee/proximity.csv').merge(cells[['cell_id', 'x0', 'y0']], on='cell_id')
VIL = {(int(r.x0), int(r.y0)): r.dist_village / 1000 for r in prox.itertuples()}
W6 = pd.read_csv(f'{R}/ratapani/ee/era5land_06utc.csv', parse_dates=['time']); W6['date'] = W6.time.dt.normalize(); W6 = W6.set_index('date')
PRIOR = {}
def prior_share(season):
    if season not in PRIOR:
        p = np.zeros(EL.shape, np.float32)
        for y in range(2017, season): p += BS[y] > -999
        PRIOR[season] = p / max(season - 2017, 1)
    return PRIOR[season]

def clusters(xy):
    if len(xy) == 1: return np.zeros(1, int)
    p = np.array(list(cKDTree(xy).query_pairs(LINK)))
    if len(p) == 0: return np.arange(len(xy))
    return connected_components(coo_matrix((np.ones(len(p)), (p[:, 0], p[:, 1])), shape=(len(xy),) * 2), directed=False)[1]

def fuel_at(X, Y):
    tf = FUEL.transform; c = np.floor((X - tf.c) / tf.a).astype(int); r = np.floor((Y - tf.f) / tf.e).astype(int)
    ok = (r >= 0) & (r < FUELA.shape[0]) & (c >= 0) & (c < FUELA.shape[1]); out = np.full(len(r), np.nan)
    out[ok] = FUELA[r[ok], c[ok]]; return out

steps, origins = [], []
S = np.arange(0, MAXS + 1, STEP)
for page, fire in enumerate(L.fire.tolist(), 1):
    d = C.viirs_looks(A[A.fire == fire]).reset_index(drop=True); t0 = d.t.min(); d['th'] = (d.t - t0).dt.total_seconds() / 3600
    poly = SC[fire]; season = int(F.season[fire]); doy0 = t0.dayofyear
    xs = np.r_[poly.bounds[0], poly.bounds[2], d.x.min(), d.x.max()]; ys = np.r_[poly.bounds[1], poly.bounds[3], d.y.min(), d.y.max()]
    r0, c0 = C.rc_of(xs.min() - MAXS, ys.max() + MAXS); r1, c1 = C.rc_of(xs.max() + MAXS, ys.min() - MAXS)
    r0, c0 = max(int(r0), 0), max(int(c0), 0); r1, c1 = min(int(r1), C.NR - 1) + 1, min(int(c1), C.NC - 1) + 1
    tr = Affine(20, 0, C.X0 + c0 * 20, 0, -20, C.Y0 - r0 * 20)
    dom = features.rasterize([poly], out_shape=(r1 - r0, c1 - c0), transform=tr).astype(bool)
    BE = (BS[season] > -999) & (BS[season] < doy0 - 2); PR = prior_share(season)
    # origins
    org = []
    for k in sorted(d.lk.unique()):
        g = d[d.lk == k]; prev = d[d.lk < k]
        if k > 0:
            dp = cKDTree(prev[['x', 'y']].values).query(g[['x', 'y']].values)[0]; g = g[dp > LINK]; dp = dp[dp > LINK]
        if not len(g): continue
        lab = clusters(g[['x', 'y']].values)
        for c in np.unique(lab):
            gg = g[lab == c]
            kind = 'first' if k == 0 else ('separate' if dp[lab == c].min() <= 3000 else 'independent')
            org.append(dict(fire=fire, season=season, look=int(k), kind=kind, x=gg.x.mean(), y=gg.y.mean(), th=gg.th.min(),
                            n_dots=len(gg), frp=gg.frp.sum(), date=(gg.t.min()).normalize(), doy=gg.t.min().dayofyear))
    O = np.array([[o['x'], o['y']] for o in org])
    for oi, o in enumerate(org):
        o['origin'] = f'{fire}_{oi}'
        w = W6.loc[o['date']] if o['date'] in W6.index else None
        wto = np.degrees(np.arctan2(w.u_component_of_wind_10m, w.v_component_of_wind_10m)) % 360 if w is not None else np.nan
        o['wind_ms'] = float(np.hypot(w.u_component_of_wind_10m, w.v_component_of_wind_10m)) if w is not None else np.nan
        o['wind_to'] = wto
        reach = np.full(NRAY, np.nan); cens = np.zeros(NRAY, bool)
        for j in range(NRAY):
            az = j * 360 / NRAY; X = o['x'] + S * np.sin(np.radians(az)); Y = o['y'] + S * np.cos(np.radians(az))
            rr, cc = C.rc_of(X, Y); inb = (rr >= r0) & (rr < r1) & (cc >= c0) & (cc < c1)
            rr = np.clip(rr, 0, C.NR - 1); cc = np.clip(cc, 0, C.NC - 1)
            ins = np.zeros(len(S), bool); ins[inb] = dom[rr[inb] - r0, cc[inb] - c0]
            own = np.ones(len(S), bool)
            if len(O) > 1:
                dd = np.hypot(X[:, None] - O[None, :, 0], Y[:, None] - O[None, :, 1]); own = dd.argmin(1) == oi
            ent = np.where(ins[:26])[0]
            if not len(ent): continue
            e = ent[0]
            # stop = first i > e where i, i+1, i+2 all outside
            out3 = ~ins & np.r_[~ins[1:], True] & np.r_[~ins[2:], True, True]
            lim = np.where(~(own & inb))[0]; lim = lim[lim > e]; lim = lim[0] if len(lim) else len(S)
            st = np.where(out3 & (np.arange(len(S)) > e))[0]; st = st[0] if len(st) else None
            if st is not None and st >= lim: st = None
            reach[j] = (S[st] if st is not None else S[lim - 1]) - S[e]; cens[j] = st is None
            i = np.arange(e + 1, lim)
            if not len(i): continue
            ip, inx = np.clip(i - 2, 0, len(S) - 1), np.clip(i + 2, 0, len(S) - 1)
            r_, c_ = rr[i], cc[i]
            vil = np.array([VIL.get((int(np.floor(x / 500) * 500), int(np.floor(y / 500) * 500)), np.nan) for x, y in zip(X[i], Y[i])])
            trp = np.array([TREE[rr[max(a - 5, e):a], cc[max(a - 5, e):a]].mean() if a > e else np.nan for a in i])
            steps.append(pd.DataFrame(dict(
                origin=o['origin'], fire=fire, season=season, ray=j, az=az, s=S[i] - S[e], i_rel=i - e,
                stop=(i == st) if st is not None else np.zeros(len(i), bool), after_stop=(i > st) if st is not None else np.zeros(len(i), bool),
                tree=TREE[r_, c_], grass=GRASS[r_, c_], crop=CROP[r_, c_], water=WATER[r_, c_], road=ROADN[r_, c_],
                tree_prev100=trp, grade=(EL[rr[inx], cc[inx]] - EL[rr[ip], cc[ip]]) / (STEP * (inx - ip)),
                local_height=LOC[r_, c_], slope=SLOPE[r_, c_], fuel=fuel_at(X[i], Y[i]), village_km=vil,
                burned_earlier=BE[r_, c_], prior_burns=PR[r_, c_],
                downwind=np.cos(np.radians(az - wto)) if np.isfinite(wto) else np.nan)))
        o['reach'] = reach.tolist(); o['censored'] = cens.tolist()
    origins += org
    if page % 10 == 0: print(page, sum(len(s) for s in steps), flush=True)
ST = pd.concat(steps, ignore_index=True)
for c in ['tree', 'grass', 'crop', 'water', 'road', 'burned_earlier']: ST[c] = ST[c].astype(np.int8)
ST.to_parquet(f'{C.SCRATCH}/rays.parquet'); pd.DataFrame(origins).to_csv(f'{HERE}/results/ray_origins.csv', index=False)
print(len(ST), 'steps', len(origins), 'origins', ST[~ST.after_stop].stop.sum(), 'stops')
