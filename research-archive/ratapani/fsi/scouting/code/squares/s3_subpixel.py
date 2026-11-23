"""Experiment 3: where inside a VIIRS (or MODIS) footprint is the fire?  Truth: Sentinel-2 / Landsat 20-30 m hot pixels
(fire-alert-scars/out/af) of the same day.
3a  Clusters of adjacent pixels in one pass: plain centre vs FRP-weighted, brightness-weighted, FRP^2-weighted and a
    PSF fit (triangle response across scan and track) -> distance to the hot pixels' centre.
3b  Single pixels: where do the hot pixels sit inside the footprint (offset along scan / track, in half-widths)?
3c  Intersection of near-time footprints (two VIIRS satellites < 2 h, or Terra MODIS + the next VIIRS pass): are hot
    pixels denser inside the overlap than in the rest of the union?
3d  Photos: closest-dot score using sub-pixel positions instead of pixel centres.
Time gap: S2/Landsat ~05:00-05:30 UTC; VIIRS day passes 06:30-09:00 UTC (1-4 h later); Terra ~05:00 UTC (< 1 h).
"""
import glob, json
import numpy as np, pandas as pd, pyproj, shapely
from shapely.ops import unary_union
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from s_lib import *
rng = np.random.default_rng(0)
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
H = pd.concat([pd.read_csv(f) for f in glob.glob(f'{ROOT}/fire-alert-scars/out/af/af_20*.csv')], ignore_index=True)
H['t'] = pd.to_datetime(H.date + ' ' + H.time_utc); H['x'], H['y'] = tp(H.lon.values, H.lat.values)
H = H.drop_duplicates(['x', 'y', 't'])
D = load_det(); D = D[D.type.fillna(0) != 2].reset_index(drop=True)
D['cl'] = -1
for pid, g in D.groupby('pass_id'):     # clusters of adjacent pixels inside a pass
    P = g[['x', 'y']].values; lim = 1.3 * np.maximum(g.scan_m.values, g.track_m.values).max()
    pr = cKDTree(P).query_pairs(lim, output_type='ndarray')
    if len(pr):   # keep only truly adjacent pairs (within 1.3 pixel in both footprint axes)
        us, ut = axes(g.heading.iloc[0]); dv = P[pr[:, 1]] - P[pr[:, 0]]
        sc = g.scan_m.values[pr[:, 0]]; trk = g.track_m.values[pr[:, 0]]
        ok = (np.abs(dv @ us) < 1.3 * sc) & (np.abs(dv @ ut) < 1.3 * trk); pr = pr[ok]
    n = len(P); _, lab = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])) if len(pr) else ([], ([], [])), shape=(n, n)), directed=False)
    D.loc[g.index, 'cl'] = pid * 1000 + lab
def psf_fit(g):
    """Single point source; pixel response = triangle(1 - |offset|/size) along scan and along track. Grid search over the
    cluster's footprint union for the position whose predicted FRP shares best match the observed shares."""
    us, ut = axes(g.heading.iloc[0]); P = g[['x', 'y']].values; f = g.frp.clip(lower=.01).values; f = f / f.sum()
    sc, tr = g.scan_m.values, g.track_m.values
    c = P.mean(0); a = np.linspace(-1, 1, 41)
    span_s = np.abs((P - c) @ us).max() + sc.max() / 2; span_t = np.abs((P - c) @ ut).max() + tr.max() / 2
    A, B = np.meshgrid(a * span_s, a * span_t); Q = c + A.ravel()[:, None] * us + B.ravel()[:, None] * ut
    o = Q[:, None, :] - P[None]
    rs = np.clip(1 - np.abs(o @ us) / sc[None], 0, None) * np.clip(1 - np.abs(o @ ut) / tr[None], 0, None)
    tot = rs.sum(1, keepdims=True); ok = tot[:, 0] > 0
    pred = np.where(ok[:, None], rs / np.where(tot > 0, tot, 1), 0)
    err = ((pred - f[None]) ** 2).sum(1); err[~ok] = np.inf
    return Q[np.argmin(err)]
