"""Day-varying budget (no peeking) with a hard per-beat daily cap: picks ranked sanctuary-wide but no beat gets more than CAP a day."""
import json, sys, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts')
import exp_budget as E
m = E.m; res = {}
for split, sel in (('loso_2017_24', m.season < 2025), ('test_2025_26', m.season >= 2025)):
    d = m[sel].reset_index(drop=True); sc = E.scale_nopeek(d, 'mu_N2'); r = {}
    rb = d.groupby(['season', 'date', 'beat_uid'])['s'].rank('first', ascending=False)
    for cap in (5, 8, 10, 15, 25, 999):
        ok = rb <= cap                                  # cells a beat could check today under the cap
        s2 = d.s.where(ok, -1e9)
        rd = s2.groupby([d.season, d.date]).rank('first', ascending=False)
        p = (rd <= E.K * E.NB * sc) & ok
        r[f'cap{cap}'] = round(float(d.pos[p].sum() / d.pos.sum()), 4); r[f'cap{cap}_picks_per_day'] = round(float(p.sum() / d.groupby(['season', 'date']).ngroups), 1)
    res[split] = r; print(split, r, flush=True)
json.dump(res, open('/mnt/project-files/research/reframe/results/budget_caps.json', 'w'), indent=1)
