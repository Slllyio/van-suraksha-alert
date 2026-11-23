"""Step 7: pooled growth of pixel count, flagged footprint area and FRP over small gaps (25/50/75 min), with the view-angle
effect removed. For every VIIRS->VIIRS pair of the same fire:
   y = log(B / A) for pixel count n, footprint area (sum scan x track, i.e. count normalised by pixel size) and FRP.
   y = (c_B - c_A) [sensor sensitivity, S-NPP = 0] + beta * log(pixel area B / pixel area A) [view angle] + gamma * gap_h
Both orders of each sensor pair exist, so sensitivity, view angle and real growth (gamma, per hour) separate.
Static industrial sites through the same model are the null (gamma must be ~0). Day and night apart; forest only.
Also per gap class (25/50/75 min, which includes the NOAA-21 -> S-NPP -> NOAA-20 triplet spacing) the mean residual.
Out: results/growth_*.csv/json"""
import json, os
import numpy as np, pandas as pd
SC = os.environ.get('POOL_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_pool')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
rng = np.random.default_rng(5)
R = pd.read_parquet(f'{SC}/pairs2.parquet')
R = R[R.vv & R.small].copy(); R['gap_h'] = R.gap_min / 60
R['cl'] = np.where(R.typ == 2, 's' + R.site, R.season.astype(str) + '_' + (R.lonA * 20).round().astype(int).astype(str) + '_' + (R.latA * 20).round().astype(int).astype(str))
R['ly_n'] = np.log(R.nB / R.nA); R['ly_area'] = np.log(R.areaB / R.areaA); R['ly_frp'] = np.log(R.frpB.clip(lower=.1) / R.frpA.clip(lower=.1))
R['ly_frpmax'] = np.log(R.frp_maxB.clip(lower=.1) / R.frp_maxA.clip(lower=.1))
R['lpix'] = np.log((R.scanB * R.trackB) / (R.scanA * R.trackA))
R['forest'] = ~R.vtm.isin([170, 180, 190, 191, 200])
def design(g):
    return np.c_[np.ones(len(g)) * 0, (g.sB == 'NOAA-20') * 1.0 - (g.sA == 'NOAA-20'), (g.sB == 'NOAA-21') * 1.0 - (g.sA == 'NOAA-21'), g.lpix, g.gap_h][:, 1:]
def fit(g, y, n=300):
    X = design(g); yy = g[y].values; ok = np.isfinite(yy); X, yy, cl = X[ok], yy[ok], pd.factorize(g.cl.values[ok])[0]
    co = np.linalg.lstsq(X, yy, rcond=None)[0]
    idx = [np.where(cl == c)[0] for c in range(cl.max() + 1)]; bs = []
    for _ in range(n):
        k = np.concatenate([idx[c] for c in rng.integers(0, len(idx), len(idx))]); bs.append(np.linalg.lstsq(X[k], yy[k], rcond=None)[0])
    bs = np.array(bs); resid = yy - X[:, :3] @ co[:3]
    return co, bs, resid, ok
rows = []; gc = []
for typ in (0, 2):
    for sub in (['all', 'forest'] if typ == 0 else ['all']):
        for dn in 'DN':
            g = R[(R.typ == typ) & (R.dn == dn)]
            if sub == 'forest': g = g[g.forest]
            for y in ['ly_n', 'ly_area', 'ly_frp', 'ly_frpmax']:
                co, bs, resid, ok = fit(g, y)
                rows.append(dict(set='fires' if typ == 0 else 'static null', subset=sub, slot='13:30 day' if dn == 'D' else '01:30 night', y=y, n=int(ok.sum()),
                                 growth_pct_per_h=round(100 * (np.exp(co[3]) - 1), 1),
                                 ci=f'{100 * (np.exp(np.quantile(bs[:, 3], .025)) - 1):.1f} to {100 * (np.exp(np.quantile(bs[:, 3], .975)) - 1):.1f}',
                                 beta_view_angle=round(co[2], 2), beta_ci=f'{np.quantile(bs[:, 2], .025):.2f} to {np.quantile(bs[:, 2], .975):.2f}',
                                 noaa20_vs_snpp=round(co[0], 3), noaa21_vs_snpp=round(co[1], 3), sd=round(np.nanstd(g[y].values), 2)))
                gg = g[ok].assign(res=resid)
                for c_, d in gg.groupby(pd.cut(gg.gap_min, [0, 35, 62, 120], labels=['~25 min', '~50 min', '~75 min']), observed=True):
                    gc.append(dict(set='fires' if typ == 0 else 'static null', subset=sub, slot=dn, y=y, gap=str(c_), n=len(d), mean_log_change=round(d.res.mean(), 3),
                                   se=round(d.res.std() / np.sqrt(len(d)), 3)))
