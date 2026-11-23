"""B step 1c: robustness of the between-fire SD (tau) from split halves (odd / even fire-days, no shared pass).
Raw weighted covariance, the same with values winsorised at 2/98%, and the same restricted to fires whose halves are each
measured with noise SD < 4 or < 1 (factor units); Spearman rank correlation of the halves; perpendicular part as null.
95% ranges: bootstrap over fires. Out: results/b1c_tau_robust.json"""
import sys, os, json, pickle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b1_hier import *
from scipy.stats import spearmanr
O, kap = load(); C = pickle.load(open(f'{SC}/class_model.pkl', 'rb')); cm = C['full']
mu = class_mean(O, cm); O['yc'] = O.y - nuisance(O, cm)
k = (O.seg != '12h_night>day').values; O3 = O[k]; mu3 = mu[k]; h = (O3.fday % 2).values
rng = np.random.default_rng(0); res = {}
for col, c0, nm in [('yc', 1, 'outward'), ('yq', 0, 'perpendicular_null')]:
    A = per_fire(O3[h == 0], mu3[h == 0], col=col); B = per_fire(O3[h == 1], mu3[h == 1], col=col)
    J = A.join(B, lsuffix='1', rsuffix='2', how='inner'); res[nm] = {}
    for lim in [None, 4.0, 1.0]:
        JJ = J if lim is None else J[(J.s21 < lim ** 2) & (J.s22 < lim ** 2)]
        a = JJ.f_hat1.values - c0; b = JJ.f_hat2.values - c0; w = 1 / np.sqrt(JJ.s21 * JJ.s22).values
        def stats(kk):
            aa, bb, ww = a[kk], b[kk], w[kk]; qa = np.quantile(aa, [.02, .98]); qb = np.quantile(bb, [.02, .98])
            return np.sum(ww * aa * bb) / np.sum(ww), np.sum(ww * np.clip(aa, *qa) * np.clip(bb, *qb)) / np.sum(ww), spearmanr(aa, bb)[0]
        s0 = stats(np.arange(len(a))); bs = np.array([stats(rng.integers(0, len(a), len(a))) for _ in range(300)])
        res[nm][f'noise_sd_below_{lim}' if lim else 'all'] = dict(fires=len(a), cov=round(s0[0], 4), cov_ci=np.round(np.quantile(bs[:, 0], [.025, .975]), 4).tolist(),
            cov_winsorised=round(s0[1], 4), cov_w_ci=np.round(np.quantile(bs[:, 1], [.025, .975]), 4).tolist(),
            spearman=round(s0[2], 3), spearman_ci=np.round(np.quantile(bs[:, 2], [.025, .975]), 3).tolist())
json.dump(res, open(f'{OUT}/b1c_tau_robust.json', 'w'), indent=1); print(json.dumps(res, indent=1))
