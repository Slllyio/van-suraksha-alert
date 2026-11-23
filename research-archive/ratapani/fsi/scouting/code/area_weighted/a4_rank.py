"""Steps 2, 4, 5: score the current list and the area-aware rankings with the round-22 strict officer rule, at matched ground.
P = the kept model's chance (round-22 cube C_static_newhead), isotonic-calibrated on the other season of its test block
(held: fitted on 2022; fwd: fitted on 2026, scored on 2025), so P is a real probability before it is multiplied.
E = the size model (a3). Rankings (all per division, one cut over the test square-days, as the current list):
  P             current list (top 10% by P; isotonic keeps its order)
  E             size only (reference)
  PxE           expected burnt area = P x E
  P^1 E^w       blends, w = 0.25, 0.5, 0.75, 1.5, 2 (w = 1 is PxE)
  poolM         take the top M x k squares by P, then keep the k with the highest P x E (M = 1.25, 1.5, 2, 3)
For each ranking the flag share is set so that ground (flagged or next to a flag) equals the current list's, then each fire
is scored once (caught when a first-day square is flagged or next to a flag on day -1 or -2).
Reported: % fires, % brand-new fires, % burnt ha (scar truth; and best-available truth), % of 200 ha+ fires, lead time,
median distance to a road / village of the flagged square-days. Paired bootstrap by fire against the current list.
Usage: python3 a4_rank.py held|fwd. Out: out/rank_{period}.csv, scratch r24 hits_{period}.parquet."""
import sys, pickle, json, numpy as np, pandas as pd
from multiprocessing import Pool
from scipy.ndimage import maximum_filter
from sklearn.isotonic import IsotonicRegression
import aw_common as A
C, Fe, E = A.C, A.Fe, A.E
W_BLEND = (0.25, 0.5, 0.75, 1.5, 2.0)
POOLS = (1.25, 1.5, 2.0, 3.0)
G = {}


def rankings():
    r = ['P', 'E', 'PxE'] + [f'P1E{w}' for w in W_BLEND] + [f'pool{m}' for m in POOLS]
    return r


def score_of(name, P, Ev):
    lp, le = np.log(np.maximum(P, 1e-7)), np.log(np.maximum(Ev, 1e-3))
    if name == 'P': return lp
    if name == 'E': return le
    if name == 'PxE': return lp + le
    if name.startswith('P1E'): return lp + float(name[3:]) * le
    raise KeyError(name)


def flags(name, P, Ev, q):
    """Boolean flag array (T x n) for ranking `name` at flag share 1-q of the division's test square-days."""
    if name.startswith('pool'):
        m = float(name[4:]); lp = np.log(np.maximum(P, 1e-7)); k = (1 - q) * lp.size
        pool = lp >= np.quantile(lp, max(0.0, 1 - m * (1 - q)))
        s = np.where(pool, np.log(np.maximum(P, 1e-7)) + np.log(np.maximum(Ev, 1e-3)), -np.inf)
        thr = np.sort(s.ravel())[::-1][max(0, int(round(k)) - 1)]
        return s >= thr
    s = score_of(name, P, Ev); return s >= np.quantile(s, q)


def lag(A_, consec, k):
    Z = np.zeros_like(A_)
    if k == 1: Z[1:] = A_[:-1] & consec[1:, None]
    else: Z[2:] = A_[:-2] & (consec[2:] & consec[1:-1])[:, None]
    return Z


def div_job(args):
    name, rk, qs = args
    d = G['E'][name]; m = G['mask'][name]; P = G['P'][name]; Ev = G['Ecube'][name]
    gi, gj = d['gi'], d['gj']; labc = d['labc'][m]; FIRE = d['FIRE'][m]; fdy = d['firstday'][m]; consec = d['consec'][m].copy(); consec[0] = False
    n_ev = d['n_ev']; ids = np.nonzero(d['valid'] & np.isin(d['ev_season'], G['seasons']))[0]
    droad = G['droad'][G['uidx'][name]]; dvil = G['dvil'][G['uidx'][name]]
    out = []
    for q in qs:
        fl = flags(rk, P, Ev, q); T = fl.shape[0]
        R3 = np.zeros((T, d['NJ'], d['NI']), bool); R3[:, gi, gj] = fl
        NEAR = maximum_filter(R3, size=(1, 3, 3))[:, gi, gj]
        c1 = lag(NEAR, consec, 1) & FIRE & fdy; c2 = lag(NEAR, consec, 2) & FIRE & fdy
        h1 = np.bincount(labc[c1], minlength=n_ev + 1) > 0; h2 = np.bincount(labc[c2], minlength=n_ev + 1) > 0
        nf = fl.sum(0)
        out.append(dict(q=q, ev=ids, hit=(h1 | h2)[ids], lead2=h2[ids], ground=float(NEAR.mean()), nflag=int(fl.sum()),
                        road_counts=(droad, nf), vil_counts=(dvil, nf)))
    return name, out


