"""Re-score true-lead variants on v1 vs v2 labels (FSI thread's one-day dating fix), real 94 beats, 5 per beat per day."""
import json, numpy as np, pandas as pd
real = pd.read_csv('/mnt/project-files/ratapani/beats/cell_beat.csv').set_index('cell_id').beat_uid
def score(m, col, k=5):
    s = m[col].fillna(-1e9); r = s.groupby([m.season, m.date, m.cell_id.map(real)]).rank('first', ascending=False); return round(float(m.pos[r <= k].sum() / m.pos.sum()) * 100, 2)
lean = pd.read_parquet('pred_lean_loso.parquet')
ens = pd.read_parquet('/mnt/project-files/research/ratapani-ignition/results/lean_ensemble_pred.parquet'); ens = ens[ens.season < 2025]
res = {}
for ver, f in (('v1', 'true_lead_labels.parquet'), ('v2', 'true_lead_labels_v2.parquet')):
    TL = pd.read_parquet('/mnt/project-files/ratapani/fsi/' + f); TL['date'] = pd.to_datetime(TL['date']); TL = TL[TL.season < 2025]
    for v in ('strict', 'lenient'):
        L = TL[TL[f'valid_{v}']][['season', 'date', 'cell_id', 'pos']]
        m = L.merge(lean, on=['season', 'date', 'cell_id'], how='left').merge(ens[['season', 'date', 'cell_id', 'lean_ensemble']], on=['season', 'date', 'cell_id'], how='left')
        m['random'] = np.random.default_rng(0).random(len(m))
        res[f'{ver}_{v}'] = dict(positives=int(m.pos.sum()), lean_clf=score(m, 'pipeline_lean'), lean_ensemble=score(m, 'lean_ensemble'), random=score(m, 'random'))
        print(ver, v, res[f'{ver}_{v}'], flush=True)
json.dump(res, open('/mnt/project-files/ratapani/beats/results_truelead_v2.json', 'w'), indent=1)
