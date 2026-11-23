"""B step 1: per-fire spread speed by partial pooling (empirical Bayes; the full Bayesian check is b1b_numpyro.py).

Model for pair j of fire i (every look its own sensor and time; pairs from b0):
    p_ij = f_i * mu(x_ij) * K_ij + e_ij
  mu(x)  class mean daily-average outward speed (m/h): forest type x day/night start, month, pixels in the two looks,
         FRP fifth, fire age (the squares_v2 pooled factors), fitted jointly by weighted least squares on all pairs
         (optionally leaving one season out: fit_class(..., exclude_season=s)). Part A's correction enters through b_lib.
  K_ij   clock hours over the pair's own interval (diurnal multiplier, mean 1), so a 13:30 small gap counts ~2x its
         length and a 01:30 one ~0.45x.
  f_i    the fire-specific factor (1 = a typical fire of its class). Between-fire SD tau.
  e_ij   noise. Its size per segment is calibrated on the PERPENDICULAR part q of the same pairs (true value 0): this
         contains measurement noise (static-site model) plus real sideways wandering of the active centre.
Per fire: f_hat = sum w p m / sum w m^2 (m = mu K, w = 1/sigma^2), nominal variance s^2 = 1 / sum w m^2.
Because a fire's pairs share passes, the true error of f_hat is DE x s^2; DE (design effect) is measured from the same
estimator applied to q (f_perp, truth 0), by number of pairs. Then
    tau^2 (moments, DerSimonian-Laird) from (f_hat - 1)^2 - DE s^2, and independently
    tau^2 (split halves) = cov(f_hat half 1, f_hat half 2), halves = disjoint sets of passes (fire-days 06-06 IST,
    odd vs even), so their noise is independent.
Posterior (shrinkage): f_post = 1 + B (f_hat - 1), B = tau^2 / (tau^2 + DE s^2); sd = sqrt(B DE s^2).
CIs: bootstrap over fires (each fire is one cluster of linked pairs; MP: 5 km x season blocks of fires).
Out: results/b1_*.json/csv; scratch fires_post.parquet (per fire, all MP), class_model.pkl"""
import sys, os, json, pickle
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b_lib import *
rng = np.random.default_rng(11)
CLIPS = {'small_day': 2000, 'small_night': 2000}
FT = {'teak': 'teak', 'dry deciduous': 'dry deciduous', 'sal': 'sal', 'moist deciduous': 'moist deciduous',
      'other forest': 'other forest', 'degraded forest': 'degraded/bamboo', 'bamboo': 'degraded/bamboo',
      'scrub/grass': 'scrub/grass', 'agriculture': 'agriculture', 'other non-forest': 'other non-forest'}

def load():
    O = pd.read_parquet(f'{SC}/obs.parquet')
    cl = O.seg.map(CLIPS).fillna(3000)
    O['y'] = O.p_raw.clip(-cl, cl) - O.edge                    # part A: subtract the edge term from the clipped move
    O['yq'] = O.q.clip(-O.seg.map(CLIPS).fillna(3000), O.seg.map(CLIPS).fillna(3000))
    O['dn0'] = np.where(O.seg.isin(['small_day', 'terra_day', '12h_day>night']), 'D', 'N')
    O['ft'] = O.ftype.map(FT).fillna('other non-forest')
    O['pixb'] = pd.cut(O.npix, [0, 2, 4, 9, 1e5], labels=['2', '3-4', '5-9', '10+']).astype(str)
    O['frpb'] = pd.qcut(O.frp2.rank(method='first'), 5, labels=['f1', 'f2', 'f3', 'f4', 'f5']).astype(str)
    O['ageb'] = pd.cut(O.age_h.fillna(0), [-1, 13, 25, 49, 1e5], labels=['<13h', '13-25h', '25-49h', '>49h']).astype(str)
    O['fday'] = ((O.tA + pd.Timedelta(hours=5.5) - pd.Timedelta(hours=6)).dt.floor('D') - pd.Timestamp('2018-01-01')).dt.days
    # noise per segment from the perpendicular part (robust, MAD)
    kap = {}
    for s, g in O.groupby('seg'):
        mad = 1.4826 * np.median(np.abs(g.yq - g.yq.median())); kap[s] = float(mad ** 2 / g.var2.mean())
    O['sig2'] = O.seg.map(kap) * O.var2
    return O, kap

