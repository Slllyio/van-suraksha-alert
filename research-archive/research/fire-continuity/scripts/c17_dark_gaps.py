"""Fires that go dark between VIIRS passes and come back: put out and restarted, or still burning too weakly to see?

Unit: a 'dark gap' = a VIIRS pass that saw the fire, then 1+ passes that did not, then a pass that saw it again
(a 'return'). Gaps with no return within the mask window (last alert + 36 h) are 'ends'.

Tests
 1. Where the fire comes back: distance from the returning dots to the fire's earlier dots, against the same
    distance for (a) back-to-back passes that both saw fire and (b) gaps hidden by cloud. If 'clear, no fire'
    really meant 'out', clear gaps should come back farther away (new ignitions) than cloud gaps.
 2. 30 m look inside the gap: Sentinel-2 / Landsat hot pixels near the fire during the dark period, against the
    same rate between two passes that both saw fire (fire known burning) and after the fire ended.
 3. Weak-fire physics: miss rate by day/night, view angle and the heat (FRP) of the last detection.
 4. Null: if misses were random coin flips on a fire that keeps burning, how long would dark runs be?
    Shuffle each fire's seen/missed passes within day and night and compare run lengths.
-> results/dark_gaps.json, results/dark_gaps.csv, figures/dark_gaps.png
"""
import json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
from scipy.ndimage import distance_transform_edt
import sys
sys.path.insert(0, '/mnt/project-files/research/fire-continuity/scripts')
import c0_lib as C

ROOT = '/mnt/project-files'
OUT = f'{ROOT}/research/fire-continuity'
R = f'{ROOT}/ratapani/fsi/scouting/code/squares_v2/tracking/results/'
rng = np.random.default_rng(0)

# ---------------- passes and their state ----------------
S = pd.read_csv(R + 'mask_fire_pass_summary.csv', parse_dates=['t_pass'])
A = pd.read_csv(f'{ROOT}/research/big-fires/results/fire_alerts.csv', parse_dates=['t'])
A = A[A.sat.str.startswith('viirs') & A.fire.isin(S.fire.unique())].copy()
A['sensor'] = A.sat.map({'viirs-snpp': 'S-NPP', 'viirs-jpss1': 'NOAA-20', 'viirs-noaa21': 'NOAA-21'})
S = S.sort_values(['fire', 't_pass']).reset_index(drop=True)
S['pid'] = np.arange(len(S))
# attach each alert to its pass (granule start <= t <= start + 7 min, same satellite, same fire)
M = A.merge(S[['fire', 'sensor', 't_pass', 'pid']], on=['fire', 'sensor'])
M = M[(M.t >= M.t_pass - pd.Timedelta('1min')) & (M.t <= M.t_pass + pd.Timedelta('7min'))]
M = M.sort_values('t').drop_duplicates(['latitude', 'longitude', 't'])
print('alerts matched to a mask pass', len(M), 'of', len(A))
seen = M.groupby('pid').size()
S['n_alert'] = S.pid.map(seen).fillna(0).astype(int)
S['frp_max'] = S.pid.map(M.groupby('pid').frp.max())
S['frp_sum'] = S.pid.map(M.groupby('pid').frp.sum())
S['hour'] = S.t_pass.dt.hour + S.t_pass.dt.minute / 60
S['day'] = S.hour.between(4, 12)          # VIIRS day passes ~06-09 UTC, night ~18-22 UTC
nf = S.n_front.clip(lower=1)
S['state'] = np.select([S.n_alert > 0,
                        (S.n_front > 0) & (S.n_clear / nf >= 0.8),
                        (S.n_front == 0) | ((S.n_cloud + S.n_noinfo + S.n_missing) / nf >= 0.5)],
                       ['fire', 'clear', 'blind'], 'partial')
print(S.state.value_counts().to_dict())

