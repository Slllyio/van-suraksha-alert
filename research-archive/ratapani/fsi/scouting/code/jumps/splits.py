"""Splits of the near-repeat excess (new fire 0-2 km from another fire's detection, 0-1 day after it):
far-distance control, child hour of ignition, night first detection, downwind (ERA5-Land), month, beat, scar adjacency.
Null as in knox.py (times shuffled within season); expected counts carry the shuffled time's hour/month/wind."""
import pandas as pd, numpy as np, json, glob
from scipy.spatial import cKDTree
import geopandas as gpd
OUT = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r13_jump_code/'
NP = 299; rng = np.random.default_rng(7); H = 86400.0
F = pd.read_parquet(OUT + 'ign.parquet').reset_index(drop=True)
D = pd.read_parquet(OUT + 'det.parquet').reset_index(drop=True)
tF = F.t.values.astype('datetime64[s]').astype(np.int64) / H; tD = D.t.values.astype('datetime64[s]').astype(np.int64) / H
yr = F.yr.values; gF = F.fire_group.values; gD = D.fire_group.values
XF = F[['x', 'y']].values; XD = D[['x', 'y']].values
idx = {y: np.where(yr == y)[0] for y in np.unique(yr)}
def perm():
    t = tF.copy()
    for y, ii in idx.items(): t[ii] = tF[rng.permutation(ii)]
    return t
PERMS = [perm() for _ in range(NP)]
R = {}
# ---- 1. far-distance control for the Knox ratio at lag 0-1 day (new fire after other-fire detection)
nb = cKDTree(XD).query_ball_point(XF, 20000)
j_ = np.concatenate([np.full(len(v), i) for i, v in enumerate(nb)]); k_ = np.concatenate([np.array(v, int) for v in nb])
keep = gF[j_] != gD[k_]; j_, k_ = j_[keep], k_[keep]; d_ = np.hypot(*(XF[j_] - XD[k_]).T)
DB = [0, 500, 1000, 2000, 3000, 5000, 10000, 20000]
def cnt(t, lo=0, hi=1):
    lag = t[j_] - tD[k_]; ok = (lag > lo) & (lag <= hi)
    db = np.digitize(d_[ok], DB) - 1; key = np.unique(np.c_[j_[ok], db], axis=0)
    return np.bincount(key[:, 1], minlength=len(DB) - 1)
far = []
for lo, hi, lab in [(0, 0.25, '0-6h'), (0.25, 0.5, '6-12h'), (0.5, 1, '12-24h'), (1, 2, '1-2d'), (2, 3, '2-3d')]:
    o = cnt(tF, lo, hi); e = np.mean([cnt(t, lo, hi) for t in PERMS], 0)
    for i in range(len(DB) - 1): far.append(dict(lag=lab, dist_km=f'{DB[i]/1000:g}-{DB[i+1]/1000:g}', observed=int(o[i]), expected=round(e[i], 1), ratio=round(o[i] / e[i], 2)))
far = pd.DataFrame(far); far.to_csv(OUT + 'ratio_by_distance_lag.csv', index=False); print(far.pivot(index='dist_km', columns='lag', values='ratio').loc[[f'{DB[i]/1000:g}-{DB[i+1]/1000:g}' for i in range(len(DB)-1)]])
# ---- children: nearest other-fire detection within 0.5-2 km... define per time vector
def children(t, dlo=500, dhi=2000, lo=0, hi=1):
    lag = t[j_] - tD[k_]; ok = (lag > lo) & (lag <= hi) & (d_ >= dlo) & (d_ < dhi)
    P = pd.DataFrame(dict(j=j_[ok], k=k_[ok], d=d_[ok], lag=lag[ok])).sort_values('lag').groupby('j').first()  # most recent parent detection
    return P
