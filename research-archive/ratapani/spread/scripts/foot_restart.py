"""Learned restart (reverse engineering, pass by pass): from everything the satellites have shown up to pass k, where will
the NEXT pass show fire, and where does the fire END? LightGBM per 20 m pixel, leave-one-season-out, no physics inside.
Fires: events_viirs.parquet (S-NPP + NOAA-20 + NOAA-21), 2+ passes within 48 h, scar mapped (for the end label).
Baselines at the same area: persistence (475 m around the known detections = restart.py's 375 m around 100 m ignition
discs) and the plain distance ranking.  Modes:
  build k/n out.parquet       training rows on a 120 m lattice, one block of rows per (fire, step); labels y_next (pixel
                              within 240 m of a next-pass detection) and y_scar (pixel in the final scar)
  train rows mdir             two models per held-out season (next, scar)
  score mdir k/n out.parquet  per step at 20 m: next-pass hits at the persistence area and at half of it, new-ground hits,
                              AUC; at the last pass: end footprint vs scar at scar area and at the expected area
"""
import numpy as np, pandas as pd, sys, json, os, time
from scipy import ndimage
import sim, score
import footprint as fp
R_MAX = 2500.0; CAP = 3000.0; LAT = 6; HOURS = 48; HIT = 12; PERS = 475.0
STAT = ['wc', 'elev', 'slope', 'd_road', 'd_nonveg', 'd_built', 'd_prev', 'nburn_hist', 'last_burn', 'rf1', 'lf', 'lean', 'forest']
DYN = ['d_all', 'd_last', 'd_first', 'd_cent_all', 'd_cent_last', 'rel_mom', 'mom_len', 'rel_last_axis', 'rel_all_axis', 'rel_w',
       'dd_road', 'dd_nonveg', 'dd_built', 'dd_prev', 'delev', 'drf1', 'dlf', 'dlean']
FIRE = ['k', 'n_prev', 'n_last', 'elapsed_h', 'lead_h', 'frp_last', 'frp_all', 'night_last', 'doy', 'ext_all', 'ws', 'rh', 'm1', 'temp', 'run_so_far']
FEATS = STAT + DYN + FIRE + (['d_last_far', 'd_all_far'] if os.environ.get('FAR_SIDE') else [])


_NPZ = sim.G
class _G(dict):          # sim.G decompresses on every access: keep the last few burn layers
    def __missing__(self, k):
        a = _NPZ[k]
        if k.startswith('burn_'):
            if len(self) > 8:
                self.pop(next(iter(self)))
            self[k] = a
        return a
sim.G = _G(); fp._BE.clear()
if os.environ.get('SCAR_GROWN'):          # scar thread's grown outlines as the end label / truth (grown.py); fires without one are skipped
    import grown
    score.scar_footprint = grown.scar_footprint


def events(k_n=None):
    v = pd.read_parquet(f"{sim.DATA}/{os.environ.get('EVENTS_FILE', 'events_viirs.parquet')}"); v = v[v.t.dt.month <= 6]
    g = v.groupby('event'); ids = [e for e, d in g if d.overpass.nunique() >= 2]
    if os.environ.get('SCAR_GROWN'):
        import grown
        ids = [e for e in ids if e in grown.load()]
    if k_n:
        k, n = map(int, k_n.split('/')); ids = ids[k::n]
    return v, ids


def hits(sub, A, win):
    r, c = sim.rc(sub.x.values, sub.y.values); r -= win[0]; c -= win[2]
    return sum(bool(A[max(a - HIT, 0):a + HIT + 1, max(b - HIT, 0):b + HIT + 1].any()) for a, b in zip(r, c))