def design(O):
    cols = [f'{a}|{d}' for a in sorted(set(FT.values())) for d in 'DN']
    X = [((O.ft + '|' + O.dn0) == c).astype(float).values for c in cols]
    names = list(cols)
    Kfree = []
    for var, levels in [('month', [1, 2, 4, 5, 6]), ('pixb', ['2', '5-9', '10+']), ('frpb', ['f1', 'f2', 'f4', 'f5']), ('ageb', ['<13h', '25-49h', '>49h'])]:
        for lv in levels:   # contrasts against March, 3-4 pixels, middle FRP fifth, 13-25 h
            X.append((O[var] == lv).astype(float).values); names.append(f'{var}={lv}')
    # terms NOT multiplied by clock hours (metres per pair): cluster-size change (part A: centre moves inward ~11-16 m per
    # doubling of the pixel count) by day/night, and an own offset for each Terra segment (part A: Terra +254 m unexplained)
    lr = np.log2(O.nB.values / O.nA.values)
    extra = [(lr * (O.dn0 == 'D').values, 'm_per_doubling|D'), (lr * (O.dn0 == 'N').values, 'm_per_doubling|N'),
             ((O.seg == 'terra_day').values * 1.0, 'terra_offset|D'), ((O.seg == 'terra_night').values * 1.0, 'terra_offset|N')]
    return np.column_stack(X), names, np.column_stack([e for e, _ in extra]), [n for _, n in extra]

def fit_class(O, exclude_season=None, flat=False):
    """weighted LS of y on K * X beta. Returns dict(beta, names, flat)."""
    m = np.ones(len(O), bool) if exclude_season is None else (O.season != exclude_season).values
    w = 1 / O.sig2.values[m]
    X, names, E, enames = design(O)
    Z = O.K.values[m][:, None] if flat else X[m] * O.K.values[m][:, None]
    if flat: names = ['all']
    Z = np.c_[Z, E[m]]
    sw = np.sqrt(w); beta = np.linalg.lstsq(Z * sw[:, None], O.y.values[m] * sw, rcond=None)[0]
    k = len(names)
    return dict(beta=beta[:k], names=names, gamma=beta[k:], enames=enames, flat=flat, excl=exclude_season)

def nuisance(O, cm):
    """metres per pair from the non-clock terms (cluster-size change, Terra offsets); subtracted before per-fire fits"""
    _, _, E, _ = design(O); return E @ cm['gamma']

def class_mean(O, cm):
    """mu (m/h, daily-mean outward speed of the pair's class), with part A's day/night factors if given"""
    corr, _ = class_correction()
    if cm['flat']: mu = np.full(len(O), cm['beta'][0])
    else:
        X, names, _, _ = design(O); assert names == cm['names']; mu = X @ cm['beta']
    return mu * O.dn0.map(corr).values

def per_fire(O, mu, key='fire_mp', col='y'):
    m = mu * O.K.values; w = 1 / O.sig2.values
    g = pd.DataFrame({key: O[key].values, 'a': w * O[col].values * m, 'b': w * m * m, 'n': 1})
    s = g.groupby(key).sum()
    s['f_hat'] = s.a / s.b; s['s2'] = 1 / s.b
    return s[['f_hat', 's2', 'n']]

def design_effect(fo, fp):
    """DE by number of pairs, from the perpendicular estimator (truth 0): mean(f_perp^2 / s^2), robust (MAD^2)"""
    z = (fp.f_hat / np.sqrt(fp.s2)); nb = pd.cut(fo.n, [0, 1, 2, 4, 8, 16, 1e6])
    de = {}
    for b, zz in z.groupby(nb, observed=True):
        mad = 1.4826 * np.median(np.abs(zz - zz.median())); de[b] = float(mad ** 2)
    return nb.map(de).astype(float).values, {str(k): round(v, 2) for k, v in de.items()}

def tau2_dl(f, s2e):
    """DerSimonian-Laird moments estimate of the between-fire variance around 1"""
    ok = np.isfinite(f) & (s2e > 0)
    f, s2e = f[ok], s2e[ok]; t2 = 0.05
    for _ in range(50):
        w = 1 / (t2 + s2e); t2n = max(0.0, np.sum(w ** 2 * ((f - 1) ** 2 - s2e)) / np.sum(w ** 2));
        if abs(t2n - t2) < 1e-6: break
        t2 = t2n
    return t2

def split_half_tau2(O, mu, key='fire_mp', min_b=None, col='y'):
    """cov of the two halves' f_hat over fires with both halves informative"""
    O2 = O[~(O.seg == '12h_night>day')]                    # this segment crosses fire-days
    mu2 = mu[~(O.seg == '12h_night>day').values]
    h = (O2.fday % 2).values
    A = per_fire(O2[h == 0], mu2[h == 0], key, col); B = per_fire(O2[h == 1], mu2[h == 1], key, col)
    J = A.join(B, lsuffix='1', rsuffix='2', how='inner')
    if min_b is not None: J = J[(J.s21 < min_b) & (J.s22 < min_b)]
    w = 1 / np.sqrt(J.s21 * J.s22)
    c = np.sum(w * (J.f_hat1 - 1) * (J.f_hat2 - 1)) / np.sum(w)
    return c, J

