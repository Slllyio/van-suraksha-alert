"""Step 4. Score every square-day of a test season with every model (held models for 2022-24, fwd models for 2025).
Out: scratch cube_<MODEL>_<YEAR>.npy (float16, issue days x squares) + baselines HIST (VIIRS fire history, h_r1),
BIGH (200 ha+ scar-fire burned share, 3.5 km box, earlier seasons) and the two-stage product TWO = START x SIZE."""
import sys, pickle, numpy as np, lightgbm as lgb
import lf_common as L, l2_samples as S2


def main(y):
    per = 'fwd' if y >= 2025 else 'held'
    Ms = {k: (lgb.Booster(model_str=s), f) for k, (s, f) in pickle.load(open(L.SC + f'models_{per}.pkl', 'rb')).items()}
    out = {k: [] for k in list(Ms) + ['HIST', 'BIGH', 'TWO']}; col = None
    for it in S2.iter_season(y):
        if col is None: col = {n: i for i, n in enumerate(it['names'])}
        X = it['X']
        for k, (m, f) in Ms.items(): out[k].append(m.predict(X[:, [col[n] for n in f]], num_threads=4).astype(np.float16))
        out['TWO'].append((out['START'][-1].astype(np.float32) * out['SIZE'][-1].astype(np.float32)).astype(np.float16))
        out['HIST'].append(X[:, col['h_r1']].astype(np.float16) + np.float16(1e-3) * X[:, col['h_r3']].astype(np.float16))
        out['BIGH'].append(np.nan_to_num(X[:, col['bf_big_r3']]).astype(np.float16))
    for k, v in out.items(): np.save(L.SC + f'cube_{k}_{y}.npy', np.stack(v))
    print('predicted', y, flush=True)


if __name__ == '__main__':
    main(int(sys.argv[1]))