def fire_static(ev, win):
    i0, i1, j0, j1 = win; s = int(ev.season.iloc[0]); d0 = ev.t.min().dayofyear
    wc = sim.WC[i0:i1, j0:j1]; elev = sim.ELEV[i0:i1, j0:j1].astype(np.float32); slope = sim.SLOPE[i0:i1, j0:j1].astype(np.float32)
    be = fp.burn_end(s)[i0:i1, j0:j1]; prev = (be > -999) & (be < d0 - 26)   # final 25 days after the window end (audit, Oct 15)
    nb = np.zeros(wc.shape, np.float32)
    for y in range(2017, s):
        nb += (fp.burn_end(y)[i0:i1, j0:j1] > -999)
    last = (fp.burn_end(s - 1)[i0:i1, j0:j1] > -999).astype(np.float32) if s > 2017 else np.full(wc.shape, np.nan, np.float32)
    rf1 = sim._rf_cache(fp.CFG['rfuel_file'])[f'rf_{s}'][0, i0:i1, j0:j1].astype(np.float32)
    mo = ev.t.min().month; band = {12: 0, 1: 0, 2: 1, 3: 2, 4: 3}.get(mo, None)
    if band is not None:
        lf = sim.LEAFFALL[band, i0:i1, j0:j1].astype(np.float32)
        if band < 4:
            nxt = sim.LEAFFALL[band + 1, i0:i1, j0:j1].astype(np.float32); lf = lf + (nxt - lf) * min(ev.t.min().day / 30.0, 1.0)
    else:
        lf = np.ones(wc.shape, np.float32)
    cid = fp.CELL[i0:i1, j0:j1]
    B = np.isin(wc, [10, 20, 30]) & ~sim.BARRIER[i0:i1, j0:j1]
    F = dict(wc=wc.astype(np.float32), elev=elev, slope=slope, d_road=fp.edt(sim.BARRIER[i0:i1, j0:j1]), d_nonveg=fp.edt(~np.isin(wc, [10, 20, 30])),
             d_built=fp.edt(wc == 50), d_prev=fp.edt(prev), nburn_hist=nb, last_burn=last, rf1=rf1, lf=lf, forest=fp.lut_cells(fp.FOREST, cid))
    return F, B, cid


