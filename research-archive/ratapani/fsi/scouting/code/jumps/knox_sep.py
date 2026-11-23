"""Is the near-repeat excess the same fire split in two (scars touching), or separate fires?
For each same-season pair (new fire j, other fire g with a detection within 5 km of j's ignition), flag 'joined' if the v2 scar
outlines of j's and g's fire groups are within 100 m of each other. Count new fires with a parent detection in ring r, 0-1 day
before, split by joined / separate, observed vs the within-season time-permutation null."""
import pandas as pd, numpy as np, geopandas as gpd, json
from scipy.spatial import cKDTree
OUT = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r13_jump_code/'
NP = 199; rng = np.random.default_rng(11); H = 86400.0
F = pd.read_parquet(OUT + 'ign.parquet').reset_index(drop=True); D = pd.read_parquet(OUT + 'det.parquet').reset_index(drop=True)
tF = F.t.values.astype('datetime64[s]').astype(np.int64) / H; tD = D.t.values.astype('datetime64[s]').astype(np.int64) / H
yr = F.yr.values; yD = D.t.dt.year.values; gF = F.fire_group.values; gD = D.fire_group.values; XF = F[['x', 'y']].values; XD = D[['x', 'y']].values
nb = cKDTree(XD).query_ball_point(XF, 5000)
j_ = np.concatenate([np.full(len(v), i) for i, v in enumerate(nb)]); k_ = np.concatenate([np.array(v, int) for v in nb])
keep = (gF[j_] != gD[k_]) & (yr[j_] == yD[k_]); j_, k_ = j_[keep], k_[keep]; d_ = np.hypot(*(XF[j_] - XD[k_]).T)
S2 = gpd.read_file('/mnt/project-files/fire-alert-scars/reference/v2_2026-10-16/firms_event_scars.geojson').to_crs(32643)
ip = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/ignition_points.csv', usecols=['event_id', 'fire_group'])
GU = S2.merge(ip, on='event_id').dissolve('fire_group').geometry
pairs = pd.DataFrame(dict(a=gF[j_], b=gD[k_])).drop_duplicates()
gap = [GU[a].distance(GU[b]) if (a in GU.index and b in GU.index) else np.nan for a, b in zip(pairs.a, pairs.b)]
pairs['joined'] = np.array(gap) <= 100
jm = pairs.set_index(['a', 'b']).joined
joined = jm.reindex(pd.MultiIndex.from_arrays([gF[j_], gD[k_]])).values.astype(bool)
print('pairs', len(pairs), 'joined share of pairs', round(pairs.joined.mean(), 3))
RB = [0, 500, 1000, 2000, 3000, 5000]; RL = ['0-0.5', '0.5-1', '1-2', '2-3', '3-5']; rb = np.digitize(d_, RB) - 1
def count(t):
    lag = t[j_] - tD[k_]; ok = (lag > 0) & (lag <= 1)
    out = np.zeros((2, 5))
    for jflag in (0, 1):
        m = ok & (joined == bool(jflag)); key = np.unique(np.c_[j_[m], rb[m]], axis=0)
        out[jflag] = np.bincount(key[:, 1], minlength=5)
    return out
idx = {y: np.where(yr == y)[0] for y in np.unique(yr)}
def perm():
    t = tF.copy()
    for y, ii in idx.items(): t[ii] = tF[rng.permutation(ii)]
    return t
o = count(tF); N = np.stack([count(perm()) for _ in range(NP)]); e = N.mean(0); p = ((N >= o).sum(0) + 1) / (NP + 1)
rows = [dict(scars=['separate (>100 m apart)', 'joined (<=100 m)'][f], ring_km=RL[r], observed=int(o[f, r]), expected=round(e[f, r], 1),
             ratio=round(o[f, r] / e[f, r], 2), excess=round(o[f, r] - e[f, r], 1), p=round(p[f, r], 3)) for f in (0, 1) for r in range(5)]
T = pd.DataFrame(rows); T.to_csv(OUT + 'knox_joined_vs_separate.csv', index=False); print(T.to_string())
