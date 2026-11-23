"""Revisit, detection probability and position noise from raw VIIRS tracks (r1_tracks.py output)."""
import pandas as pd, numpy as np, sys, json
from scipy.spatial import cKDTree
S = sys.argv[1]
A = pd.read_parquet(S + '/tracks.parquet'); P = pd.read_parquet(S + '/passes.parquet')
md = A.t.dt.strftime('%m-%d')
A = A[(md >= '02-15') & (md <= '06-15')]
P['md'] = P.look.str[5:10]; P = P[(P.md >= '02-15') & (P.md <= '06-15')]
R = {}
# 1. which satellites look, and time between looks
P['yr'] = P.look.str[:4].astype(int)
for yr in [2019, 2025]:
    q = P[P.yr == yr]
    R[f'looks_per_slot_{yr}'] = q.groupby('look').sat.nunique().value_counts().to_dict()
    tt = q.sort_values('t').groupby('look').t.agg(['min', 'max'])
    R[f'spread_within_slot_min_{yr}'] = float(((tt['max'] - tt['min']).dt.total_seconds() / 60).median())
    g = tt['min'].sort_values().diff().dt.total_seconds().div(3600).dropna()
    R[f'gap_between_slots_h_{yr}'] = g.round(1).value_counts().head(4).to_dict()
# 2. detection probability: fire seen by sat a in a slot, sat b also looked in the slot -> did b see it?
seen = A.groupby(['fire', 'look', 'sat']).agg(n=('x', 'size'), frp=('frp', 'sum'), scan=('scan', 'mean')).reset_index()
looked = set(zip(P.sat, P.look))
rows = []
for (f, lk), g in seen.groupby(['fire', 'look']):
    sats = set(g.sat)
    for a in sats:
        for b in ['viirs-snpp', 'viirs-jpss1', 'viirs-noaa21']:
            if b != a and (b, lk) in looked:
                ra = g[g.sat == a].iloc[0]
                rows.append(dict(fire=f, look=lk, a=a, b=b, b_saw=b in sats, n_a=ra.n, frp_a=ra.frp, night=lk.endswith('N')))
Q = pd.DataFrame(rows)
R['p_other_sat_sees'] = float(Q.b_saw.mean())
R['p_other_sat_sees_by_frp'] = Q.groupby(pd.cut(Q.frp_a, [0, 2, 5, 10, 20, 50, 1e4])).b_saw.mean().round(2).astype(str).to_dict()
R['p_other_sat_sees_day_night'] = Q.groupby('night').b_saw.mean().round(3).to_dict()
R['p_other_sat_sees_by_npix'] = Q.groupby(pd.cut(Q.n_a, [0, 1, 2, 4, 8, 100])).b_saw.mean().round(2).astype(str).to_dict()
# 3. position noise: same slot, two satellites ~50 min apart: nearest-neighbour distance between their points
nn = []
for (f, lk), g in A.groupby(['fire', 'look']):
    if g.sat.nunique() < 2: continue
    s = g.sat.unique()
    a, b = g[g.sat == s[0]], g[g.sat == s[1]]
    dt = abs((a.t.median() - b.t.median()).total_seconds()) / 3600
    d, _ = cKDTree(a[['x', 'y']].values).query(b[['x', 'y']].values)
    nn += [dict(fire=f, look=lk, d=x, dt=dt) for x in d]
N = pd.DataFrame(nn)
R['same_slot_nn_dist_m_quantiles'] = N.d.quantile([.25, .5, .75, .9]).round(0).to_dict()
R['same_slot_dt_h_median'] = float(N.dt.median())
# 4. fire lifetime in slots, and silent slots inside a fire's life
fl = A.groupby('fire').agg(t0=('t', 'min'), t1=('t', 'max'), nlook=('look', 'nunique'), n=('x', 'size'))
fl['hours'] = (fl.t1 - fl.t0).dt.total_seconds() / 3600
R['fires'] = int(len(fl))
R['fires_by_nlook'] = fl.nlook.clip(upper=8).value_counts().sort_index().to_dict()
R['share_fires_single_slot'] = float((fl.nlook == 1).mean())
R['share_detections_in_single_slot_fires'] = float(fl[fl.nlook == 1].n.sum() / fl.n.sum())
allslots = sorted(P.look.unique()); idx = {s: i for i, s in enumerate(allslots)}
sil = []
for f, g in A.groupby('fire'):
    ls = sorted(set(g.look) & set(idx))
    if len(ls) < 2: continue
    i0, i1 = idx[ls[0]], idx[ls[-1]]
    inner = allslots[i0 + 1:i1]
    sil.append(dict(fire=f, inner=len(inner), silent=sum(s not in set(ls) for s in inner)))
Sl = pd.DataFrame(sil)
R['inner_slots_silent_share'] = float(Sl.silent.sum() / max(Sl.inner.sum(), 1))
R = json.loads(json.dumps({k: ({str(a): b for a, b in v.items()} if isinstance(v, dict) else v) for k, v in R.items()}, default=str))
json.dump(R, open(S + '/r2.json', 'w'), indent=1)
Q.to_parquet(S + '/r2_detprob.parquet'); N.to_parquet(S + '/r2_nn.parquet'); fl.to_parquet(S + '/r2_fires.parquet')
print(json.dumps(R, indent=1))
