"""Robustness of the day-varying budget: (a) true-lead strict labels (FSI thread), (b) burns caught: share of first burns listed on
at least one issue day of their window (each burn counts once, so long cloudy windows do not weigh more)."""
import json, sys, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts')
import exp_budget as E   # rebuilds m and helpers (prints its own table)
m = E.m; res = {}
TL = pd.read_parquet(D_ := '/mnt/project-files/ratapani/fsi/true_lead_labels.parquet'); TL['date'] = pd.to_datetime(TL.date)
TL = TL[TL.valid_strict][['season', 'date', 'cell_id', 'pos']].rename(columns={'pos': 'pos_tl'})
for name, d in (('true_lead_strict_loso', m[m.season < 2025].drop(columns='pos').merge(TL, on=['season', 'date', 'cell_id']).rename(columns={'pos_tl': 'pos'})),):
    d = d.reset_index(drop=True); r = {}
    for rule, sc in (('fixed5', None), ('beat_shared', None), ('day_varying', E.scale_nopeek(d, 'mu_N2')), ('day_varying_seasonality_only', E.scale_nopeek(d, 'mu_N2', clim=True)), ('day_varying_fixed', E.scale_nopeek(d, 'mu_N2'))):
        p = E.pick(d, 's', rule.replace('_seasonality_only', ''), sc); r[rule] = round(float(d.pos[p].sum() / d.pos.sum()), 4)
    d['rnd'] = np.random.default_rng(0).random(len(d)); r['fixed5_random'] = round(float(d.pos[E.pick(d, 'rnd', 'fixed5')].sum() / d.pos.sum()), 4)
    res[name] = r; print(name, r, flush=True)
for split, sel in (('burns_caught_loso', m.season < 2025), ('burns_caught_2025_26', m.season >= 2025)):
    d = m[sel].reset_index(drop=True); r = {}
    for rule, sc in (('fixed5', None), ('beat_shared', None), ('day_varying', E.scale_nopeek(d, 'mu_N2')), ('day_varying_seasonality_only', E.scale_nopeek(d, 'mu_N2', clim=True)), ('day_varying_fixed', E.scale_nopeek(d, 'mu_N2'))):
        p = E.pick(d, 's', rule.replace('_seasonality_only', ''), sc)
        g = d[d.pos].assign(hit=p[d.pos].values).groupby(['season', 'cell_id']).hit.max(); r[rule] = round(float(g.mean()), 4)
    res[split] = r; print(split, r, flush=True)
json.dump(res, open('/mnt/project-files/research/reframe/results/budget_robustness.json', 'w'), indent=1)
