"""Akkshay 18 Oct 04:21Z: "VIIRS placement error about 300 m, u sure? check thoroughly". Split the hot-pixel-to-block distance
into its parts on the 3,469 statewide passes: (1) pixel size (a fire anywhere inside a 375-800 m pixel is reported at the pixel
centre), (2) true geolocation error, (3) fire movement in the 2-3.5 h gap, (4) fire extent and the 600 m selection radius.
Nulls keep each pass's real hot-pixel shape. Out: results/mp_hotpix_error_parts.json"""
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
P = []
for _, r in V.iterrows():
    f = glob.glob(f"{SC}/{r.pass_id.replace('|', '_').replace(':', '')}_*.npz")
    if not f or r.pass_id not in G: continue
    z = np.load(f[0]); P.append((r.pass_id, r.satellite, r.gap_h, z['x'].astype(float), z['y'].astype(float), G[r.pass_id]))
print('passes', len(P))
def stats(hx, hy, b, radius=600):
    bx, by, bw, bh = b.x.values, b.y.values, b.pw.values, b.ph.values
    d = np.hypot(hx[:, None] - bx[None], hy[:, None] - by[None]); keep = d.min(1) <= radius
    if keep.sum() < 3: return None
    hx, hy, d = hx[keep], hy[keep], d[keep]; i = d.argmin(1)
    u = np.maximum(np.abs(hx - bx[i]) / (bw[i] / 2), np.abs(hy - by[i]) / (bh[i] / 2))
    cx, cy = hx.mean(), hy.mean(); dc = np.hypot(cx - bx, cy - by).min(); j = np.hypot(cx - bx, cy - by).argmin()
    out = dict(d_pix=np.median(d.min(1)), d_cen=dc, d_cen_over_pw=dc / bw[j], outer=(u > 0.5).mean(), inside=(u <= 1).mean(), pw=bw[j], n=len(hx),
               extent=np.hypot(hx.std(), hy.std()))
    if len(b) == 2:
        p0 = np.array([bx[0], by[0]]); dd = np.array([bx[1] - bx[0], by[1] - by[0]]); L = np.hypot(*dd)
        s = ((hx - p0[0]) * dd[0] + (hy - p0[1]) * dd[1]) / L ** 2; out['between'] = ((s >= 0) & (s <= 1)).mean(); out['sep'] = L
    return out
def summarise(rows):
    T = pd.DataFrame([r for r in rows if r]); two = T[T.get('sep', pd.Series(dtype=float)).notna()] if 'sep' in T else T.iloc[0:0]
    o = dict(passes=len(T), hot_pixel_to_centre_m=round(T.d_pix.median()), hot_centroid_to_centre_m=round(T.d_cen.median()), centroid_over_pixel_width=round(T.d_cen_over_pw.median(), 2),
             outer_half=round(T.outer.mean(), 3), inside=round(T.inside.mean(), 2))
    if len(two): o['adjacent_between'] = round(two[two.sep < 500].between.median(), 2); o['far_between'] = round(two[two.sep >= 500].between.median(), 2)
    return o
res = {}
# observed, with selection radius sensitivity
for rad in [400, 600, 800]: res[f'observed_radius_{rad}m'] = summarise([stats(hx, hy, b, rad) for _, _, _, hx, hy, b in P])
# observed by scan width and by gap
obs = pd.DataFrame([dict(sat=s, gap=g, **st) for (pid, s, g, hx, hy, b) in P for st in [stats(hx, hy, b)] if st])
obs['pw_bin'] = pd.cut(obs.pw, [0, 400, 450, 550, 700, 1000], labels=['375-400', '400-450', '450-550', '550-700', '700+'])
res['observed_by_pixel_width'] = {str(k): dict(passes=int(len(g)), centroid_to_centre_m=round(g.d_cen.median()), over_pixel_width=round(g.d_cen_over_pw.median(), 2), outer_half=round(g.outer.mean(), 3)) for k, g in obs.groupby('pw_bin', observed=True)}
obs['gap_bin'] = pd.cut(obs.gap, [0, 2.5, 2.8, 3.1, 3.6]); res['observed_by_gap'] = {str(k): dict(passes=int(len(g)), centroid_to_centre_m=round(g.d_cen.median())) for k, g in obs.groupby('gap_bin', observed=True)}
sl = np.polyfit(obs.gap, obs.d_cen, 1)[0]; res['gap_slope_m_per_h'] = round(float(sl))
# nulls with real shapes
rng = np.random.default_rng(2)
def null(geo_sigma=0, move=False, uniform=True, label=''):
    rows = []
    for pid, s, g, hx, hy, b in P:
        if len(b) == 1:
            cx, cy = b.x.iloc[0], b.y.iloc[0]
            if uniform: cx += rng.uniform(-b.pw.iloc[0] / 2, b.pw.iloc[0] / 2); cy += rng.uniform(-b.ph.iloc[0] / 2, b.ph.iloc[0] / 2)
        else:   # multi-block: fire centroid uniform inside a random one of its blocks? no: inside the cluster's bounding footprint
            k = rng.integers(len(b)); cx, cy = b.x.iloc[k], b.y.iloc[k]
            if uniform: cx += rng.uniform(-b.pw.iloc[k] / 2, b.pw.iloc[k] / 2); cy += rng.uniform(-b.ph.iloc[k] / 2, b.ph.iloc[k] / 2)
            # keep the real spread of the fire across the cluster: centre the shape on the cluster centre, then offset as above relative to it
            cx, cy = b.x.mean() + (cx - b.x.iloc[k]), b.y.mean() + (cy - b.y.iloc[k])
        ex, ey = rng.normal(0, geo_sigma, 2) if geo_sigma else (0, 0)
        if move:
            th = rng.uniform(0, 2 * np.pi); mv = 25 * g; ex += mv * np.cos(th); ey += mv * np.sin(th)
        rows.append(stats(hx - hx.mean() + cx + ex, hy - hy.mean() + cy + ey, b))
    res[label] = summarise(rows)
null(0, False, False, 'null_fire_at_block_centre')
null(0, False, True, 'null_pixel_size_only')
null(75, False, True, 'null_pixel_size_plus_geolocation_75m')
null(75, True, True, 'null_pixel_size_plus_geolocation_75m_plus_move_25mph')
null(150, True, True, 'null_pixel_size_plus_geolocation_150m_plus_move')
null(250, True, True, 'null_pixel_size_plus_geolocation_250m_plus_move')
json.dump(res, open(f'{R}/mp_hotpix_error_parts.json', 'w'), indent=1); print(json.dumps(res, indent=1))