def wmedian(vals, w):
    o = np.argsort(vals); v, w = vals[o], w[o]; c = np.cumsum(w); return float(v[np.searchsorted(c, c[-1] / 2)])


def run(rk, qs, names):
    with Pool(4) as p: R = p.map(div_job, [(n, rk, qs) for n in names], chunksize=1)
    res = {}
    for qi, q in enumerate(qs):
        hits = pd.concat([pd.DataFrame(dict(division=n, ev=o[qi]['ev'], hit=o[qi]['hit'], lead2=o[qi]['lead2'])) for n, o in R], ignore_index=True)
        ground = 100 * np.mean([o[qi]['ground'] for n, o in R])
        rv = np.concatenate([o[qi]['road_counts'][0] for n, o in R]); rw = np.concatenate([o[qi]['road_counts'][1] for n, o in R])
        vv = np.concatenate([o[qi]['vil_counts'][0] for n, o in R])
        res[q] = dict(hits=hits, ground=ground, road_med=wmedian(rv, rw.astype(float)), vil_med=wmedian(vv, rw.astype(float)),
                      road_far=float((rw * (rv > 2)).sum() / rw.sum()))
    return res


def metrics(h, ev):
    x = h.merge(ev, on=['division', 'ev'])
    sc = x[x.area_src == 'scar']; big = sc[sc.area_ha >= A.BIG]; bigv = x[x.area_ha >= A.BIG]
    return dict(fires=100 * x.hit.mean(), new=100 * x.hit[x.new].mean(), ha_scar=100 * (sc.hit * sc.area_ha).sum() / sc.area_ha.sum(),
                ha_best=100 * (x.hit * x.area_ha).sum() / x.area_ha.sum(), big_scar=100 * big.hit.mean(), n_big_scar=len(big),
                big_best=100 * bigv.hit.mean(), new_ha_scar=100 * (sc.hit * sc.area_ha)[sc.new].sum() / sc.area_ha[sc.new].sum(),
                lead2=100 * x.lead2[x.hit].mean(), lead_mean=1 + x.lead2[x.hit].mean(), big_lead2=100 * big.lead2[big.hit].mean())


def paired(ha, hb, ev, B=1000, seed=0):
    x = ha.merge(hb, on=['division', 'ev'], suffixes=('_a', '_b')).merge(ev, on=['division', 'ev'])
    sc = x.area_src.values == 'scar'; area = x.area_ha.values; a, b = x.hit_a.values.astype(float), x.hit_b.values.astype(float)
    big = sc & (area >= A.BIG); nw = x.new.values
    rng = np.random.default_rng(seed); n = len(x); D = {k: [] for k in ('fires', 'new', 'ha_scar', 'big_scar')}
    def stat(i):
        s = i[sc[i]]; g = i[big[i]]; w = i[nw[i]]
        return dict(fires=(b[i] - a[i]).mean(), new=(b[w] - a[w]).mean(), ha_scar=((b[s] - a[s]) * area[s]).sum() / area[s].sum(),
                    big_scar=(b[g] - a[g]).mean() if len(g) else np.nan)
    pt = stat(np.arange(n))
    for _ in range(B):
        for k, v in stat(rng.integers(0, n, n)).items(): D[k].append(v)
    return {k: (100 * pt[k], 100 * np.nanpercentile(D[k], 2.5), 100 * np.nanpercentile(D[k], 97.5)) for k in D}


