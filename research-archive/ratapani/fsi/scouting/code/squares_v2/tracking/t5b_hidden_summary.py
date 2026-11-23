"""Paired summaries of the held-out (odd-season) hidden-pass tests: differences inversion - baseline, 95% range by
bootstrap over fires, split by the gap to the nearest remaining pass. Out: results/t5_hidden_test_summary.json"""
import json, numpy as np, pandas as pd
OUT = '/mnt/project-files/ratapani/fsi/scouting/code/squares_v2/tracking/results'; rng = np.random.default_rng(0); res = {}
for cfg in ['grid12', 'ring']:
    try: X = pd.read_csv(f'{OUT}/t5_hidden_test_{cfg}.csv')
    except FileNotFoundError: continue
    X['gapc'] = np.where(X.gap_h <= 2, 'gap<=2h', 'gap>2h')
    r = {}
    for sub, g in [('all', X)] + list(X.groupby('gapc')):
        F = g[g.flagged]; P = F.pivot_table(index=['fire', 'pass_key'], columns='method', values=['auc_node', 'logloss_node'])
        s = dict(hidden_flagged_passes=int(len(P)), mean={m: [round(P['auc_node'][m].mean(), 4), round(P['logloss_node'][m].mean(), 4) if m in P['logloss_node'] else None] for m in P['auc_node'].columns})
        for b in ['nearest', 'idw4', 'kernel']:
            for met in ['auc_node', 'logloss_node']:
                if b not in P[met] or P[met][b].isna().all(): continue
                d = (P[met]['inversion'] - P[met][b]).dropna(); fz = d.index.get_level_values(0).values; uf = np.unique(fz)
                agg = pd.DataFrame({'d': d.values, 'f': fz}).groupby('f').d.agg(['sum', 'size'])
                bs = []
                for _ in range(2000):
                    k = rng.integers(0, len(agg), len(agg)); bs.append(agg['sum'].values[k].sum() / agg['size'].values[k].sum())
                s[f'{met}_inversion_minus_{b}'] = [round(float(d.mean()), 4), round(float(np.quantile(bs, .025)), 4), round(float(np.quantile(bs, .975)), 4)]
        r[sub] = s
    res[cfg] = r
json.dump(res, open(f'{OUT}/t5_hidden_test_summary.json', 'w'), indent=1); print(json.dumps(res, indent=1))
