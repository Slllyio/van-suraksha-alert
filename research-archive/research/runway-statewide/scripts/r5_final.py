"""Final 'which side runs farther' model for the field app: LightGBM on all 4,104 statewide fronts, inputs available statewide at
alert time (terrain, land cover, roads, the front's own dots; past burns left out: no statewide burn history in the app, -0.9 pt).
Also scores the held-out (other reserves) version with 8 compass sectors of 45 deg, the way the card shows it.
Out: field-system/data/runway/model.json (LightGBM dump), results/runway_8sector.json"""
import json, os, numpy as np, pandas as pd, lightgbm as lgb
SCR = os.environ['RW_SCRATCH']; HERE = '/mnt/project-files/research/runway-statewide'
F = pd.read_parquet(f'{SCR}/F.parquet')
COLS = [c for c in F.columns if c.startswith(('d_', 'tree_', 'grass_', 'crop_', 'grade_', 'local_height_', 'slope_'))] + ['hot_side', 'along_dots', 'momentum']
KW = dict(n_estimators=300, learning_rate=.03, num_leaves=15, min_child_samples=200, subsample=.8, subsample_freq=1, colsample_bytree=.8, verbose=-1)
p = np.full(len(F), np.nan)
for s in F.reserve.unique():
    tr, te = (F.reserve != s).values, (F.reserve == s).values
    p[te] = lgb.LGBMRegressor(**KW).fit(F.loc[tr, COLS].astype(float), F.yc[tr]).predict(F.loc[te, COLS].astype(float))
F['p'] = p
SEC = ((np.arange(36) * 10 + 22.5) // 45 % 8).astype(int)        # ray -> compass sector N, NE, ... (rays at 0..350 deg)
rows = []
for _, g in F.groupby('origin'):
    if len(g) < 36: continue
    r = g.reach_real.values; v = g.p.values
    sr = np.array([np.nanmean(r[SEC == k]) for k in range(8)]); sp = np.array([v[SEC == k].mean() for k in range(8)])
    a, b = np.argmax(sp), np.argmin(sp)
    r5 = np.where(np.isfinite(r), r > 500, np.nan); s5 = np.array([np.nanmean(r5[SEC == k]) for k in range(8)])
    if np.isfinite(sr[a]) and np.isfinite(sr[b]) and sr[a] != sr[b]:
        rows.append((g.event.iloc[0], g.kind.iloc[0], sr[a] > sr[b], s5[a], s5[b], int(np.argmax(sr) == a)))
R = pd.DataFrame(rows, columns=['fire', 'kind', 'right', 'o5', 's5', 'top'])
rng = np.random.default_rng(0); u = R.fire.unique(); ix = {f: np.where(R.fire.values == f)[0] for f in u}
bs = [R.right.values[np.concatenate([ix[f] for f in rng.choice(u, len(u))])].mean() for _ in range(500)]
out = dict(fronts=len(R), right=[round(R.right.mean(), 3), round(float(np.quantile(bs, .025)), 3), round(float(np.quantile(bs, .975)), 3)],
           first_look_right=round(R[R.kind == 'first'].right.mean(), 3), open_past500=round(R.o5.mean(), 3), stop_past500=round(R.s5.mean(), 3),
           open_is_the_farthest_sector=round(R.top.mean(), 3), chance_farthest=0.125)
print(out); json.dump(out, open(f'{HERE}/results/runway_8sector.json', 'w'), indent=1)
m = lgb.LGBMRegressor(**KW).fit(F[COLS].astype(float), F.yc)
d = m.booster_.dump_model(); d['cols'] = COLS
json.dump(d, open('/mnt/project-files/field-system/data/runway/model.json', 'w'))
np.save(f'{SCR}/final_pred.npy', m.predict(F[COLS].astype(float)))
print('saved', os.path.getsize('/mnt/project-files/field-system/data/runway/model.json') / 1e6, 'MB')