def step_rows(ev, passes, k, F, B, cid, S, win, wx, lattice):
    """features for the step that knows passes[:k] (k = len(passes): the end step, no target)"""
    i0, i1, j0, j1 = win
    known = ev[ev.overpass <= passes[k - 1]]; last = ev[ev.overpass == passes[k - 1]]; first = ev[ev.overpass == passes[0]]
    target = ev[ev.overpass == passes[k]] if k < len(passes) else None
    yy, xx = np.mgrid[i0:i1, j0:j1]
    px = (sim.X0 + xx * sim.RES + sim.RES / 2).astype(np.float64); py = (sim.Y0 - yy * sim.RES - sim.RES / 2).astype(np.float64)
    def dmin(sub):
        d = np.full(px.shape, np.inf)
        for a, b in zip(sub.x.values, sub.y.values):
            d = np.minimum(d, np.hypot(px - a, py - b))
        return d
    d_all, d_last, d_first = dmin(known), dmin(last), dmin(first)
    FAR = os.environ.get('FAR_SIDE') and 'scan' in known.columns
    if FAR:
        def farside(sub, ref):
            hs, ht = sub.scan.values * 500.0, sub.track.values * 500.0
            return pd.DataFrame(dict(x=sub.x.values + np.sign(sub.x.values - ref[0]) * hs, y=sub.y.values + np.sign(sub.y.values - ref[1]) * ht))
        earlier = ev[ev.overpass < passes[k - 1]]
        if len(earlier):
            ref = (earlier.x.mean(), earlier.y.mean()); d_last_far = dmin(farside(last, ref))
            d_all_far = np.minimum(dmin(earlier), d_last_far)
        else:
            d_last_far, d_all_far = d_last, d_all
    ca = (known.x.mean(), known.y.mean()); cl = (last.x.mean(), last.y.mean()); cf = (first.x.mean(), first.y.mean())
    d_cent_all = np.hypot(px - ca[0], py - ca[1]); d_cent_last = np.hypot(px - cl[0], py - cl[1])
    bearing = np.degrees(np.arctan2(px - cl[0], py - cl[1]))
    mom = np.hypot(cl[0] - cf[0], cl[1] - cf[1]); rel_mom = np.full(px.shape, np.nan, np.float32)
    if mom > 100:
        rel_mom = np.cos(np.radians(bearing - np.degrees(np.arctan2(cl[0] - cf[0], cl[1] - cf[1]))))
    def axis_rel(sub, cen):
        if len(sub) < 2:
            return np.full(px.shape, np.nan, np.float32)
        x_, y_ = sub.x.values - cen[0], sub.y.values - cen[1]
        if np.hypot(x_[:, None] - x_[None, :], y_[:, None] - y_[None, :]).max() < 100:
            return np.full(px.shape, np.nan, np.float32)
        _, V = np.linalg.eigh(np.cov(np.c_[x_, y_].T)); az = np.degrees(np.arctan2(V[0, 1], V[1, 1]))
        return np.abs(np.cos(np.radians(np.degrees(np.arctan2(px - cen[0], py - cen[1])) - az)))
    rel_last_axis, rel_all_axis = axis_rel(last, cl), axis_rel(known, ca)
    W, P = wx; pid = P.index[np.argmin(np.hypot(P.x - cl[0], P.y - cl[1]))]; w = W[pid]
    th = last.t.max().floor('h'); w0 = w.loc[th] if th in w.index else None
    rel_w = np.cos(np.radians(bearing - float(w0.waz))) if w0 is not None else np.full(px.shape, np.nan, np.float32)
    dday = last.t.max().normalize()
    lv = fp.LEAN.loc[dday].reindex(range(fp.NCELL)).values if dday in fp.LEAN.index else np.full(fp.NCELL, np.nan)
    lean = fp.lut_cells(lv, cid)
    rc_, cc_ = sim.rc(np.array([cl[0]]), np.array([cl[1]])); ri = int(np.clip(rc_[0] - i0, 0, px.shape[0] - 1)); ci = int(np.clip(cc_[0] - j0, 0, px.shape[1] - 1))
    at = lambda a: float(a[ri, ci])
    disc = (slice(max(ri - 25, 0), ri + 26), slice(max(ci - 25, 0), ci + 26))
    lean_c = float(np.nanmean(lean[disc])) if np.isfinite(lean[disc]).any() else np.nan
    ext_all = float(np.hypot(known.x.values - ca[0], known.y.values - ca[1]).max())
    run = float(np.hypot(known.x.values - cf[0], known.y.values - cf[1]).max())
    D = dict(d_all=d_all, d_last=d_last, d_first=d_first, d_last_far=(d_last_far if FAR else d_last), d_all_far=(d_all_far if FAR else d_all), d_cent_all=d_cent_all, d_cent_last=d_cent_last, rel_mom=rel_mom, mom_len=np.full(px.shape, mom, np.float32),
             rel_last_axis=rel_last_axis, rel_all_axis=rel_all_axis, rel_w=rel_w, dd_road=F['d_road'] - at(F['d_road']), dd_nonveg=F['d_nonveg'] - at(F['d_nonveg']),
             dd_built=F['d_built'] - at(F['d_built']), dd_prev=F['d_prev'] - at(F['d_prev']), delev=F['elev'] - at(F['elev']), drf1=F['rf1'] - at(F['rf1']),
             dlf=F['lf'] - at(F['lf']), dlean=lean - lean_c, lean=lean)
    fl = dict(k=k, n_prev=len(known), n_last=len(last), elapsed_h=(last.t.max() - first.t.min()).total_seconds() / 3600,
              lead_h=(target.t.min() - last.t.max()).total_seconds() / 3600 if target is not None else np.nan,
              frp_last=float(last.frp.sum()), frp_all=float(known.frp.sum()), night_last=float(last.daynight.iloc[0] == 'N'), doy=first.t.min().dayofyear,
              ext_all=ext_all, ws=float(w0.ws) if w0 is not None else np.nan, rh=float(w0.rh) if w0 is not None else np.nan,
              m1=float(w0.m1) if w0 is not None else np.nan, temp=float(w0['T']) if w0 is not None else np.nan, run_so_far=run)
    mask = B & (d_all <= R_MAX)
    if lattice:
        mask &= (yy % LAT == 0) & (xx % LAT == 0)
    X = np.empty((int(mask.sum()), len(FEATS)), np.float32)
    for q, f in enumerate(FEATS):
        X[:, q] = (D[f] if f in D else F[f])[mask] if f not in fl else fl[f]
    y_next = np.full(int(mask.sum()), -1, np.int8)
    if target is not None:
        r, c = sim.rc(target.x.values, target.y.values); r -= i0; c -= j0
        tm = np.zeros(px.shape, bool); tm[np.clip(r, 0, px.shape[0] - 1), np.clip(c, 0, px.shape[1] - 1)] = True
        tm = ndimage.binary_dilation(tm, structure=np.ones((2 * HIT + 1, 2 * HIT + 1)))
        y_next = tm[mask].astype(np.int8)
    meta = dict(mask=mask, d_all=d_all, known=known, target=target, last=last)
    return X, y_next, S[mask].astype(np.int8), meta


