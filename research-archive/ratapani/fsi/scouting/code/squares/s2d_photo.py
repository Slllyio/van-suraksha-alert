"""Experiment 2d: does the direction of the last small-gap pair before a mid-fire photo help say which ground has burned
by the photo?  Score = kernel of VIIRS dots seen >= 1 h before (sum exp(-d/400 m)), times 1 + a*cos(angle between the
pixel's bearing from the centre of those dots and the pair's direction). Direction from (i) FRP-weighted centre shift,
(ii) bearing of new pixels, (iii) persistence (previous growth direction, for comparison). a = 0 / 0.25 / 0.5."""
import json
import numpy as np, pandas as pd
from s_lib import *
P = pd.read_csv(f'{OUT}/e2_small_gap_pairs.csv', parse_dates=['t']); P = P[P.vv]
D = load_det(); V = D[(D.kind == 'viirs') & (D.type.fillna(0) != 2)]
rows = []
for ph in photos():
    X, Y, y, T = ph['X'], ph['Y'], ph['y'], ph['T']
    if y.sum() == 0 or y.all(): continue
    pp = P[(P.fire == ph['fire']) & (P.t <= T - pd.Timedelta(hours=1)) & (P.t >= T - pd.Timedelta(hours=24))]
    if not len(pp): continue
    pr = pp.sort_values('t').iloc[-1]
    v = V[(V.fire == ph['fire']) & (V.t <= T - pd.Timedelta(hours=1))]
    d = np.hypot(X[:, None] - v.x.values[None], Y[:, None] - v.y.values[None]); k = np.exp(-d / 400).sum(1)
    bx, by = X - v.x.mean(), Y - v.y.mean(); bn = np.hypot(bx, by) + 1e-9
    r = dict(fire=ph['fire'], season=ph['season'], auc_kernel=auc(y, k))
    for nm, (ux, uy) in [('frp_shift', (pr.swx, pr.swy)), ('new_pixels', (pr.get('nbx', np.nan), pr.get('nby', np.nan))), ('persistence', (pr.get('px', np.nan), pr.get('py', np.nan)))]:
        if not np.isfinite(ux) or np.hypot(ux, uy) == 0: continue
        c = (bx * ux + by * uy) / (bn * np.hypot(ux, uy))
        for a in [0.25, 0.5]:
            r[f'auc_{nm}_a{a}'] = auc(y, k * (1 + a * c))
    rows.append(r)
E = pd.DataFrame(rows); E.to_csv(f'{OUT}/e2_photo_direction.csv', index=False)
res = dict(photos=len(E))
for c in [c for c in E.columns if c.startswith('auc_') and c != 'auc_kernel']:
    g = E.dropna(subset=[c])
    res[c] = dict(n=len(g), auc=round(g[c].mean(), 4), kernel_same_photos=round(g.auc_kernel.mean(), 4), diff_95=boot_diff(g, c, 'auc_kernel'))
json.dump(res, open(f'{OUT}/e2_photo_direction.json', 'w'), indent=1); print(json.dumps(res, indent=1))
