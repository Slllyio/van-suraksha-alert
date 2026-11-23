"""Score 'which side runs farther' rules on the statewide rays (r2_rays.py), exactly as fire-continuity c14/c15:
each front's 36 rays -> 9 sectors of 40 deg; the rule's 'open' sector (highest mean score) vs its 'stop' sector (lowest);
right if the open sector really burned farther (mean reach to the scar edge). Real stops only: censored rays (cut by another front
or the window) count as unknown. Fronts need >= 30 rays with a reach. 95% ranges: bootstrap over fires.
Models (LightGBM, within-front relative target) are scored held out: (a) leave one season out, (b) leave one tiger reserve out.
Out: results/runway_statewide.json, results/runway_statewide_fronts.csv"""
import glob, json, os, pickle, sys, warnings
import numpy as np, pandas as pd, lightgbm as lgb
warnings.simplefilter('ignore')
SCR = os.environ['RW_SCRATCH']; HERE = '/mnt/project-files/research/runway-statewide'
F = pd.concat([pd.read_parquet(f) for f in glob.glob(f'{SCR}/rays/*.parquet')], ignore_index=True)
E = pickle.load(open(f'{SCR}/events.pkl', 'rb'))
meta = pd.DataFrame([dict(origin=o['origin'], event=e['event'], season=e['season'], reserve=e['reserve'], kind=o['kind'], n_dots=o['n_dots'],
                          scar_ha=e['scar_ha'], n_fronts=len(e['origins'])) for e in E for o in e['origins']])
F = F.merge(meta, on=['origin', 'event'])
F['reach_real'] = np.where(F.cens, np.nan, F.reach)
ok = F.groupby('origin').reach.transform('count') >= 30
F = F[ok].sort_values(['origin', 'ray']).reset_index(drop=True)
F['yc'] = np.log1p(F.reach) - F.groupby('origin').reach.transform(lambda r: np.log1p(r).mean())
GROUND = [c for c in F.columns if c.startswith(('d_', 'tree_', 'grass_', 'crop_', 'grade_', 'local_height_', 'slope_', 'prior_burns_'))]
DOTS = ['hot_side', 'along_dots', 'momentum']
P = {'most tree cover (c14/c15 rule)': F.tree_0_300 + F.tree_300_1000,
     'farthest to first barrier (road, forest edge, crop)': np.minimum(np.minimum(F.d_road, F.d_edge), F.d_crop),
     'farthest to first forest edge': F.d_edge, 'farthest to first road': F.d_road,
     'uphill side': F.grade_0_300 + F.grade_300_1000, 'hot side of the dots': F.hot_side}
def fit(cols, split):
    p = np.full(len(F), np.nan)
    for s in sorted(F[split].unique()):
        tr, te = (F[split] != s).values, (F[split] == s).values
        m = lgb.LGBMRegressor(n_estimators=300, learning_rate=.03, num_leaves=15, min_child_samples=200, subsample=.8, subsample_freq=1,
                              colsample_bytree=.8, verbose=-1).fit(F.loc[tr, cols].astype(float), F.yc[tr])
        p[te] = m.predict(F.loc[te, cols].astype(float))
    return p
for name, cols in [('ground', GROUND), ('ground + dots', GROUND + DOTS)]:
    P[f'model, {name}, other seasons'] = fit(cols, 'season')
    P[f'model, {name}, other reserves'] = fit(cols, 'reserve')
pd.DataFrame({k: np.asarray(v) for k, v in P.items()}).assign(origin=F.origin.values, ray=F.ray.values).to_parquet(f'{SCR}/preds.parquet')
F.to_parquet(f'{SCR}/F.parquet')
rng = np.random.default_rng(0)
def score(pv, g):
    rows = []
    pv = np.asarray(pv)
    for oid, gi in g.groupby('origin'):
        if len(gi) < 36: continue
        r = gi.reach_real.values.astype(float); v = pv[gi.index.values]
        if not np.isfinite(v).all() or np.ptp(v) == 0: continue
        sr, sp = np.nanmean(r.reshape(9, 4), 1), v.reshape(9, 4).mean(1); a, b = np.argmax(sp), np.argmin(sp)
        if not (np.isfinite(sr[a]) and np.isfinite(sr[b])) or sr[a] == sr[b]: continue
        rows.append((gi.event.iloc[0], oid, sr[a] > sr[b], sr[a] > 500, sr[b] > 500, sr[a], sr[b]))
    R = pd.DataFrame(rows, columns=['fire', 'origin', 'right', 'o500', 's500', 'open_m', 'stop_m'])
    fr = R.fire.values; u, inv = np.unique(fr, return_inverse=True); idx = [np.where(inv == k)[0] for k in range(len(u))]; bs = []
    for _ in range(500):
        m = np.concatenate([idx[k] for k in rng.integers(0, len(u), len(u))]); bs.append(R.right.values[m].mean())
    return dict(fronts=len(R), right=[round(R.right.mean(), 3), round(float(np.quantile(bs, .025)), 3), round(float(np.quantile(bs, .975)), 3)],
                open_past500=round(R.o500.mean(), 3), stop_past500=round(R.s500.mean(), 3),
                open_median_m=float(R.open_m.median()), stop_median_m=float(R.stop_m.median())), R
out = {}; keep = None
subsets = [('all fronts', F), ('first-look fronts', F[F.kind == 'first']), ('first-look, fire grew 50 ha+', F[(F.kind == 'first') & (F.scar_ha >= 50)])]
subsets += [(f'reserve {r}', F[F.reserve == r]) for r in sorted(F.reserve.unique())]
for sname, g in subsets:
    out[sname] = {}
    for k, v in P.items():
        s, R = score(v, g); out[sname][k] = s
        if sname == 'first-look fronts' and k == 'model, ground + dots, other reserves': keep = R
    print(sname, {k: v['right'][0] for k, v in out[sname].items()}, flush=True)
# what drives it: gain importance of a model on all fronts
m = lgb.LGBMRegressor(n_estimators=300, learning_rate=.03, num_leaves=15, min_child_samples=200, subsample=.8, subsample_freq=1, colsample_bytree=.8,
                      verbose=-1, importance_type='gain').fit(F[GROUND + DOTS].astype(float), F.yc)
out['importance'] = {c: round(float(v), 3) for c, v in sorted(zip(GROUND + DOTS, m.feature_importances_ / m.feature_importances_.sum()), key=lambda z: -z[1])}
out['n'] = dict(fires=int(F.event.nunique()), fronts=int(F.origin.nunique()), rays=len(F), censored_share=round(float(F.cens.mean()), 3))
json.dump(out, open(f'{HERE}/results/runway_statewide.json', 'w'), indent=1)
if keep is not None: keep.to_csv(f'{HERE}/results/runway_statewide_fronts.csv', index=False)
print(json.dumps(out['n']), json.dumps(out['importance']))
