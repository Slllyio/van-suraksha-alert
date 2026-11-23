"""Variant registry: name -> (cfg, extras(y) -> dict(static=..., looks=..., fpw=...))."""
import numpy as np, pandas as pd
import common as C

_V = {}


def reg(name, **cfg):
    def deco(fn=None):
        _V[name] = (cfg, fn); return fn
    return deco


def get(name):
    if name not in _V: raise KeyError(name)
    cfg, fn = _V[name]
    return dict(cfg), fn


reg('B0')()


class Looks:
    """Look features for one season from scratch looks_{y}.npz (s2_looks.py). Day axis = 1 Jan..2 Jun of y.
    lk_n{w}: VIIRS views in the last w days (incl. today); lk_eff{w}: effective looks (375 m^2 / pixel area summed);
    lk_slant7: share of views at VZA>50 in 7 d; lk_night7: share of night views; lk_best1/3: lowest VZA today / 3 d;
    lk_fut_eff / lk_fut_best: the same for t+1..t+2 (orbits are deterministic, so tomorrow's geometry is known).
    good_cs: cumulative count of good looks (VZA <= 40 deg) for 'good looks since the last fire'."""
    def __init__(s, y):
        import features as Fe
        L = np.load(C.SC + f'looks_{y}.npz'); fi = Fe.base()['fidx']
        s.nv = L['nv'][:, fi].astype(np.float32); s.ns = L['ns'][:, fi].astype(np.float32); s.nd = L['nd'][:, fi].astype(np.float32); s.mv = L['mv'][:, fi]; s.ef = L['ef'][:, fi].astype(np.float32)
        z = lambda a: np.vstack([np.zeros((1, a.shape[1]), np.float32), np.cumsum(a, 0)])
        s.cv, s.cs, s.cd, s.ce = z(s.nv), z(s.ns), z(s.nd), z(s.ef)
        s.good_cs = z((s.mv <= 40).astype(np.float32))
        s.n = s.nv.shape[0]
    def day(s, d):
        w = lambda c, k: c[d + 1] - c[max(0, d + 1 - k)]
        o = {}
        for k in (1, 3, 7): o[f'lk_n{k}'] = w(s.cv, k); o[f'lk_eff{k}'] = w(s.ce, k)
        n7 = np.maximum(o['lk_n7'], 1); o['lk_slant7'] = w(s.cs, 7) / n7; o['lk_night7'] = 1 - w(s.cd, 7) / n7
        o['lk_best1'] = s.mv[d].astype(np.float32); o['lk_best3'] = s.mv[max(0, d - 2):d + 1].min(0).astype(np.float32)
        o['lk_fut_eff'] = s.ce[min(s.n, d + 3)] - s.ce[d + 1]; o['lk_fut_best'] = s.mv[d + 1:d + 3].min(0).astype(np.float32)
        return o


_FP = {}
def fpw(kind='fp'):
    if kind not in _FP: _FP[kind] = pd.read_parquet(C.SC + f'{kind}.parquet')
    return _FP[kind]


def _static():
    import features as Fe
    z = np.load(C.SC + 'static.npz'); fi = Fe.base()['fidx']; return {k: z[k][fi] for k in z.files}


def ex_looks(y): return dict(looks=Looks(y))
def ex_fp(y): return dict(fpw=fpw('fp'))
def ex_static(y): return dict(static=_static())


reg('L1a_looks')(ex_looks)
reg('L1b_fpfeat', fp_feats=True)(ex_fp)
reg('L1b_fplabel', fp_label=True)(ex_fp)
reg('L1c_offsets', offsets=True)()
reg('L1c_droplow', drop_low=True)()
reg('L1c_conf', conf_feats=True)()
reg('L1c_frp', frp_feats=True)()
reg('L1d_histnorm', hist_norm=True)()
reg('L1d_histsnpp', hist_snpp=True)()
reg('L1d_nsat', nsat_feat=True)()
reg('L2_static')(ex_static)


def _obs_w(it, y):
    """Negatives whose next two days have no view better than 50 deg VZA get weight x0.5 (detected-given-viewed)."""
    j = it['names'].index('lk_fut_best'); poor = it['X'][:, j] > 50
    return np.where(poor & ~it['y'], 0.5, 1.0).astype(np.float32)


def _l3(name):
    import l3; return getattr(l3, name)


reg('L3_newhead', custom_train=lambda *a: _l3('newhead')(*a))()
reg('L3_blockcv', custom_train=lambda *a: _l3('blockcv')(*a))()
reg('L3_obsw', obs_w=_obs_w)(ex_looks)
reg('L1c_dedup', dedup=True)()
reg('B0_seed2', sample_seed=2, params=dict(seed=2, bagging_seed=2, feature_fraction_seed=2))()

_GROUPS = {'terrain': ['elev', 'slope', 'rugged', 'rough_in', 'tpi5', 'south'],
           'lc': ['lc_forest', 'lc_scrub', 'lc_grass', 'lc_farm', 'lc_settle', 'lc_water', 'lc_sal', 'lc_teak', 'lc_drymix', 'lc_moistmix',
                  'lc_bamboo', 'lc_degraded', 'farm_2k5', 'farm_5k', 'forest_5k', 'd_edge_in', 'd_forest_out', 'beat_frac', 'beat_5k'],
           'access': ['road_km', 'major_km', 'road_km_5k', 'd_major', 'd_road', 'd_village', 'villages_5k', 'settle_5k']}
def _ex_group(g):
    def f(y):
        s = _static(); return dict(static={k: s[k] for k in _GROUPS[g]})
    return f
for _g in _GROUPS: reg(f'L2_{_g}')(_ex_group(_g))


def ex_static_looks(y): return dict(static=_static(), looks=Looks(y))
reg('C_static_newhead', custom_train=lambda *a: _l3('newhead')(*a))(ex_static)
reg('C_static_looks_newhead', custom_train=lambda *a: _l3('newhead')(*a))(ex_static_looks)


def _obs_w2(it, y):
    """Negatives weighted by tomorrow's+next day's effective looks relative to the day's median (capped 0.3..1):
    a square seen through fewer/worse looks gives weaker evidence of 'no fire'."""
    j = it['names'].index('lk_fut_eff'); e = it['X'][:, j]; r = np.clip(e / max(np.median(e), 1e-6), 0.3, 1.0)
    return np.where(~it['y'], r, 1.0).astype(np.float32)
reg('L3_obsw2', obs_w=_obs_w2)(ex_looks)
