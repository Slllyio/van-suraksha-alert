"""Does the ray stop model (c11) help draw the burn scar? Per front, 36 rays: true reach (to scar edge) vs predicted reach
(expected distance before stopping, LightGBM hazard trained on the OTHER seasons). Outline overlap (IoU) computed in polar form:
inter = sum min(r,p)^2, union = sum max(r,p)^2 over the 36 rays.
  size + shape : model's own predicted reaches vs a circle from the distance+front-state model (no ground) vs circle of median reach
  shape only   : every candidate rescaled to the true mean reach (perfect size), so only the shape is scored
Out: results/ray_outline.json"""
import os, sys, json, numpy as np, pandas as pd, lightgbm as lgb
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import c0_lib as C
HERE = '/mnt/project-files/research/fire-continuity'
ST = pd.read_parquet(f'{C.SCRATCH}/rays.parquet'); O = pd.read_csv(f'{HERE}/results/ray_origins.csv')
O['reach'] = O.reach.apply(lambda s: np.array(json.loads(s.replace('nan', 'NaN'))))
ST = ST.merge(O[['origin', 'kind', 'n_dots', 'frp', 'doy', 'wind_ms', 'th']], on='origin')
ST['is_first'] = (ST.kind == 'first').astype(int)
ST['fuel'] = ST.fuel.fillna(ST.fuel.median()); ST['village_km'] = ST.village_km.fillna(ST.village_km.median())
PIX = ['tree', 'grass', 'crop', 'water', 'road', 'tree_prev100', 'grade', 'local_height', 'slope', 'fuel', 'village_km', 'prior_burns', 'downwind']
BASE = ['s', 'n_dots', 'frp', 'doy', 'wind_ms', 'th', 'is_first']
prm = dict(n_estimators=300, learning_rate=.05, num_leaves=15, min_child_samples=200, subsample=.7, subsample_freq=1, colsample_bytree=.8, verbose=-1)
ST = ST.sort_values(['origin', 'ray', 'i_rel']).reset_index(drop=True)
T = ST[~ST.after_stop]
for m, cols in [('base', BASE), ('full', BASE + PIX)]:
    h = np.zeros(len(ST))
    for s in sorted(ST.season.unique()):
        tr = T.season != s; te = (ST.season == s).values
        h[te] = lgb.LGBMClassifier(**prm).fit(T.loc[tr, cols].astype(float), T.stop[tr]).predict_proba(ST.loc[te, cols].astype(float))[:, 1]
    ST[f'h_{m}'] = h
def exp_reach(col):
    surv = np.exp(ST.assign(l=np.log1p(-np.clip(ST[col], 0, .999))).groupby(['origin', 'ray']).l.cumsum())
    return (surv * 20).groupby([ST.origin, ST.ray]).sum()
P = pd.DataFrame(dict(full=exp_reach('h_full'), base=exp_reach('h_base')))
P.to_parquet(f'{C.SCRATCH}/ray_pred_reach.parquet')
iou = lambda a, b: np.sum(np.minimum(a, b) ** 2) / np.sum(np.maximum(a, b) ** 2)
med_all = np.nanmedian(np.concatenate(O.reach.values))
rows = []
for o in O.itertuples():
    r = o.reach; ok = np.isfinite(r)
    if ok.sum() < 30 or o.origin not in P.index.get_level_values(0): continue
    p = P.loc[o.origin].reindex(range(36)); okp = ok & p.full.notna().values
    if okp.sum() < 30: continue
    r_, pf, pb = r[okp], p.full.values[okp], p.base.values[okp]
    circ_true = np.full_like(r_, r_.mean())
    rows.append(dict(origin=o.origin, season=o.season, kind=o.kind,
        model=iou(r_, pf), no_ground_circle=iou(r_, pb), fixed_circle=iou(r_, np.full_like(r_, med_all)),
        shape_model=iou(r_, pf * r_.mean() / pf.mean()), shape_circle=iou(r_, circ_true),
        shape_uphill_only=np.nan))
R = pd.DataFrame(rows)
rng = np.random.default_rng(0); fires = R.origin.str.split('_').str[0].values; uf = np.unique(fires)
def ci(a, b):
    d = (R[a] - R[b]).values; bs = []
    for _ in range(1000):
        sel = rng.choice(uf, len(uf)); m = np.concatenate([np.where(fires == f)[0] for f in sel]); bs.append(d[m].mean())
    return [round(float(d.mean()), 3), round(float(np.quantile(bs, .025)), 3), round(float(np.quantile(bs, .975)), 3)]
out = dict(n_fronts=len(R), mean_iou={c: round(float(R[c].mean()), 3) for c in ['model', 'no_ground_circle', 'fixed_circle', 'shape_model', 'shape_circle']},
           gain_size_and_shape_vs_no_ground=ci('model', 'no_ground_circle'), gain_shape_only_vs_circle=ci('shape_model', 'shape_circle'),
           share_fronts_shape_better=round(float((R.shape_model > R.shape_circle).mean()), 3),
           by_kind=R.groupby('kind')[['model', 'no_ground_circle', 'shape_model', 'shape_circle']].mean().round(3).to_dict('index'))
print(json.dumps(out, indent=1)); json.dump(out, open(f'{HERE}/results/ray_outline.json', 'w'), indent=1)
