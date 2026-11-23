"""Item 1 on the dated truth (item 2): chance a cell BURNS (arrival map, a2) in the next 12/24/48 h, for multi-look fires
with an outline. Same issue times and features as f1; cells already burned at issue time are dropped.
Then the f2 training/scoring is run on these labels."""
import pandas as pd, numpy as np, sys
from scipy.spatial import cKDTree
S = sys.argv[1]; AR = '/mnt/project-files/research/spread-review/arrival/'
D = pd.read_parquet(S + '/rows.parquet')
A = pd.read_parquet(S + '/tracks.parquet'); P = pd.read_parquet(S + '/passes.parquet')
slots = pd.DataFrame({'look': sorted(set(P.look) | set(A.look))})
slots['t'] = slots.look.map(P.groupby('look').t.min()).fillna(slots.look.map(A.groupby('look').t.min()))
slots = slots.sort_values('t').reset_index(drop=True)
AP = pd.read_parquet(AR + 'arrival_px.parquet'); fires = set(AP.fire.unique())
D = D[D.fire.isin(fires)].copy()
D['t_issue'] = slots.t.values[D.s.values]
out = []
for f, g in D.groupby('fire'):
    a = AP[AP.fire == f]
    d, i = cKDTree(a[['x', 'y']].values).query(g[['x', 'y']].values, distance_upper_bound=40)
    inside = np.isfinite(d)
    T = np.full(len(g), np.datetime64('NaT'), 'datetime64[ns]'); T[inside] = a.t_arrival.values[i[inside]]
    g = g.assign(T=T)
    out.append(g)
D = pd.concat(out)
burned_before = D['T'].notna() & (D['T'] <= D.t_issue)
D = D[~burned_before].copy()
for h in (12, 24, 48):
    D[f'y{h}'] = D['T'].notna() & (D['T'] > D.t_issue) & (D['T'] <= D.t_issue + pd.Timedelta(hours=h))
D.drop(columns=['T', 't_issue']).to_parquet(S + '/rows_arrival.parquet')
print(len(D), 'rows', D.fire.nunique(), 'fires', D.groupby(['fire', 's']).ngroups, 'issues', D[['y12', 'y24', 'y48']].mean().round(4).to_dict())
