"""Score the lean ensemble on Akkshay's fire season (issue days Feb 15 - Jun 15) vs the SCORING.md window (Feb 1 - Jun 20)."""
import json, numpy as np, pandas as pd, importlib.util
spec = importlib.util.spec_from_file_location('ps', '/mnt/project-files/research/ratapani-ignition/scripts/pipeline_score.py'); ps = importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)
beat = pd.read_csv('/mnt/project-files/ratapani/beats/cell_beat.csv').set_index('cell_id').beat_uid
ens = pd.read_parquet('/mnt/project-files/research/ratapani-ignition/results/lean_ensemble_pred.parquet')[['season', 'date', 'cell_id', 'lean_ensemble']]
def r(m, c):
    s = m[c].fillna(-1e9); rr = s.groupby([m.season, m.date, m.b]).rank('first', ascending=False); return round(float(m.pos[rr <= 5].sum() / m.pos.sum()) * 100, 2)
for nm, ss in (('LOSO 2017-24', list(range(2017, 2025))), ('2025-26', [2025, 2026])):
    L = ps.labels(ss)[['season', 'date', 'cell_id', 'pos']]; L['date'] = pd.to_datetime(L['date'])
    m = L.merge(ens, on=['season', 'date', 'cell_id'], how='left'); m['b'] = m.cell_id.map(beat).values; m['random'] = np.random.default_rng(0).random(len(m))
    md = m.date.dt.month * 100 + m.date.dt.day; w = m[(md >= 215) & (md <= 615)]
    print(nm, 'Feb1-Jun20:', {c: r(m, c) for c in ('random', 'lean_ensemble')}, 'pos', int(m.pos.sum()),
          '| Feb15-Jun15:', {c: r(w, c) for c in ('random', 'lean_ensemble')}, 'pos', int(w.pos.sum()), f'({w.pos.sum() / m.pos.sum():.0%} of positives)')
