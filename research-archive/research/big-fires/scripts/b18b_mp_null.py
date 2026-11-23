"""Null test for 15a (coordinator 20:01Z, after the 70 m thread's 15b): if every fire burned at its block centre and VIIRS placed
blocks with a random ~250 m error, would the hot pixels still look "at the edge"? Null = take each visible pass's real hot pixels,
re-centre them on the block (single) or cluster (2+) centre, shift the whole set by a random isotropic error with the given median
radius, and re-measure. Also: mean offset vector (hot centroid minus nearest block centre) east/north by satellite and scan width,
to see whether the error has a consistent direction that could be corrected. Out: results/mp_hotpix_null.json"""
import glob, json, numpy as np, pandas as pd
from pyproj import Transformer
R = 'results'; SC = '/tmp/claude-0/-home-user/408de539-c392-557a-989b-ab3e8eea191b/scratchpad/mp_hotpix'; M = '/mnt/project-files/fire-alert-scars/mp/out'
D = pd.read_csv(f'{R}/mp_hotpix_passes.csv'); V = D[D.visible == True]
A = pd.read_csv(f'{M}/mp_alert_event.csv', usecols=['latitude', 'longitude', 'acq_date', 'acq_time', 'satellite', 'instrument', 'scan', 'track', 'event_id'])
A = A[(A.instrument == 'VIIRS') & (A.event_id.isin(V.event_id))].copy()
A['t'] = pd.to_datetime(A.acq_date + ' ' + A.acq_time.astype(int).astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
to43 = Transformer.from_crs('EPSG:4326', 'EPSG:32643', always_xy=True); A['x'], A['y'] = to43.transform(A.longitude.values, A.latitude.values)
A['pass_id'] = A.event_id + '|' + A.satellite + '|' + A.t.dt.floor('15min').astype(str); A['pw'] = A.scan * 1000; A['ph'] = A.track * 1000
G = {k: g for k, g in A.groupby('pass_id')}
def measures(hx, hy, b):
    bx, by, bw, bh = b.x.values, b.y.values, b.pw.values, b.ph.values
    d = np.hypot(hx[:, None] - bx[None], hy[:, None] - by[None]); i = d.argmin(1)
    u = np.maximum(np.abs(hx - bx[i]) / (bw[i] / 2), np.abs(hy - by[i]) / (bh[i] / 2))
    out = dict(u_med=np.median(u), outer=(u > 0.5).mean(), inside=(u <= 1).mean(), dnear=np.median(d.min(1)))
    if len(b) == 2:
        p0 = np.array([bx[0], by[0]]); dd = np.array([bx[1] - bx[0], by[1] - by[0]]); L = np.hypot(*dd)
        s = ((hx - p0[0]) * dd[0] + (hy - p0[1]) * dd[1]) / L ** 2; out['between'] = ((s >= 0) & (s <= 1)).mean(); out['sep'] = L
    return out
rng = np.random.default_rng(1); passes = []
for _, r in V.iterrows():
    f = glob.glob(f"{SC}/{r.pass_id.replace('|', '_').replace(':', '')}_*.npz")
    if not f or r.pass_id not in G: continue
    z = np.load(f[0]); b = G[r.pass_id]; hx, hy = z['x'], z['y']
    near = np.hypot(hx[:, None] - b.x.values[None], hy[:, None] - b.y.values[None]).min(1) <= 600; hx, hy = hx[near], hy[near]
    if len(hx) < 3: continue
    passes.append((r.pass_id, r.satellite, r.n_blocks, hx, hy, b))
print('passes', len(passes))
res = {}
for med in [0, 150, 250, 350]:
    sig = med / 1.1774; rows = []
    for pid, sat, nb, hx, hy, b in passes:
        cx, cy = (b.x.iloc[0], b.y.iloc[0]) if nb == 1 else (b.x.mean(), b.y.mean())
        ex, ey = rng.normal(0, sig, 2) if med > 0 else (0, 0)
        m = measures(hx - hx.mean() + cx + ex, hy - hy.mean() + cy + ey, b); m['kind'] = 'single' if nb == 1 else ('two' if nb == 2 else 'three+'); rows.append(m)
    T = pd.DataFrame(rows); two = T[T.kind == 'two']
    res[f'null_error_median_{med}m'] = dict(outer_half=round(T.outer.mean(), 3), position=round(T.u_med.median(), 2), inside=round(T.inside.mean(), 2), hot_to_centre_m=round(T.dnear.median()),
                                            by_kind={k: round(g.outer.mean(), 3) for k, g in T.groupby('kind')},
                                            two_adjacent_between=round(two[two.sep < 500].between.median(), 2), two_far_between=round(two[two.sep >= 500].between.median(), 2))
obs = pd.DataFrame([dict(**measures(hx, hy, b), kind='single' if nb == 1 else ('two' if nb == 2 else 'three+')) for pid, sat, nb, hx, hy, b in passes]); two = obs[obs.kind == 'two']
res['observed'] = dict(outer_half=round(obs.outer.mean(), 3), position=round(obs.u_med.median(), 2), inside=round(obs.inside.mean(), 2), hot_to_centre_m=round(obs.dnear.median()),
                       by_kind={k: round(g.outer.mean(), 3) for k, g in obs.groupby('kind')}, two_adjacent_between=round(two[two.sep < 500].between.median(), 2), two_far_between=round(two[two.sep >= 500].between.median(), 2))
# ---- direction of the offset: hot centroid minus nearest block centre, east/north, by satellite and scan width
rows = []
for pid, sat, nb, hx, hy, b in passes:
    cx, cy = hx.mean(), hy.mean(); i = np.hypot(cx - b.x.values, cy - b.y.values).argmin()
    rows.append(dict(sat=sat, scan=b.pw.iloc[i], dx=cx - b.x.iloc[i], dy=cy - b.y.iloc[i], nb=nb))
O = pd.DataFrame(rows); O['scan_bin'] = pd.cut(O.scan, [0, 450, 600, 900], labels=['near nadir <450 m', '450-600 m', 'edge >600 m'])
def vec(g):
    n = len(g); mx, my = g.dx.mean(), g.dy.mean(); se = np.sqrt((g.dx.var() + g.dy.var()) / n)
    return dict(passes=int(n), mean_east_m=round(mx), mean_north_m=round(my), mean_vector_m=round(np.hypot(mx, my)), se_m=round(se), median_radius_m=round(np.hypot(g.dx, g.dy).median()))
res['offset_direction'] = {'all': vec(O), 'by_satellite': {k: vec(g) for k, g in O.groupby('sat')}, 'by_scan_width': {str(k): vec(g) for k, g in O.groupby('scan_bin', observed=True)},
                           'by_satellite_and_scan': {f'{s} {k}': vec(g) for (s, k), g in O.groupby(['sat', 'scan_bin'], observed=True)}}
json.dump(res, open(f'{R}/mp_hotpix_null.json', 'w'), indent=1); print(json.dumps(res, indent=1))
