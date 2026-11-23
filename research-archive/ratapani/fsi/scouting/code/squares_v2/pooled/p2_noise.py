"""Step 2: the displacement error model from things that cannot move (FIRMS type 2 static industrial sources, all MP,
2018-2026), for every ordered sensor pair, day/night, pixel count, pixel size (view angle), side of nadir and year.
d = (later look centroid) - (earlier look centroid), east/north metres; also turned into along-scan / along-track.
1. bias vector per ordered pair x day/night (mean, bootstrap by site), and per-sensor offsets by least squares;
2. regression of the bias on side x pixel size, year;
3. covariance: along-scan / along-track spread vs pixel size and count (model var = k * (s_A^2/n_A + s_B^2/n_B) + g^2);
4. cross-check: fires' own both-order estimate of the offsets ((A->B) - (B->A))/2 removes real motion.
Out: results/noise_*.csv/json, scratch bias table."""
import json, os
import numpy as np, pandas as pd
SC = os.environ.get('POOL_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_pool')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results'); os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(1)
R = pd.read_parquet(f'{SC}/pairs.parquet')
V = {'S-NPP', 'NOAA-20', 'NOAA-21'}
R['vv'] = R.sA.isin(V) & R.sB.isin(V)
R['small'] = (R.gap_min <= 120) & (R.sA != R.sB)
R['pair'] = R.sA + '>' + R.sB
R['nmin'] = R[['nA', 'nB']].min(1).clip(upper=4)
R['pix'] = np.sqrt((R.scanA * R.trackA + R.scanB * R.trackB) / 2)
h = np.radians(np.where(R.dn == 'D', 347.0, 193.0))
R['d_scan'] = R.dE * np.cos(h) - R.dN * np.sin(h); R['d_track'] = R.dE * np.sin(h) + R.dN * np.cos(h)
R['site'] = (R.lonA * 30).round().astype(int).astype(str) + '_' + (R.latA * 30).round().astype(int).astype(str)   # ~3.5 km cells
R.to_parquet(f'{SC}/pairs2.parquet')
CLIP = 2000.0
def bmean(df, col, key='site', n=400):
    v = df[col].clip(-CLIP, CLIP); g = v.groupby(df[key]).agg(['sum', 'size']); s, c = g['sum'].values, g['size'].values
    if len(g) < 3: return np.nan, np.nan, np.nan
    bs = [];
    for _ in range(n):
        k = rng.integers(0, len(g), len(g)); bs.append(s[k].sum() / c[k].sum())
    return float(v.mean()), float(np.quantile(bs, .025)), float(np.quantile(bs, .975))
S = R[(R.typ == 2) & R.vv & R.small].copy()
res = dict(static_pairs=len(S), sites=int(S.site.nunique()))
rows = []
for (p, dn), g in S.groupby(['pair', 'dn']):
    if len(g) < 30: continue
    r = dict(pair=p, dn=dn, n=len(g), sites=g.site.nunique(), gap_min=round(g.gap_min.median(), 1))
    for c in ['dE', 'dN', 'd_scan', 'd_track']:
        m, lo, hi = bmean(g, c); r[c] = round(m, 1); r[c + '_ci'] = f'{lo:.0f} to {hi:.0f}'
    r['sd_scan'] = round(g.d_scan.clip(-CLIP, CLIP).std(), 0); r['sd_track'] = round(g.d_track.clip(-CLIP, CLIP).std(), 0)
    r['median_move'] = round(np.hypot(g.dE, g.dN).median(), 0)
    rows.append(r)
B = pd.DataFrame(rows); B.to_csv(f'{OUT}/noise_bias_by_pair.csv', index=False); print(B.to_string())
# per-sensor offsets (S-NPP = 0) by least squares over ordered pairs, separately day and night
offs = {}
for dn in 'DN':
    g = S[S.dn == dn]; sens = ['NOAA-20', 'NOAA-21']
    Xm = np.zeros((len(g), 2));
    for k, s in enumerate(sens): Xm[:, k] = (g.sB == s).astype(float) - (g.sA == s).astype(float)
    for c in ['dE', 'dN']:
        y = g[c].clip(-CLIP, CLIP).values; coef = np.linalg.lstsq(Xm, y, rcond=None)[0]
        bs = []
        sites = g.site.values; us = np.unique(sites); gi = {u: np.where(sites == u)[0] for u in us}
        for _ in range(200):
            k = np.concatenate([gi[u] for u in rng.choice(us, len(us))]); bs.append(np.linalg.lstsq(Xm[k], y[k], rcond=None)[0])
        bs = np.array(bs)
        for k, s in enumerate(sens):
            offs[f'{s} minus S-NPP, {"day" if dn == "D" else "night"}, {c}'] = f'{coef[k]:.0f} m ({np.quantile(bs[:, k], .025):.0f} to {np.quantile(bs[:, k], .975):.0f})'
