"""T1: does a fuel layer at the first alert's dots predict how big the fire gets?
2,640 fires (big-fire warning set), only fires first seen on/after 15 Feb (so every HLS frame used is before the fire).
Held out: leave-one-season-out. Same fires and same base inputs for every model; only the fuel layer changes.
Targets: log final scar area (R2 on held-out), big >= 200 ha (AUC, Brier). Fire bootstrap for the gain vs canopy-only."""
import json, sys, numpy as np, pandas as pd, warnings
warnings.filterwarnings('ignore')
from sklearn.linear_model import LogisticRegression, RidgeCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score, brier_score_loss, r2_score
import common as C
G = pd.read_parquet(f'{C.SP}/fires.parquet'); D = pd.read_parquet(f'{C.SP}/dots.parquet')
G = G[G.doy >= 46].reset_index(drop=True)
D = D[D.fire.isin(G.fire)].merge(G[['fire', 'season']], on='fire')
for kind in ('prithvi', 'raw'):
    rows = []
    for Y, d in D.groupby('season'):
        v = C.sample(Y, kind, d.x.values, d.y.values); rows.append(pd.DataFrame(v, index=d.fire.values).groupby(level=0).mean())
    V = pd.concat(rows); V.columns = C.NAMES[kind]; G = G.join(V, on='fire')
G['l_area'] = np.log(G.area_ha)
BASE = ['doy', 'slope', 'burnt_last', 'hist_years', 'tmax', 'rh', 'wind', 'rain30', 'l_near']
PR = C.NAMES['prithvi']; RAW = C.NAMES['raw']
SETS = {'no fuel layer': BASE, 'canopy': BASE + ['canopy'], 'canopy + fuel map v3': BASE + ['canopy', 'litter', 'grass', 'teak'],
        'canopy + raw HLS (same pixels)': BASE + ['canopy'] + RAW, 'canopy + Prithvi': BASE + ['canopy'] + PR,
        'canopy + v3 + Prithvi': BASE + ['canopy', 'litter', 'grass', 'teak'] + PR, 'Prithvi only (+ base)': BASE + PR}
out = {'fires': int(len(G)), 'big': int(G.big.sum()), 'models': {}}
def mk(cls): return make_pipeline(SimpleImputer(strategy='median'), StandardScaler(), cls)
preds = {}
for dots in (False, True):
    for name, f in SETS.items():
        f = f + (['l_n'] if dots else []); key = name + (' + dot count' if dots else '')
        pa, pb = np.zeros(len(G)), np.zeros(len(G))
        for s in G.season.unique():
            tr, te = (G.season != s).values, (G.season == s).values
            pa[te] = mk(RidgeCV(alphas=np.logspace(-1, 4, 12))).fit(G.loc[tr, f], G.l_area[tr]).predict(G.loc[te, f])
            pb[te] = mk(LogisticRegression(C=0.05, max_iter=3000)).fit(G.loc[tr, f], G.big[tr]).predict_proba(G.loc[te, f])[:, 1]
        preds[key] = (pa, pb)
        out['models'][key] = dict(r2_log_area=round(r2_score(G.l_area, pa), 3), auc_big=round(roc_auc_score(G.big, pb), 3), brier_big=round(brier_score_loss(G.big, pb), 4))
        print(f'{key:45s}', out['models'][key], flush=True)
rng = np.random.default_rng(0); y, yb = G.l_area.values, G.big.values
def boot(a, b):
    r, u = [], []
    for i in range(1000):
        k = rng.integers(0, len(G), len(G))
        r.append(r2_score(y[k], preds[a][0][k]) - r2_score(y[k], preds[b][0][k])); u.append(roc_auc_score(yb[k], preds[a][1][k]) - roc_auc_score(yb[k], preds[b][1][k]))
    q = lambda z: [round(float(np.mean(z)), 3), [round(float(x), 3) for x in np.percentile(z, [2.5, 97.5])]]
    return {'r2_gain': q(r), 'auc_gain': q(u)}
out['gains'] = {}
for a, b in [('canopy + Prithvi', 'canopy'), ('canopy + fuel map v3', 'canopy'), ('canopy + raw HLS (same pixels)', 'canopy'), ('canopy + Prithvi', 'canopy + raw HLS (same pixels)'),
             ('canopy + Prithvi + dot count', 'canopy + dot count'), ('canopy + v3 + Prithvi + dot count', 'canopy + fuel map v3 + dot count')]:
    out['gains'][f'{a} vs {b}'] = boot(a, b); print(a, 'vs', b, out['gains'][f'{a} vs {b}'], flush=True)
# within-canopy view: residual of log area after base+canopy+dots, vs each Prithvi PC (held-out residuals)
res = G.l_area - preds['canopy + dot count'][0]
out['top_pc_vs_residual_spearman'] = dict(sorted({c: round(float(pd.Series(G[c]).corr(res, method='spearman')), 3) for c in PR}.items(), key=lambda kv: -abs(kv[1]))[:6])
print(out['top_pc_vs_residual_spearman'])
json.dump(out, open(f'{C.SP}/t1_fires.json', 'w'), indent=1)
G[['fire', 'season', 'doy', 'area_ha', 'big', 'canopy', 'litter']].assign(**{f'p_{k}': v[1] for k, v in preds.items()}).to_csv(f'{C.SP}/t1_fires_pred.csv', index=False)