if __name__ == '__main__':
    O, kap = load(); res = dict(noise_kappa_by_segment={k: round(v, 2) for k, v in kap.items()}, clock=diurnal()['src'],
                                correction=class_correction()[1], edge_term=O.edge_src.iloc[0], pairs=len(O))
    cm = fit_class(O); mu = class_mean(O, cm); cmf = fit_class(O, flat=True); muf = class_mean(O, cmf)
    pickle.dump(dict(full=cm, flat=cmf, kap=kap), open(f'{SC}/class_model.pkl', 'wb'))
    O['y_class'] = O.y - nuisance(O, cm); O['y_flat'] = O.y - nuisance(O, cmf)
    res['class_model'] = {n: round(float(b), 2) for n, b in zip(cm['names'], cm['beta'])}
    res['class_model_nuisance_m'] = {n: round(float(b), 1) for n, b in zip(cm['enames'], cm['gamma'])}
    res['flat_daily_mean_m_h'] = round(float(cmf['beta'][0]), 2)
    # class model check, each season held out: predicted vs observed pooled outward move per segment and season
    chk = []
    for s in sorted(O.season.unique()):
        c = fit_class(O, exclude_season=s); g = O[O.season == s]; mm = class_mean(g, c) * g.K.values + nuisance(g, c)
        for sg, gg in g.groupby('seg'):
            chk.append(dict(season=s, seg=sg, n=len(gg), obs_m=gg.y.mean(), pred_m=mm[(g.seg == sg).values].mean()))
    chk = pd.DataFrame(chk); chk.to_csv(f'{OUT}/b1_class_loso_check.csv', index=False)
    res['class_loso_corr_obs_pred_per_season_segment'] = round(float(np.corrcoef(chk.obs_m, chk.pred_m)[0, 1]), 3)
    out = {}
    for lab, mu_ in [('class', mu), ('flat', muf)]:
        yc = f'y_{lab}'
        fo = per_fire(O, mu_, col=yc); fp = per_fire(O, mu_, col='yq')
        DE, detab = design_effect(fo, fp); s2e = DE * fo.s2.values
        t2 = tau2_dl(fo.f_hat.values, s2e)
        c, J = split_half_tau2(O, mu_, col=yc)
        cq, Jq = split_half_tau2(O, mu_, col='yq')          # null: perpendicular halves must covary ~0 around 0
        # q halves: centre at 0, so compute cov of f_hat (not f_hat-1)
        wq = 1 / np.sqrt(Jq.s21 * Jq.s22); cq = float(np.sum(wq * Jq.f_hat1 * Jq.f_hat2) / np.sum(wq))
        # bootstrap over fires (blocks: 5 km x season of the fire's first pair) for tau^2 (DL) and split-half
        first = O.groupby('fire_mp').agg(ax=('ax', 'first'), ay=('ay', 'first'), season=('season', 'first'))
        blk = (first.season.astype(str) + '_' + (first.ax / 5000).round().astype(int).astype(str) + '_' + (first.ay / 5000).round().astype(int).astype(str))
        bl_fo = pd.factorize(blk.reindex(fo.index))[0]; nb = bl_fo.max() + 1
        Jb = pd.factorize(blk.reindex(J.index))[0]
        bs, bs2 = [], []
        idx_by = pd.Series(np.arange(len(fo))).groupby(bl_fo).apply(np.array).values
        jdx_by = {k: v for k, v in pd.Series(np.arange(len(J))).groupby(Jb).apply(np.array).items()}
        wJ = 1 / np.sqrt(J.s21.values * J.s22.values); pJ = (J.f_hat1.values - 1) * (J.f_hat2.values - 1)
        jb_codes = pd.factorize(blk.reindex(J.index))[1]
        jmap = {code: i for i, code in enumerate(jb_codes)}
        bl_names = pd.factorize(blk.reindex(fo.index))[1]
        for _ in range(200):
            k = rng.integers(0, nb, nb); ii = np.concatenate([idx_by[q] for q in k])
            bs.append(tau2_dl(fo.f_hat.values[ii], s2e[ii]))
            jj = [jdx_by[jmap[bl_names[q]]] for q in k if bl_names[q] in jmap]
            jj = np.concatenate(jj) if jj else np.array([], int)
            bs2.append(np.sum(wJ[jj] * pJ[jj]) / np.sum(wJ[jj]))
        B = t2 / (t2 + s2e); fpost = 1 + B * (fo.f_hat.values - 1); sdpost = np.sqrt(B * s2e)
        fo = fo.assign(DE=DE, s2e=s2e, B=B, f_post=fpost, sd_post=sdpost)
        out[lab] = fo
        rel = B
        res[f'{lab}'] = dict(fires=len(fo), design_effect_by_pairs=detab,
                             tau_DL=round(np.sqrt(t2), 3), tau_DL_ci=[round(np.sqrt(np.quantile(bs, .025)), 3), round(np.sqrt(np.quantile(bs, .975)), 3)],
                             tau_split_half=round(float(np.sqrt(max(c, 0))), 3), tau2_split_half=round(float(c), 4),
                             tau2_split_half_ci=[round(float(np.quantile(bs2, .025)), 4), round(float(np.quantile(bs2, .975)), 4)],
                             split_half_fires=len(J), split_half_null_perp_cov=round(cq, 4),
                             median_noise_sd_of_f=round(float(np.median(np.sqrt(s2e))), 2),
                             noise_sd_of_f_by_pairs={str(k): round(float(np.median(np.sqrt(v))), 2) for k, v in pd.Series(s2e).groupby(pd.cut(fo.n.values, [0, 1, 2, 4, 8, 16, 32, 1e6]), observed=True)},
                             reliability_B_quantiles={q: round(float(np.quantile(rel, q)), 3) for q in [.1, .25, .5, .75, .9, .99]},
                             fires_B_over_half=int((rel > .5).sum()),
                             fires_post_ci_excludes_1=int((np.abs(fpost - 1) > 1.96 * sdpost).sum()),
                             fires_post_ci_excludes_1_fast=int(((fpost - 1) > 1.96 * sdpost).sum()))
    F = out['class'].join(out['flat'], rsuffix='_flat')
    meta = O.groupby('fire_mp').agg(season=('season', 'first'), n_seg=('seg', 'nunique'), fire_rt=('fire_rt', lambda v: int(pd.Series(v[v >= 0]).mode().iloc[0]) if (v >= 0).any() else -1),
                                    ft=('ft', lambda v: v.mode().iloc[0]), lat=('latA', 'mean'), lon=('lonA', 'mean'), npix_mean=('npix', 'mean'),
                                    frp_mean=('frp2', 'mean'), mu_class=('ft', 'size'))
    meta['mu_class'] = pd.Series(mu, index=O.index).groupby(O.fire_mp).mean()
    F = F.join(meta); F.to_parquet(f'{SC}/fires_post.parquet')
    # variance decomposition of one pair's outward move, by segment (m^2): static-site noise, real wandering, persistent fire factor
    dec = []
    for sg, g in O.groupby('seg'):
        noise_static = g.var2.mean()                                   # kappa = 1 on static sites by construction
        perp = (1.4826 * np.median(np.abs(g.yq - g.yq.median()))) ** 2
        mm = (mu * O.K.values)[(O.seg == sg).values]
        pers = float(np.mean(mm ** 2)) * res['class']['tau2_split_half']
        dec.append(dict(segment=sg, pairs=len(g), mean_clock_h=round(g.K.mean(), 2), mean_class_move_m=round(float(mm.mean()), 1),
                        sd_measurement_m=round(np.sqrt(noise_static)), sd_sideways_wander_m=round(np.sqrt(max(perp - noise_static, 0))),
                        sd_between_fire_m=round(np.sqrt(max(pers, 0)), 1)))
    pd.DataFrame(dec).to_csv(f'{OUT}/b1_variance_decomposition.csv', index=False)
    # split-half checks with wider separation between the halves (the earlier-position window E reaches back 48 h),
    # outward (truth tau^2) and perpendicular (truth 0); bootstrap over fires
    keep_ = (O.seg != '12h_night>day').values; O3 = O[keep_]; mu3 = mu[keep_]
    rel = (O3.fday - O3.groupby('fire_mp').fday.transform('min')).values
    def cov(a, b, col, c0):
        A = per_fire(O3[a], mu3[a], col=col); B = per_fire(O3[b], mu3[b], col=col)
        J = A.join(B, lsuffix='1', rsuffix='2', how='inner'); w = (1 / np.sqrt(J.s21 * J.s22)).values; v = ((J.f_hat1 - c0) * (J.f_hat2 - c0)).values
        bs = [np.sum(w[k] * v[k]) / np.sum(w[k]) for k in (rng.integers(0, len(J), len(J)) for _ in range(300))]
        return dict(fires=len(J), cov=round(float(np.sum(w * v) / np.sum(w)), 4), ci=[round(float(np.quantile(bs, .025)), 4), round(float(np.quantile(bs, .975)), 4)])
    res['split_half_checks'] = {nm: dict(outward=cov(a, b, 'y_class', 1), perpendicular_null=cov(a, b, 'yq', 0)) for nm, (a, b) in
                                {'odd vs even fire-days': (rel % 2 == 0, rel % 2 == 1), 'first fire-day vs day 3+': (rel == 0, rel >= 3),
                                 'days 0-1 vs day 4+': (rel <= 1, rel >= 4)}.items()}
    json.dump(res, open(f'{OUT}/b1_hier.json', 'w'), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str)); print(pd.DataFrame(dec).to_string())
