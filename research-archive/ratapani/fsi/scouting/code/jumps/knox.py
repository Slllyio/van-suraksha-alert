"""Knox / near-repeat tests for new fires near active fires, Ratapani 2017-2026.
Null: space-time permutation = shuffle ignition times among new fires of the same season (locations fixed).
Outputs JSON + CSV tables into OUT."""
import pandas as pd, numpy as np, json
from scipy.spatial import cKDTree
OUT = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r13_jump_code/'
NP = 499; rng = np.random.default_rng(13)
F = pd.read_parquet(OUT + 'ign.parquet').reset_index(drop=True)
D = pd.read_parquet(OUT + 'det.parquet').reset_index(drop=True)
DB = [0, 500, 1000, 2000, 5000]; DL = ['0-0.5', '0.5-1', '1-2', '2-5']
LB = [0, 1, 2, 3]; LL = ['0-1', '1-2', '2-3']
H = 86400.0
tF = F.t.values.astype('datetime64[s]').astype(np.int64) / H      # days
tD = D.t.values.astype('datetime64[s]').astype(np.int64) / H
yr = F.yr.values
gF = F.fire_group.values; gD = D.fire_group.values
def perms():
    """yield permuted ignition times, shuffled within season"""
    idx = {y: np.where(yr == y)[0] for y in np.unique(yr)}
    for _ in range(NP):
        t = tF.copy()
        for y, ii in idx.items(): t[ii] = tF[rng.permutation(ii)]
        yield t
def perms_month():
    key = yr * 100 + F.mon.values; idx = {k: np.where(key == k)[0] for k in np.unique(key)}
    for _ in range(NP):
        t = tF.copy()
        for k, ii in idx.items(): t[ii] = tF[rng.permutation(ii)]
        yield t
res = {}
# ---------- A. classic Knox, new fire vs new fire ----------
XF = F[['x', 'y']].values; tree = cKDTree(XF)
P = np.array(sorted(tree.query_pairs(5000))); a, b = P[:, 0], P[:, 1]
dA = np.hypot(*(XF[a] - XF[b]).T); dbin = np.digitize(dA, DB) - 1
def knoxA(t):
    lag = np.abs(t[a] - t[b]); lb = np.digitize(lag, LB) - 1; ok = (lb >= 0) & (lb < 3)
    M = np.zeros((4, 3)); np.add.at(M, (dbin[ok], lb[ok]), 1); return M
def run(fn, gen, tag):
    obs = fn(tF); S = np.stack([fn(t) for t in gen()]); exp = S.mean(0)
    p = ((S >= obs).sum(0) + 1) / (NP + 1)
    T = []
    for i in range(obs.shape[0]):
        for j in range(obs.shape[1]):
            T.append(dict(test=tag, dist_km=DL[i], lag_days=LL[j], observed=int(obs[i, j]), expected=round(float(exp[i, j]), 1),
                          ratio=round(float(obs[i, j] / max(exp[i, j], 1e-9)), 2), excess=round(float(obs[i, j] - exp[i, j]), 1), p=round(float(p[i, j]), 3)))
    return pd.DataFrame(T)
TA = run(knoxA, perms, 'A_newfire_pairs_permyear'); TAm = run(knoxA, perms_month, 'A_newfire_pairs_permmonth')
# ---------- B. new fire after an active fire (detections of other fires before the ignition) ----------
td = cKDTree(D[['x', 'y']].values)
nb = td.query_ball_point(XF, 5000)
j_ = np.concatenate([np.full(len(v), i) for i, v in enumerate(nb)]); k_ = np.concatenate([np.array(v, int) for v in nb])
keep = gF[j_] != gD[k_]; j_, k_ = j_[keep], k_[keep]
dB = np.hypot(*(XF[j_] - D[['x', 'y']].values[k_]).T); dbB = np.digitize(dB, DB) - 1
def knoxB(t, detail=False):
    lag = t[j_] - tD[k_]; lb = np.digitize(lag, LB) - 1; ok = (lag > 0) & (lb < 3)
    # count each new fire once per cell (any parent detection in that ring & lag)
    key = np.unique(np.c_[j_[ok], dbB[ok], lb[ok]], axis=0)
    M = np.zeros((4, 3)); np.add.at(M, (key[:, 1], key[:, 2]), 1)
    return M
TB = run(knoxB, perms, 'B_newfire_after_active_permyear'); TBm = run(knoxB, perms_month, 'B_newfire_after_active_permmonth')
pd.concat([TA, TAm, TB, TBm]).to_csv(OUT + 'knox_tables.csv', index=False)
print(pd.concat([TA, TAm, TB, TBm]).to_string())
# nearest active-fire parent for each new fire (for the splits): nearest other-fire detection 0-3 days before, within 5 km
lag = tF[j_] - tD[k_]; ok = (lag > 0) & (lag <= 3)
Pj = pd.DataFrame(dict(j=j_[ok], k=k_[ok], d=dB[ok], lag=lag[ok])).sort_values('d').groupby('j').first()
F2 = F.join(Pj, how='left'); F2['parent_group'] = np.where(F2.k.notna(), gD[F2.k.fillna(0).astype(int)], None)
F2.to_parquet(OUT + 'ign_with_parent.parquet')
