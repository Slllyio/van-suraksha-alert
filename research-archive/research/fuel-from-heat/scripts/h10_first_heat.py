"""Second method, test 4: is the heat useful at all? Does a fire's FIRST pass heat, judged against the rest of that pass
(relative heat from h9, geometry and weather removed), tell how big the fire will get, how long it will burn, and whether
it will be seen again? Baseline: raw FRP of the first pass. Scar outlines v2 for size.
Out: results/first_heat.json
"""
import json
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
from h0_lib import RES, BF

v = pd.read_csv(f'{RES}/place_det.csv', parse_dates=['t']).dropna(subset=['fire'])
v['fire'] = v.fire.astype(int)
F = pd.read_csv(f'{BF}/fires.csv')
F = F[F.month.between(2, 6)]
first = v.sort_values('t').groupby('fire').head(1)[['fire', 'pass']]
fp = v.merge(first, on=['fire', 'pass'])
G = fp.groupby('fire').agg(rel_max=('rel', 'max'), rel_sum=('rel', lambda s: np.log(np.exp(s).sum())), frp_max=('frp', 'max'),
                           frp_sum=('frp', 'sum'), n=('frp', 'size')).reset_index().merge(F[['fire', 'area_ha', 'n_looks', 'hours']], on='fire')
G['seen_again'] = (G.n_looks >= 2).astype(int)
out = {'fires': len(G)}
rows = []
for k, lab in [('frp_max', 'raw FRP, brightest pixel'), ('frp_sum', 'raw FRP, summed'), ('n', 'number of pixels'),
               ('rel_max', 'relative heat, brightest pixel'), ('rel_sum', 'relative heat, summed')]:
    rows.append(dict(measure=lab, rho_scar_size=round(spearmanr(G[k], G.area_ha)[0], 3), rho_duration=round(spearmanr(G[k], G.hours)[0], 3),
                     auc_seen_again=round(roc_auc_score(G.seen_again, G[k]), 3)))
T = pd.DataFrame(rows); print(T.to_string(index=False)); out['table'] = T.to_dict('records')
q = pd.qcut(G.rel_max, 5, labels=['coolest fifth', '2', '3', '4', 'hottest fifth'])
t = G.groupby(q, observed=True).agg(fires=('area_ha', 'size'), scar_ha_median=('area_ha', 'median'), seen_again=('seen_again', 'mean'))
print(t.round(2)); out['by_quintile'] = t.round(3).reset_index().astype(str).to_dict('records')
json.dump(out, open(f'{RES}/first_heat.json', 'w'), indent=1, default=float)