# ERA5-Land wind
W = []
for f in sorted(glob.glob('/mnt/project-files/ratapani/ee/era5/era5land_hourly_*.csv')):
    W.append(pd.read_csv(f, usecols=['longitude', 'latitude', 'u_component_of_wind_10m', 'v_component_of_wind_10m', 'datetime_utc', 'point_id']))
W = pd.concat(W); W['h'] = (pd.to_datetime(W.datetime_utc).values.astype('datetime64[h]').astype(np.int64))
pts = W.drop_duplicates('point_id').set_index('point_id')[['longitude', 'latitude']]
from pyproj import Transformer
px, py = Transformer.from_crs(4326, 32643, always_xy=True).transform(pts.longitude.values, pts.latitude.values)
ptree = cKDTree(np.c_[px, py]); pid = pts.index.values
UV = {}
Wp = W.pivot_table(index='h', columns='point_id', values=['u_component_of_wind_10m', 'v_component_of_wind_10m'])
hidx = Wp.index.values; Uarr = Wp['u_component_of_wind_10m'].values; Varr = Wp['v_component_of_wind_10m'].values; cols = list(Wp['u_component_of_wind_10m'].columns)
def wind(x, y, t_days_ist, back_h=6):
    """mean u,v over back_h hours before t at nearest ERA5-Land point"""
    p = pid[ptree.query(np.c_[x, y])[1]]; c = np.array([cols.index(q) for q in p])
    h = np.floor(t_days_ist * 24 - 5.5).astype(np.int64)
    u = np.zeros(len(x)); v = np.zeros(len(x)); n = np.zeros(len(x))
    for b in range(back_h):
        r = np.searchsorted(hidx, h - b); r = np.clip(r, 0, len(hidx) - 1); ok = hidx[r] == h - b
        u[ok] += Uarr[r[ok], c[ok]]; v[ok] += Varr[r[ok], c[ok]]; n[ok] += 1
    u = np.where(n > 0, u / np.maximum(n, 1), np.nan); v = np.where(n > 0, v / np.maximum(n, 1), np.nan)
    return u, v
def describe(t, P):
    j = P.index.values; k = P.k.values
    x0, y0 = XD[k].T; x1, y1 = XF[j].T
    brg = np.degrees(np.arctan2(x1 - x0, y1 - y0)) % 360            # parent->child bearing
    u, v = wind((x0 + x1) / 2, (y0 + y1) / 2, t[j]); wto = np.degrees(np.arctan2(u, v)) % 360; ws = np.hypot(u, v)
    ang = np.abs((brg - wto + 180) % 360 - 180)
    hr = ((t[j] + 0) % 1) * 24                                     # IST hour (t in IST days)
    phr = ((tD[k]) % 1) * 24
    mon = pd.to_datetime(t[j] * H, unit='s').month
    return pd.DataFrame(dict(j=j, d=P.d.values, lag_h=P.lag.values * 24, hr=hr, parent_hr=phr, ang=ang, ws=ws, mon=mon,
                             beat=F.beat_uid.values[j], div=F.division.values[j]))
obs = describe(tF, children(tF)); nulls = [describe(t, children(t)) for t in PERMS]
def split(col, bins=None, labels=None, name=None):
    def lab(df):
        return pd.cut(df[col], bins, labels=labels, right=False) if bins is not None else df[col]
    o = lab(obs).value_counts().sort_index(); e = pd.concat([lab(n).value_counts() for n in nulls], axis=1).fillna(0).mean(1)
    T = pd.DataFrame(dict(observed=o, expected=e)).fillna(0); T['excess'] = T.observed - T.expected
    T['share_of_excess'] = T.excess / T.excess.sum(); T['ratio'] = T.observed / T.expected
    T['excess_share_of_obs'] = T.excess / T.observed
    print('\n==', name or col); print(T.round(2).to_string()); return T