res['sensor_offsets_static'] = offs; print(json.dumps(offs, indent=1))
# dependence of the bias on side of nadir x pixel size, pixel count, year (OLS on the along-scan / along-track parts,
# after removing the pair x day/night mean; site-bootstrap CIs)
S['ps'] = S.sideB * (S.scanB - 375) - S.sideA * (S.scanA - 375)        # signed growth of the scan pixel, m
dep = {}
for c in ['d_scan', 'd_track']:
    y = S[c].clip(-CLIP, CLIP) - S.groupby(['pair', 'dn'])[c].transform(lambda v: v.clip(-CLIP, CLIP).mean())
    Xd = np.c_[S.ps / 100, (S.nmin >= 2), S.season - 2022]
    coef = np.linalg.lstsq(np.c_[np.ones(len(S)), Xd], y.values, rcond=None)[0]
    us = S.site.unique(); gi = {u: np.where(S.site.values == u)[0] for u in us}; bs = []
    for _ in range(200):
        k = np.concatenate([gi[u] for u in rng.choice(us, len(us))]); bs.append(np.linalg.lstsq(np.c_[np.ones(len(k)), Xd[k]], y.values[k], rcond=None)[0])
    bs = np.array(bs)
    dep[c] = {nm: f'{coef[i + 1]:.1f} m ({np.quantile(bs[:, i + 1], .025):.1f} to {np.quantile(bs[:, i + 1], .975):.1f})'
              for i, nm in enumerate(['per 100 m signed scan-pixel growth (view-angle side)', '2+ pixels vs 1', 'per year'])}
res['bias_dependence'] = dep; print(json.dumps(dep, indent=1))
# year-by-year N-S offset of NOAA-20 vs S-NPP (static)
yr = {}
for y_, g in S[S.pair.isin(['S-NPP>NOAA-20', 'NOAA-20>S-NPP'])].groupby('season'):
    sg = np.where(g.pair == 'S-NPP>NOAA-20', 1, -1); yr[int(y_)] = dict(n=len(g), dN=round(float((sg * g.dN.clip(-CLIP, CLIP)).mean()), 1), dE=round(float((sg * g.dE.clip(-CLIP, CLIP)).mean()), 1))
res['noaa20_minus_snpp_by_year'] = yr; print(yr)
# covariance model: robust spread (1.4826 MAD) by pixel-size and count bins; fit var = k*(s^2/n sum)/12 + g^2
S['jit_s'] = (S.scanA ** 2 / S.nA + S.scanB ** 2 / S.nB) / 12; S['jit_t'] = (S.trackA ** 2 / S.nA + S.trackB ** 2 / S.nB) / 12
cov = []
S['pixbin'] = pd.cut(S.pix, [300, 420, 520, 650, 2000]);
for (pb, nm), g in S.groupby(['pixbin', 'nmin'], observed=True):
    if len(g) < 50: continue
    cov.append(dict(pixel=str(pb), min_pixels=int(nm), n=len(g), rsd_scan=round(1.4826 * np.median(np.abs(g.d_scan - g.d_scan.median()))),
                    rsd_track=round(1.4826 * np.median(np.abs(g.d_track - g.d_track.median()))), corr_scan_track=round(np.corrcoef(g.d_scan.clip(-CLIP, CLIP), g.d_track.clip(-CLIP, CLIP))[0, 1], 3),
                    sd_scan_clip=round(g.d_scan.clip(-CLIP, CLIP).std()), sd_track_clip=round(g.d_track.clip(-CLIP, CLIP).std()),
                    model_jitter_scan=round(np.sqrt(g.jit_s.mean())), model_jitter_track=round(np.sqrt(g.jit_t.mean()))))
C = pd.DataFrame(cov); C.to_csv(f'{OUT}/noise_cov_bins.csv', index=False); print(C.to_string())
fit = {}
for c, j in [('d_scan', 'jit_s'), ('d_track', 'jit_t')]:
    # robust variance per row ~ (1.4826*|resid|)^2 is noisy; fit on bins instead
    S['q'] = pd.qcut(S[j], 20, duplicates='drop')
    b = S.groupby('q', observed=True).apply(lambda g: pd.Series(dict(j=g[j].mean(), v=(1.4826 * np.median(np.abs(g[c] - g[c].median()))) ** 2)))
    k, g2 = np.linalg.lstsq(np.c_[b.j, np.ones(len(b))], b.v, rcond=None)[0]
    fit[c] = dict(k=round(float(k), 3), geoloc_sd_m=round(float(np.sqrt(max(g2, 0))), 1))