T = pd.DataFrame(rows); T.to_csv(f'{OUT}/growth_model.csv', index=False); pd.set_option('display.width', 250); print(T.to_string())
G = pd.DataFrame(gc); G.to_csv(f'{OUT}/growth_by_gap.csv', index=False); print(G.to_string())
# naive view (no view-angle term): how much of the raw change is pixel-size driven
naive = {}
for typ in (0, 2):
    for dn in 'DN':
        g = R[(R.typ == typ) & (R.dn == dn)]
        naive[f"{'fires' if typ == 0 else 'static'} {dn}"] = dict(raw_mean_dlog_n=round(g.ly_n.mean(), 3), raw_mean_dlog_frp=round(g.ly_frp.mean(), 3),
                                                                 corr_dlog_n_vs_dlog_pixel=round(np.corrcoef(g.ly_n, g.lpix)[0, 1], 3),
                                                                 corr_dlog_frp_vs_dlog_pixel=round(np.corrcoef(g.ly_frp, g.lpix)[0, 1], 3))
json.dump(naive, open(f'{OUT}/growth_naive.json', 'w'), indent=1); print(naive)
# ---- difference-in-differences: fires minus static, cell by cell (ordered sensor pair x day/night), after each set's
# own view-angle term; then the per-hour rate from a weighted fit of the cell differences on the cell's gap.
dd = []
for sub in ['all', 'forest']:
    for dn in 'DN':
        for y in ['ly_n', 'ly_frp', 'ly_frpmax']:
            cells = []
            for typ in (0, 2):
                g = R[(R.typ == typ) & (R.dn == dn)]
                if typ == 0 and sub == 'forest': g = g[g.forest]
                co, bs, resid, ok = fit(g, y, n=2)
                adj = g[y].values[ok] - co[2] * g.lpix.values[ok]
                cells.append(pd.DataFrame(dict(pair=(g.sA + '>' + g.sB).values[ok], v=adj, gap=g.gap_h.values[ok], cl=g.cl.values[ok])))
            f, s = cells
            ag = lambda d: d.groupby('pair').agg(m=('v', 'mean'), se=('v', lambda u: u.std() / np.sqrt(len(u))), n=('v', 'size'), gap=('gap', 'mean'))
            C = ag(f).join(ag(s), rsuffix='_s', how='inner'); C = C[C.n_s >= 30]
            C['d'] = C.m - C.m_s; C['se_d'] = np.hypot(C.se, C.se_s)
            w = 1 / C.se_d ** 2; slope = np.sum(w * C.d * C.gap) / np.sum(w * C.gap ** 2); se = 1 / np.sqrt(np.sum(w * C.gap ** 2))
            dd.append(dict(subset=sub, slot='13:30 day' if dn == 'D' else '01:30 night', y=y, cells=len(C), static_pairs=int(C.n_s.sum()),
                           fire_minus_static_pct_per_h=round(100 * (np.exp(slope) - 1), 1),
                           ci=f'{100 * (np.exp(slope - 1.96 * se) - 1):.1f} to {100 * (np.exp(slope + 1.96 * se) - 1):.1f}',
                           cells_detail='; '.join(f'{p}: {r.d:+.3f} ({r.gap * 60:.0f} min)' for p, r in C.iterrows())))
DD = pd.DataFrame(dd); DD.to_csv(f'{OUT}/growth_fire_minus_static.csv', index=False); print(DD.drop(columns='cells_detail').to_string())
