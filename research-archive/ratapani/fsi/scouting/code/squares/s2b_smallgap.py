"""Experiment 2b: do small-gap pairs (two passes of one fire by different satellites < 2 h apart) carry spread signal
beyond the no-movement noise of s2a?  Signals: (a) new pixels in the later look outside every footprint of the earlier,
(b) change in burning-pixel area (union of footprints, so overlapping near-duplicate pixels count once), (c) FRP change, (d) FRP-weighted centre shift (and plain centre shift).
Targets: the next VIIRS look 6-30 h later: direction of new burning (big-fires definition: detections > 400 m from
everything seen so far; bearing from the centre of everything so far) and amount (new detections; new footprint ha).
Null for (a)-(d): the same statistics on static industrial hot sources (FIRMS type 2, all MP), which do not move.
"""
import glob, json, os
import numpy as np, pandas as pd, pyproj, shapely
from shapely.ops import unary_union
from scipy.stats import spearmanr
from s_lib import *
rng = np.random.default_rng(0)
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform
def pass_stats(d):
    w = d.frp.clip(lower=.01).values
    return dict(t=d.t.min(), sensor=d.sensor.iloc[0], kind=d.kind.iloc[0], n=len(d), x=d.x.mean(), y=d.y.mean(),
                xw=np.average(d.x, weights=w), yw=np.average(d.y, weights=w), frp=d.frp.sum(),
                area=unary_union([poly(r) for r in d.itertuples()]).area / 1e4,   # union: overlapping (duplicate) pixels count once
                pix=np.sqrt((d.scan_m * d.track_m).mean()), heading=d.heading.iloc[0])
def pair_feats(da, db, A, B):
    ins = foot_dist(db.x.values, db.y.values, da).min(1) <= 0     # later pixels inside an earlier footprint
    newb = db[~ins]
    f = dict(gap_min=(B['t'] - A['t']).total_seconds() / 60, n0=A['n'], n1=B['n'], pix=(A['pix'] + B['pix']) / 2,
             sx=B['x'] - A['x'], sy=B['y'] - A['y'], swx=B['xw'] - A['xw'], swy=B['yw'] - A['yw'],
             n_new=len(newb), dlogarea=np.log(B['area'] / A['area']), dlogfrp=np.log(max(B['frp'], .05) / max(A['frp'], .05)))
    f['shift'] = np.hypot(f['sx'], f['sy']); f['shift_w'] = np.hypot(f['swx'], f['swy'])
    if len(newb): f['nbx'], f['nby'] = newb.x.mean() - A['x'], newb.y.mean() - A['y']
    return f
