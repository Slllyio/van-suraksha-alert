"""Train one variant of the pooled LightGBM (all 87 divisions, division id categorical = per-division intercept and
interactions), predict every test square-day, score it with the strict officer rule (evalr.py).
Usage: python3 run.py VARIANT [held|fwd|both]. Variants are defined in variants.py.
Negatives subsampled at rate Q with weight 1/Q; all positives kept."""
import sys, os, json, time, pickle
import numpy as np, pandas as pd, lightgbm as lgb
import common as C, features as Fe, evalr as E

Q = 0.015
PARAMS = dict(objective='binary', learning_rate=0.06, num_leaves=127, min_data_in_leaf=400, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, verbose=-1, num_threads=int(os.environ.get('NT', 4)), max_cat_to_onehot=4, cat_smooth=20)
NROUND = 350


def collect(seasons, cfg, V, extras, seed=0):
    rng = np.random.default_rng(seed); Xs, ys, ws, ts, cis, names = [], [], [], [], [], None
    soft = cfg.get('fp_label')
    for y in seasons:
        ex = extras(y) if extras else {}
        for it in Fe.season_iter(y, cfg, V, need_fp_label=soft, **ex):
            lab = it['ys'] if soft else it['y'].astype(np.float32)
            pos = lab > 0; keep = pos | (rng.random(len(lab)) < Q)
            w = np.where(pos, 1.0, 1.0 / Q).astype(np.float32)
            if cfg.get('obs_w') is not None: w = w * cfg['obs_w'](it, y)  # observation-aware weight
            k = keep & (w > 0)
            Xs.append(it['X'][k]); ys.append(lab[k]); ws.append(w[k]); ts.append(np.full(k.sum(), y * 1000 + it['t'].dayofyear, np.int32)); cis.append(np.nonzero(k)[0].astype(np.int32))
            names = it['names']
        print('collected', y, sum(len(a) for a in ys), flush=True)
    return np.vstack(Xs), np.concatenate(ys), np.concatenate(ws), np.concatenate(ts), np.concatenate(cis), names


def predict_cubes(models, seasons, cfg, V, extras, combine=None):
    cube = {}
    for y in seasons:
        ex = extras(y) if extras else {}; out = []
        for it in Fe.season_iter(y, cfg, V, **ex):
            if combine is None: p = models[0].predict(it['X'], num_threads=int(os.environ.get('NT', 4)))
            else: p = combine(models, it)
            out.append(p.astype(np.float32))
        cube[y] = np.stack(out); print('predicted', y, flush=True)
    return cube


def fit(X, y, w, names, cfg, params=None):
    pr = dict(PARAMS, **(params or cfg.get('params') or {}))
    if cfg.get('fp_label'): pr['objective'] = 'cross_entropy'
    drop = set(cfg.get('drop_feats', ()))
    keep = [i for i, n in enumerate(names) if n not in drop]
    ds = lgb.Dataset(X[:, keep], y, weight=w, feature_name=[names[i] for i in keep], categorical_feature=['div'] if 'div' in [names[i] for i in keep] else [], free_raw_data=True)
    m = lgb.train(pr, ds, cfg.get('nround', NROUND))
    m._keep = keep
    return m


class Wrapped:
    def __init__(s, m): s.m = m; s.keep = m._keep
    def predict(s, X, num_threads=None): return s.m.predict(X[:, s.keep], num_threads=num_threads or int(os.environ.get('NT', 4)))


def run(name, cfg, period, extras=None, save_cube=False):
    tr, te = C.PERIODS[period]
    V = C.load_det()
    t0 = time.time()
    if cfg.get('custom_train'):
        models, combine = cfg['custom_train'](tr, cfg, V, extras)
    else:
        X, y, w, ts, ci, names = collect(tr, cfg, V, extras, seed=cfg.get('sample_seed', 0))
        print('train rows', len(y), 'pos', int((y > 0).sum()), 'feats', len(names), flush=True)
        m = fit(X, y, w, names, cfg); del X
        models, combine = [Wrapped(m)], None
        imp = pd.DataFrame(dict(feat=[names[i] for i in m._keep], gain=m.feature_importance('gain'))).sort_values('gain', ascending=False)
        imp['share'] = imp.gain / imp.gain.sum(); imp.to_csv(C.OUT + f'imp_{name}_{period}{C.TAG}.csv', index=False)
    print('trained', round(time.time() - t0), 's', flush=True)
    cube = predict_cubes(models, te, cfg, V, extras, combine)
    if save_cube: pickle.dump(cube, open(C.SC + f'cube_{name}_{period}{C.TAG}.pkl', 'wb'), protocol=4)
    sm, ev, dv = E.score(cube, Fe.base()['U'], period)
    sm.update(E.boot(ev)); sm['variant'] = name; sm['period'] = period
    ev.to_parquet(C.SC + f'ev_{name}_{period}{C.TAG}.parquet'); dv.to_csv(C.SC + f'dv_{name}_{period}{C.TAG}.csv', index=False)
    os.makedirs(C.OUT + 'results', exist_ok=True)
    json.dump(sm, open(C.OUT + f'results/{name}_{period}{C.TAG}.json', 'w'), indent=1, default=float)
    print('RESULT', name, period, json.dumps({k: (round(v, 2) if isinstance(v, float) else v) for k, v in sm.items()}, default=str), flush=True)
    return sm, cube


if __name__ == '__main__':
    import variants
    name = sys.argv[1]; per = sys.argv[2] if len(sys.argv) > 2 else 'both'
    cfg, extras = variants.get(name)
    for p in (('held', 'fwd') if per == 'both' else (per,)):
        run(name, cfg, p, extras, save_cube=cfg.get('save_cube', C.SUB))
