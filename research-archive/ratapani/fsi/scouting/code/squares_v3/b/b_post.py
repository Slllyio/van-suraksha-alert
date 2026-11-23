"""Per-fire posterior speeds for the Ratapani truth tests, with every fitted thing held out by season.
For each season s: the class model, the design-effect table and the between-fire variance tau^2 (split halves) are fitted
on all MP pairs of the OTHER seasons (b1 functions). A fire's posterior factor then uses only the pairs given to it (e.g.
those finished before a forecast is issued):  f_post = 1 + B (f_hat - 1),  B = tau^2 / (tau^2 + DE s^2).
fire_speed(fires_meta, pairs, season) -> per fire: mu (class daily-mean speed, m/h), f_post, sd, v_post = mu f_post.
A fire with no pairs gets f = 1 (its class mean); its class comes from its forest type (VTM at its first detection) and month.
Cache: scratch post_models.pkl"""
import sys, os, pickle
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b_lib import *
from b1_hier import load, fit_class, class_mean, nuisance, per_fire, design_effect, split_half_tau2, design, FT

_M = {}
def models():
    if _M: return _M
    fn = f'{SC}/post_models.pkl'
    if os.path.exists(fn) and not os.environ.get('B_REDO'):
        _M.update(pickle.load(open(fn, 'rb'))); return _M
    O, kap = load(); out = {'kap': kap}
    for s in list(range(2017, 2027)) + ['none']:
        tr = O if s == 'none' else O[O.season != s]
        cm = fit_class(tr); cmf = fit_class(tr, flat=True)
        mu = class_mean(tr, cm); trc = tr.assign(yc=tr.y - nuisance(tr, cm))
        fo = per_fire(trc, mu, col='yc'); fp = per_fire(trc, mu, col='yq'); _, detab = design_effect(fo, fp)
        t2, _ = split_half_tau2(trc, mu, col='yc')
        muf = class_mean(tr, cmf); trf = tr.assign(yc=tr.y - nuisance(tr, cmf))
        fof = per_fire(trf, muf, col='yc'); fpf = per_fire(trf, muf, col='yq'); _, detabf = design_effect(fof, fpf)
        t2f, _ = split_half_tau2(trf, muf, col='yc')
        out[s] = dict(cm=cm, cmf=cmf, de=detab, tau2=max(t2, 0.0), def_=detabf, tau2f=max(t2f, 0.0))
        print('season out', s, 'tau2', round(t2, 3), 'flat', round(t2f, 3), flush=True)
    pickle.dump(out, open(fn, 'wb')); _M.update(out); return _M

def de_of(n, tab):
    edges = [(0, 1), (1, 2), (2, 4), (4, 8), (8, 16), (16, 1e6)]
    vals = list(tab.values())
    return np.array([vals[next(i for i, (a, b) in enumerate(edges) if a < k <= b)] for k in np.atleast_1d(n)])

def default_rows(meta):
    """synthetic pair rows (day and night) carrying a fire's class: forest type, month, middle size / FRP / age bins"""
    R = []
    for dn, seg in [('D', 'small_day'), ('N', 'small_night')]:
        R.append(pd.DataFrame(dict(fire=meta.fire.values, ft=meta.ft.values, dn0=dn, seg=seg, month=meta.month.values, pixb='3-4', frpb='f3',
                                   ageb='13-25h', nA=1.0, nB=1.0, K=1.0)))
    return pd.concat(R, ignore_index=True)

def fire_speed(meta, pairs, season, flat=False):
    """meta: fire, ft, month (one row per fire). pairs: b1-loaded rows (fire_rt set) that may be used. Returns DataFrame by fire."""
    M = models()[season]; cm = M['cmf'] if flat else M['cm']; tau2 = M['tau2f'] if flat else M['tau2']; de = M['def_'] if flat else M['de']
    dr = default_rows(meta); mu0 = pd.Series(class_mean(dr, cm), index=dr.fire).groupby(level=0).mean()
    out = pd.DataFrame(index=meta.fire.values); out['mu'] = mu0.reindex(out.index).values
    out['f_hat'] = np.nan; out['s2e'] = np.inf; out['n_pairs'] = 0
    if len(pairs):
        p = pairs.copy(); mu = class_mean(p, cm); p['yc'] = p.y - nuisance(p, cm)
        fo = per_fire(p, mu, key='fire_rt', col='yc'); fo = fo[fo.index.isin(out.index)]
        out.loc[fo.index, 'f_hat'] = fo.f_hat.values; out.loc[fo.index, 's2e'] = (fo.s2 * de_of(fo.n.values, de)).values
        out.loc[fo.index, 'n_pairs'] = fo.n.values
        # the fire's own mean class speed over its pairs (size / FRP / age of its own looks)
        mp = pd.Series(mu, index=p.fire_rt.values).groupby(level=0).mean(); ok = mp.index.isin(out.index)
        out.loc[mp.index[ok], 'mu'] = mp.values[ok]
    B = np.where(np.isfinite(out.s2e), tau2 / (tau2 + out.s2e), 0.0)
    out['B'] = B; out['f_post'] = 1 + B * (out.f_hat.fillna(1.0) - 1); out['sd_f'] = np.sqrt(np.where(np.isfinite(out.s2e), B * out.s2e, tau2))
    out['v_post'] = out.mu * out.f_post
    return out

_RT = {}
def ratapani_meta():
    """per Ratapani fire (big-fires ids): first time, season, month, forest type (VTM at the nearest MP point to its first detection)"""
    if _RT: return _RT['m']
    D = pd.read_parquet(f'{TRACK}/det.parquet'); D = D[(D.fire >= 0) & (D.kind == 'viirs')]
    f = D.sort_values('t').groupby('fire').agg(t0=('t', 'first'), t1=('t', 'last'), lat=('latitude', 'first'), lon=('longitude', 'first')).reset_index()
    P = pd.read_parquet(f'{POOL}/pts.parquet', columns=['latitude', 'longitude', 'vtm', 'season'])
    P = P[P.latitude.between(22.6, 23.3) & P.longitude.between(77.1, 78.3)]
    from scipy.spatial import cKDTree
    tr = cKDTree(np.c_[P.longitude.values, P.latitude.values]); _, j = tr.query(np.c_[f.lon.values, f.lat.values])
    f['vtm'] = P.vtm.values[j]; f['ft'] = pd.Series(ftype(f.vtm.values)).map(FT).fillna('other non-forest').values
    f['season'] = f.t0.dt.year; f['month'] = f.t0.dt.month
    _RT['m'] = f; return f

if __name__ == '__main__':
    models()
