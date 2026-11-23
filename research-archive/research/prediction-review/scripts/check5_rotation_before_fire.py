"""Does the no-repeat rotation still win when only listings BEFORE the fire count?
Uses the FSI thread's VIIRS-dated first burns (ratapani/fsi/true_lead_labels_v2.parquet, fire_day). A dated burn is
'warned' if its cell was listed on issue day t with fire_day - t in {1, 2} (a true 1-2 day warning), or on any day
before the fire day. Rules: fixed 5 per beat by lean ensemble; same but skipping cells listed in the previous 2 days;
random 5 per beat. LOSO 2017-24 predictions (lean_ensemble_pred.parquet). -> ../results/check5.json"""
import json, importlib.util, numpy as np, pandas as pd
RS = '/mnt/project-files/research/'; RA = '/mnt/project-files/ratapani/'; OUT = RS + 'prediction-review/results/'
spec = importlib.util.spec_from_file_location('ps', RS + 'ratapani-ignition/scripts/pipeline_score.py'); ps = importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)
beat = pd.read_csv(RA + 'beats/cell_beat.csv').set_index('cell_id').beat_uid
lab = ps.labels(range(2017, 2025)); lab['b'] = lab.cell_id.map(beat).values
ens = pd.read_parquet(RS + 'ratapani-ignition/results/lean_ensemble_pred.parquet'); ens['date'] = pd.to_datetime(ens['date'])
m = lab.merge(ens[['season', 'date', 'cell_id', 'lean_ensemble']], on=['season', 'date', 'cell_id'], how='left')
m['s'] = m.lean_ensemble.fillna(-1e9) + 1e-6 * np.random.default_rng(1).random(len(m)); m['rnd'] = np.random.default_rng(0).random(len(m))
tl = pd.read_parquet(RA + 'fsi/true_lead_labels_v2.parquet'); tl['date'] = pd.to_datetime(tl['date'])
fd = tl[tl.dated & tl.fire_day.notna()].groupby(['season', 'cell_id']).fire_day.first()
listed = {k: [] for k in ('fixed5', 'no_repeat_2d', 'random')}
for Y in range(2017, 2025):
    d = m[m.season == Y]; recent = []
    for x, g in d.groupby('date'):
        r0 = g.s.groupby(g.b).rank(ascending=False) <= 5
        blocked = g.cell_id.isin(set().union(*recent) if recent else set())
        r1 = g.s.where(~blocked, g.s - 1e6).groupby(g.b).rank(ascending=False) <= 5
        rr = g.rnd.groupby(g.b).rank(ascending=False) <= 5
        for k, sel in (('fixed5', r0), ('no_repeat_2d', r1), ('random', rr)):
            listed[k].append(pd.DataFrame({'season': Y, 'cell_id': g.cell_id[sel].values, 'date': x}))
        recent = (recent + [set(g.cell_id[r1])])[-2:]
res = {'dated_first_burns': int(len(fd))}
F = fd.rename('fire_day').reset_index()
for k, L in listed.items():
    L = pd.concat(L).merge(F, on=['season', 'cell_id']); lead = (L.fire_day - L.date).dt.days
    w12 = L[lead.between(1, 2)].groupby(['season', 'cell_id']).size(); wany = L[lead >= 1].groupby(['season', 'cell_id']).size()
    res[k] = {'warned_1_2_days_before': round(100 * len(w12) / len(fd), 1), 'listed_any_day_before': round(100 * len(wany) / len(fd), 1),
              'listings_per_dated_burn_before_fire': round(float(wany.mean()), 2)}
json.dump(res, open(OUT + 'check5.json', 'w'), indent=1); print(json.dumps(res, indent=1)); print('CHECK5_DONE')
