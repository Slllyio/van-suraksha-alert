"""'Jump chance' table for the spread thread.
Issue = each fire (fire_group) on each IST day it is detected; issue time t0 = its last detection that day;
the parent footprint = all its detections up to t0.
Event = a NEW fire (another fire_group's ignition, posterior-median time) in a distance ring of the footprint
within (t0, t0+1d], (1,2d], (2,3d].
Observed P(any) per issue, and the background P from the space-time permutation null (ignition times shuffled within
season, locations kept). Excess = observed - background = the part an occurrence map without fire-to-fire coupling misses.
Held-out seasons: rates from the other seasons predict the count of issues with an event in the held-out season."""
import pandas as pd, numpy as np, json
from scipy.spatial import cKDTree
OUT = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r13_jump_code/'
NP = 199; rng = np.random.default_rng(5); H = 86400.0
F = pd.read_parquet(OUT + 'ign.parquet').reset_index(drop=True)
D = pd.read_parquet(OUT + 'det.parquet').reset_index(drop=True)
tF = F.t.values.astype('datetime64[s]').astype(np.int64) / H; tD = D.t.values.astype('datetime64[s]').astype(np.int64) / H
D['td'] = tD; D['day'] = D.t.dt.floor('D')
yr = F.yr.values; gF = F.fire_group.values; XF = F[['x', 'y']].values; ftree = cKDTree(XF)
RB = [0, 500, 1000, 2000, 3000, 5000]; RL = ['0-0.5', '0.5-1', '1-2', '2-3', '3-5']; LL = ['0-1', '1-2', '2-3']
iss, pj, pd_ = [], [], []
info = []
for g, G in D.sort_values('td').groupby('fire_group'):
    for day, Gd in G.groupby('day'):
        t0 = Gd.td.max(); P = G[G.td <= t0][['x', 'y']].values
        near = set()
        for v in ftree.query_ball_point(P, 5000): near.update(v)
        near = np.array(sorted(j for j in near if gF[j] != g), int)
        i = len(info); info.append(dict(fire_group=g, day=day, t0=t0, yr=day.year, mon=day.month, n_det_sofar=len(P), n_det_day=len(Gd),
                                       frp_day=Gd.frp.sum(), night_only=bool((Gd.t.dt.hour.between(0, 5)).all())))
        if len(near):
            d = cKDTree(P).query(XF[near])[0]
            iss.append(np.full(len(near), i)); pj.append(near); pd_.append(d)
I = pd.DataFrame(info); iss = np.concatenate(iss); pj = np.concatenate(pj); dd = np.concatenate(pd_)
rb = np.digitize(dd, RB) - 1; t0 = I.t0.values
print('issues', len(I), 'pairs', len(iss))
def table(t):
    lag = t[pj] - t0[iss]; ok = (lag > 0) & (lag <= 3); lb = np.ceil(lag[ok]).astype(int) - 1
    hit = np.zeros((len(I), 5, 3), bool); hit[iss[ok], rb[ok], lb] = True
    cnt = np.zeros((len(I), 5, 3)); np.add.at(cnt, (iss[ok], rb[ok], lb), 1)
    return hit, cnt
idx = {y: np.where(yr == y)[0] for y in np.unique(yr)}
def perm():
    t = tF.copy()
    for y, ii in idx.items(): t[ii] = tF[rng.permutation(ii)]
    return t
hit0, cnt0 = table(tF)
nullP = np.zeros((len(I), 5, 3)); nullC = np.zeros((len(I), 5, 3))
for _ in range(NP):
    h, c = table(perm()); nullP += h; nullC += c
nullP /= NP; nullC /= NP
rows = []
groups = {'all': np.ones(len(I), bool), 'Jan-Feb': I.mon.isin([1, 2]).values, 'Mar': (I.mon == 3).values, 'Apr': (I.mon == 4).values, 'May-Jun': I.mon.isin([5, 6]).values,
          'parent>=3 det that day': (I.n_det_day >= 3).values, 'parent 1-2 det that day': (I.n_det_day < 3).values}
for gname, m in groups.items():
    for r in range(5):
        for l in range(3):
            o = hit0[m, r, l].mean(); b = nullP[m, r, l].mean()
            rows.append(dict(group=gname, ring_km=RL[r], lag_days=LL[l], n_issues=int(m.sum()), p_obs=round(o, 4), p_background=round(b, 4),
                             excess=round(o - b, 4), ratio=round(o / b, 2) if b > 0 else np.nan,
                             new_fires_per_issue_obs=round(cnt0[m, r, l].mean(), 4), new_fires_per_issue_bg=round(nullC[m, r, l].mean(), 4)))
T = pd.DataFrame(rows); T.to_csv(OUT + 'jump_rate_table.csv', index=False)
print(T[T.group == 'all'].to_string())
print(T[(T.group != 'all') & (T.lag_days == '0-1')].to_string())
# held-out seasons
ho = []
for y in sorted(I.yr.unique()):
    tr = (I.yr != y).values; te = ~tr
    for r in range(5):
        for l in range(3):
            p = hit0[tr, r, l].mean(); pb = nullP[te, r, l].mean()
            ho.append(dict(season=y, ring_km=RL[r], lag_days=LL[l], n_issues=int(te.sum()), observed=int(hit0[te, r, l].sum()),
                           predicted_from_other_seasons=round(p * te.sum(), 1), background_this_season=round(pb * te.sum(), 1),
                           excess_rate_this_season=round(hit0[te, r, l].mean() - pb, 4)))
HO = pd.DataFrame(ho); HO.to_csv(OUT + 'jump_rate_heldout.csv', index=False)
S = HO.groupby(['ring_km', 'lag_days']).agg(obs=('observed', 'sum'), pred=('predicted_from_other_seasons', 'sum'),
        excess_mean=('excess_rate_this_season', 'mean'), excess_sd=('excess_rate_this_season', 'std'),
        seasons_with_positive_excess=('excess_rate_this_season', lambda s: int((s > 0).sum())))
S['abs_err_by_season'] = HO.assign(e=(HO.observed - HO.predicted_from_other_seasons).abs()).groupby(['ring_km', 'lag_days']).e.sum()
print(S.round(4).to_string()); S.to_csv(OUT + 'jump_rate_heldout_summary.csv')
# the 'skip' check: 1-day cumulative chance of >=1 new fire within 2 km, obs vs background
o = (hit0[:, :3, 0].any(1)).mean(); b = 1 - np.prod(1 - nullP[:, :3, 0], axis=1)
json.dump(dict(n_issues=len(I), p_any_new_within2km_24h=round(float(o), 4), p_background_approx=round(float(b.mean()), 4),
               p_any_new_within5km_24h=round(float(hit0[:, :, 0].any(1).mean()), 4)), open(OUT + 'jump_rate_summary.json', 'w'), indent=1)
print(open(OUT + 'jump_rate_summary.json').read())
