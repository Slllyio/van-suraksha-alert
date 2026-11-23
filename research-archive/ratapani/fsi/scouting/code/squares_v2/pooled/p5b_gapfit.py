"""Step 5b: does the pooled outward move grow with the time gap? Real spread does (move = v * gap); a per-pair artefact of
the geometry or of the noise does not. Fit p = a + v * gap_h over all pairs (gaps 25, 50, 75 min), bootstrap by fire
cluster. v is the artefact-free speed if the artefact does not depend on the gap; a is the artefact (m).
Same for the static null. Out: results/gapfit.csv"""
import os
import numpy as np, pandas as pd
SC = os.environ.get('POOL_SCRATCH', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r19_pool')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
rng = np.random.default_rng(7)
F = pd.read_parquet(f'{SC}/fires_small.parquet'); N0 = pd.read_parquet(f'{SC}/static_small.parquet')
for D in (F, N0): D['forest'] = ~D.vtm.isin([170, 180, 190, 191, 200])
rows = []
def fit(d, col):
    d = d[np.isfinite(d[col])]; y = d[col].clip(-2000, 2000).values; X = np.c_[np.ones(len(d)), d.gap_h.values]
    co = np.linalg.lstsq(X, y, rcond=None)[0]; cl = pd.factorize(d.cl)[0]
    idx = pd.Series(np.arange(len(d))).groupby(cl).apply(np.array).values; bs = []
    for _ in range(300):
        k = np.concatenate(idx[rng.integers(0, len(idx), len(idx))]); bs.append(np.linalg.lstsq(X[k], y[k], rcond=None)[0])
    bs = np.array(bs)
    return dict(n=len(d), intercept_m=round(co[0], 1), int_ci=f'{np.quantile(bs[:, 0], .025):.1f} to {np.quantile(bs[:, 0], .975):.1f}',
                speed_m_h=round(co[1], 1), ci=f'{np.quantile(bs[:, 1], .025):.1f} to {np.quantile(bs[:, 1], .975):.1f}')
for nm, D in [('fires', F), ('fires, forest+scrub', F[F.forest]), ('fires, farm', F[F.vtm == 170]), ('static null', N0)]:
    for dn in 'DN':
        for col, lab in [('p_out', 'outward'), ('p_grow', 'towards later growth')]:
            r = fit(D[D.dn == dn], col); r.update(set=nm, slot='13:30 day' if dn == 'D' else '01:30 night', direction=lab); rows.append(r)
T = pd.DataFrame(rows); T.to_csv(f'{OUT}/gapfit.csv', index=False); pd.set_option('display.width', 200); print(T.to_string())
