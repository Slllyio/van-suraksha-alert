"""Tracking step 1: calibrate the pieces of the forward detection model that do not need the inversion.
(a) Per-satellite geolocation offset and scatter from static industrial sources (FIRMS type 2, all MP).
    Each site's reference point = mean of all its VIIRS pass centroids (all three satellites). Offset of a satellite =
    mean (pass centroid - site reference) over its passes, by day/night; 95% range by bootstrap over sites.
    Geolocation scatter per axis = sqrt(var(single-pixel pass position) - pixel^2/12): the observed scatter of a fixed
    point minus the scatter that pure grid placement (uniform inside the pixel) explains.
(b) Pixel lattice spacing: separation of adjacent fire pixels of one pass, along scan and along track, in units of the
    FIRMS scan / track size (does the next pixel start where this footprint ends?).
(c) Pass-level detection rate of a fire known to be burning (detected by some pass before and after within 14 h).
Out: results/t1_calib.json (+ geoloc offsets used by t2)."""
import json, os
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
SC = os.environ.get('TR_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_track')
OUT = '/mnt/project-files/ratapani/fsi/scouting/code/squares_v2/tracking/results'; os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(0)
def axes(h):
    h = np.radians(np.asarray(h, float))
    return np.stack([np.cos(h), -np.sin(h)], -1), np.stack([np.sin(h), np.cos(h)], -1)
