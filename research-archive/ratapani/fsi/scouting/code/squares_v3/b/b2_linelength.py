"""B step 2a: active fire-line length from the VIIRS blocks of one pass, calibrated on 20-30 m hot pixels.

Truth: Sentinel-2 / Landsat hot pixels (fire-alert-scars/out/af, on a common 20 m grid, ~10:45 IST) inside a Ratapani
fire's v2 outline + 300 m, scenes with >= 3 hot pixels. Hot-line length = skeleton length of the hot-pixel mask (closed by
one 20 m pixel so a broken line stays one line; isolated pixels count 20 m).
VIIRS: every pass of the same fire within 4 h of the scene, each pass on its own (no merging). Per pass, from its
blocks (scan x track boxes turned to the track):
  n         number of blocks
  n_w       n x mean along-scan width (m): "each block holds one block-width of line"
  half_per  half the outer perimeter of the union of the blocks (m): a line along the cluster's edge (big-fires 14c)
  extent    longest distance across the block centres + one block width (m)
  groups    clusters of touching blocks
Fit on even seasons, scored on odd seasons (and the reverse): log(hot length) = a + b log(predictor) [+ gap term].
Also the same for Terra MODIS passes within 1 h (near-simultaneous, 1 km blocks).
Out: results/b2_linelength.csv/json, scratch line_pass.parquet (line length for EVERY VIIRS pass of every fire)."""
import sys, os, json, glob, pickle
import numpy as np, pandas as pd, pyproj
from scipy.spatial import cKDTree
from scipy import ndimage
from skimage.morphology import skeletonize
from shapely.geometry import Polygon
from shapely.ops import unary_union
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b_lib import *
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform

def blocks_poly(d):
    """union of the pass's footprints (scan x track boxes turned to the satellite track)"""
    ps = []
    for r in d.itertuples():
        h = np.radians(r.heading); us = np.array([np.cos(h), -np.sin(h)]); ut = np.array([np.sin(h), np.cos(h)])
        a, b = r.scan_m / 2, r.track_m / 2; c = np.array([r.x, r.y])
        ps.append(Polygon([c + sa * a * us + sb * b * ut for sa, sb in [(-1, -1), (1, -1), (1, 1), (-1, 1)]]))
    return unary_union(ps)

def pass_geometry(d):
    """arrangement measures of one pass's blocks on one fire"""
    n = len(d); w = d.scan_m.mean()
    U = blocks_poly(d.assign(scan_m=d.scan_m * 1.02, track_m=d.track_m * 1.03))     # 1.006 / 1.024 spacing: touching blocks merge
    xy = d[['x', 'y']].values
    ext = (np.max(np.hypot(*(xy[:, None] - xy[None]).transpose(2, 0, 1))) if n > 1 else 0.0) + w
    groups = len(U.geoms) if hasattr(U, 'geoms') else 1
    return dict(n=n, w=w, n_w=n * w, half_per=U.length / 2, extent=ext, groups=groups, area_ha=U.area / 1e4)

def hot_length(rows, cols):
    r0, c0 = rows.min() - 2, cols.min() - 2
    M = np.zeros((rows.max() - r0 + 3, cols.max() - c0 + 3), bool); M[rows - r0, cols - c0] = True
    Mc = ndimage.binary_closing(M, structure=np.ones((3, 3)), iterations=1) | M
    sk = skeletonize(Mc)
    lab, nl = ndimage.label(Mc, structure=np.ones((3, 3)))
    # skeleton length: orthogonal steps 20 m, diagonal 28 m (count neighbours)
    L = 0.0
    if sk.any():
        o = sk[:, 1:] & sk[:, :-1]; v = sk[1:, :] & sk[:-1, :]; d1 = sk[1:, 1:] & sk[:-1, :-1]; d2 = sk[1:, :-1] & sk[:-1, 1:]
        L = 20 * (o.sum() + v.sum()) + 28.3 * (d1.sum() + d2.sum()) * 0.5
    L = max(L, 20.0 * nl)
    return dict(hot_n=len(rows), hot_len=L, hot_groups=nl)

