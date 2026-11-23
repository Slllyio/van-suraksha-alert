"""A1b: robustness of A1 -- the same exogenous decomposition on the projection towards LATER growth (g = F - E, built
from detections 2-48 h before A and 2-48 h after B), which has no mid-point noise coupling. Edge reach is radial
(along u), so its projection on g is dpix * cos(u, g). Out: results/a1b_growth_check.json"""
import json, numpy as np, pandas as pd, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a1_decomp import load, fit, pooled_speed, OUT
D = load(); D = D[(D.fire == 1) & np.isfinite(D.pg)].copy()
cosug = (D.uE * D.gE + D.uN * D.gN) / (D.u_len * D.g_len)
D['dpix_g'] = D.dpix * cosug; D['geo'] = (D.tzB - D.tzA).fillna(0) * D.gE / D.g_len * 100
res = {}
for dn in 'DN':
    d = D[D.dn == dn]
    r, co, _ = fit(d.assign(p=d.pg), ['int_fire', 'gap_fire', 'o20', 'o21', 'dpix_g', 'geo'])
    res[dn] = dict(fit={k: {q: round(w, 3) for q, w in v.items()} for k, v in r.items()}, raw=pooled_speed(d.assign(q=d.pg), 'q'),
                   corrected=pooled_speed(d.assign(q=d.pg - co[2] * d.o20 - co[3] * d.o21 - co[4] * d.dpix_g - co[5] * d.geo), 'q'))
json.dump(res, open(f'{OUT}/a1b_growth_check.json', 'w'), indent=1); print(json.dumps(res, indent=1))
