"""Step 4: pooled small-gap displacement. Every pair alone is noise; the mean over N pairs has error ~ sigma/sqrt(N).
Displacement d = (B centroid - A centroid) - sensor bias (o_B - o_A, per day/night, fitted on static sites).
Projected onto: (a) upslope, (b) ERA5 wind (Ratapani only), (c) later growth g = F - E (out of sample: built from
detections 2-48 h before A and 2-48 h after B, never A or B), (d) outward u = M - E.
Speed = mean projection / mean gap. 95% CIs: bootstrap over fire clusters (5 km cell x season); every test is repeated on
static industrial sites through the same code (the null; must give ~0).
Out: results/pooled_*.csv/json; scratch fires_small.parquet for later steps."""
import json, os
import numpy as np, pandas as pd
SC = os.environ.get('POOL_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_pool')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
rng = np.random.default_rng(2)
CLIP = 2000.0
R = pd.read_parquet(f'{SC}/ctx.parquet')
V = {'S-NPP', 'NOAA-20', 'NOAA-21'}
R['vv'] = R.sA.isin(V) & R.sB.isin(V)
R['gap_h'] = R.gap_min / 60
R['cl'] = R.season.astype(str) + '_' + (R.mx / 5000).round().astype(int).astype(str) + '_' + (R.my / 5000).round().astype(int).astype(str)
R.loc[R.typ == 2, 'cl'] = 's' + R.loc[R.typ == 2, 'site']
# ---------------- sensor offsets o_s (S-NPP = 0) per day/night and component, least squares on static VIIRS small gaps
S = R[(R.typ == 2) & R.vv & R.small]
off = {}
for dn in 'DN':
    g = S[S.dn == dn]
    X = np.c_[(g.sB == 'NOAA-20') * 1.0 - (g.sA == 'NOAA-20'), (g.sB == 'NOAA-21') * 1.0 - (g.sA == 'NOAA-21')]
    for c in ['dE', 'dN']:
        off[(dn, c)] = dict(zip(['NOAA-20', 'NOAA-21'], np.linalg.lstsq(X, g[c].clip(-CLIP, CLIP).values, rcond=None)[0]))
        off[(dn, c)]['S-NPP'] = 0.0
def bias(df, src=off):
    bE = np.array([src[(dn, 'dE')].get(b, 0) - src[(dn, 'dE')].get(a, 0) for a, b, dn in zip(df.sA, df.sB, df.dn)])
    bN = np.array([src[(dn, 'dN')].get(b, 0) - src[(dn, 'dN')].get(a, 0) for a, b, dn in zip(df.sA, df.sB, df.dn)])
    return bE, bN
# alternative offsets: fires' joint fit d = (o_B - o_A) + v_dn * gap  (motion vector v absorbs any mean drift)
Fs = R[(R.typ == 0) & R.vv & R.small]
offF = {}; drift = {}
for dn in 'DN':
    g = Fs[Fs.dn == dn]
    X = np.c_[(g.sB == 'NOAA-20') * 1.0 - (g.sA == 'NOAA-20'), (g.sB == 'NOAA-21') * 1.0 - (g.sA == 'NOAA-21'), g.gap_h]
    for c in ['dE', 'dN']:
        co = np.linalg.lstsq(X, g[c].clip(-CLIP, CLIP).values, rcond=None)[0]
        offF[(dn, c)] = {'NOAA-20': co[0], 'NOAA-21': co[1], 'S-NPP': 0.0}; drift[f'{dn} {c} m/h'] = round(co[2], 1)
res = dict(offsets_static={f'{k[0]} {k[1]}': {s: round(v, 1) for s, v in d.items()} for k, d in off.items()},
           offsets_fires_joint={f'{k[0]} {k[1]}': {s: round(v, 1) for s, v in d.items()} for k, d in offF.items()},
           fires_mean_drift_vector=drift)