res['variance_model (robust core)'] = fit; print(fit)
# heavy tail: share beyond 3 robust SD
for c in ['d_scan', 'd_track']:
    rs = 1.4826 * np.median(np.abs(S[c] - S[c].median())); res[f'tail_share_beyond_3rsd_{c}'] = round(float((np.abs(S[c] - S[c].median()) > 3 * rs).mean()), 3)
# Terra / Aqua vs VIIRS biases from static sites (all gaps <= 4 h)
T = R[(R.typ == 2) & ~R.vv & (R.sA != R.sB)]
tb = []
for (p, dn), g in T.groupby(['pair', 'dn']):
    if len(g) < 30: continue
    r = dict(pair=p, dn=dn, n=len(g), gap_min=round(g.gap_min.median()))
    for c in ['dE', 'dN']:
        m, lo, hi = bmean(g, c); r[c] = round(m, 1); r[c + '_ci'] = f'{lo:.0f} to {hi:.0f}'
    r['rsd_E'] = round(1.4826 * np.median(np.abs(g.dE - g.dE.median()))); r['rsd_N'] = round(1.4826 * np.median(np.abs(g.dN - g.dN.median())))
    tb.append(r)
TB = pd.DataFrame(tb); TB.to_csv(f'{OUT}/noise_bias_modis_pairs.csv', index=False); print(TB.to_string())
# 12 h pairs (VIIRS, static): bias by sensors and day->night / night->day
L = R[(R.typ == 2) & R.vv & (R.gap_min >= 600)].copy()
L['dir'] = np.where(L.istA.between(8, 20), 'day>night', 'night>day')
lb = []
for (p, dr), g in L.groupby(['pair', 'dir']):
    if len(g) < 30: continue
    r = dict(pair=p, dir=dr, n=len(g))
    for c in ['dE', 'dN']:
        m, lo, hi = bmean(g, c); r[c] = round(m, 1); r[c + '_ci'] = f'{lo:.0f} to {hi:.0f}'
    lb.append(r)
LB = pd.DataFrame(lb); LB.to_csv(f'{OUT}/noise_bias_12h_pairs.csv', index=False); print(LB.to_string())
# the bias table used downstream: mean static (dE, dN) per ordered pair x day/night (small gaps), per pair x direction (12 h)
bt = S.groupby(['pair', 'dn']).agg(bE=('dE', lambda v: v.clip(-CLIP, CLIP).mean()), bN=('dN', lambda v: v.clip(-CLIP, CLIP).mean()), nb=('dE', 'size')).reset_index()
bt.to_csv(f'{OUT}/bias_table_small.csv', index=False)
T2 = T.groupby(['pair', 'dn']).agg(bE=('dE', lambda v: v.clip(-CLIP, CLIP).mean()), bN=('dN', lambda v: v.clip(-CLIP, CLIP).mean()), nb=('dE', 'size')).reset_index()
T2.to_csv(f'{OUT}/bias_table_modis.csv', index=False)
L2 = L.groupby(['pair', 'dir']).agg(bE=('dE', lambda v: v.clip(-CLIP, CLIP).mean()), bN=('dN', lambda v: v.clip(-CLIP, CLIP).mean()), nb=('dE', 'size')).reset_index()
L2.to_csv(f'{OUT}/bias_table_12h.csv', index=False)
# fires' own estimate of sensor offsets from both orders (motion cancels if both orders have similar gaps)
Fi = R[(R.typ == 0) & R.vv & R.small]
fo = {}
for a, b in [('S-NPP', 'NOAA-20'), ('NOAA-20', 'NOAA-21'), ('S-NPP', 'NOAA-21')]:
    for dn in 'DN':
        g1 = Fi[(Fi.sA == a) & (Fi.sB == b) & (Fi.dn == dn)]; g2 = Fi[(Fi.sA == b) & (Fi.sB == a) & (Fi.dn == dn)]
        if len(g1) < 100 or len(g2) < 100: continue
        fo[f'{b} minus {a}, {dn}'] = dict(n=[len(g1), len(g2)], gaps=[round(g1.gap_min.median()), round(g2.gap_min.median())],
                                          dE=round((g1.dE.clip(-CLIP, CLIP).mean() - g2.dE.clip(-CLIP, CLIP).mean()) / 2, 1),
                                          dN=round((g1.dN.clip(-CLIP, CLIP).mean() - g2.dN.clip(-CLIP, CLIP).mean()) / 2, 1))
res['sensor_offsets_from_fires_both_orders'] = fo; print(json.dumps(fo, indent=1))
json.dump(res, open(f'{OUT}/noise_summary.json', 'w'), indent=1, default=str)