# ---------------- gaps ----------------
AX = {pid: g[['x', 'y']].values for pid, g in M.groupby('pid')}
gaps = []
for fire, g in S.groupby('fire', sort=False):
    st, pid, t = g.state.values, g.pid.values, g.t_pass.values
    fi = np.where(st == 'fire')[0]
    if len(fi) == 0:
        continue
    for k, i in enumerate(fi):
        j = fi[k + 1] if k + 1 < len(fi) else None
        mid = range(i + 1, (j if j is not None else len(st)))
        if j is not None and j == i + 1:
            # back-to-back seen passes: control pair
            gaps.append(dict(fire=fire, kind='pair', i=pid[i], j=pid[j], t0=t[i], t1=t[j], n_mid=0, n_clear=0, n_blind=0,
                             n_partial=0, n_night_clear=0, n_day_clear=0))
            continue
        sub = g.iloc[list(mid)]
        if j is None:  # ended: keep only passes within 36 h (the window)
            sub = sub[sub.t_pass <= t[i] + np.timedelta64(36, 'h')]
            if len(sub) == 0:
                continue
        gaps.append(dict(fire=fire, kind='return' if j is not None else 'end', i=pid[i], j=pid[j] if j is not None else -1,
                         t0=t[i], t1=t[j] if j is not None else sub.t_pass.max(), n_mid=len(sub),
                         n_clear=(sub.state == 'clear').sum(), n_blind=(sub.state == 'blind').sum(),
                         n_partial=(sub.state == 'partial').sum(),
                         n_night_clear=((sub.state == 'clear') & ~sub.day).sum(),
                         n_day_clear=((sub.state == 'clear') & sub.day).sum()))
G = pd.DataFrame(gaps)
G['hours'] = (G.t1 - G.t0) / np.timedelta64(1, 'h')
G['type'] = np.select([G.kind == 'pair', (G.n_clear == G.n_mid), (G.n_blind == G.n_mid)],
                      ['pair', 'clear', 'cloud'], 'mixed')
print(G.groupby(['kind', 'type']).size())

# return distance: nearest returning dot to any earlier dot of the same fire, and share of returning dots > 750 m away
FA = {f: g.sort_values('t') for f, g in M.groupby('fire')}
dmin, dfar, frp_ret, frp_pre, xr, yr = [], [], [], [], [], []
for r in G.itertuples():
    if r.kind == 'end':
        dmin.append(np.nan); dfar.append(np.nan); frp_ret.append(np.nan); xr.append(np.nan); yr.append(np.nan)
        frp_pre.append(S.frp_max.values[r.i]); continue
    fa = FA[r.fire]
    prev = fa[fa.t < pd.Timestamp(r.t1) - pd.Timedelta('1min')][['x', 'y']].values
    ret = AX[r.j]
    d = cKDTree(prev).query(ret)[0]
    dmin.append(d.min()); dfar.append((d > 750).mean())
    k = d.argmax(); xr.append(ret[k, 0]); yr.append(ret[k, 1])
    frp_ret.append(S.frp_max.values[r.j]); frp_pre.append(S.frp_max.values[r.i])
G['d_return'] = dmin; G['share_far'] = dfar; G['frp_ret'] = frp_ret; G['frp_pre'] = frp_pre
G['x_far'] = xr; G['y_far'] = yr
G['jump'] = G.d_return > 1000      # even the closest returning dot is > 1 km from every earlier dot

HB = [0, 3, 8, 14, 26, 50, 200]
G['hbin'] = pd.cut(G.hours, HB)
res = {}
T1 = (G[G.kind != 'end'].groupby(['hbin', 'type'], observed=True)
      .agg(n=('fire', 'size'), d_med=('d_return', 'median'), jump=('jump', 'mean'), far=('share_far', 'mean'))
      .round(3).reset_index())
T1['hbin'] = T1.hbin.astype(str)
print(T1.to_string())
res['test1_return_distance'] = T1.to_dict('records')


