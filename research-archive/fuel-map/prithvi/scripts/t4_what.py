"""T4: what is Prithvi's extra burn-share signal made of? Uses held-out predictions from t2c (season + block held out).
extra = logit(p with raw + Prithvi) - logit(p with raw HLS only): what Prithvi adds beyond its own pixels and all controls.
Compared, within the same canopy tenth and season (rank correlation of residuals), with:
  years since the cell last burned (litter build-up; 2020-26 so history is known 3+ years back),
  Feb moisture (NDMI 1-14 Feb), Jan moisture, leaf-fall amount (NDVI Nov minus Feb), forest share within 2 km (continuity),
  teak share, fuel map v3 litter.
Also: Prithvi's AUC gain split by years since last burn."""
import json, numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
import common as C
D = pd.read_parquet(f'{C.SP}/t2c_preds.parquet')
cs = pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/cell_season.csv')
burnt = set(zip(cs.season, cs.cell_id))
def ysb(r):
    for k in range(1, 9):
        if (r.season - k, r.cell_id) in burnt: return k
    return 9
D = D[D.season >= 2020].copy(); D['years_since_burn'] = [ysb(r) for r in D[['season', 'cell_id']].itertuples()]
lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
D['extra'] = lg(D.p_prithvi) - lg(D.p_raw)
D['feb_moist'] = D.F4_ndmi; D['jan_moist'] = D.F3_ndmi; D['leaf_fall'] = D.F2_ndvi - D.F4_ndvi
D['cb'] = D.groupby('season').canopy.transform(lambda s: pd.qcut(s, 10, labels=False, duplicates='drop'))
def within(c):
    g = D[['season', 'cb', 'extra', c]].dropna()
    r = g.groupby(['season', 'cb'])[['extra', c]].rank(pct=True)
    return round(float(r.extra.corr(r[c])), 3)
VARS = ['years_since_burn', 'feb_moist', 'jan_moist', 'leaf_fall', 'forest_2000', 'forest_1000', 'teak', 'litter']
out = {'cell_seasons': int(len(D)), 'extra_vs_same_canopy': {v: within(v) for v in VARS}}
print(out['extra_vs_same_canopy'])
out['auc_gain_by_years_since_burn'] = {}
for lab, m in [('burnt last season', D.years_since_burn == 1), ('2-3 years', D.years_since_burn.between(2, 3)), ('4+ years', D.years_since_burn >= 4)]:
    g = D[m]; out['auc_gain_by_years_since_burn'][lab] = dict(cells=int(len(g)), most_rate=round(float(g.most.mean()), 3),
        auc_raw=round(roc_auc_score(g.most, g.p_raw), 3), auc_prithvi=round(roc_auc_score(g.most, g.p_prithvi), 3))
print(json.dumps(out['auc_gain_by_years_since_burn'], indent=0))
# does burn share itself track years since burn at the same canopy? (is there litter build-up at all?)
out['share_vs_years_since_burn_same_canopy'] = round(float(D.groupby(['season', 'cb'])[['share', 'years_since_burn']].rank(pct=True).corr().iloc[0, 1]), 3)
out['most_rate_by_ysb'] = D.groupby(D.years_since_burn.clip(upper=5)).most.mean().round(3).to_dict()
print(out['share_vs_years_since_burn_same_canopy'], out['most_rate_by_ysb'])
json.dump(out, open(f'{C.SP}/t4_what.json', 'w'), indent=1, default=str)
