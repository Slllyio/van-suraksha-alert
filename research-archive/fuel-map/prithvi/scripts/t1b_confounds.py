"""T1b: is Prithvi's fire-size gain fuel, or just 'where crews can't reach / where big fires always happen'?
Adds access and place controls at the first dots: distance to road, track, village, sanctuary boundary, depth inside forest,
distance to crops, forest share within 1 and 2 km, elevation, relief, and place memory (mean log size of OTHER seasons' fires
within 3 km). Held out by season AND by 10 km spatial block (5 folds), so Prithvi cannot just recall a place.
Out: scratch t1b.json"""
import json, numpy as np, pandas as pd, warnings
warnings.filterwarnings('ignore')
from scipy.spatial import cKDTree
from sklearn.linear_model import LogisticRegression, RidgeCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score, r2_score
import common as C
G = pd.read_parquet(f'{C.SP}/fires.parquet'); D = pd.read_parquet(f'{C.SP}/dots.parquet')
G = G[G.doy >= 46].reset_index(drop=True); D = D[D.fire.isin(G.fire)].merge(G[['fire', 'season']], on='fire')
for kind in ('prithvi', 'raw'):
    rows = [pd.DataFrame(C.sample(Y, kind, d.x.values, d.y.values), index=d.fire.values).groupby(level=0).mean() for Y, d in D.groupby('season')]
    V = pd.concat(rows); V.columns = C.NAMES[kind]; G = G.join(V, on='fire')
cells = pd.read_parquet(f'{C.SP}/cells.parquet')
EE = '/mnt/project-files/ratapani/ee/'
cells = cells.merge(pd.read_csv(EE + 'proximity.csv'), on='cell_id').merge(pd.read_csv(EE + 'terrain.csv'), on='cell_id')
t = cKDTree(cells[['x', 'y']].values)
for r in (1000, 2000):
    nb = t.query_ball_point(cells[['x', 'y']].values, r + 1); cells[f'forest_{r}'] = [cells.forest_frac.values[n].mean() for n in nb]
xy = D.groupby('fire')[['x', 'y']].mean(); G = G.join(xy, on='fire')
_, ci = t.query(G[['x', 'y']].values); CTRL = ['dist_road', 'dist_track', 'dist_village', 'dist_boundary', 'depth_in_forest', 'dist_crop_cell', 'forest_1000', 'forest_2000', 'elev_m_mean', 'elev_m_stdDev']
for c in CTRL: G[c] = cells[c].values[ci]
G['l_area'] = np.log(G.area_ha)
blk = ((G.x - 739500) // 10000).astype(int) * 7 + ((G.y - 2524000) // 10000).astype(int); G['fold'] = blk.map(dict(zip(sorted(blk.unique()), np.arange(blk.nunique()) % 5)))
def place_memory(te_season):
    o = G[G.season != te_season]; tt = cKDTree(o[['x', 'y']].values); nb = tt.query_ball_point(G[['x', 'y']].values, 3000)
    return np.array([o.l_area.values[n].mean() if len(n) else np.nan for n in nb]), np.array([o.big.values[n].mean() if len(n) else np.nan for n in nb])
BASE = ['doy', 'slope', 'burnt_last', 'hist_years', 'tmax', 'rh', 'wind', 'rain30', 'l_near', 'l_n', 'canopy']
PR, RAW = C.NAMES['prithvi'], C.NAMES['raw']
SETS = {'canopy + dots (as T1)': BASE, '+ access & place controls': BASE + CTRL + ['pm_area', 'pm_big'],
        '+ controls + fuel map v3': BASE + CTRL + ['pm_area', 'pm_big', 'litter', 'grass', 'teak'],
        '+ controls + raw HLS': BASE + CTRL + ['pm_area', 'pm_big'] + RAW, '+ controls + Prithvi': BASE + CTRL + ['pm_area', 'pm_big'] + PR,
        '+ controls + v3 + Prithvi': BASE + CTRL + ['pm_area', 'pm_big', 'litter', 'grass', 'teak'] + PR}
mk = lambda c: make_pipeline(SimpleImputer(strategy='median'), StandardScaler(), c)
out = {'fires': int(len(G)), 'models': {}}; P = {}
for holdout in ('season', 'season + block'):
    for name, f in SETS.items():
        pa, pb = np.zeros(len(G)), np.zeros(len(G))
        for s in G.season.unique():
            G['pm_area'], G['pm_big'] = place_memory(s)
            for k in (range(5) if holdout != 'season' else [None]):
                tr = (G.season != s) & ((G.fold != k) if k is not None else True); te = (G.season == s) & ((G.fold == k) if k is not None else True)
                tr, te = tr.values, te.values
                pa[te] = mk(RidgeCV(alphas=np.logspace(-1, 4, 12))).fit(G.loc[tr, f], G.l_area[tr]).predict(G.loc[te, f])
                pb[te] = mk(LogisticRegression(C=0.05, max_iter=3000)).fit(G.loc[tr, f], G.big[tr]).predict_proba(G.loc[te, f])[:, 1]
        key = f'{holdout} | {name}'; P[key] = (pa, pb)
        out['models'][key] = dict(r2_log_area=round(r2_score(G.l_area, pa), 3), auc_big=round(roc_auc_score(G.big, pb), 3)); print(f'{key:55s}', out['models'][key], flush=True)
rng = np.random.default_rng(1); y, yb = G.l_area.values, G.big.values
out['gains'] = {}
for h in ('season', 'season + block'):
    for a, b in [('+ controls + Prithvi', '+ access & place controls'), ('+ controls + fuel map v3', '+ access & place controls'), ('+ controls + raw HLS', '+ access & place controls'), ('+ controls + Prithvi', '+ controls + raw HLS'), ('+ controls + v3 + Prithvi', '+ controls + fuel map v3')]:
        A, Bb = P[f'{h} | {a}'], P[f'{h} | {b}']; r, u = [], []
        for i in range(1000):
            k = rng.integers(0, len(G), len(G)); r.append(r2_score(y[k], A[0][k]) - r2_score(y[k], Bb[0][k])); u.append(roc_auc_score(yb[k], A[1][k]) - roc_auc_score(yb[k], Bb[1][k]))
        q = lambda z: [round(float(np.mean(z)), 3), [round(float(x), 3) for x in np.percentile(z, [2.5, 97.5])]]
        out['gains'][f'{h} | {a} vs {b}'] = {'r2_gain': q(r), 'auc_gain': q(u)}; print(h, '|', a, 'vs', b, out['gains'][f'{h} | {a} vs {b}'], flush=True)
# what is Prithvi's size signal made of? held-out Prithvi-only size score vs landscape variables (Spearman)
G['prithvi_size_score'] = P['season + block | + controls + Prithvi'][0] - P['season + block | + access & place controls'][0]
out['prithvi_extra_vs'] = {c: round(float(G.prithvi_size_score.corr(G[c], method='spearman')), 3) for c in ['canopy', 'litter', 'grass', 'teak', 'slope', 'burnt_last', 'hist_years', 'doy'] + CTRL}
print(out['prithvi_extra_vs'])
json.dump(out, open(f'{C.SP}/t1b.json', 'w'), indent=1); G.to_parquet(f'{C.SP}/t1b_fires.parquet')
