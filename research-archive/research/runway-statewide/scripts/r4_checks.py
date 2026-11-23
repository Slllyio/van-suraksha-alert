"""Is the statewide 'runway' signal real spread, or just where the burn scar sits relative to the VIIRS dot (dot position error
~230 m median, while the median reach is only 200-450 m)? Checks:
 1. score by final fire size (big fires reach km, much more than the dot error);
 2. 'past 500 m' truth only (a 230 m offset alone rarely makes a sector burn past 500 m);
 3. offset: angle and distance from the dot centre to the scar centroid; score on fronts whose dots sit near the scar centre;
 4. how often the model's open sector simply points at the scar centroid.
Out: results/runway_checks.json"""
import json, os, pickle, numpy as np, pandas as pd
SCR = os.environ['RW_SCRATCH']; HERE = '/mnt/project-files/research/runway-statewide'
F = pd.read_parquet(f'{SCR}/F.parquet'); P = pd.read_parquet(f'{SCR}/preds.parquet')
E = pickle.load(open(f'{SCR}/events.pkl', 'rb'))
cen = {}
for e in E:
    c = e['scar'].centroid
    for o in e['origins']:
        dx, dy = c.x - o['x'], c.y - o['y']; cen[o['origin']] = (np.hypot(dx, dy), np.degrees(np.arctan2(dx, dy)) % 360)
M = 'model, ground + dots, other reserves'; T = 'most tree cover (c14/c15 rule)'; B = 'farthest to first barrier (road, forest edge, crop)'
rows = []
for oid, gi in F.groupby('origin'):
    if len(gi) < 36: continue
    r = gi.reach_real.values.astype(float); sr = np.nanmean(r.reshape(9, 4), 1); p5 = np.nanmean(np.where(np.isfinite(r), r > 500, np.nan).reshape(9, 4), 1)
    rec = dict(origin=oid, event=gi.event.iloc[0], scar_ha=gi.scar_ha.iloc[0], kind=gi.kind.iloc[0], off_m=cen[oid][0], off_az=cen[oid][1])
    for k in [M, T, B]:
        v = P.loc[gi.index, k].values.astype(float)
        if not np.isfinite(v).all() or np.ptp(v) == 0: continue
        sp = v.reshape(9, 4).mean(1); a, b = np.argmax(sp), np.argmin(sp)
        rec[k + '|right'] = float(sr[a] > sr[b]) if np.isfinite(sr[a]) and np.isfinite(sr[b]) and sr[a] != sr[b] else np.nan
        rec[k + '|o500'] = p5[a]; rec[k + '|s500'] = p5[b]
        oaz = a * 40 + 20; rec[k + '|to_centroid'] = abs((oaz - cen[oid][1] + 180) % 360 - 180) <= 45
    rows.append(rec)
R = pd.DataFrame(rows); out = {}
def summ(g):
    d = {'fronts': len(g)}
    for k, n in [(M, 'model'), (T, 'tree rule'), (B, 'barrier rule')]:
        if k + '|right' in g:
            d[n] = dict(right=round(float(g[k + '|right'].mean()), 3), past500_open_vs_stop=[round(float(g[k + '|o500'].mean()), 3), round(float(g[k + '|s500'].mean()), 3)],
                        open_points_at_scar_centre=round(float(g[k + '|to_centroid'].mean()), 3))
    return d
out['all'] = summ(R)
for lo, hi in [(10, 50), (50, 100), (100, 200), (200, 1e9)]:
    out[f'scar {lo}-{hi:.0f} ha'] = summ(R[(R.scar_ha >= lo) & (R.scar_ha < hi)])
for lo, hi in [(0, 150), (150, 300), (300, 600), (600, 1e9)]:
    out[f'dot centre {lo}-{hi:.0f} m from scar centre'] = summ(R[(R.off_m >= lo) & (R.off_m < hi)])
out['chance that a 40 deg sector points within 45 deg of the scar centre'] = 0.25
out['median dot-to-scar-centre distance m'] = float(R.off_m.median())
json.dump(out, open(f'{HERE}/results/runway_checks.json', 'w'), indent=1); print(json.dumps(out, indent=1))