# variance model per row (from p2): along-scan k=0.59, geoloc 180 m; along-track k=0.90, geoloc 132 m
R['var'] = (0.592 * (R.scanA ** 2 / R.nA + R.scanB ** 2 / R.nB) / 12 + 180 ** 2) + (0.899 * (R.trackA ** 2 / R.nA + R.trackB ** 2 / R.nB) / 12 + 132 ** 2)
R['w'] = 1 / R['var']
def unit(e, n):
    L = np.hypot(e, n); return e / L, n / L
def pooled(df, col, wcol=None, n=500):
    """mean of df[col] (clipped) with cluster bootstrap; returns (mean, lo, hi, N, clusters, naive_se, boot_se)"""
    df = df[np.isfinite(df[col])]
    if len(df) < 20: return dict(n=len(df))
    v = df[col].clip(-CLIP, CLIP).values; w = df[wcol].values if wcol else np.ones(len(df))
    cl = pd.factorize(df.cl)[0]; nc = cl.max() + 1
    sw = np.bincount(cl, w, nc); swv = np.bincount(cl, w * v, nc)
    m = swv.sum() / sw.sum(); bs = []
    for _ in range(n):
        k = rng.integers(0, nc, nc); bs.append(swv[k].sum() / sw[k].sum())
    naive = np.sqrt(np.average((v - m) ** 2, weights=w) * (w ** 2).sum() / w.sum() ** 2)
    return dict(mean=float(m), lo=float(np.quantile(bs, .025)), hi=float(np.quantile(bs, .975)), n=int(len(df)), clusters=int(nc),
                se_naive=float(naive), se_boot=float(np.std(bs)))
def prep(df, src=off):
    df = df.copy(); bE, bN = bias(df, src); df['month_'] = df.tA.dt.month
    df['cE'] = df.dE - bE; df['cN'] = df.dN - bN; df['cEw'] = df.dEw - bE; df['cNw'] = df.dNw - bN
    ue, un = unit(df.uE, df.uN); df['p_out'] = df.cE * ue + df.cN * un; df['p_out_w'] = df.cEw * ue + df.cNw * un
    df['p_out_raw'] = df.dE * ue + df.dN * un
    ge, gn = unit(df.gE, df.gN); df['p_grow'] = df.cE * ge + df.cN * gn; df['p_grow_raw'] = df.dE * ge + df.dN * gn
    az = np.radians(df.upaz); df['p_up'] = np.where(df.slope >= 2, df.cE * np.sin(az) + df.cN * np.cos(az), np.nan)
    df['p_up_raw'] = np.where(df.slope >= 2, df.dE * np.sin(az) + df.dN * np.cos(az), np.nan)
    we, wn = unit(df.wE, df.wN); ok = np.hypot(df.wE, df.wN) >= 1.0
    df['p_wind'] = np.where(ok, df.cE * we + df.cN * wn, np.nan); df['p_wind_raw'] = np.where(ok, df.dE * we + df.dN * wn, np.nan)
    # cross-wind / cross-growth components (should be ~0 by symmetry)
    df['p_grow_perp'] = -df.cE * gn + df.cN * ge
    df['p_out_perp'] = -df.cE * un + df.cN * ue
    # centred: remove the mean corrected displacement vector of the stratum (ordered pair x day/night x season x month);
    # kills any constant bias (incl. view-geometry effects) but also any real drift common to the whole stratum
    key = df.sA + df.sB + df.dn + df.season.astype(str) + df.month_.astype(str)
    mE = df.cE.clip(-CLIP, CLIP).groupby(key).transform('mean'); mN = df.cN.clip(-CLIP, CLIP).groupby(key).transform('mean')
    df['p_up_c'] = np.where(df.slope >= 2, (df.cE - mE) * np.sin(az) + (df.cN - mN) * np.cos(az), np.nan)
    df['p_wind_c'] = np.where(ok, (df.cE - mE) * we + (df.cN - mN) * wn, np.nan)
    # random-direction null: d projected on the later-growth direction of a random other pair of the same stratum
    g2 = pd.DataFrame(dict(k=key.values, a=ge.values, b=gn.values)).groupby('k').transform(lambda v: v.sample(frac=1, random_state=0).values)
    df['p_grow_shuf'] = df.cE * g2['a'].values + df.cN * g2['b'].values
    for c in ['p_up_c', 'p_wind_c', 'p_grow_shuf', 'p_out', 'p_out_w', 'p_grow', 'p_up', 'p_wind', 'p_out_raw', 'p_grow_raw', 'p_up_raw', 'p_wind_raw', 'p_grow_perp', 'p_out_perp']:
        df['v_' + c] = df[c] / df.gap_h        # per-pair speed (m/h); pooled speed uses mean(p)/mean(gap) instead
    return df
