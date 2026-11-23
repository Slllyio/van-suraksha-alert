"""Where is the headroom under the forecast-driven daily budget? Swap in truth for one part at a time:
 daily total from true N2 (perfect day forecast) x model cell ranking, and model daily total x perfect cell ranking."""
import json, sys, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts')
import exp_budget as E
m = E.m; res = {}
for split, sel in (('loso_2017_24', m.season < 2025), ('test_2025_26', m.season >= 2025)):
    d = m[sel].reset_index(drop=True); r = {}
    sc_f = E.scale_nopeek(d, 'mu_N2')
    sc_t = E.scale(d, 'N2')     # perfect day forecast (same season total)
    for nm, col, sc in (('model_day_model_cells', 's', sc_f), ('perfect_day_model_cells', 's', sc_t),
                        ('model_day_perfect_cells', 'truth', sc_f), ('perfect_both', 'truth', sc_t)):
        p = E.pick(d, col, 'day_varying', sc); r[nm] = round(float(d.pos[p].sum() / d.pos.sum()), 4)
    res[split] = r; print(split, r, flush=True)
json.dump(res, open('/mnt/project-files/research/reframe/results/headroom.json', 'w'), indent=1)
