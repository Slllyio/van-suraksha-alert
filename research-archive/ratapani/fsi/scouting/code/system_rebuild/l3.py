"""Layer 3 (ML) and the spatial-block check: custom trainers plugged into run.py through cfg['custom_train'].
- newhead: a second LightGBM trained only on square-days with no fire in the 21x21 block (+-5 km) over the last 7 days
  ('clear' squares, the brand-new-fire situation); its probability replaces the main model's on clear squares.
- blockcv: 20 km x 20 km blocks split at random into two folds; a model trained on fold A squares scores fold B squares
  and vice versa (test seasons unchanged). If the score holds, the model is not just memorising squares.
- obs weights: negatives on square-days whose next two days have no view better than 50 deg VZA get weight x0.5
  (a fire there could have been missed), see variants.py."""
import numpy as np
import run as R


def _wrap(m): return R.Wrapped(m)


def newhead(tr, cfg, V, extras):
    X, y, w, ts, ci, names = R.collect(tr, cfg, V, extras)
    j = names.index('f_r10_w7'); clear = X[:, j] == 0
    m_all = R.fit(X, y, w, names, cfg); m_new = R.fit(X[clear], y[clear], w[clear], names, cfg)
    print('newhead rows', int(clear.sum()), 'pos', int((y[clear] > 0).sum()), flush=True)
    A, Bm = _wrap(m_all), _wrap(m_new)
    def combine(models, it):
        Xd = it['X']; c = Xd[:, it['names'].index('f_r10_w7')] == 0
        p = A.predict(Xd); p[c] = Bm.predict(Xd[c]); return p
    return [A, Bm], combine


def blockcv(tr, cfg, V, extras, km=20, seed=1):
    import features as Fe
    B = Fe.base(); ur, uc = B['ur'], B['uc']; k = int(km * 2)
    blk = (ur // k) * 1000 + (uc // k); ub = np.unique(blk); rng = np.random.default_rng(seed)
    fold_of = dict(zip(ub, rng.integers(0, 2, len(ub)))); fold = np.array([fold_of[b] for b in blk], np.int8)
    X, y, w, ts, ci, names = R.collect(tr, cfg, V, extras)
    fr = fold[ci]; M = []
    for f in (0, 1):
        m = R.fit(X[fr == f], y[fr == f], w[fr == f], names, cfg); M.append(_wrap(m))
    def combine(models, it):
        Xd = it['X']; p = np.empty(len(Xd))
        p[fold == 1] = M[0].predict(Xd[fold == 1]); p[fold == 0] = M[1].predict(Xd[fold == 0]); return p
    return M, combine
