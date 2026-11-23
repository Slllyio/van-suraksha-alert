"""Independent rebuild of the "when to check" result, plus a no-repeat rotation rule, from saved lean-ensemble predictions.
Calendar budget: each day's sanctuary total = 470 x (training seasons' mean positives on that day-of-year, 7-day smoothed,
divided by its season mean), clipped 0.25-3x and rescaled to average 470. Picks = top cells sanctuary-wide by lean score.
Also reports a fixed 5-per-beat rule that skips cells already listed in the previous 2 days (rotation), scored on both
cell-days and on first-burn windows caught at least once. LOSO 2017-24 and 2025-26.
Usage: python3 check4_when_and_rotation.py -> ../results/check4.json"""
import json, importlib.util, numpy as np, pandas as pd
RS = '/mnt/project-files/research/'; RA = '/mnt/project-files/ratapani/'; OUT = RS + 'prediction-review/results/'
spec = importlib.util.spec_from_file_location('ps', RS + 'ratapani-ignition/scripts/pipeline_score.py'); ps = importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)
beat = pd.read_csv(RA + 'beats/cell_beat.csv').set_index('cell_id').beat_uid
lab = ps.labels(range(2017, 2027)); lab['b'] = lab.cell_id.map(beat).values
ens = pd.read_parquet(RS + 'ratapani-ignition/results/lean_ensemble_pred.parquet'); ens['date'] = pd.to_datetime(ens['date'])
m = lab.merge(ens[['season', 'date', 'cell_id', 'lean_ensemble']], on=['season', 'date', 'cell_id'], how='left')
m['s'] = m.lean_ensemble.fillna(-1e9) + 1e-6 * np.random.default_rng(1).random(len(m)); m['doy'] = m.date.dt.dayofyear
m['rnd'] = np.random.default_rng(0).random(len(m))
daily = m.groupby(['season', 'doy']).pos.sum().unstack(0).fillna(0)
res = {}
def calendar_total(train):
    c = daily[train].mean(1).rolling(7, center=True, min_periods=1).mean(); c = (c / c.mean()).clip(0.25, 3); return c
for nm, test, train in [('loso', list(range(2017, 2025)), None), ('test2526', [2025, 2026], list(range(2017, 2025)))]:
    hit_cal = hit_fix = hit_flat = hit_cal_rnd = npos = 0
    for Y in test:
        tr = train or [s for s in range(2017, 2025) if s != Y]
        cal = calendar_total(tr); d = m[m.season == Y]; days = sorted(d.date.unique())
        mult = cal.reindex([pd.Timestamp(x).dayofyear for x in days]).fillna(0.25).values; mult = mult / mult.mean()
        for x, mu in zip(days, mult):
            g = d[d.date == x]; k = int(round(470 * mu))
            top = g.nlargest(k, 's'); hit_cal += int(top.pos.sum()); hit_cal_rnd += int(g.nlargest(k, 'rnd').pos.sum())
            hit_flat += int(g.nlargest(470, 's').pos.sum())
            r = g.s.groupby(g.b).rank(ascending=False); hit_fix += int(g.pos[r <= 5].sum())
            npos += int(g.pos.sum())
    res[nm] = {'fixed5_per_beat': round(100 * hit_fix / npos, 1), 'same_470_sanctuary_wide_flat': round(100 * hit_flat / npos, 1),
               'calendar_total_sanctuary_wide': round(100 * hit_cal / npos, 1), 'calendar_total_random_cells': round(100 * hit_cal_rnd / npos, 1)}
    print(nm, res[nm], flush=True)
# rotation: fixed 5 per beat, a cell listed on either of the previous 2 days is skipped
for nm, seasons in (('loso', range(2017, 2025)), ('test2526', (2025, 2026))):
    hits = hits_r = npos = 0; caught = {}; caught_r = {}; caught_rnd = {}
    for Y in seasons:
        d = m[m.season == Y]; recent = []
        for x, g in d.groupby('date'):
            r0 = g.s.groupby(g.b).rank(ascending=False) <= 5
            blocked = g.cell_id.isin(set().union(*recent) if recent else set())
            s2 = g.s.where(~blocked, g.s - 1e6); r1 = s2.groupby(g.b).rank(ascending=False) <= 5
            rr = g.rnd.groupby(g.b).rank(ascending=False) <= 5
            hits += int(g.pos[r0].sum()); hits_r += int(g.pos[r1].sum()); npos += int(g.pos.sum())
            for c in g.cell_id[g.pos & r0]: caught[(Y, c)] = True
            for c in g.cell_id[g.pos & r1]: caught_r[(Y, c)] = True
            for c in g.cell_id[g.pos & rr]: caught_rnd[(Y, c)] = True
            recent = (recent + [set(g.cell_id[r1])])[-2:]
    nwin = m[m.season.isin(list(seasons)) & m.pos].groupby(['season', 'cell_id']).ngroups
    res[nm + '_rotation'] = {'celldays_fixed5': round(100 * hits / npos, 1), 'celldays_fixed5_no_repeat_2d': round(100 * hits_r / npos, 1),
                             'windows_caught_fixed5': round(100 * len(caught) / nwin, 1), 'windows_caught_no_repeat_2d': round(100 * len(caught_r) / nwin, 1),
                             'windows_caught_random': round(100 * len(caught_rnd) / nwin, 1)}
    print(nm, res[nm + '_rotation'], flush=True)
json.dump(res, open(OUT + 'check4.json', 'w'), indent=1); print('CHECK4_DONE')