if __name__ == '__main__':
    H = pd.concat([pd.read_csv(f, usecols=['row', 'col', 'date', 'time_utc', 'lon', 'lat', 'scene', 'sensor']) for f in glob.glob(f'{ROOT}/fire-alert-scars/out/af/af_20*.csv')])
    H['x'], H['y'] = tp(H.lon.values, H.lat.values); H['t'] = pd.to_datetime(H.date + ' ' + H.time_utc)
    H = H.drop_duplicates(['row', 'col', 't']).reset_index(drop=True); htree = cKDTree(H[['x', 'y']].values)
    D = pd.read_parquet(f'{TRACK}/det.parquet'); D = D[(D.fire >= 0) & (D.type.fillna(0) != 2)].copy()
    S = pickle.load(open(f'{R17}/scars.pkl', 'rb'))
    # line geometry of every VIIRS / MODIS pass on every fire (used later for growth and forecasts)
    CACHE = os.path.exists(f'{OUT}/b2_linelength_pairs.csv') and os.path.exists(f'{SC}/pass_geom.parquet') and not os.environ.get('B_REDO')
    G = []
    for (fire, pk), d in ([] if CACHE else D.groupby(['fire', 'pass_key'])):
        g = pass_geometry(d); g.update(fire=fire, pass_key=pk, sensor=d.sensor.iloc[0], kind=d.kind.iloc[0], t=d.t.min(), dn=d.daynight.iloc[0],
                                       frp=d.frp.sum(), track=d.track_m.mean()); G.append(g)
    if CACHE: G = pd.read_parquet(f'{SC}/pass_geom.parquet')
    else: G = pd.DataFrame(G); G.to_parquet(f'{SC}/pass_geom.parquet')
    rows = []
    for fire, d in ([] if CACHE else D.groupby('fire')):
        poly = S[fire].buffer(300); x0, y0, x1, y1 = poly.bounds
        ii = htree.query_ball_point([(x0 + x1) / 2, (y0 + y1) / 2], np.hypot(x1 - x0, y1 - y0) / 2 + 10)
        if not ii: continue
        h = H.iloc[ii]; h = h[(h.t >= d.t.min() - pd.Timedelta(hours=30)) & (h.t <= d.t.max() + pd.Timedelta(hours=30))]
        if not len(h): continue
        from shapely.prepared import prep
        pp = prep(poly); h = h[[pp.contains_xy(a, b) if hasattr(pp, 'contains_xy') else pp.contains(__import__('shapely').geometry.Point(a, b)) for a, b in zip(h.x, h.y)]]
        for ts, hs in h.groupby('t'):
            if len(hs) < 3: continue
            hl = hot_length(hs.row.values, hs.col.values)
            gg = G[(G.fire == fire) & ((G.t - ts).abs() <= pd.Timedelta(hours=4))]
            for r in gg.itertuples():
                rows.append(dict(fire=fire, season=ts.year, scene=hs.scene.iloc[0], hs_sensor=hs.sensor.iloc[0], t_scene=ts, pass_key=r.pass_key,
                                 sensor=r.sensor, kind=r.kind, dn=r.dn, gap_h=(r.t - ts).total_seconds() / 3600, n=r.n, w=r.w, n_w=r.n_w,
                                 half_per=r.half_per, extent=r.extent, groups=r.groups, frp=r.frp, track=r.track, **hl))
    if CACHE: X = pd.read_csv(f'{OUT}/b2_linelength_pairs.csv', parse_dates=['t_scene'])
    else: X = pd.DataFrame(rows); X.to_csv(f'{OUT}/b2_linelength_pairs.csv', index=False)
    V = X[(X.kind == 'viirs') & X.gap_h.between(1.5, 4)].copy()      # the ~13:30 day passes 2-3 h after the scene
    Tm = X[(X.kind == 'modis') & (X.sensor == 'Terra MODIS') & (X.gap_h.abs() <= 1)].copy()
    res = dict(scene_fire_pairs=int(X.groupby(['fire', 'scene']).ngroups), viirs_day_pass_pairs=len(V), viirs_fires=int(V.fire.nunique()), terra_pairs=len(Tm),
               hot_len_median_m=float(V.hot_len.median()), hot_len_iqr=[float(V.hot_len.quantile(.25)), float(V.hot_len.quantile(.75))])
    out = []
    for nm, data in [('viirs_day', V), ('terra_same_time', Tm)]:
        if len(data) < 20: continue
        y = np.log(data.hot_len.values)
        for pred in ['n', 'n_w', 'half_per', 'extent', 'frp']:
            x = np.log(np.clip(data[pred].values, 1e-3, None)); sc = []
            for tr_par in (0, 1):
                tr = (data.season % 2 == tr_par).values; te = ~tr
                b, a = np.polyfit(x[tr], y[tr], 1); e = y[te] - (a + b * x[te])
                sc.append(dict(r2=1 - np.mean(e ** 2) / np.var(y[te]), a=a, b=b, n_te=int(te.sum()), med_ratio=float(np.exp(np.median(e)))))
            b, a = np.polyfit(x, y, 1)
            r2 = np.mean([s['r2'] for s in sc])
            # bootstrap over fires of the held-out R2 (even->odd and odd->even averaged)
            rng = np.random.default_rng(5); fires = data.fire.unique(); bs = []
            for _ in range(300):
                k = rng.choice(fires, len(fires)); dd = pd.concat([data[data.fire == f] for f in k]) if len(fires) < 400 else data.sample(frac=1, replace=True)
                yy = np.log(dd.hot_len.values); xx = np.log(np.clip(dd[pred].values, 1e-3, None)); v = []
                for tr_par in (0, 1):
                    tr = (dd.season % 2 == tr_par).values; te = ~tr
                    if tr.sum() < 10 or te.sum() < 10: continue
                    if np.ptp(xx[tr]) == 0 or np.var(yy[te]) == 0: continue
                    try: bb, aa = np.polyfit(xx[tr], yy[tr], 1)
                    except Exception: continue
                    ee = yy[te] - (aa + bb * xx[te]); v.append(1 - np.mean(ee ** 2) / np.var(yy[te]))
                if v: bs.append(np.mean(v))
            out.append(dict(set=nm, predictor=pred, n=len(data), fires=int(data.fire.nunique()), heldout_r2=round(r2, 3),
                            r2_ci=f'{np.quantile(bs, .025):.3f} to {np.quantile(bs, .975):.3f}', slope_b=round(b, 3), intercept_a=round(a, 3),
                            spearman=round(float(pd.Series(data[pred].values).corr(pd.Series(data.hot_len.values), method='spearman')), 3)))
    T = pd.DataFrame(out); T.to_csv(f'{OUT}/b2_linelength.csv', index=False); print(T.to_string())
    # chosen calibration: half perimeter (or best held-out); stored as L = exp(a) * pred^b, fitted on all seasons for later steps,
    # plus per-season-held-out versions so downstream tests stay held out
    best = T[T.set == 'viirs_day'].sort_values('heldout_r2', ascending=False).iloc[0]
    res['best_predictor'] = best.predictor
    cal = {}
    for s in sorted(D.t.dt.year.unique()):
        tr = V[V.season != s]; x = np.log(np.clip(tr[best.predictor].values, 1e-3, None)); b, a = np.polyfit(x, np.log(tr.hot_len.values), 1)
        cal[int(s)] = (float(a), float(b))
    x = np.log(np.clip(V[best.predictor].values, 1e-3, None)); b, a = np.polyfit(x, np.log(V.hot_len.values), 1); cal['all'] = (float(a), float(b))
    res['calibration'] = {str(k): v for k, v in cal.items()}
    # by block count: median hot length per block count (plain table)
    tab = V.groupby(pd.cut(V.n, [0, 1, 2, 3, 5, 9, 1e4]), observed=True).agg(passes=('n', 'size'), hot_len_med=('hot_len', 'median'), hot_n_med=('hot_n', 'median'),
                                                                           half_per_med=('half_per', 'median'))
    res['by_blocks'] = {str(k): {q: round(float(v), 1) for q, v in r.items()} for k, r in tab.iterrows()}
    # line length for every pass (season-held-out calibration); night passes use the day calibration [inference]
    G['season'] = G.t.dt.year
    ab = G.season.map(lambda s: cal.get(int(s), cal['all']))
    G['L_m'] = np.exp([a for a, b in ab]) * np.clip(G[best.predictor].values, 1e-3, None) ** np.array([b for a, b in ab])
    G.to_parquet(f'{SC}/line_pass.parquet')
    json.dump(res, open(f'{OUT}/b2_linelength.json', 'w'), indent=1, default=str); print(json.dumps(res, indent=1, default=str))
