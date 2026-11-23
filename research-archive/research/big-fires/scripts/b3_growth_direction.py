"""Step 3: does a big fire keep growing the same way from one look to the next?

Growth direction at look k = bearing from the centroid of every alert seen BEFORE look k to the alerts of look k that sit on
new ground (> 400 m from every earlier alert). This avoids the zig-zag of centroid-to-centroid steps, where one noisy
centroid is shared by two steps.
Tests (big fires, then smaller multi-look fires):
  1. persistence: growth direction at look k vs at the next look with new ground (cosine; random = 0, 25% within 45 deg)
  2. same against the fire's overall heading so far (first look -> all earlier alerts' centroid)
  3. permutation baseline: shuffle the order of looks inside the fire 200 times and recompute (keeps every alert where it
     is, destroys time order). If the observed number sits inside the shuffled spread, the direction carries no time signal.
Out: results/growth_steps.csv, results/growth_summary.json
"""
import json
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
R = '/mnt/project-files/research/big-fires/results'
F = pd.read_csv(f'{R}/fires.csv')
A = pd.read_csv(f'{R}/fire_alerts.csv', parse_dates=['t'])
V = A[A.sat != 'modis']
F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
rng = np.random.default_rng(1)

def growth(v, order):
    """v: alerts with look; order: list of looks in time order. Returns list of (k, bearing, dist, heading_so_far, n_new)."""
    out = []
    for k in range(1, len(order)):
        prev = v[v.look.isin(order[:k])][['x', 'y']].values
        cur = v[v.look == order[k]][['x', 'y']].values
        d = cKDTree(prev).query(cur)[0]
        new = cur[d > 400]
        if not len(new): continue
        c0 = prev.mean(0); c1 = new.mean(0)
        first = v[v.look == order[0]][['x', 'y']].values.mean(0)
        hx, hy = c0 - first
        out.append((k, np.arctan2(c1[1] - c0[1], c1[0] - c0[0]), np.hypot(*(c1 - c0)),
                    np.arctan2(hy, hx) if np.hypot(hx, hy) > 300 else np.nan, len(new)))
    return out

def stats(rows):
    cos_next, cos_head = [], []
    for i in range(1, len(rows)):
        cos_next.append(np.cos(rows[i][1] - rows[i - 1][1]))
    for r in rows:
        if np.isfinite(r[3]): cos_head.append(np.cos(r[1] - r[3]))
    return cos_next, cos_head

res, steps = {}, []
for grp_name, sel in [('big', F.big), ('smaller', (~F.big) & (F.n_looks >= 3))]:
    obs_n, obs_h, null_n, null_h = [], [], [], []
    for _, f in F[sel].iterrows():
        v = V[V.fire == f.fire]
        order = list(v.groupby('look').t.median().sort_values().index)
        if len(order) < 3: continue
        rows = growth(v, order)
        for r in rows:
            steps.append(dict(fire=f.fire, group=grp_name, k=r[0], bearing=np.degrees(r[1]), dist=r[2], n_new=r[4]))
        cn, ch = stats(rows); obs_n += cn; obs_h += ch
        pn, ph = [], []
        for _ in range(200):
            perm = list(rng.permutation(order))
            a, b = stats(growth(v, perm)); pn.append(a); ph.append(b)
        null_n.append(pn); null_h.append(ph)
    # null distribution of the pooled mean cosine
    def pooled(null):
        return np.array([np.mean(sum([n[i] for n in null], [])) for i in range(200)])
    pn, ph = pooled(null_n), pooled(null_h)
    on, oh = np.array(obs_n), np.array(obs_h)
    res[grp_name] = dict(
        next_look=dict(n=len(on), mean_cos=round(on.mean(), 3), within45=round((on > np.cos(np.pi / 4)).mean(), 3),
                       within90=round((on > 0).mean(), 3), shuffled_mean_cos_95=[round(np.quantile(pn, .025), 3), round(np.quantile(pn, .975), 3)]),
        heading_so_far=dict(n=len(oh), mean_cos=round(oh.mean(), 3), within45=round((oh > np.cos(np.pi / 4)).mean(), 3),
                            within90=round((oh > 0).mean(), 3), shuffled_mean_cos_95=[round(np.quantile(ph, .025), 3), round(np.quantile(ph, .975), 3)]))
    print(grp_name, json.dumps(res[grp_name], indent=1))
pd.DataFrame(steps).to_csv(f'{R}/growth_steps.csv', index=False)
json.dump(res, open(f'{R}/growth_summary.json', 'w'), indent=1)
