"""Step 2c: how much of the no-movement noise is pure grid jitter? A fixed point source seen by two looks: each look's
pixel grid falls at a random offset (rotated to its own track), the flagged pixel is the one containing the point, plus a
geolocation error (normal, sd g per axis). Matched to the static-source single-pixel pairs (pixel sizes, day/night)."""
import json
import numpy as np, pandas as pd
from s_lib import *
N = pd.read_parquet(f'{SC}/static_pairs_feats.parquet'); sp = N[(N.n0 == 1) & (N.n1 == 1)]
rng = np.random.default_rng(1)
def sim(pix, g, k=20):
    out = []
    for p in pix:
        pos = []
        for h in [347, 347]:
            hr = np.radians(h); ut = np.array([np.sin(hr), np.cos(hr)]); us = np.array([np.cos(hr), -np.sin(hr)])
            a = rng.uniform(-.5, .5, (k, 2)) * p
            pos.append(a[:, :1] * us + a[:, 1:] * ut + rng.normal(0, g, (k, 2)))
        out.append(np.hypot(*(pos[1] - pos[0]).T))
    return np.concatenate(out)
q = lambda v: {k: round(float(np.quantile(v, x))) for k, x in [('p50', .5), ('p75', .75), ('p95', .95)]}
res = dict(static_single_pixel_pairs=len(sp), observed=q(sp['shift']), median_pixel_m=round(sp.pix.median()))
for g in [0, 50, 100, 150, 200, 250]:
    res[f'sim_geoloc_sd_{g}m'] = q(sim(sp.pix.values[:3000], g))
json.dump(res, open(f'{OUT}/e2_jitter_sim.json', 'w'), indent=1); print(json.dumps(res, indent=1))
