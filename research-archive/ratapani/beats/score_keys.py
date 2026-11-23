"""Score the deep-model blends on both answer keys (SCORING.md main rule, and the best-dated af_high_s key from labels_v3),
real 94 beats, 5 picks per beat per day. Usage: python3 scr/score_keys.py <joint_pred.parquet>..."""
import sys, json, numpy as np, pandas as pd, importlib.util
spec = importlib.util.spec_from_file_location('ps', '/mnt/project-files/research/ratapani-ignition/scripts/pipeline_score.py'); ps = importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)
beat = pd.read_csv('/mnt/project-files/ratapani/beats/cell_beat.csv').set_index('cell_id').beat_uid
ens = pd.read_parquet('/mnt/project-files/research/ratapani-ignition/results/lean_ensemble_pred.parquet')[['season', 'date', 'cell_id', 'lean_clf', 'lean_ensemble']]
dl = pd.concat([pd.read_parquet(f) for f in sys.argv[1:]]); dcol = [c for c in dl.columns if c not in ('season', 'date', 'cell_id')][0]; dl = dl.rename(columns={dcol: 'deep'})
ss = sorted(dl.season.unique().tolist())
af = pd.read_parquet('/mnt/project-files/ratapani/labels_v3/labels_v3_af.parquet'); af = af[af.valid_af_high_s & af.season.isin(ss)][['season', 'date', 'cell_id', 'pos_af_high_s']].rename(columns={'pos_af_high_s': 'pos'})
keys = {'main': ps.labels(ss)[['season', 'date', 'cell_id', 'pos']], 'af_high_s': af}
def r(m, c):
    s = m[c].fillna(-1e9); rr = s.groupby([m.season, m.date, m.b]).rank('first', ascending=False); return round(float(m.pos[rr <= 5].sum() / m.pos.sum()) * 100, 2)
res = {'seasons': ss}
for k, L in keys.items():
    L = L.copy(); L['date'] = pd.to_datetime(L['date'])
    m = L.merge(ens, on=['season', 'date', 'cell_id'], how='left').merge(dl, on=['season', 'date', 'cell_id'], how='left'); m['b'] = m.cell_id.map(beat).values
    g = [m.season, m.date, m.b]
    for c in ('lean_clf', 'lean_ensemble', 'deep'): m['p_' + c] = m[c].groupby(g).rank(pct=True)
    m['deep+ens'] = m.p_deep + m.p_lean_ensemble; m['random'] = np.random.default_rng(0).random(len(m))
    res[k] = {c: r(m, c) for c in ('random', 'lean_clf', 'lean_ensemble', 'deep', 'deep+ens')}
    res[k]['per_season'] = {int(y): {c: r(m[m.season == y], c) for c in ('lean_ensemble', 'deep', 'deep+ens')} for y in ss}
print(json.dumps(res, indent=1))
