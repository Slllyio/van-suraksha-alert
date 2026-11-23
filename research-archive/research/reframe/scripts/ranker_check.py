"""Robustness of the sanctuary-wide ranker (pooled_ranker.py) under the forecast-driven daily budget:
true-lead strict labels, and burns caught at least once."""
import json, sys, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts')
import data as D, exp_budget as E
m = pd.read_parquet(D.OUT + 'pooled_full.parquet'); res = {}
TL = pd.read_parquet('/mnt/project-files/ratapani/fsi/true_lead_labels.parquet'); TL['date'] = pd.to_datetime(TL.date)
TL = TL[TL.valid_strict][['season', 'date', 'cell_id', 'pos']].rename(columns={'pos': 'pos_tl'})
for split, sel in (('loso', m.season < 2025), ('2025_26', m.season >= 2025)):
    d = m[sel].drop(columns='pos').merge(TL, on=['season', 'date', 'cell_id']).rename(columns={'pos_tl': 'pos'}).reset_index(drop=True)
    r = {}
    if d.pos.sum():
        sc = E.scale_nopeek(d, 'mu_N2')
        for col in ('s', 'p_avg'): r[col] = round(float(d.pos[E.pick(d, col, 'day_varying', sc)].sum() / d.pos.sum()), 4)
    res['true_lead_strict_' + split] = r
    d = m[sel].reset_index(drop=True); sc = E.scale_nopeek(d, 'mu_N2'); r = {}
    for col in ('s', 'p_avg'):
        p = E.pick(d, col, 'day_varying', sc)
        r[col] = round(float(d[d.pos].assign(hit=p[d.pos].values).groupby(['season', 'cell_id']).hit.max().mean()), 4)
    res['burns_caught_' + split] = r
print(res)
json.dump(res, open('/mnt/project-files/research/reframe/results/pooled_ranker_robustness.json', 'w'), indent=1)