S = {}
S['hour'] = split('hr', [0, 6, 9, 12, 15, 18, 24], ['00-06', '06-09', '09-12', '12-15', '15-18', '18-24'], 'child ignition hour IST (posterior median)')
S['lag'] = split('lag_h', [0, 3, 6, 12, 18, 24], ['0-3h', '3-6h', '6-12h', '12-18h', '18-24h'], 'hours since most recent parent detection')
S['parent_hr'] = split('parent_hr', [0, 6, 12, 18, 24], ['00-06', '06-12', '12-18', '18-24'], 'parent detection hour IST')
S['ang'] = split('ang', [0, 45, 90, 135, 181], ['downwind<45', '45-90', '90-135', 'upwind>135'], 'angle between parent->child and wind (6h mean before child)')
S['mon'] = split('mon', name='month of child')
S['dist'] = split('d', [500, 1000, 1500, 2000], ['0.5-1', '1-1.5', '1.5-2'], 'distance km')
S['div'] = split('div', name='division')
bt = split('beat', name='beat')
for k, v in S.items(): v.to_csv(OUT + f'split_{k}.csv')
bt.sort_values('excess', ascending=False).to_csv(OUT + 'split_beat.csv')
# strict spotting-compatible: daytime child ignition 10-18, parent detected <=6h before, downwind <45, wind >=2 m/s
def strict(df): return ((df.hr >= 10) & (df.hr < 18) & (df.lag_h <= 6) & (df.ang < 45)).sum()
R['strict_spot_obs'] = int(strict(obs)); R['strict_spot_exp'] = float(np.mean([strict(n) for n in nulls]))
R['children_obs'] = len(obs); R['children_exp'] = float(np.mean([len(n) for n in nulls]))
# scar adjacency of real children to parent's v2 scar
S2 = gpd.read_file('/mnt/project-files/fire-alert-scars/reference/v2_2026-10-16/firms_event_scars.geojson').to_crs(32643)
ip = pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/ignition_points.csv', usecols=['event_id', 'fire_group'])
S2 = S2.merge(ip, on='event_id', how='left'); GU = S2.dissolve('fire_group').geometry
Pc = children(tF); pg = gD[Pc.k.values]; cg = gF[Pc.index.values]
from shapely.geometry import Point
dist_to_parent_scar = np.array([GU[p].distance(Point(*XF[j])) if p in GU.index else np.nan for j, p in zip(Pc.index.values, pg)])
scar_touch = np.array([GU[p].distance(GU[c]) if (p in GU.index and c in GU.index) else np.nan for p, c in zip(pg, cg)])
R['child_ign_to_parent_scar_m_quantiles'] = np.nanpercentile(dist_to_parent_scar, [10, 25, 50, 75, 90]).round(0).tolist()
R['share_child_ign_inside_or_within100m_parent_scar'] = float(np.nanmean(dist_to_parent_scar <= 100))
R['share_child_scar_touches_parent_scar'] = float(np.nanmean(scar_touch <= 0))
R['share_child_scar_within100m_parent_scar'] = float(np.nanmean(scar_touch <= 100))
# same for null pairs (a random 'child' at the same spot but shuffled time): scars are fixed so compare to children at 2-5 km lag 2-3 d
Pf = children(tF, 500, 2000, 3, 10); pg2 = gD[Pf.k.values]; cg2 = gF[Pf.index.values]
st2 = np.array([GU[p].distance(GU[c]) if (p in GU.index and c in GU.index) else np.nan for p, c in zip(pg2, cg2)])
R['control_lag3-10d_share_scar_touch'] = float(np.nanmean(st2 <= 0)); R['control_lag3-10d_share_within100m'] = float(np.nanmean(st2 <= 100))
obs.assign(dist_to_parent_scar_m=dist_to_parent_scar, scar_gap_m=scar_touch).to_csv(OUT + 'children_0.5-2km_0-1d.csv', index=False)
json.dump(R, open(OUT + 'splits_summary.json', 'w'), indent=1); print(json.dumps(R, indent=1))