# matched comparison clear vs cloud gaps: same hours bin, bootstrap by fire
def boot_diff(df, col, a='clear', b='cloud', B=1000):
    df = df[df.type.isin([a, b])]
    fires = df.fire.unique()
    w = df.groupby('hbin', observed=True).size()

    def stat(d):
        out = []
        for h, gg in d.groupby('hbin', observed=True):
            ca, cb = gg[gg.type == a][col], gg[gg.type == b][col]
            if len(ca) >= 5 and len(cb) >= 5:
                out.append((ca.mean() - cb.mean(), len(gg)))
        return np.average([o[0] for o in out], weights=[o[1] for o in out]) if out else np.nan
    est = stat(df)
    idx = {f: df.index[df.fire == f] for f in fires}
    bs = []
    for _ in range(B):
        pick = rng.choice(fires, len(fires))
        bs.append(stat(df.loc[np.concatenate([idx[f] for f in pick])]))
    return dict(diff=round(float(est), 3), lo=round(float(np.nanpercentile(bs, 2.5)), 3),
                hi=round(float(np.nanpercentile(bs, 97.5)), 3))


RET = G[G.kind == 'return'].copy()
res['clear_minus_cloud_jump'] = boot_diff(RET, 'jump')
RET['logd'] = np.log10(RET.d_return + 50)
res['clear_minus_cloud_logdist'] = boot_diff(RET, 'logd')
print('clear-cloud jump', res['clear_minus_cloud_jump'], 'log10 dist', res['clear_minus_cloud_logdist'])

# return rate: after a clear vs a cloud first miss (does 'clear' predict 'out'?)
G2 = G[G.kind != 'pair'].copy()
G2['first'] = [S.state.values[i + 1] if i + 1 < len(S) and S.fire.values[i + 1] == f else None
               for i, f in zip(G2.i, G2.fire)]
res['return_rate_by_first_miss'] = (G2.groupby('first').apply(lambda d: pd.Series(dict(n=len(d), returned=(d.kind == 'return').mean())))
                                    .round(3).reset_index().to_dict('records'))
print(res['return_rate_by_first_miss'])

# ---------------- test 2: 30 m looks inside gaps ----------------
SC = pd.read_csv(f'{OUT}/results/s2ls_scenes.csv')
SC['t'] = pd.to_datetime(SC.t, utc=True, format='mixed').dt.tz_localize(None)
SC = SC[SC.cloud < 30].copy()
bb = np.array([json.loads(b) for b in SC.bbox])
SC['lon0'], SC['lat0'], SC['lon1'], SC['lat1'] = bb[:, 0], bb[:, 1], bb[:, 2], bb[:, 3]
AF = pd.read_csv(f'{ROOT}/fire-alert-scars/out/af/af_pixels_clean.csv')
from pyproj import Transformer
TR = Transformer.from_crs(4326, 32643, always_xy=True)
AF['x'], AF['y'] = TR.transform(AF.lon.values, AF.lat.values)
AFs = {s: g[['x', 'y']].values for s, g in AF.groupby('scene')}
AFt = {s: cKDTree(v) for s, v in AFs.items()}
fll = M.groupby('fire')[['longitude', 'latitude']].mean()


def look(r, t0, t1):
    """30 m scenes strictly inside (t0, t1) covering the fire: list of (scene, hot within 1 km of the fire's dots so far)."""
    lo, la = fll.loc[r.fire]
    sc = SC[(SC.t > t0) & (SC.t < t1) & (SC.lon0 < lo) & (SC.lon1 > lo) & (SC.lat0 < la) & (SC.lat1 > la)]
    out = []
    pts = FA[r.fire]
    pts = pts[pts.t <= pd.Timestamp(t1)][['x', 'y']].values
    for s in sc.scene:
        hot = bool(s in AFt and len(pts) and (AFt[s].query_ball_point(pts, 1000, return_length=True) > 0).any())
        out.append(hot)
    return out


rows = []
for r in G.itertuples():
    t0, t1 = pd.Timestamp(r.t0), pd.Timestamp(r.t1)
    if r.kind == 'end':
        t1 = t0 + pd.Timedelta('36h')
    for h in look(r, t0, t1):
        rows.append(dict(fire=r.fire, kind=r.kind, type=r.type, hours=r.hours, hot=h))
    if r.kind == 'end':   # long after the end: 3-10 days later (false-alarm floor)
        for h in look(r, t0 + pd.Timedelta('3D'), t0 + pd.Timedelta('10D')):
            rows.append(dict(fire=r.fire, kind='after_end_3_10d', type='-', hours=np.nan, hot=h))
