"""Step 5: one table of alerts with both truths and the growth-crossing hour.
Population: alerts (first-look dot groups) on forest-department land with at least one dot on forest/scrub/grass (VTM < 150),
first look 15 Feb - 8 Jun (so 7 days of growth are inside the data window), seasons 2017-2026.
Truth A (scar): union of the fire's scar outlines (b3); only scar-measured fires; edge-cut outlines kept but flagged.
Truth B (VIIRS footprint): distinct 375 m cells hit within 7 days -> hectares by a power law fitted per satellite era
  (1 VIIRS 2017, 2 VIIRS 2018-22, 3 VIIRS 2023-26) on scar-measured fires with an uncut outline (log-log least squares).
Crossing hour: first look at which the fire's estimated size passes the threshold (truth B: law on cumulative cells;
  truth A: final scar x (cumulative / final cells)^b). Out: scratch ds.parquet, out/truth_law.json"""
import json
import numpy as np, pandas as pd
SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r21_big'
OUT = '/mnt/project-files/ratapani/fsi/scouting/code/big_fire_chance/out'
A = pd.read_parquet(f'{SC}/alerts.parquet'); S = pd.read_parquet(f'{SC}/fire_scar.parquet'); G = pd.read_parquet(f'{SC}/growth.parquet')
A['era'] = np.where(A.season <= 2017, 1, np.where(A.season <= 2022, 2, 3))
A = A.merge(S[['fire', 'scar_ha', 'edge', 'src']], on='fire', how='left')
F = A.drop_duplicates('fire')
fit = F[F.scar_ha.notna() & (F.scar_ha > 0) & ~F.edge.fillna(False).astype(bool)]
law = {}
for e, g in fit.groupby('era'):
    b, la = np.polyfit(np.log(g.cells7), np.log(g.scar_ha), 1)
    res = np.log(g.scar_ha) - (la + b * np.log(g.cells7))
    law[int(e)] = dict(a=float(np.exp(la)), b=float(b), fires=len(g), resid_factor=float(np.exp(res.std())),
                       spearman=float(g[['cells7', 'scar_ha']].corr('spearman').iloc[0, 1]))
print(law)
json.dump(law, open(f'{OUT}/truth_law.json', 'w'), indent=1)
a_ = A.era.map({k: v['a'] for k, v in law.items()}); b_ = A.era.map({k: v['b'] for k, v in law.items()})
A['viirs_ha'] = a_ * A.cells7 ** b_
# population
md = A.t0.dt.month * 100 + A.t0.dt.day
A = A[(A.g_nonforest_dots < 1) & (md <= 608)].copy()
for thr in (50, 200, 500):
    A[f'yV{thr}'] = (A.viirs_ha >= thr).astype(int)
    A[f'yS{thr}'] = np.where(A.scar_ha.notna(), (A.scar_ha >= thr).astype(float), np.nan)
# crossing hours
G = G.merge(A[['fire', 'era', 'cells7', 'scar_ha']].drop_duplicates('fire'), on='fire')
G['a'] = G.era.map({k: v['a'] for k, v in law.items()}); G['b'] = G.era.map({k: v['b'] for k, v in law.items()})
G['estV'] = G.a * G.cum ** G.b
G['estS'] = G.scar_ha * (G.cum / G.cells7) ** G.b
for thr in (50, 200, 500):
    for k in ('V', 'S'):
        c = G[G[f'est{k}'] >= thr].groupby('fire').h.min().rename(f'cross{k}{thr}')
        A = A.merge(c, left_on='fire', right_index=True, how='left')
A.to_parquet(f'{SC}/ds.parquet')
print('alerts', len(A), 'fires', A.fire.nunique(), 'scar-measured alerts', A.yS200.notna().sum())
for k in ('V', 'S'):
    print(k, {thr: round(float(A[f'y{k}{thr}'].mean()), 4) for thr in (50, 200, 500)})
sm = A[A.yS200.notna()]
from sklearn.metrics import roc_auc_score, cohen_kappa_score
print('agreement of the two truths at 200 ha on scar-measured alerts: kappa', round(cohen_kappa_score(sm.yS200, sm.yV200), 3),
      'share of scar-big that are VIIRS-big', round(sm.yV200[sm.yS200 == 1].mean(), 3), 'share of VIIRS-big that are scar-big', round(sm.yS200[sm.yV200 == 1].mean(), 3))
print(A.groupby('season')[['yV200', 'yS200']].agg(['mean', 'count']).round(3))
