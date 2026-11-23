"""Experiment D: how the same number of checks is spread across beats and days. Cell-level labels and recall exactly as SCORING.md
(first burns, H = 2, valid cell-days, real 94 beats); cell ranking = lean classifier predictions (shared parquet).
Rules, all with the same season total of 5 x 94 picks per day:
  fixed5        5 per beat per day (the headline rule)
  beat_shared   daily 470 split across beats by summed cell score (1-25 per beat)  [SCORING.md secondary number]
  beat_shared_p same, split by the beat model's calibrated P(beat burns in 2 days)
  day_varying   daily total scaled by the big-fire-day count forecast (0.25x-3x, season total unchanged), picks shared across beats
  day_varying_fixed  daily total scaled the same way, but split evenly across beats (per-beat cap moves with the day)
Ceilings use the true labels in place of scores."""
import json, sys, importlib.util, numpy as np, pandas as pd
sys.path.insert(0, '/mnt/project-files/research/reframe/scripts'); import data as D
spec = importlib.util.spec_from_file_location('ps', '/mnt/project-files/research/ratapani-ignition/scripts/pipeline_score.py'); ps = importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)
lab = ps.labels(D.SEASONS); lp = D.lean_preds()
m = lab.merge(lp[['season', 'date', 'cell_id', 'pipeline_lean']], on=['season', 'date', 'cell_id'], how='left')
cb = D.cells().set_index('cell_id').beat_uid; m['beat_uid'] = m.cell_id.map(cb).values
bp = pd.read_parquet(D.OUT + 'beat_preds.parquet')[['date', 'beat_uid', 'p_y2']]; m = m.merge(bp, on=['date', 'beat_uid'], how='left')
dp = pd.read_parquet(D.OUT + 'day_preds.parquet')[['date', 'mu_N2', 'p_big_N2', 'N2']]; m = m.merge(dp, on='date', how='left')
m['s'] = m.pipeline_lean.fillna(0); m['truth'] = m.pos.astype(float) + 1e-6 * m.s
NB = 94; K = 5

def pick(m, score, rule, daily_scale=None):
    r = m.groupby(['season', 'date', 'beat_uid'])[score].rank('first', ascending=False)
    if rule == 'fixed5': return r <= K
    if rule in ('beat_shared', 'beat_shared_p'):
        w = m[score].clip(lower=0) if rule == 'beat_shared' else m.p_y2.fillna(0) / m.groupby(['season', 'date', 'beat_uid']).cell_id.transform('size')
        tot = w.groupby([m.season, m.date, m.beat_uid]).transform('sum'); day = w.groupby([m.season, m.date]).transform('sum')
        alloc = np.clip(np.round(tot / day * K * NB), 1, 25); return r <= alloc
    budget = K * NB * daily_scale        # day_varying*: total picks on this day
    if rule == 'day_varying':
        rd = m.groupby(['season', 'date'])[score].rank('first', ascending=False); return rd <= budget
    if rule == 'day_varying_fixed': return r <= np.round(budget / NB)

def scale(m, col):
    d = m.groupby(['season', 'date'])[col].first(); s = d / d.groupby(level=0).transform('mean'); s = s.clip(0.25, 3)
    s = s / s.groupby(level=0).transform('mean')          # season total unchanged
    return m.set_index(['season', 'date']).index.map(s).values

DAYTAB = m.groupby(['season', 'date'])[['mu_N2', 'N2']].first().reset_index(); DAYTAB['doy'] = DAYTAB.date.dt.dayofyear

def scale_nopeek(m, col, clim=False):
    """Operational version: no look at the rest of this season. Scale = clip(today's value / training-season mean, 0.25, 3),
    rescaled so the training seasons average exactly 470 picks a day. clim=True uses the training seasons' mean N2 for this day of
    year (seasonality only) in place of the forecast."""
    d = DAYTAB.copy(); out = pd.Series(np.nan, index=d.index); CV = list(range(2017, 2025))
    for s_ in m.season.unique():
        trs = [x for x in CV if x != s_]; tr = d[d.season.isin(trs)]
        cur = tr.groupby('doy').N2.mean().rolling(15, center=True, min_periods=1).mean()
        val = (lambda x: x.doy.map(cur).values) if clim else (lambda x: x[col].values)
        M = val(tr).mean(); c_tr = np.clip(val(tr) / M, 0.25, 3); te = d.season == s_
        out[te] = np.clip(val(d[te]) / M, 0.25, 3) / c_tr.mean()
    s = pd.Series(out.values, index=pd.MultiIndex.from_frame(d[['season', 'date']]))
    return m.set_index(['season', 'date']).index.map(s).values

res = {}
for split, sel in (('loso_2017_24', m.season < 2025), ('test_2025_26', m.season >= 2025)):
    d = m[sel].copy(); r = {'positives': int(d.pos.sum())}
    sc_model = scale(d, 'mu_N2'); sc_true = scale(d, 'N2')
    for rule in ('fixed5', 'beat_shared', 'beat_shared_p', 'day_varying', 'day_varying_fixed'):
        for who, col, sc in (('model', 's', sc_model), ('ceiling', 'truth', sc_true)):
            if rule == 'beat_shared_p' and who == 'ceiling': continue
            p = pick(d, col, rule, sc)
            r[f'{rule}_{who}'] = round(float(d.pos[p].sum() / d.pos.sum()), 4)
        r[f'{rule}_picks_per_day'] = round(float(pick(d, 's', rule, sc_model).sum() / d.groupby(['season', 'date']).ngroups), 1)
    for nm, sc in (('nopeek_forecast', scale_nopeek(d, 'mu_N2')), ('nopeek_seasonality_only', scale_nopeek(d, 'mu_N2', clim=True))):
        for rule in ('day_varying', 'day_varying_fixed'):
            p = pick(d, 's', rule, sc); r[f'{rule}_{nm}'] = round(float(d.pos[p].sum() / d.pos.sum()), 4)
            r[f'{rule}_{nm}_picks_per_day'] = round(float(p.sum() / d.groupby(['season', 'date']).ngroups), 1)
    d['rnd'] = np.random.default_rng(0).random(len(d)); r['fixed5_random'] = round(float(d.pos[pick(d, 'rnd', 'fixed5')].sum() / d.pos.sum()), 4)
    res[split] = r; print(split, json.dumps(r), flush=True)
json.dump(res, open('/mnt/project-files/research/reframe/results/budget.json', 'w'), indent=1); print('DONE')