def fire_setup(ev):
    ev = ev.sort_values('t'); ev = ev[ev.t <= ev.t.min() + pd.Timedelta(hours=HOURS - 1)]
    passes = sorted(ev.overpass.unique())
    if len(passes) < 2:
        return None
    pad = int(2600 / sim.RES); r, c = sim.rc(ev.x.values, ev.y.values)
    win = (max(r.min() - pad, 0), min(r.max() + pad, sim.NY), max(c.min() - pad, 0), min(c.max() + pad, sim.NX))
    S, _ = score.scar_footprint(dict(win=win, season=int(ev.season.iloc[0])), ev)
    return ev, passes, win, S


def build(k_n, out):
    v, ids = events(k_n); wx = {}; Xs, yn, ys, meta = [], [], [], []; tt = time.time()
    for q, e in enumerate(ids):
        st = fire_setup(v[v.event == e])
        if st is None:
            continue
        ev, passes, win, S = st; s = int(ev.season.iloc[0])
        if S.sum() < 25:
            continue
        if s not in wx:
            wx.clear(); wx[s] = sim.load_weather(s)
        F, B, cid = fire_static(ev, win)
        for k in range(1, len(passes) + 1):
            X, a, b, m = step_rows(ev, passes, k, F, B, cid, S, win, wx[s], True)
            Xs.append(X); yn.append(a); ys.append(b); meta.append(np.c_[np.full(len(a), e), np.full(len(a), s), np.full(len(a), k)])
        if q % 50 == 0:
            print(q, len(ids), f'{time.time() - tt:.0f}s', flush=True)
    d = pd.DataFrame(np.concatenate(Xs), columns=FEATS); d['y_next'] = np.concatenate(yn); d['y_scar'] = np.concatenate(ys)
    m = np.concatenate(meta); d['event'], d['season'], d['step'] = m[:, 0], m[:, 1], m[:, 2]
    d.to_parquet(out); print('rows', len(d), 'next pos', int((d.y_next == 1).sum()), 'scar pos', int(d.y_scar.sum()))


def _seasons():
    q = os.environ.get('SEASONS')
    return [int(x) if x != 'all' else 'all' for x in q.split(',')] if q else list(range(2017, 2025)) + ['all']


def train(rows, mdir):
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score
    os.makedirs(mdir, exist_ok=True)
    d = pd.concat([pd.read_parquet(f) for f in rows.split(',')], ignore_index=True)
    print('rows', len(d), 'fires', d.event.nunique(), 'steps', d.groupby(['event', 'step']).ngroups)
    params = dict(objective='binary', learning_rate=0.05, num_leaves=63, min_child_samples=300, feature_fraction=0.8, bagging_fraction=0.7, bagging_freq=1,
                  lambda_l2=5.0, num_threads=4, verbose=-1)
    rep = {}
    for head, lab in [('next', 'y_next'), ('scar', 'y_scar')]:
        dd = d[d[lab] >= 0]
        for s in _seasons():          # 'all' = every season, for the forward test on 2025-26; SEASONS=all trains only that one
            tr, te = (dd, dd.iloc[:0]) if s == 'all' else (dd[dd.season != s], dd[dd.season == s])
            m = lgb.train(params, lgb.Dataset(tr[FEATS], tr[lab], categorical_feature=['wc']), num_boost_round=300)
            m.save_model(f'{mdir}/{head}_{s}.txt')
            if len(te):
                p = m.predict(te[FEATS]); rep[f'{head}_{s}'] = dict(n=len(te), auc=round(roc_auc_score(te[lab], p), 4), base=round(float(te[lab].mean()), 4))
                print(head, s, rep[f'{head}_{s}'], flush=True)
        imp = pd.Series(m.feature_importance('gain'), index=FEATS).sort_values(ascending=False); print(head, imp.round(0).head(15).to_string())
        rep[f'{head}_importance'] = imp.round(1).to_dict()
    json.dump(rep, open(f"{mdir}/train_report{'_' + os.environ['SEASONS'] if os.environ.get('SEASONS') else ''}.json", 'w'), indent=1)