L = pd.DataFrame(rows)
T2 = L.groupby(['kind', 'type']).agg(scenes=('hot', 'size'), fires=('fire', 'nunique'), hot_rate=('hot', 'mean')).round(3).reset_index()
print(T2.to_string())
res['test2_30m_looks'] = T2.to_dict('records')

# ---------------- test 3: who gets missed ----------------
# passes inside a fire's active period (between a seen pass and a later seen pass, <= 24 h apart)
P = S.copy()
P['prev_t'] = P.t_pass.where(P.state == 'fire').groupby(P.fire).ffill().groupby(P.fire).shift()
P['next_t'] = P.t_pass.where(P.state == 'fire').groupby(P.fire).bfill().groupby(P.fire).shift(-1)
P['prev_frp'] = P.frp_max.groupby(P.fire).ffill().groupby(P.fire).shift()
P['prev_n'] = P.n_alert.where(P.state == 'fire').groupby(P.fire).ffill().groupby(P.fire).shift()
act = P[(P.t_pass - P.prev_t <= pd.Timedelta('24h')) & (P.next_t - P.t_pass <= pd.Timedelta('24h')) & P.state.isin(['fire', 'clear'])].copy()
act['seen'] = act.state == 'fire'
act['vza_bin'] = pd.cut(act.vza_med, [0, 30, 50, 70])
act['frp_bin'] = pd.cut(act.prev_frp, [0, 2, 4, 8, 400])
T3 = {}
for c in ['day', 'vza_bin', 'frp_bin']:
    t = act.groupby(c, observed=True).seen.agg(['size', 'mean']).round(3)
    t.index = t.index.astype(str)
    T3[c] = t.reset_index().to_dict('records')
t = act.groupby(['day', 'frp_bin'], observed=True).seen.agg(['size', 'mean']).round(3).reset_index()
t['frp_bin'] = t.frp_bin.astype(str)
T3['day_x_frp'] = t.to_dict('records')
res['test3_seen_rate_while_alive'] = T3
print(json.dumps(T3, indent=0)[:2000])
res['frp_of_detections'] = dict(share_lt_2MW=round(float((M.frp < 2).mean()), 3), median=float(M.frp.median()),
                                day_median=float(M[M.daynight == 'D'].frp.median()), night_median=float(M[M.daynight == 'N'].frp.median()))
# FRP just before a gap vs before a back-to-back seen pass
res['frp_before'] = {k: round(float(G[G.kind == k].frp_pre.median()), 2) for k in ['pair', 'return', 'end']}
res['frp_after_return_vs_pair'] = {k: round(float(G[G.kind == k].frp_ret.median()), 2) for k in ['pair', 'return']}

# ---------------- test 4: null of random misses ----------------
# within each fire's alive span (first to last seen pass), shuffle seen/clear outcomes among day passes and among
# night passes; count dark runs of >= k clear passes
def runs(st):
    out, c = [], 0
    for s in st:
        if s == 'clear':
            c += 1
        else:
            if c:
                out.append(c)
            c = 0
    if c:
        out.append(c)
    return out


obs, sims = [], []
span = []
for f, g in S.groupby('fire'):
    fi = np.where(g.state.values == 'fire')[0]
    if len(fi) < 2:
        continue
    span.append(g.iloc[fi[0]:fi[-1] + 1])
SP = pd.concat(span)
SP = SP[SP.state.isin(['fire', 'clear'])]      # drop blind/partial passes: they neither see nor rule out
for g in [g for _, g in SP.groupby('fire')]:
    obs += runs(g.state.values)
for b in range(200):
    sm = []
    for f, g in SP.groupby('fire'):
        st = g.state.values.copy(); d = g.day.values
        inner = np.arange(1, len(st) - 1)   # keep first and last seen passes fixed
        for flag in (True, False):
            ix = inner[d[inner] == flag]
            st[ix] = rng.permutation(st[ix])
        sm += runs(st)
    sims.append(np.bincount(np.clip(sm, 0, 8), minlength=9))