rows, single = [], []
for cl, g in D.groupby('cl'):
    t = g.t.min(); kind = g.kind.iloc[0]
    h = H[(H.t.dt.date == t.date())]
    if not len(h): continue
    dt_h = (t - h.t.iloc[0]).total_seconds() / 3600
    if kind == 'viirs' and not (-0.5 <= dt_h <= 5): continue
    if kind == 'modis' and abs(dt_h) > 1: continue
    near = foot_dist(h.x.values, h.y.values, g, pad=300).min(1) <= 0
    hh = h[near]
    if len(hh) == 0: continue
    truth = hh[['x', 'y']].values.mean(0)
    w = g.frp.clip(lower=.01).values; b4 = (g.bt4 - g.bt4.min() + 1).values
    est = dict(plain=g[['x', 'y']].values.mean(0), frp=np.average(g[['x', 'y']].values, 0, w),
               frp2=np.average(g[['x', 'y']].values, 0, w ** 2), bright=np.average(g[['x', 'y']].values, 0, b4))
    est['psf'] = psf_fit(g) if len(g) > 1 else est['plain']
    r = dict(cl=cl, kind=kind, sensor=g.sensor.iloc[0], n=len(g), gap_h=dt_h, n_hot=len(hh), pix=np.sqrt((g.scan_m * g.track_m).mean()))
    for k, e in est.items():
        r['d_' + k] = float(np.hypot(*(e - truth))); r['dn_' + k] = float(np.hypot(hh.x - e[0], hh.y - e[1]).min())
    rows.append(r)
    if len(g) == 1:
        us, ut = axes(g.heading.iloc[0]); o = truth - g[['x', 'y']].values[0]
        single.append(dict(kind=kind, sensor=g.sensor.iloc[0], gap_h=dt_h, os=float(o @ us) / (g.scan_m.iloc[0] / 2), ot=float(o @ ut) / (g.track_m.iloc[0] / 2)))
C = pd.DataFrame(rows); C.to_csv(f'{OUT}/e3_clusters_vs_hotpix.csv', index=False)
Sg = pd.DataFrame(single)
res = {}
def summ(c):
    out = dict(clusters=len(c), median_pixels=float(c.n.median()), median_gap_h=round(c.gap_h.median(), 2))
    out['median_dist_to_hotpix_centre_m'] = {k: round(c['d_' + k].median()) for k in ['plain', 'frp', 'frp2', 'bright', 'psf']}
    out['median_dist_to_nearest_hotpix_m'] = {k: round(c['dn_' + k].median()) for k in ['plain', 'frp', 'frp2', 'bright', 'psf']}
    for k in ['frp', 'frp2', 'bright', 'psf']:
        d = (c['d_' + k] - c.d_plain).values; bs = [np.median(d[rng.integers(0, len(d), len(d))]) for _ in range(1000)]
        out[f'{k}_minus_plain_median_m'] = [round(np.median(d), 1), round(np.quantile(bs, .025), 1), round(np.quantile(bs, .975), 1)]
        out[f'{k}_closer_share'] = round(float((c['d_' + k] < c.d_plain - 1e-6).mean()), 3)
    return out
for nm, c in [('viirs_multi_pixel', C[(C.kind == 'viirs') & (C.n > 1)]), ('viirs_multi_pixel_gap_le_2h', C[(C.kind == 'viirs') & (C.n > 1) & (C.gap_h <= 2)]),
              ('viirs_3plus_pixels', C[(C.kind == 'viirs') & (C.n >= 3)]), ('modis_terra_multi_pixel', C[(C.kind == 'modis') & (C.n > 1)])]:
    if len(c) >= 10: res['3a_' + nm] = summ(c)
res['3a_cluster_sizes'] = dict(viirs_clusters_with_hotpix=int((C.kind == 'viirs').sum()), single_pixel_share=round(float((C[C.kind == 'viirs'].n == 1).mean()), 3),
                               single_pixel_median_dist_to_hotpix_centre_m=round(C[(C.kind == 'viirs') & (C.n == 1)].d_plain.median()))
for kind in ['viirs', 'modis']:
    s = Sg[Sg.kind == kind]
    if len(s) < 10: continue
    inside = (s.os.abs() <= 1) & (s.ot.abs() <= 1)
    res[f'3b_single_{kind}'] = dict(n=len(s), hot_centre_inside_footprint=round(inside.mean(), 3),
                                   inside_inner_half_area=round(((s.os.abs() <= .7071) & (s.ot.abs() <= .7071)).mean() / max(inside.mean(), 1e-9), 3),
                                   uniform_expectation_inner_half=0.5, median_abs_offset_scan=round(s.os.abs().median(), 3), median_abs_offset_track=round(s.ot.abs().median(), 3),
                                   uniform_expectation_median_abs_offset=0.5)