F = prep(R[(R.typ == 0) & R.vv & R.small & (R.nE > 0)])
N0 = prep(R[(R.typ == 2) & R.vv & R.small & (R.nE > 0)])
F.to_parquet(f'{SC}/fires_small.parquet'); N0.to_parquet(f'{SC}/static_small.parquet')
res['counts'] = dict(fire_pairs_small_vv_all=int(((R.typ == 0) & R.vv & R.small).sum()),
                     with_earlier_detections=len(F), with_later=int(F.nF.gt(0).sum()), with_wind=int(F.p_wind.notna().sum()),
                     static_pairs_with_earlier=len(N0), clusters=int(F.cl.nunique()),
                     by_pair={f'{a}>{b} {c}': int(v) for (a, b, c), v in F.groupby(['sA', 'sB', 'dn']).size().items()},
                     median_gap_min=float(F.gap_min.median()))
def speed_row(df, col, label, wcol=None):
    r = pooled(df, col, wcol)
    if 'mean' not in r: return dict(test=label, n=r['n'])
    gh = df.loc[np.isfinite(df[col]), 'gap_h'].mean()
    return dict(test=label, n=r['n'], clusters=r['clusters'], mean_m=round(r['mean'], 1), ci_m=f"{r['lo']:.1f} to {r['hi']:.1f}",
                speed_m_h=round(r['mean'] / gh, 1), ci_m_h=f"{r['lo'] / gh:.1f} to {r['hi'] / gh:.1f}", gap_min=round(gh * 60, 1),
                se_boot=round(r['se_boot'], 2), design_effect=round((r['se_boot'] / r['se_naive']) ** 2, 2))
rows = []
for nm, df in [('fires', F), ('static null', N0)]:
    for dn in ['D', 'N']:
        d = df[df.dn == dn]
        for col, lab in [('p_out', 'outward (away from earlier detections)'), ('p_out_w', 'outward, FRP-weighted centres'),
                         ('p_out_raw', 'outward, no bias correction'), ('p_out_perp', 'outward, perpendicular part (symmetry check)'),
                         ('p_grow', 'towards later growth (out of sample)'), ('p_grow_raw', 'towards later growth, no bias corr.'),
                         ('p_grow_perp', 'later growth, perpendicular part'),
                         ('p_grow_shuf', 'NULL: later-growth direction of a random other pair'),
                         ('p_up', 'upslope (slope >= 2 deg)'), ('p_up_raw', 'upslope, no bias correction'), ('p_up_c', 'upslope, stratum-centred'),
                         ('p_wind', 'downwind (ERA5, Ratapani)'), ('p_wind_c', 'downwind, stratum-centred')]:
            r = speed_row(d, col, lab); r.update(set=nm, dn=dn); rows.append(r)
            if col == 'p_out':
                r = speed_row(d, col, lab + ', inverse-variance weights', 'w'); r.update(set=nm, dn=dn); rows.append(r)
T = pd.DataFrame(rows); T.to_csv(f'{OUT}/pooled_main.csv', index=False)
pd.set_option('display.width', 250); print(T.to_string())
json.dump(res, open(f'{OUT}/pooled_summary.json', 'w'), indent=1, default=float)
