"""Direction of travel from several VIIRS looks a few hours apart, with the true pixel geolocation of the fire masks.
For each fire and each pass P with fire pixels (class 7-9), earlier passes of the same fire 0.5-6 h before P that also had
fire pixels form the short sequence. Directions:
  A  seq   = centroid of fire pixels at P - centroid of fire pixels in the earlier passes (= what FIRMS dots give)
  B  died  = centroid of fire pixels at P - centroid of pixels that were fire earlier but are clear land (class 5) at P (clear pixel centre within 200 m of an earlier fire pixel; pixel grids differ per pass)
             (uses the mask's "looked, no fire": the side that burned out -> the live side)
Truth: centroid of fire pixels in this fire's passes 12-36 h after P minus centroid at P (only when >=200 m apart).
Score: share within 45 deg (random 25%), fire-bootstrap CI. Input results/mask_pixels_near_fires.parquet.
Output results/mask_direction_test.json"""
import os, json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
HERE = os.path.dirname(os.path.abspath(__file__)); RES = os.environ.get('MASK_RES', f'{HERE}/results')
X = pd.read_parquet(f'{RES}/mask_pixels_near_fires.parquet', columns=['fire', 't_pass', 'lat', 'lon', 'cls'])
X['x'] = X.lon * 111195 * np.cos(np.radians(23.0)); X['y'] = X.lat * 111195
def ang(a, b): return float(np.degrees(np.abs(np.arctan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))))
rows = []
for f, g in X.groupby('fire'):
    fp = g[g.cls >= 7]; ts = sorted(fp.t_pass.unique())
    if len(ts) < 2: continue
    cen = {t: fp[fp.t_pass == t][['x', 'y']].mean().values for t in ts}
    for t in ts:
        t = pd.Timestamp(t); prev = [s for s in ts if pd.Timedelta(minutes=30) <= t - pd.Timestamp(s) <= pd.Timedelta(hours=6)]
        nxt = [s for s in ts if pd.Timedelta(hours=12) <= pd.Timestamp(s) - t <= pd.Timedelta(hours=36)]
        if not prev or not nxt: continue
        cP = cen[t]; truth = fp[fp.t_pass.isin(nxt)][['x', 'y']].mean().values - cP
        if np.hypot(*truth) < 200: continue
        cE = fp[fp.t_pass.isin(prev)][['x', 'y']].mean().values
        rec = dict(fire=f, t=t, n_prev=len(prev), truth_m=float(np.hypot(*truth)), ang_A=ang(cP - cE, truth))
        E = fp[fp.t_pass.isin(prev)][['x', 'y']].values; C = g[(g.t_pass == t) & (g.cls == 5)]
        now = C[cKDTree(E).query(C[['x', 'y']].values, distance_upper_bound=200)[0] < 200] if len(C) else C
        if len(now) >= 1: rec['ang_B'] = ang(cP - now[['x', 'y']].mean().values, truth)
        rows.append(rec)
D = pd.DataFrame(rows); rng = np.random.default_rng(0)
def sc(c):
    d = D.dropna(subset=[c]); fs = d.fire.unique(); gg = {k: (v[c] <= 45).values for k, v in d.groupby('fire')}
    b = [np.mean(np.concatenate([gg[k] for k in rng.choice(fs, len(fs))])) for _ in range(1000)]
    return dict(n=int(len(d)), fires=int(len(fs)), within_45=round(float((d[c] <= 45).mean()), 3),
                ci=[round(float(np.percentile(b, 2.5)), 3), round(float(np.percentile(b, 97.5)), 3)], median_angle=round(float(d[c].median()), 1))
out = dict(random_within_45=0.25, A_sequence_of_looks=sc('ang_A'), B_burnt_out_side_to_live_side=sc('ang_B'))
both = D.dropna(subset=['ang_B']); out['same_cases'] = dict(n=len(both), A=round(float((both.ang_A <= 45).mean()), 3), B=round(float((both.ang_B <= 45).mean()), 3))
json.dump(out, open(f'{RES}/mask_direction_test.json', 'w'), indent=1); print(json.dumps(out, indent=1))