res = {}
# ---------------- (a) static sites
S = pd.read_parquet(f'{SC}/static.parquet'); S = S[S.kind == 'viirs']
S['cell'] = (S.x // 3000).astype(int).astype(str) + '_' + (S.y // 3000).astype(int).astype(str)
pc = S.groupby(['cell', 'pass_key']).agg(x=('x', 'mean'), y=('y', 'mean'), n=('x', 'size'), sensor=('sensor', 'first'),
                                       dn=('daynight', 'first'), h=('heading', 'first'), scan=('scan_m', 'mean'), track=('track_m', 'mean'),
                                       t=('t', 'first')).reset_index()
cnt = pc.groupby('cell').sensor.agg(['size', 'nunique']); good = cnt[(cnt['size'] >= 30) & (cnt['nunique'] == 3)].index
pc = pc[pc.cell.isin(good)].copy()
ref = pc.groupby('cell')[['x', 'y']].mean()
pc['dx'] = pc.x - ref.loc[pc.cell, 'x'].values; pc['dy'] = pc.y - ref.loc[pc.cell, 'y'].values
pc = pc[np.hypot(pc.dx, pc.dy) < 1500]
us, ut = axes(pc.h.values); pc['ds'] = pc.dx * us[:, 0] + pc.dy * us[:, 1]; pc['dt'] = pc.dx * ut[:, 0] + pc.dy * ut[:, 1]
res['static_sites'] = int(pc.cell.nunique()); res['static_passes'] = len(pc)
cells = pc.cell.unique()
off = {}
for (s, dn), g in pc.groupby(['sensor', 'dn']):
    m = lambda d: np.array([d.dx.mean(), d.dy.mean(), d.ds.mean(), d.dt.mean()])
    gi = g.set_index('cell'); v = []
    gc = gi.index.unique().values
    for _ in range(300):
        k = rng.choice(gc, len(gc)); v.append(m(gi.loc[k]))
    lo, hi = np.quantile(v, [.025, .975], 0)
    one = g[g.n == 1]
    var_s = one.ds.var() - (one.scan ** 2).mean() / 12; var_t = one.dt.var() - (one.track ** 2).mean() / 12
    # robust version: MAD-based (heavy tail from multi-stack sites)
    rs = (1.4826 * np.median(np.abs(one.ds - one.ds.median()))) ** 2 - (one.scan ** 2).mean() / 12
    rt = (1.4826 * np.median(np.abs(one.dt - one.dt.median()))) ** 2 - (one.track ** 2).mean() / 12
    off[f'{s}|{dn}'] = dict(n_pass=len(g), n_sites=len(gc), east_m=round(g.dx.mean(), 1), north_m=round(g.dy.mean(), 1),
                            east_ci=[round(lo[0], 1), round(hi[0], 1)], north_ci=[round(lo[1], 1), round(hi[1], 1)],
                            along_scan_m=round(g.ds.mean(), 1), along_track_m=round(g.dt.mean(), 1),
                            geoloc_sd_scan_m=round(float(np.sqrt(max(var_s, 0))), 1), geoloc_sd_track_m=round(float(np.sqrt(max(var_t, 0))), 1),
                            geoloc_sd_scan_robust_m=round(float(np.sqrt(max(rs, 0))), 1), geoloc_sd_track_robust_m=round(float(np.sqrt(max(rt, 0))), 1),
                            single_pixel_passes=len(one))
res['offsets'] = off
# null check: offsets estimated on even years, applied to odd years -> does the S-NPP vs NOAA-20 difference persist?
pc['yr'] = pc.t.dt.year
for half, gg in [('even_years', pc[pc.yr % 2 == 0]), ('odd_years', pc[pc.yr % 2 == 1])]:
    res[f'offsets_{half}'] = {f'{s}|{dn}': [round(g.dx.mean(), 1), round(g.dy.mean(), 1), len(g)] for (s, dn), g in gg.groupby(['sensor', 'dn'])}
# ---------------- (b) lattice spacing from adjacent fire pixels (Ratapani box detections, all seasons)
D = pd.read_parquet(f'{SC}/det.parquet'); V = D[(D.kind == 'viirs') & (D.type.fillna(0) != 2)]
rows = []
for pk, g in V.groupby('pass_key'):
    if len(g) < 2: continue
    P = g[['x', 'y']].values; pr = cKDTree(P).query_pairs(1.8 * g[['scan_m', 'track_m']].values.max(), output_type='ndarray')
    if not len(pr): continue
    us, ut = axes(g.heading.iloc[0]); dv = P[pr[:, 1]] - P[pr[:, 0]]
    s0 = .5 * (g.scan_m.values[pr[:, 0]] + g.scan_m.values[pr[:, 1]]); t0 = .5 * (g.track_m.values[pr[:, 0]] + g.track_m.values[pr[:, 1]])
    rows.append(pd.DataFrame(dict(ds=np.abs(dv @ us) / s0, dt=np.abs(dv @ ut) / t0, scan=s0, track=t0,
                                  same_frp=g.frp.values[pr[:, 0]] == g.frp.values[pr[:, 1]])))
L = pd.concat(rows)
alg_s = L[(L.dt < .25) & (L.ds > .4) & (L.ds < 1.6)].ds; alg_t = L[(L.ds < .25) & (L.dt > .4) & (L.dt < 1.6)].dt
res['lattice'] = dict(pairs_scan_neighbours=len(alg_s), along_scan_spacing_over_scan=dict(median=round(alg_s.median(), 3), iqr=[round(alg_s.quantile(.25), 3), round(alg_s.quantile(.75), 3)]),
                      pairs_track_neighbours=len(alg_t), along_track_spacing_over_track=dict(median=round(alg_t.median(), 3), iqr=[round(alg_t.quantile(.25), 3), round(alg_t.quantile(.75), 3)]))
for lo_, hi_ in [(0, .45), (.45, .6), (.6, 1)]:
    q = L[(L.ds < .25) & (L.dt > .4) & (L.dt < 1.6) & (L.track / 1000).between(lo_, hi_)].dt
    res['lattice'][f'track_spacing_ratio_track_{lo_}-{hi_}km'] = [round(q.median(), 3), len(q)]
# ---------------- (c) pass-level detection of a burning fire
P = pd.read_parquet(f'{SC}/passes.parquet')
Df = D[D.fire >= 0]
rows = []
for fire, g in Df.groupby('fire'):
    tt = np.sort(g.t.unique()); t0, t1 = tt.min(), tt.max()
    if (t1 - t0) < np.timedelta64(12, 'h'): continue
    pp = P[(P.t > t0) & (P.t < t1)]
    flagged = set(g.pass_key)
    for r in pp.itertuples():
        before = tt[tt < r.t - np.timedelta64(20, 'm')]; after = tt[tt > r.t + np.timedelta64(20, 'm')]
        if not len(before) or not len(after): continue
        if (r.t - before.max()) > np.timedelta64(14, 'h') or (after.min() - r.t) > np.timedelta64(14, 'h'): continue
        rows.append(dict(fire=fire, sensor=r.sensor, dn=r.daynight, scan=r.scan_m, hit=r.pass_key in flagged))
H = pd.DataFrame(rows)
res['pass_detection_rate_burning_fire'] = {f'{s}|{dn}': [round(g.hit.mean(), 3), len(g)] for (s, dn), g in H.groupby(['sensor', 'dn'])}
H['zone'] = pd.cut(H.scan, [0, 420, 520, 650, 2000])
res['pass_detection_rate_by_scan_size_viirs'] = {str(k): [round(g.hit.mean(), 3), len(g)] for k, g in H[~H.sensor.str.contains('MODIS')].groupby('zone', observed=True)}
json.dump(res, open(f'{OUT}/t1_calib.json', 'w'), indent=1); print(json.dumps(res, indent=1))
