"""Runway map test: around a front, which side has open ground to run into and which side has a natural stop close by?
Uses the held-out (other-seasons) ray model reach from c12 ($FC_SCRATCH/ray_pred_reach.parquet). Per front:
  9 sectors of 40 deg (mean of their rays' reach). 'Open side' = sector with the longest predicted reach, 'stop side' = shortest.
  Half test: the 180 deg half with the longest predicted mean reach vs the opposite half.
Scored against the true reach to the scar edge: share of fronts where the open side really burned farther (chance 50%),
and how much farther. Baselines: same with the uphill-only, tree-cover-only and distance-only (no ground) predictions.
First-alert fronts reported separately (that is when crews would use it). Out: results/runway.json"""
import os, sys, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import c0_lib as C
HERE = '/mnt/project-files/research/fire-continuity'
P = pd.read_parquet(f'{C.SCRATCH}/ray_pred_reach.parquet'); ST = pd.read_parquet(f'{C.SCRATCH}/rays.parquet', columns=['origin', 'ray', 's', 'grade', 'tree'])
f5 = ST[ST.s <= 500].groupby(['origin', 'ray']); P['uphill'] = f5.grade.mean(); P['trees'] = f5.tree.mean()
O = pd.read_csv(f'{HERE}/results/ray_origins.csv'); O['reach'] = O.reach.apply(lambda s: np.array(json.loads(s.replace('nan', 'NaN'))))
rng = np.random.default_rng(0); res = {}
rows = []
for o in O.itertuples():
    r = o.reach
    if np.isfinite(r).sum() < 30 or o.origin not in P.index.get_level_values(0): continue
    p = P.loc[o.origin].reindex(range(36)); r = pd.Series(r).fillna(np.nanmean(r)).values
    rec = dict(origin=o.origin, fire=o.fire, season=o.season, first=o.kind == 'first')
    sec_r = r.reshape(9, 4).mean(1)       # sector j covers rays 4j..4j+3 (0-30 deg rays = a 40 deg sector)
    for m in ['full', 'base', 'uphill', 'trees']:
        v = p[m].fillna(p[m].mean()).values
        if not np.isfinite(v).all() or np.ptp(v) == 0: continue
        sp = v.reshape(9, 4).mean(1); a, b = np.argmax(sp), np.argmin(sp)
        rec[f'sec_{m}'] = sec_r[a] > sec_r[b]; rec[f'secratio_{m}'] = sec_r[a] / max(sec_r[b], 20)
        hv = np.array([v[np.arange(k, k + 18) % 36].mean() for k in range(36)]); k = int(np.argmax(hv))
        ho = r[np.arange(k, k + 18) % 36].mean(); hs = r[np.arange(k + 18, k + 36) % 36].mean()
        rec[f'half_{m}'] = ho > hs; rec[f'halfratio_{m}'] = ho / max(hs, 20)
        rec[f'beyond500_open_{m}'] = float(sec_r[a] > 500); rec[f'beyond500_stop_{m}'] = float(sec_r[b] > 500)
    rows.append(rec)
R = pd.DataFrame(rows); fires = R.fire.values; uf = np.unique(fires)
def boot(col, g):
    x = g[col].astype(float).values; fr = g.fire.values; u = np.unique(fr); bs = []
    for _ in range(1000):
        s = rng.choice(u, len(u)); m = np.concatenate([np.where(fr == f)[0] for f in s]); bs.append(np.nanmean(x[m]))
    return [round(float(np.nanmean(x)), 3), round(float(np.quantile(bs, .025)), 3), round(float(np.quantile(bs, .975)), 3)]
for setn, g in [('all fronts', R), ('first-alert fronts', R[R['first']])]:
    o = dict(n=len(g))
    for m in ['full', 'base', 'uphill', 'trees']:
        gm = g[g[f'sec_{m}'].notna()]
        o[m] = dict(open_sector_burned_farther=boot(f'sec_{m}', gm), open_half_burned_farther=boot(f'half_{m}', gm),
                    median_ratio_sector=round(float(gm[f'secratio_{m}'].median()), 2), median_ratio_half=round(float(gm[f'halfratio_{m}'].median()), 2),
                    share_open_sector_past_500m=round(float(gm[f'beyond500_open_{m}'].mean()), 3), share_stop_sector_past_500m=round(float(gm[f'beyond500_stop_{m}'].mean()), 3))
    res[setn] = o
print(json.dumps(res, indent=1)); json.dump(res, open(f'{HERE}/results/runway.json', 'w'), indent=1)
