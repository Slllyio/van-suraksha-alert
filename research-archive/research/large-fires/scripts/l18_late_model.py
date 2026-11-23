"""Step 18. Fix B: late-season models. BIGW = BIG with late rows (doy >= 106, i.e. from 16 Apr) weighted x3;
BIGL = BIG trained only on rows from 1 Apr, used from 16 Apr (spliced into BIG's cube as BIGS; probabilities are on the
same footing because both use the same 1% negative sampling and weights). held: train 2018-21 -> 2022-24; fwd: 2018-24 -> 2025-26.
Out: scratch cube_BIGW_<y>.npy, cube_BIGS_<y>.npy."""
import sys, numpy as np, pandas as pd, lightgbm as lgb
import lf_common as L, l2_samples as S2
from l3_train import fit, P_BIG, META, TR


def main(period):
    D = pd.concat([pd.read_parquet(L.SC + f'samp_{y}.parquet') for y in TR[period]], ignore_index=True)
    feats = [c for c in D.columns if c not in META]; y = (D.lsz >= 200).values
    w = D.w.values * np.where(D.doy >= 106, 3.0, 1.0)
    MW = fit(D, y, feats, P_BIG, 500, w=w.astype(np.float32))
    m = D.doy >= 91; ML = fit(D[m].reset_index(drop=True), y[m.values], feats, P_BIG, 500)
    print(period, 'trained', flush=True)
    for yr in ((2022, 2023, 2024) if period == 'held' else (2025, 2026)):
        W, S = [], []; col = None; big = np.load(L.SC + f'cube_BIG_{yr}.npy')
        for t, it in enumerate(S2.iter_season(yr)):
            if col is None: col = {n: i for i, n in enumerate(it['names'])}
            X = it['X'][:, [col[n] for n in feats]]
            W.append(MW.predict(X, num_threads=4).astype(np.float16))
            S.append(ML.predict(X, num_threads=4).astype(np.float16) if it['t'] >= pd.Timestamp(f'{yr}-04-16') else big[t])
        np.save(L.SC + f'cube_BIGW_{yr}.npy', np.stack(W)); np.save(L.SC + f'cube_BIGS_{yr}.npy', np.stack(S)); print(yr, flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
