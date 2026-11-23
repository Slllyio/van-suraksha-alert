"""Rescore predictions on real MP beats (ratapani/beats/cell_beat.csv) next to the 68 pseudo-beats.
Fixed budget: 5 picks per beat per day. Day-shared: the same daily total (5 x beats) split by each beat's summed score, 1-25 per beat."""
import importlib.util, json, numpy as np, pandas as pd
RS = '/mnt/project-files/research/'; SC = '/mnt/project-files/ratapani/scoring/'
spec = importlib.util.spec_from_file_location('ps', RS + 'ratapani-ignition/scripts/pipeline_score.py'); ps = importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)
real = pd.read_csv('/mnt/project-files/ratapani/beats/cell_beat.csv').set_index('cell_id').beat_uid
pseudo = pd.read_csv(SC + 'pseudo_beats_pipeline.csv').set_index('cell_id').pseudo_beat
def score(m, col, beats, k=5, shared=False):
    m = m.copy(); m['b'] = m.cell_id.map(beats).values; nb = beats.nunique(); s = m[col].fillna(-1e9)
    r = s.groupby([m.season, m.date, m.b]).rank('first', ascending=False)
    if not shared: sel = r <= k
    else:
        tot = m.assign(s=s.clip(lower=0)).groupby(['season', 'date', 'b']).s.sum()
        share = tot / tot.groupby(level=[0, 1]).transform('sum')
        alloc = np.clip(np.round(share * k * nb), 1, 25)
        sel = r <= alloc.reindex(pd.MultiIndex.from_arrays([m.season, m.date, m.b])).values
    days = m.groupby(['season', 'date']).ngroups
    return dict(recall=round(float(m.pos[sel].sum() / m.pos.sum()), 4), picks_per_day=round(float(sel.sum() / days), 1))
def run(pred, col, lab, name):
    m = lab.merge(pred[['season', 'date', 'cell_id', col]], on=['season', 'date', 'cell_id'], how='left')
    m['random'] = np.random.default_rng(0).random(len(m)); out = {}
    for bn, beats in (('pseudo68', pseudo), ('real94', real)):
        for c in (col, 'random'):
            out[f'{bn}_{c}_fixed5'] = score(m, c, beats)
            if c == col: out[f'{bn}_{c}_shared'] = score(m, c, beats, shared=True)
    print(name, json.dumps(out), flush=True); return out
res = {}
lab_main = ps.labels(range(2017, 2027))
lo = pd.read_parquet('pred_lean_loso.parquet'); te = pd.read_parquet('pred_lean_test.parquet')
res['lean_loso_main'] = run(lo, 'pipeline_lean', lab_main[lab_main.season < 2025], 'lean LOSO main')
res['lean_2526_main'] = run(te, 'pipeline_lean', lab_main[lab_main.season >= 2025], 'lean 2025-26 main')
TL = pd.read_parquet('/mnt/project-files/ratapani/fsi/true_lead_labels.parquet'); TL['date'] = pd.to_datetime(TL['date'])
for v in ('strict', 'lenient'):
    L = TL[TL[f'valid_{v}']][['season', 'date', 'cell_id', 'pos']]
    res[f'lean_loso_truelead_{v}'] = run(lo, 'pipeline_lean', L, f'lean LOSO true-lead {v}')
json.dump(res, open('results_real_beats.json', 'w'), indent=1); print('BEATS_DONE')