# 3c intersections
rows = []
Dd = D[D.daynight == 'D']
for day, g in Dd.groupby(Dd.t.dt.date):
    h = H[H.t.dt.date == day]
    if not len(h): continue
    pt = g.groupby('pass_id').agg(t=('t', 'min'), sensor=('sensor', 'first'), kind=('kind', 'first'))
    ids = list(pt.index)
    for i in ids:
        for j in ids:
            if j <= i or pt.sensor[i] == pt.sensor[j]: continue
            dt = abs((pt.t[j] - pt.t[i]).total_seconds()) / 3600
            if dt > 3: continue
            ki, kj = pt.kind[i], pt.kind[j]
            if ki == 'modis' and kj == 'modis': continue
            if 'modis' in (ki, kj) and pt.sensor[i if ki == 'modis' else j] != 'Terra MODIS': continue
            if ki == 'viirs' and kj == 'viirs' and dt > 2: continue
            Ui = unary_union([poly(r) for r in g[g.pass_id == i].itertuples()]); Uj = unary_union([poly(r) for r in g[g.pass_id == j].itertuples()])
            I = Ui.intersection(Uj)
            if I.area < 1e4: continue
            Uu = Ui.union(Uj); pts = shapely.points(h.x.values, h.y.values)
            inU = shapely.contains(Uu, pts); inI = shapely.contains(I, pts)
            for comp in (I.geoms if hasattr(I, 'geoms') else [I]):   # per overlapping patch, only patches with hot pixels nearby
                pass
            if inU.sum() == 0: continue
            rows.append(dict(day=day, pair='VIIRS+VIIRS' if ki == kj == 'viirs' else 'Terra+VIIRS', dt_h=dt, area_I=I.area, area_U=Uu.area,
                             hot_U=int(inU.sum()), hot_I=int(inI.sum()), hot_Ui=int(shapely.contains(Ui, pts).sum()), hot_Uj=int(shapely.contains(Uj, pts).sum())))
X3 = pd.DataFrame(rows); X3.to_csv(f'{OUT}/e3_intersections_vs_hotpix.csv', index=False)
for pair, x in X3.groupby('pair'):
    share_hot = x.hot_I.sum() / x.hot_U.sum(); share_area = x.area_I.sum() / x.area_U.sum()
    bs = []
    for _ in range(1000):
        k = rng.integers(0, len(x), len(x)); xx = x.iloc[k]; bs.append((xx.hot_I.sum() / xx.hot_U.sum()) / (xx.area_I.sum() / xx.area_U.sum()))
    res[f'3c_{pair}'] = dict(pass_pairs=len(x), hot_pixels_in_union=int(x.hot_U.sum()), share_of_hot_in_overlap=round(share_hot, 3),
                            overlap_share_of_union_area=round(share_area, 3), density_lift=round(share_hot / share_area, 2),
                            lift_ci95=[round(np.quantile(bs, .025), 2), round(np.quantile(bs, .975), 2)],
                            hot_outside_overlap_share=round(1 - share_hot, 3))
# 3d photos: closest-dot with sub-pixel (FRP-weighted cluster) positions
PH = photos(); V = D[D.kind == 'viirs']
cen = V.groupby('cl').apply(lambda g: pd.Series(dict(cxw=np.average(g.x, weights=g.frp.clip(lower=.01)), cyw=np.average(g.y, weights=g.frp.clip(lower=.01)))))
V = V.join(cen, on='cl')
rows = []
for ph in PH:
    X, Y, y, T = ph['X'], ph['Y'], ph['y'], ph['T']
    if y.sum() == 0 or y.all(): continue
    cx, cy = X.mean(), Y.mean()
    v = V[(V.t <= T - pd.Timedelta(hours=1)) & (V.t >= T - pd.Timedelta(days=4)) & (np.abs(V.x - cx) < 4000) & (np.abs(V.y - cy) < 4000)]
    if not len(v): continue
    r = dict(fire=ph['fire'], season=ph['season'])
    for nm, (px, py) in [('centres', (v.x.values, v.y.values)), ('half_to_frp_centre', (.5 * (v.x + v.cxw).values, .5 * (v.y + v.cyw).values)),
                         ('frp_centre', (v.cxw.values, v.cyw.values))]:
        d = np.hypot(X[:, None] - px[None], Y[:, None] - py[None])
        r['auc_closest_' + nm] = auc(y, -d.min(1)); r['auc_kernel_' + nm] = auc(y, np.exp(-d / 400).sum(1))
    rows.append(r)
E = pd.DataFrame(rows); E.to_csv(f'{OUT}/e3_photo.csv', index=False)
res['3d_photos'] = dict(n=len(E), **{c: round(E[c].mean(), 4) for c in E.columns if c.startswith('auc_')},
                       diff_closest_frp_centre_vs_centres_95=boot_diff(E, 'auc_closest_frp_centre', 'auc_closest_centres'),
                       diff_kernel_half_vs_centres_95=boot_diff(E, 'auc_kernel_half_to_frp_centre', 'auc_kernel_centres'))
json.dump(res, open(f'{OUT}/e3_summary.json', 'w'), indent=1, default=float); print(json.dumps(res, indent=1, default=float))