# ---------- null: static sources (MP archive, type 2), consecutive looks by different VIIRS satellites < 2 h
fn = f'{SC}/static_pairs_feats.parquet'
if not os.path.exists(fn):
    rows = []
    for f in sorted(glob.glob(f'{ROOT}/fire-alert-scars/alerts_mp/viirs-*.csv')):
        a = pd.read_csv(f); a = a[a.type == 2].copy(); a['sensor'] = os.path.basename(f).split('_')[0]; rows.append(a)
    S = pd.concat(rows, ignore_index=True)
    S['t'] = pd.to_datetime(S.acq_date) + pd.to_timedelta(S.acq_time.astype(int) // 100, 'h') + pd.to_timedelta(S.acq_time.astype(int) % 100, 'min')
    S['x'], S['y'] = tp(S.longitude.values, S.latitude.values); S['scan_m'] = S.scan * 1000; S['track_m'] = S.track * 1000
    S['heading'] = np.where(S.daynight == 'D', 347.0, 193.0); S['kind'] = 'viirs'
    S['site'] = (np.round(S.x / 3000)).astype(int).astype(str) + '_' + (np.round(S.y / 3000)).astype(int).astype(str)
    S = S.sort_values(['sensor', 't']); S['pass_id'] = S.sensor + ((S.groupby('sensor').t.diff().dt.total_seconds().fillna(1e9) > 900).cumsum()).astype(str)
    cnt = S.groupby('site').pass_id.nunique(); S = S[S.site.isin(cnt[cnt >= 20].index)]
    out = []
    for s, g in S.groupby('site'):
        ps = {k: (pass_stats(d), d) for k, d in g.groupby('pass_id')}
        order = sorted(ps, key=lambda k: ps[k][0]['t'])
        for i in range(len(order) - 1):
            A, da = ps[order[i]]; B, db = ps[order[i + 1]]
            if A['sensor'] == B['sensor'] or (B['t'] - A['t']).total_seconds() > 7200: continue
            out.append(dict(site=s, **pair_feats(da, db, A, B)))
    pd.DataFrame(out).to_parquet(fn)
N = pd.read_parquet(fn)
N['nmin'] = N[['n0', 'n1']].min(1)
# ---------- fires
D = load_det(); D = D[(D.fire >= 0) & (D.type.fillna(0) != 2)]
rows = []
for fire, g in D.groupby('fire'):
    passes = {k: (pass_stats(d), d) for k, d in g.groupby('pass_id')}
    order = sorted(passes, key=lambda k: passes[k][0]['t'])
    V = g[g.kind == 'viirs']
    for i in range(len(order) - 1):
        A, da = passes[order[i]]; B, db = passes[order[i + 1]]
        if A['sensor'] == B['sensor'] or (B['t'] - A['t']).total_seconds() > 7200: continue
        f = dict(fire=fire, s0=A['sensor'], s1=B['sensor'], vv=(A['kind'] == 'viirs') & (B['kind'] == 'viirs'), t=B['t'], **pair_feats(da, db, A, B))
        sofar = V[V.t <= B['t']]
        nxt = V[(V.t >= B['t'] + pd.Timedelta(hours=6)) & (V.t <= B['t'] + pd.Timedelta(hours=30))]
        if len(sofar) and len(nxt):
            nxt = nxt[nxt.pass_id == nxt.sort_values('t').pass_id.iloc[0]]
            dmin = np.hypot(nxt.x.values[:, None] - sofar.x.values[None], nxt.y.values[:, None] - sofar.y.values[None]).min(1)
            new = nxt[dmin > 400]
            f['next_gap_h'] = (nxt.t.min() - B['t']).total_seconds() / 3600; f['next_n'] = len(nxt); f['grow_n'] = len(new)
            f['sofar_n'] = len(sofar); f['sofar_frp'] = sofar.frp.sum()
            U = unary_union([poly(r) for r in sofar.itertuples()])
            f['grow_ha'] = unary_union([poly(r) for r in nxt.itertuples()]).difference(U).area / 1e4
            if len(new):
                f['gx'], f['gy'] = new.x.mean() - sofar.x.mean(), new.y.mean() - sofar.y.mean()
        # previous growth direction (persistence baseline): new burning at A vs everything before A - 6 h
        before = V[V.t < A['t'] - pd.Timedelta(hours=6)]; recent = V[(V.t >= A['t'] - pd.Timedelta(hours=30)) & (V.t <= B['t'])]
        if len(before) and len(recent):
            dm = np.hypot(recent.x.values[:, None] - before.x.values[None], recent.y.values[:, None] - before.y.values[None]).min(1)
            nr = recent[dm > 400]
            if len(nr): f['px'], f['py'] = nr.x.mean() - before.x.mean(), nr.y.mean() - before.y.mean()
        rows.append(f)
P = pd.DataFrame(rows); P.to_csv(f'{OUT}/e2_small_gap_pairs.csv', index=False)
P['nmin'] = P[['n0', 'n1']].min(1)
# noise thresholds (95th percentile of the static null) matched on pixel size and pixel count
def thr(col, r, q=.95):
    m = N[(np.abs(N.pix - r.pix) < 75) & (np.minimum(N.nmin, 4) == min(r.nmin, 4))]
    if len(m) < 30: m = N[np.abs(N.pix - r.pix) < 150]
    return np.quantile(np.abs(m[col]), q)
VV = P[P.vv].copy()
for col in ['shift', 'shift_w', 'dlogarea', 'dlogfrp']:
    VV['thr_' + col] = [thr(col, r) for r in VV.itertuples()]
    VV['sig_' + col] = np.abs(VV[col]) > VV['thr_' + col]
null_new = {k: float((N[np.minimum(N.nmin, 4) == k].n_new > 0).mean()) for k in [1, 2, 3, 4]}
VV['p_new_null'] = VV.nmin.clip(upper=4).map(null_new); VV['sig_new'] = VV.n_new > 0
def cosang(ax, ay, bx, by):
    return (ax * bx + ay * by) / (np.hypot(ax, ay) * np.hypot(bx, by) + 1e-9)
def agree(df, ax, ay, n=1000):
    g = df.dropna(subset=['gx', ax]); c = cosang(g[ax], g[ay], g.gx, g.gy)
    if len(g) < 10: return dict(n=len(g))
    fires = g.fire.values; uf = np.unique(fires); bs = []
    for _ in range(n):
        s = rng.choice(uf, len(uf)); k = np.concatenate([np.where(fires == u)[0] for u in s]); bs.append((c.values[k] > 0).mean())
    return dict(n=len(g), same_way_pct=round(100 * (c > 0).mean(), 1), ci95=[round(100 * np.quantile(bs, .025), 1), round(100 * np.quantile(bs, .975), 1)],
                mean_cos=round(c.mean(), 3))
res = {}
res['null_static'] = dict(pairs=len(N), sites=int(N.site.nunique()), shift_p50=round(N['shift'].median()), shift_p95=round(N['shift'].quantile(.95)),
                         shift_w_p95=round(N.shift_w.quantile(.95)),
                         shift_p95_by_min_pixels={k: round(N[np.minimum(N.nmin, 4) == k]['shift'].quantile(.95)) for k in [1, 2, 3, 4]},
                         shift_p50_by_min_pixels={k: round(N[np.minimum(N.nmin, 4) == k]['shift'].median()) for k in [1, 2, 3, 4]},
                         n_by_min_pixels={k: int((np.minimum(N.nmin, 4) == k).sum()) for k in [1, 2, 3, 4]},
                         dlogarea_p95=round(N.dlogarea.abs().quantile(.95), 2), dlogfrp_p95=round(N.dlogfrp.abs().quantile(.95), 2),
                         share_with_new_pixel_by_min_pixels={k: round(v, 3) for k, v in null_new.items()})
res['fires_pairs'] = dict(all=len(P), viirs_viirs=len(VV), with_modis=int((~P.vv).sum()), with_next_look=int(VV.next_n.notna().sum()),
                         with_next_growth_direction=int(VV.gx.notna().sum()), median_gap_min=float(VV.gap_min.median()),
                         fire_shift_p50=round(VV['shift'].median()), fire_shift_p95=round(VV['shift'].quantile(.95)),
                         median_pixels_per_look=float(VV[['n0', 'n1']].stack().median()))
res['share_above_noise'] = {c: round(float(VV['sig_' + c].mean()), 3) for c in ['shift', 'shift_w', 'dlogarea', 'dlogfrp']}
res['share_above_noise']['new_pixel'] = round(float(VV.sig_new.mean()), 3); res['share_above_noise']['new_pixel_null_expected'] = round(float(VV.p_new_null.mean()), 3)
res['share_above_noise']['note'] = 'noise = 95th pct of static sources, so 0.05 is expected with no signal'
# direction tests
VV['nb_ok'] = VV.nbx.notna() if 'nbx' in VV else False
dirs = {}
dirs['plain_shift_all'] = agree(VV, 'sx', 'sy'); dirs['frp_shift_all'] = agree(VV, 'swx', 'swy')
dirs['plain_shift_above_noise'] = agree(VV[VV.sig_shift], 'sx', 'sy'); dirs['frp_shift_above_noise'] = agree(VV[VV.sig_shift_w], 'swx', 'swy')
dirs['new_pixels_bearing'] = agree(VV[VV.n_new > 0], 'nbx', 'nby')
dirs['previous_growth_direction (persistence)'] = agree(VV, 'px', 'py')
both = VV.dropna(subset=['px', 'gx']).copy()
for w in [0.5, 1.0]:
    u = np.hypot(both.px, both.py) + 1e-9; s = np.hypot(both.swx, both.swy) + 1e-9
    both[f'cx{w}'] = both.px / u + w * both.sig_shift_w * both.swx / s; both[f'cy{w}'] = both.py / u + w * both.sig_shift_w * both.swy / s
    dirs[f'persistence + {w} x significant FRP shift'] = agree(both, f'cx{w}', f'cy{w}')
dirs['persistence, same pairs'] = agree(both, 'px', 'py')
nmd = MODP = P[~P.vv]
dirs['MODIS-VIIRS pairs plain shift'] = agree(P[~P.vv], 'sx', 'sy')
res['direction_vs_next_growth'] = dirs
# amount tests: partial Spearman with size so far
G = VV.dropna(subset=['grow_n']).copy()
G['l_sofar'] = np.log(G.sofar_n)
from scipy.stats import rankdata
def partial(a, b, c):
    ra, rb, rc = rankdata(a), rankdata(b), rankdata(c)
    ea = ra - np.polyval(np.polyfit(rc, ra, 1), rc); eb = rb - np.polyval(np.polyfit(rc, rb, 1), rc)
    return float(np.corrcoef(ea, eb)[0, 1])
amt = {}
for c in ['n_new', 'dlogarea', 'dlogfrp', 'shift', 'shift_w']:
    rs = []
    for _ in range(300):
        k = rng.choice(len(G), len(G)); rs.append(partial(G[c].values[k], G.grow_ha.values[k], G.l_sofar.values[k]))
    amt[c] = dict(spearman_vs_next_new_ha=round(spearmanr(G[c], G.grow_ha)[0], 3), partial_given_size=round(partial(G[c], G.grow_ha, G.l_sofar), 3),
                  partial_ci95=[round(np.quantile(rs, .025), 3), round(np.quantile(rs, .975), 3)])
res['amount_vs_next_growth'] = dict(n=len(G), **amt)
# held-out-season model: does adding the small-gap signals predict next-look growth (ha) / any growth?
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
G['season'] = pd.to_datetime(G.t).dt.year; G['grew'] = (G.grow_n > 0).astype(int); G['night'] = (pd.to_datetime(G.t).dt.hour > 12).astype(int)
base = ['l_sofar', 'night']; G['lfrp'] = np.log1p(G.sofar_frp); base += ['lfrp']; full = base + ['n_new', 'dlogarea', 'dlogfrp']
pr = {'base': np.zeros(len(G)), 'full': np.zeros(len(G))}
for s in G.season.unique():
    tr, te = G.season != s, G.season == s
    for nm, cols in [('base', base), ('full', full)]:
        m = LogisticRegression(max_iter=1000).fit(G.loc[tr, cols], G.loc[tr, 'grew']); pr[nm][te.values] = m.predict_proba(G.loc[te, cols])[:, 1]
res['any_growth_next_look_heldout_season_auc'] = dict(n=len(G), grew_share=round(G.grew.mean(), 3), base=round(roc_auc_score(G.grew, pr['base']), 3),
                                                     plus_small_gap=round(roc_auc_score(G.grew, pr['full']), 3))
# minimum detectable speed: noise p95 / gap (static null, by pixel count)
gap_h = VV.gap_min.median() / 60
res['min_detectable_speed_m_per_h'] = {f'min pixels {k}': round(N[np.minimum(N.nmin, 4) == k]['shift'].quantile(.95) / gap_h) for k in [1, 2, 3, 4]}
res['min_detectable_speed_m_per_h']['gap_h_used'] = round(gap_h, 2)
res['min_detectable_speed_m_per_h']['frp_weighted_all'] = round(N.shift_w.quantile(.95) / gap_h)
json.dump(res, open(f'{OUT}/e2_summary.json', 'w'), indent=1, default=float); print(json.dumps(res, indent=1, default=float))