class _Fallback(dict):
    """season -> model; seasons without a held-out model (2025-26) get the all-season model"""
    def __init__(self, d, allm):
        super().__init__(d); self.allm = allm
    def __missing__(self, k):
        return self.allm


def score_(mdir, k_n, out):
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score
    M = {h: {s: lgb.Booster(model_file=f'{mdir}/{h}_{s}.txt') for s in range(2017, 2025)} for h in ['next', 'scar']}
    for h in M:
        if os.path.exists(f'{mdir}/{h}_all.txt'):
            M[h] = _Fallback(M[h], lgb.Booster(model_file=f'{mdir}/{h}_all.txt'))
    v, ids = events(k_n); wx = {}; rows = []; tt = time.time()
    for q, e in enumerate(ids):
        st = fire_setup(v[v.event == e])
        if st is None:
            continue
        ev, passes, win, S = st; s = int(ev.season.iloc[0])
        if s not in wx:
            wx.clear(); wx[s] = sim.load_weather(s)
        F, B, cid = fire_static(ev, win)
        for k in range(1, len(passes) + 1):
            X, yn, ys, m = step_rows(ev, passes, k, F, B, cid, S, win, wx[s], False)
            mask, d_all, target, known = m['mask'], m['d_all'], m['target'], m['known']
            pn = np.zeros(S.shape, np.float32); pn[mask] = M['next'][s].predict(X)
            ps = np.zeros(S.shape, np.float32); ps[mask] = M['scar'][s].predict(X)
            top = lambda sc, nn: score.topn(-sc, mask, nn)
            row = dict(event=e, season=s, k=k, n_pass=len(passes), n_prev=len(known), scar_px=int(S.sum()), n_mask=int(mask.sum()))
            if target is not None:
                dmn = np.array([np.hypot(known.x.values - x, known.y.values - y).min() for x, y in zip(target.x, target.y)]); new = target[dmn > 400]
                Pm = mask & (d_all <= PERS); n_p = int(Pm.sum()); n_h = max(n_p // 2, 1)
                n_e = int(round(float(pn[mask].sum())))
                row.update(lead_h=float(X[0, FEATS.index('lead_h')]), n_target=len(target), n_new=len(new), area_pers=n_p, area_exp=n_e,
                           auc_next=roc_auc_score(yn, pn[mask]) if 0 < yn.sum() < len(yn) else np.nan,
                           auc_dist=roc_auc_score(yn, -d_all[mask]) if 0 < yn.sum() < len(yn) else np.nan)
                for nm, A in [('pers', Pm), ('learn', top(pn, n_p)), ('lscar', top(ps, n_p)), ('dist', top(-d_all, n_p)),
                              ('learn_h', top(pn, n_h)), ('dist_h', top(-d_all, n_h)), ('learn_e', top(pn, n_e)), ('dist_e', top(-d_all, n_e))]:
                    row[f'hit_{nm}'] = hits(target, A, win); row[f'hitnew_{nm}'] = hits(new, A, win) if len(new) else 0
            else:
                n = int(S.sum()); n_e = int(round(float(ps[mask].sum())))
                row.update(area_exp_scar=n_e, sor_learn_end=score.soren(top(ps, n), S), sor_dist_end=score.soren(top(-d_all, n), S),
                           sor_learn_free=score.soren(top(ps, n_e), S), sor_dist_free=score.soren(top(-d_all, n_e), S),
                           sor_pers_end=score.soren(mask & (d_all <= PERS), S), area_pers_end=int((mask & (d_all <= PERS)).sum()),
                           auc_scar=roc_auc_score(ys, ps[mask]) if 0 < ys.sum() < len(ys) else np.nan)
            rows.append(row)
        if q % 50 == 0:
            print(q, len(ids), f'{time.time() - tt:.0f}s', flush=True)
    pd.DataFrame(rows).to_parquet(out)


if __name__ == '__main__':
    {'build': lambda: build(sys.argv[2], sys.argv[3]), 'train': lambda: train(sys.argv[2], sys.argv[3]), 'score': lambda: score_(sys.argv[2], sys.argv[3], sys.argv[4])}[sys.argv[1]]()