def setup(per):
    seasons = A.TEST[per]; U = Fe.base()['U']
    Ed = pickle.load(open(C.SC + f'eval_{per}_sub.pkl', 'rb')); Ed = {k: v for k, v in Ed.items() if not k.startswith('_')}
    Pc = pickle.load(open(C.SC + f'cube_{A.KEPT}_{per}_sub.pkl', 'rb')); Ec = pickle.load(open(A.S24 + f'Ecube_{per}.pkl', 'rb'))
    fit_y = 2022 if per == 'held' else 2026
    # isotonic map raw P -> chance of a target fire on day +1/+2, fitted on fit_y (pooled over the 10 divisions)
    ps, ys = [], []
    for nm, d in Ed.items():
        idx = np.searchsorted(U, d['rows'] * C.W + d['cols']); mk = d['SEAS'] == fit_y
        ps.append(Pc[fit_y][:, idx].ravel()); ys.append(d['Y'][mk].ravel())
    ps, ys = np.concatenate(ps), np.concatenate(ys); sub = np.random.default_rng(0).random(len(ps)) < 0.3
    iso = IsotonicRegression(out_of_bounds='clip', y_min=1e-6, y_max=1).fit(ps[sub], ys[sub]); del ps, ys
    st = np.load(C.SC + 'static.npz'); fi = Fe.base()['fidx']
    G.update(E=Ed, seasons=seasons, droad=st['d_road'][fi], dvil=st['d_village'][fi], P={}, Ecube={}, mask={}, uidx={})
    for nm, d in Ed.items():
        idx = np.searchsorted(U, d['rows'] * C.W + d['cols']); mk = np.isin(d['SEAS'], seasons)
        G['mask'][nm] = mk; G['uidx'][nm] = idx
        raw = np.concatenate([Pc[y][:, idx] for y in seasons]); G['P'][nm] = iso.predict(raw.ravel()).reshape(raw.shape).astype(np.float32)
        # ties after isotonic: break them by the raw score so the P order is exactly the current list's
        G['P'][nm] = G['P'][nm] * (1 + 1e-4 * (pd.Series(raw.ravel()).rank(pct=True).values.reshape(raw.shape)))
        G['Ecube'][nm] = np.concatenate([Ec[y][:, idx] for y in seasons])
        for k in ('Y', 'CLEAR', 'stv', 'bcol', 'inb', 'rng_of'): d.pop(k, None)
    del Pc, Ec
    return list(Ed)


if __name__ == '__main__':
    per = sys.argv[1]; names = setup(per)
    ev = pd.read_parquet(A.S24 + 'events.parquet'); ev = ev[ev.season.isin(A.TEST[per]) & ev.valid]
    base = run('P', (0.90,), names)[0.90]; tg = base['ground']; mb = metrics(base['hits'], ev)
    print('current list', round(tg, 2), json.dumps({k: round(v, 2) for k, v in mb.items()}), flush=True)
    rows = [dict(ranking='P (current)', q=0.90, ground=tg, road_med=base['road_med'], vil_med=base['vil_med'], road_far=100 * base['road_far'], **mb)]
    allhits = [base['hits'].assign(ranking='P (current)')]
    for rk in rankings()[1:]:
        qs = (0.86, 0.88, 0.90, 0.92, 0.94)
        R = run(rk, qs, names); gr = np.array([R[q]['ground'] for q in qs]); o = np.argsort(gr)
        q = float(np.interp(tg, gr[o], np.array(qs)[o]))
        r = run(rk, (q,), names)[q]; mt = metrics(r['hits'], ev); d = paired(base['hits'], r['hits'], ev)
        row = dict(ranking=rk, q=round(q, 4), ground=r['ground'], road_med=r['road_med'], vil_med=r['vil_med'], road_far=100 * r['road_far'], **mt)
        for k, v in d.items(): row.update({f'd_{k}': v[0], f'd_{k}_lo': v[1], f'd_{k}_hi': v[2]})
        rows.append(row); allhits.append(r['hits'].assign(ranking=rk))
        print(rk, json.dumps({k: (round(v, 2) if isinstance(v, float) else v) for k, v in row.items()}), flush=True)
    T = pd.DataFrame(rows); T.to_csv(A.OUT + f'rank_{per}.csv', index=False)
    pd.concat(allhits).to_parquet(A.S24 + f'hits_{per}.parquet', index=False)
    print(T.round(2).to_string())