obs_c = np.bincount(np.clip(obs, 0, 8), minlength=9)
sims = np.array(sims)
T4 = [dict(run_len=k if k < 8 else '8+', observed=int(obs_c[k]), random=round(float(sims[:, k].mean()), 1),
           lo=int(np.percentile(sims[:, k], 2.5)), hi=int(np.percentile(sims[:, k], 97.5))) for k in range(1, 9)]
print(pd.DataFrame(T4).to_string())
res['test4_null_runs'] = T4

# ---------------- humans: are far returns nearer roads/villages than the fire's own dots? ----------------
road_d = distance_transform_edt(~C.ROAD.astype(bool)) * 20.0


def droad(x, y):
    r, c = C.rc_of(np.asarray(x), np.asarray(y))
    ok = (r >= 0) & (c >= 0) & (r < road_d.shape[0]) & (c < road_d.shape[1])
    out = np.full(len(np.atleast_1d(x)), np.nan)
    out[ok] = road_d[r[ok], c[ok]]
    return out


J = RET[RET.jump & RET.type.isin(['clear', 'cloud', 'mixed'])]
NJ = RET[~RET.jump]
allpts = M[['x', 'y']].values
res['road_m'] = dict(far_return=float(np.nanmedian(droad(J.x_far, J.y_far))),
                     near_return=float(np.nanmedian(droad(NJ.x_far, NJ.y_far))),
                     all_dots=float(np.nanmedian(droad(allpts[:, 0], allpts[:, 1]))))
# hour of day of returns: jumps vs non-jumps (IST)
RET['ret_day'] = S.day.values[RET.j]
res['return_by_day_pass'] = dict(jump=round(float(RET[RET.jump].ret_day.mean()), 3), near=round(float(RET[~RET.jump].ret_day.mean()), 3))
print(res['road_m'], res['return_by_day_pass'])

# ---------------- shares ----------------
# the cloud-gap jump rate is the floor that unseen spread + placement error alone produce
fl = RET.groupby('type').jump.mean()
res['jump_rate_by_type'] = fl.round(3).to_dict()
res['counts'] = dict(fires=int(S.fire.nunique()), passes=int(len(S)), gaps=G.kind.value_counts().to_dict(),
                     return_types=RET.type.value_counts().to_dict())
G.drop(columns=['hbin']).to_csv(f'{OUT}/results/dark_gaps.csv', index=False)
json.dump(res, open(f'{OUT}/results/dark_gaps.json', 'w'), indent=1, default=str)
print(json.dumps(res['counts'], default=str))


# ---------------- add-on: share of dark time the fire was still alive at 30 m, with fire bootstrap ----------------
def alive_share(L, kind, typ, B=2000):
    pos, neg = L[L.kind == 'pair'], L[L.kind == 'after_end_3_10d']
    tst = L[(L.kind == kind) & (L.type.isin(typ))]

    def s(p, n, t):
        return (t.hot.mean() - n.hot.mean()) / (p.hot.mean() - n.hot.mean())

    def bf(d):
        f = d.fire.unique(); pick = rng.choice(f, len(f))
        return pd.concat([d[d.fire == x] for x in pick]) if len(f) < 300 else d.sample(len(d), replace=True, random_state=int(rng.integers(1e9)))
    bs = [s(bf(pos), neg.sample(len(neg), replace=True, random_state=b), bf(tst)) for b in range(B // 10)]
    return dict(n_scenes=len(tst), share=round(float(s(pos, neg, tst)), 2),
                lo=round(float(np.percentile(bs, 2.5)), 2), hi=round(float(np.percentile(bs, 97.5)), 2))


res['alive_share_30m'] = {'return_clear': alive_share(L, 'return', ['clear']),
                          'return_all': alive_share(L, 'return', ['clear', 'cloud', 'mixed']),
                          'end_all': alive_share(L, 'end', ['clear', 'cloud', 'mixed'])}
print(res['alive_share_30m'])
json.dump(res, open(f'{OUT}/results/dark_gaps.json', 'w'), indent=1, default=str)
