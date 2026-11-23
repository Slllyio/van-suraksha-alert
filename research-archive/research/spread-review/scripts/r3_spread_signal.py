"""How far do next-look detections land from everything seen so far, against pure position noise (same look, other satellite)?"""
import pandas as pd, numpy as np, sys, json
from scipy.spatial import cKDTree
S = sys.argv[1]
A = pd.read_parquet(S + '/tracks.parquet'); md = A.t.dt.strftime('%m-%d'); A = A[(md >= '02-15') & (md <= '06-15')]
N = pd.read_parquet(S + '/r2_nn.parquet')
rows = []
for f, g in A.groupby('fire'):
    ls = sorted(g.look.unique())
    if len(ls) < 2: continue
    lt = g.groupby('look').t.median()
    for k in range(1, len(ls)):
        prev = g[g.look.isin(ls[:k])]; last = g[g.look == ls[k - 1]]; new = g[g.look == ls[k]]
        dall, _ = cKDTree(prev[['x', 'y']].values).query(new[['x', 'y']].values)
        dlast, _ = cKDTree(last[['x', 'y']].values).query(new[['x', 'y']].values)
        gap = (lt[ls[k]] - lt[ls[k - 1]]).total_seconds() / 3600
        for a, b in zip(dall, dlast):
            rows.append(dict(fire=f, k=k, gap=gap, d_all=a, d_last=b, n_prev=len(prev)))
X = pd.DataFrame(rows)
X['gapc'] = pd.cut(X.gap, [0, 13, 25, 37, 1000], labels=['~12h', '~24h', '~36h', '>36h'])
R = {'n_next_detections': len(X)}
qs = [.25, .5, .75, .9]
R['noise_same_look_q'] = N.d.quantile(qs).round(0).tolist()
for c, g in X.groupby('gapc', observed=True):
    R[f'next_vs_all_prev_q_{c}'] = g.d_all.quantile(qs).round(0).tolist() + [len(g)]
    R[f'next_vs_last_q_{c}'] = g.d_last.quantile(qs).round(0).tolist()
for thr in [375, 500, 750, 1000]:
    R[f'share_next_within_{thr}m_of_prev'] = round(float((X.d_all <= thr).mean()), 3)
    R[f'share_noise_within_{thr}m'] = round(float((N.d <= thr).mean()), 3)
# excess displacement: compare medians (crude deconvolution assuming independent radial noise)
for c, g in X.groupby('gapc', observed=True):
    m = g.d_last.median(); n0 = N.d.median()
    R[f'excess_median_disp_last_{c}_m'] = round(float(np.sqrt(max(m ** 2 - n0 ** 2, 0))), 0)
json.dump(R, open(S + '/r3.json', 'w'), indent=1); X.to_parquet(S + '/r3_steps.parquet')
print(json.dumps(R, indent=1))
