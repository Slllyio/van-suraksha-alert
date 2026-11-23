"""Reverse engineering from the scars: a learned burn-footprint model.
For every scarred S-NPP fire (>= 5 ha mapped scar) each burnable 20 m pixel within 2.5 km of the first VIIRS pass gets
features that say where it lies relative to the detections (distance, physics arrival time, wind / front / slope relations,
barriers, earlier burns, fuel, leaf fall, dryness) and the label "in the final scar". LightGBM, leave-one-season-out.
Modes:
  build k/n out.parquet            training rows on an 80 m lattice (shardable)
  train rows.parquet modeldir      one model per held-out season
  score modeldir k/n out.parquet   full 20 m prediction per fire: Sorensen at scar area vs circle and physics, expected-area
                                   footprint, later-pass hits, per-fire AUC
"""
import numpy as np, pandas as pd, sys, json, os, time
from scipy import ndimage
import sim, score
if os.environ.get('SCAR_GROWN'):          # scar thread's grown outlines as the truth / label (grown.py)
    import grown
    score.scar_footprint = grown.scar_footprint
CFG = dict(fuel='rfuel', rfuel_file='rfuel20_loose.npz', leaffall='interp', ros_mult=2, ign_snap=False, wind=False, hours=48, strict=1, barriers=True, pad_m=2600)
R_MAX = 2500.0; CAP = 3000.0; LAT = 4
FEATS = ['d_near', 'd_cent', 't_phys', 'reach', 'rel_w0', 'rel_w24', 'rel_front', 'wc', 'elev', 'slope', 'd_road', 'd_nonveg', 'd_built', 'd_prev',
         'nburn_hist', 'last_burn', 'rf1', 'lf', 'lean', 'forest', 'dd_road', 'dd_nonveg', 'dd_built', 'dd_prev', 'delev', 'drf1', 'dlf', 'dlean',
         'n_first', 'frp_sum', 'frp_max', 'night', 'doy', 'ext_first', 'ws0', 'rh0', 'm1_0', 'temp0']
# FSI thread's barrier layer (Oct 15, prep_barriers2.py), on with BARRIERS=1: stop probability of mapped lines at the pixel and compounded over the
# distinct lines a straight path from the nearest first-pass detection crosses; recurrent scar-edge counts (other seasons only); distances to
# big streams / any road; ground burned earlier this season by the scar thread's polygons (the label rasters miss most of it)
BAR_FEATS = ['pstop_here', 'pstop_path', 'pstop_max_path', 'n_cross', 'recur_c', 'recur_ratio', 'recur_path_mean', 'recur_path_max', 'recur5_cross',
             'd_stream_big', 'dd_stream_big', 'd_road_any', 'dd_road_any', 'd_prevp', 'dd_prevp', 'cross_prevp']
BARRIERS = bool(os.environ.get('BARRIERS'))
if BARRIERS:
    FEATS = FEATS + [f for f in BAR_FEATS if f not in os.environ.get('BAR_DROP', '').split(',')]   # BAR_DROP: ablation (e.g. recur_* use other seasons, future ones included)
if os.environ.get('PHYS_BARRIERS'):        # physics inside the features with another barrier rule (none / ms / p50 / all)
    CFG['barriers'] = {'none': False}.get(os.environ['PHYS_BARRIERS'], os.environ['PHYS_BARRIERS'])
if os.environ.get('PREBURN_POLY'):
    CFG['preburn_poly'] = True
# 500 m cell ids on the 20 m grid, lean dryness score per cell and day, forest fraction per cell
_g = json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))
_c = pd.DataFrame([f['properties'] for f in _g['features']])
_kx, _ky = (_c.x0 // 500).astype(int), (_c.y0 // 500).astype(int); kx0, ky0 = _kx.min(), _ky.min()
_lut = np.full((_ky.max() - ky0 + 1, _kx.max() - kx0 + 1), -1, np.int32); _lut[_ky - ky0, _kx - kx0] = _c.cell_id.values
_pkx = ((sim.X0 + (np.arange(sim.NX) + 0.5) * sim.RES) // 500).astype(int) - kx0
_pky = ((sim.Y0 - (np.arange(sim.NY) + 0.5) * sim.RES) // 500).astype(int) - ky0
_okx = (_pkx >= 0) & (_pkx < _lut.shape[1]); _oky = (_pky >= 0) & (_pky < _lut.shape[0])
CELL = np.full((sim.NY, sim.NX), -1, np.int32)
CELL[np.ix_(_oky, _okx)] = _lut[np.ix_(_pky[_oky], _pkx[_okx])]
FOREST = np.full(int(_c.cell_id.max()) + 2, np.nan); FOREST[_c.cell_id.values] = _c.forest_frac.values
_lp = pd.read_parquet('/mnt/project-files/ratapani/scoring/pipeline_lean_pred_loso_2017_24.parquet')
if os.path.exists('/mnt/project-files/ratapani/scoring/pipeline_lean_pred_2025_26.parquet'):     # forward test: the frozen lean model's 2025-26 scores
    _lp = pd.concat([_lp, pd.read_parquet('/mnt/project-files/ratapani/scoring/pipeline_lean_pred_2025_26.parquet')], ignore_index=True)
_lp['date'] = pd.to_datetime(_lp.date)
LEAN = _lp.pivot(index='date', columns='cell_id', values='pipeline_lean')
NCELL = len(FOREST)


_BE = {}
def burn_end(y):
    if y not in _BE:
        _BE[y] = sim.G[f'burn_end_{y}']
    return _BE[y]


def edt(mask):
    if not mask.any():
        return np.full(mask.shape, CAP, np.float32)
    return np.minimum(ndimage.distance_transform_edt(~mask) * sim.RES, CAP).astype(np.float32)


def lut_cells(vals, cid):
    out = np.full(cid.shape, np.nan, np.float32); m = cid >= 0; out[m] = vals[cid[m]]; return out


def fire_features(ev, wx, lattice=False):
    """Feature arrays over the model window for one fire. Returns (X [n, F], y, meta) with rows = burnable pixels within
    R_MAX of the nearest first-pass detection (every LAT-th row and column when lattice)."""
    o = sim.run_event(ev, wx, CFG, hours=48, scar_fn=score.scar_footprint)
    S, B, T, (i0, i1, j0, j1), t0 = o['S'], o['burnable'], o['T'], o['win'], o['t0']
    s = int(ev.season.iloc[0]); d0 = ev.t.min().dayofyear
    first = ev[ev.overpass == ev.overpass.min()]
    yy, xx = np.mgrid[i0:i1, j0:j1]
    px = (sim.X0 + xx * sim.RES + sim.RES / 2).astype(np.float64); py = (sim.Y0 - yy * sim.RES - sim.RES / 2).astype(np.float64)
    fx, fy = first.x.values, first.y.values
    d_near = np.full(px.shape, np.inf)
    for a, b in zip(fx, fy):
        d_near = np.minimum(d_near, np.hypot(px - a, py - b))
    cx, cy = fx.mean(), fy.mean(); d_cent = np.hypot(px - cx, py - cy)
    bearing = np.degrees(np.arctan2(px - cx, py - cy))
    W, P = wx; pid = P.index[np.argmin(np.hypot(P.x - cx, P.y - cy))]; w = W[pid]
    th = first.t.min().floor('h'); w0 = w.loc[th] if th in w.index else None
    w24 = w.loc[th: th + pd.Timedelta(hours=23)]
    wu, wv = (w24.ws * np.sin(np.radians(w24.waz))).mean(), (w24.ws * np.cos(np.radians(w24.waz))).mean(); waz24 = np.degrees(np.arctan2(wu, wv))
    waz0 = float(w0.waz) if w0 is not None else waz24
    rel_w0 = np.cos(np.radians(bearing - waz0)); rel_w24 = np.cos(np.radians(bearing - waz24))
    ext = 0.0; rel_front = np.full(px.shape, np.nan)
    if len(first) >= 2:
        dx = fx[:, None] - fx[None, :]; dy = fy[:, None] - fy[None, :]; ext = float(np.hypot(dx, dy).max())
        if ext > 100:
            cc = np.cov(np.c_[fx - cx, fy - cy].T); _, V = np.linalg.eigh(cc); faz = np.degrees(np.arctan2(V[0, 1], V[1, 1]))
            rel_front = np.abs(np.cos(np.radians(bearing - faz)))
    wc = sim.WC[i0:i1, j0:j1]; elev = sim.ELEV[i0:i1, j0:j1].astype(np.float32); slope = sim.SLOPE[i0:i1, j0:j1].astype(np.float32)
    road = sim.BARRIER[i0:i1, j0:j1]
    be = burn_end(s)[i0:i1, j0:j1]; prev = (be > -999) & (be < d0 - 26)   # final 25 days after the window end (audit, Oct 15)
    d_road, d_nonveg, d_built, d_prev = edt(road), edt(~np.isin(wc, [10, 20, 30])), edt(wc == 50), edt(prev)
    nb = np.zeros(wc.shape, np.float32)
    for y in range(2017, s):
        nb += (burn_end(y)[i0:i1, j0:j1] > -999)
    last = (burn_end(s - 1)[i0:i1, j0:j1] > -999).astype(np.float32) if s > 2017 else np.full(wc.shape, np.nan, np.float32)
    rf1 = sim._rf_cache(CFG['rfuel_file'])[f'rf_{s}'][0, i0:i1, j0:j1].astype(np.float32)
    mo = ev.t.min().month; band = {12: 0, 1: 0, 2: 1, 3: 2, 4: 3}.get(mo, None)
    if band is not None:
        lf = sim.LEAFFALL[band, i0:i1, j0:j1].astype(np.float32)
        if band < 4:
            nxt = sim.LEAFFALL[band + 1, i0:i1, j0:j1].astype(np.float32); lf = lf + (nxt - lf) * min(ev.t.min().day / 30.0, 1.0)
    else:
        lf = np.ones(wc.shape, np.float32)
    cid = CELL[i0:i1, j0:j1]
    dday = ev.t.min().normalize()
    lv = LEAN.loc[dday].reindex(range(NCELL)).values if dday in LEAN.index else np.full(NCELL, np.nan)
    lean = lut_cells(lv, cid); forest = lut_cells(FOREST, cid)
    rc_, cc_ = sim.rc(np.array([cx]), np.array([cy])); ri = int(np.clip(rc_[0] - i0, 0, wc.shape[0] - 1)); ci = int(np.clip(cc_[0] - j0, 0, wc.shape[1] - 1))
    at = lambda a: float(a[ri, ci])
    disc = (slice(max(ri - 25, 0), ri + 26), slice(max(ci - 25, 0), ci + 26))
    lean_c = float(np.nanmean(lean[disc])) if np.isfinite(lean[disc]).any() else np.nan
    tfirst = (ev.t.min() - t0).total_seconds() / 60
    tph = (T - tfirst) / 60.0; reach = np.isfinite(tph).astype(np.float32); tph = np.where(np.isfinite(tph), tph, 96.0).astype(np.float32)
    F = dict(d_near=d_near, d_cent=d_cent, t_phys=tph, reach=reach, rel_w0=rel_w0, rel_w24=rel_w24, rel_front=rel_front, wc=wc.astype(np.float32), elev=elev, slope=slope,
             d_road=d_road, d_nonveg=d_nonveg, d_built=d_built, d_prev=d_prev, nburn_hist=nb, last_burn=last, rf1=rf1, lf=lf, lean=lean, forest=forest,
             dd_road=d_road - at(d_road), dd_nonveg=d_nonveg - at(d_nonveg), dd_built=d_built - at(d_built), dd_prev=d_prev - at(d_prev), delev=elev - at(elev),
             drf1=rf1 - at(rf1), dlf=lf - at(lf), dlean=lean - lean_c)
    fl = dict(n_first=len(first), frp_sum=float(first.frp.sum()), frp_max=float(first.frp.max()), night=float(first.daynight.iloc[0] == 'N'), doy=d0, ext_first=ext,
              ws0=float(w0.ws) if w0 is not None else np.nan, rh0=float(w0.rh) if w0 is not None else np.nan, m1_0=float(w0.m1) if w0 is not None else np.nan,
              temp0=float(w0['T']) if w0 is not None else np.nan)
    mask = B & (d_near <= R_MAX)
    if lattice:
        mask &= (yy % LAT == 0) & (xx % LAT == 0)
    if BARRIERS:
        F.update(barrier_features(mask, wc.shape, (i0, i1, j0, j1), s, d0, fx, fy, at))
    X = np.empty((int(mask.sum()), len(FEATS)), np.float32)
    for k, f in enumerate(FEATS):
        X[:, k] = F[f][mask] if f in F else fl[f]
    meta = dict(S=S, B=B, mask=mask, win=(i0, i1, j0, j1), t0=t0, d_near=d_near, tph=tph, season=s)
    return X, S[mask].astype(np.int8), meta


def barrier_features(mask, shape, win, s, d0, fx, fy, at):
    """BAR_FEATS arrays over the window (NaN outside mask for the path features)."""
    i0, i1, j0, j1 = win
    PS = sim.bar2('pstop_d')[i0:i1, j0:j1]
    RC = sim.bar2(f'recur_c_{s}')[i0:i1, j0:j1].astype(np.float32); RN = sim.bar2(f'recur_n_{s}')[i0:i1, j0:j1].astype(np.float32)
    RR = RC / np.maximum(RN, 1); R5 = (RC >= 5) & (RR >= 0.5)
    pdy = sim.bar2(f'pday_{s}')[i0:i1, j0:j1]; prevp = (pdy > -999) & (pdy < d0 - 2)
    d_sb, d_ra, d_pp = edt(sim.bar2('stream_big')[i0:i1, j0:j1]), edt(sim.bar2('road_any')[i0:i1, j0:j1]), edt(prevp)
    F = dict(pstop_here=PS, recur_c=RC, recur_ratio=RR, d_stream_big=d_sb, dd_stream_big=d_sb - at(d_sb), d_road_any=d_ra, dd_road_any=d_ra - at(d_ra),
             d_prevp=d_pp, dd_prevp=d_pp - at(d_pp))
    # straight path from the nearest first-pass detection to the pixel, 96 samples (<= 1.3 px apart within R_MAX; lines are 3 px wide after the max filter)
    mi, mj = np.nonzero(mask)
    rf_, cf_ = sim.rc(fx, fy); rf_ = np.clip(rf_ - i0, 0, shape[0] - 1); cf_ = np.clip(cf_ - j0, 0, shape[1] - 1)
    kk = ((mi[:, None] - rf_[None, :]) ** 2 + (mj[:, None] - cf_[None, :]) ** 2).argmin(1); r0, c0 = rf_[kk], cf_[kk]
    t = np.linspace(0, 1, 96, dtype=np.float32)
    out = {k: np.zeros(len(mi), np.float32) for k in ['pstop_path', 'pstop_max_path', 'n_cross', 'recur_path_mean', 'recur_path_max', 'recur5_cross', 'cross_prevp']}
    for a in range(0, len(mi), 20000):
        b = slice(a, a + 20000)
        pr = np.rint(r0[b, None] + (mi[b] - r0[b])[:, None] * t).astype(np.int32); pc = np.rint(c0[b, None] + (mj[b] - c0[b])[:, None] * t).astype(np.int32)
        v = PS[pr, pc]; on = v > 0; start = on.copy(); start[:, 1:] &= ~on[:, :-1]
        out['pstop_path'][b] = 1 - np.prod(np.where(start, 1 - v, 1.0), axis=1); out['pstop_max_path'][b] = v.max(1); out['n_cross'][b] = start.sum(1)
        rv = RC[pr, pc]; out['recur_path_mean'][b] = rv.mean(1); out['recur_path_max'][b] = rv.max(1)
        r5 = R5[pr, pc]; s5 = r5.copy(); s5[:, 1:] &= ~r5[:, :-1]; out['recur5_cross'][b] = s5.sum(1)
        out['cross_prevp'][b] = prevp[pr, pc].any(1)
    for k, vals in out.items():
        arr = np.full(shape, np.nan, np.float32); arr[mi, mj] = vals; F[k] = arr
    return F


def events(k_n=None):
    v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); v = v[v.t.dt.month <= 6]
    ok = pd.read_parquet(f'{sim.DATA}/rundir.parquet').event.values      # the 1,223 fires with a mapped scar >= 5 ha
    v = v[v.event.isin(ok)]
    if os.environ.get('SCAR_GROWN'):
        v = v[v.event.isin(list(grown.load().keys()))]
    ids = sorted(v.event.unique())
    if k_n:
        k, n = map(int, k_n.split('/')); ids = ids[k::n]
    return v, ids


def build(k_n, out):
    v, ids = events(k_n); wx = {}; Xs, ys, ev_ids, seas = [], [], [], []; tt = time.time()
    for k, e in enumerate(ids):
        ev = v[v.event == e].sort_values('t'); s = int(ev.season.iloc[0])
        if s not in wx:
            wx.clear(); wx[s] = sim.load_weather(s)
        X, y, meta = fire_features(ev, wx[s], lattice=True)
        Xs.append(X); ys.append(y); ev_ids.append(np.full(len(y), e)); seas.append(np.full(len(y), s))
        if k % 50 == 0:
            print(k, len(ids), f'{time.time() - tt:.0f}s', flush=True)
    d = pd.DataFrame(np.concatenate(Xs), columns=FEATS); d['y'] = np.concatenate(ys); d['event'] = np.concatenate(ev_ids); d['season'] = np.concatenate(seas)
    d.to_parquet(out); print('rows', len(d), 'positives', int(d.y.sum()))


def _seasons():
    q = os.environ.get('SEASONS')
    return [int(x) if x != 'all' else 'all' for x in q.split(',')] if q else list(range(2017, 2025)) + ['all']


def train(rows, mdir):
    import lightgbm as lgb
    os.makedirs(mdir, exist_ok=True)
    d = pd.concat([pd.read_parquet(f) for f in rows.split(',')], ignore_index=True)
    print('rows', len(d), 'fires', d.event.nunique(), 'pos rate', round(d.y.mean(), 4))
    params = dict(objective='binary', learning_rate=0.05, num_leaves=63, min_child_samples=300, feature_fraction=0.8, bagging_fraction=0.7, bagging_freq=1,
                  lambda_l2=5.0, num_threads=4, verbose=-1)
    rep = {}
    for s in _seasons():          # 'all' = every season, for the forward test on 2025-26; SEASONS=all trains only that one
        tr, te = (d, d.iloc[:0]) if s == 'all' else (d[d.season != s], d[d.season == s])
        ds = lgb.Dataset(tr[FEATS], tr.y, categorical_feature=['wc'])
        m = lgb.train(params, ds, num_boost_round=400)
        m.save_model(f'{mdir}/loso_{s}.txt')
        if len(te):
            from sklearn.metrics import roc_auc_score, log_loss
            p = m.predict(te[FEATS]); rep[s] = dict(n=len(te), auc=round(roc_auc_score(te.y, p), 4), logloss=round(log_loss(te.y, p), 4), base=round(float(te.y.mean()), 4))
            print(s, rep[s], flush=True)
    imp = pd.Series(m.feature_importance('gain'), index=FEATS).sort_values(ascending=False); print(imp.round(0).to_string())
    json.dump(dict(holdout=rep, importance_gain_last=imp.round(1).to_dict()), open(f"{mdir}/train_report{'_' + os.environ['SEASONS'] if os.environ.get('SEASONS') else ''}.json", 'w'), indent=1)


def score_(mdir, k_n, out):
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score
    models = {s: lgb.Booster(model_file=f'{mdir}/loso_{s}.txt') for s in range(2017, 2025)}
    if os.path.exists(f'{mdir}/loso_all.txt'):
        import foot_restart as _fr
        models = _fr._Fallback(models, lgb.Booster(model_file=f'{mdir}/loso_all.txt'))
    v, ids = events(k_n); wx = {}; rows = []; tt = time.time()
    for k, e in enumerate(ids):
        ev = v[v.event == e].sort_values('t'); s = int(ev.season.iloc[0])
        if s not in wx:
            wx.clear(); wx[s] = sim.load_weather(s)
        X, y, meta = fire_features(ev, wx[s])
        S, B, mask, (i0, i1, j0, j1), t0, d_near, tph = meta['S'], meta['B'], meta['mask'], meta['win'], meta['t0'], meta['d_near'], meta['tph']
        p = np.zeros(S.shape, np.float32); p[mask] = models[s].predict(X)
        n = int(S.sum())
        top = lambda sc, nn: score.topn(-sc, mask, nn)          # highest score first
        Pl, Pc, Pp = top(p, n), top(-d_near, n), top(-tph, n)
        n_pred = int(round(float(p[mask].sum())))
        Pl_f, Pc_f, Pp_f = top(p, n_pred), top(-d_near, n_pred), top(-tph, n_pred)
        P48 = mask & (tph <= 48)
        # run direction: compass bearing from the first-pass centroid to the centroid of a footprint (truth = the scar)
        first_ = ev[ev.overpass == ev.overpass.min()]; rf_, cf_ = sim.rc(first_.x.values, first_.y.values); fx_, fy_ = (cf_ - j0).mean(), -(rf_ - i0).mean()
        def runaz(M):
            if not M.any(): return np.nan, np.nan
            ys_, xs_ = np.nonzero(M); vx, vy = xs_.mean() - fx_, -ys_.mean() - fy_
            return float((np.degrees(np.arctan2(vx, vy)) + 360) % 360), float(np.hypot(vx, vy) * sim.RES)
        dirs = {}
        for nm_, M in [('scar', S), ('learn', Pl), ('phys', Pp), ('learn_free', Pl_f), ('circle', Pc)]:
            dirs[f'az_{nm_}'], dirs[f'run_m_{nm_}'] = runaz(M)
        row = dict(event=e, season=s, scar_px=n, n_pred=n_pred, n_mask=int(mask.sum()), n_pass=ev.overpass.nunique(), n_first=int(X[0, FEATS.index('n_first')]), **dirs,
                   sor_learn=score.soren(Pl, S), sor_circle=score.soren(Pc, S), sor_phys=score.soren(Pp, S),
                   sor_learn_free=score.soren(Pl_f, S), sor_circle_free=score.soren(Pc_f, S), sor_phys_free=score.soren(Pp_f, S), sor_phys48=score.soren(P48, S), area48=int(P48.sum()),
                   auc_learn=roc_auc_score(y, p[mask]) if 0 < y.sum() < len(y) else np.nan, auc_circle=roc_auc_score(y, -d_near[mask]) if 0 < y.sum() < len(y) else np.nan,
                   auc_phys=roc_auc_score(y, -tph[mask]) if 0 < y.sum() < len(y) else np.nan)
        # later passes: detections >= 6 h after the first, within 72 h; hit = footprint has a pixel within 250 m
        later = ev[(ev.t >= ev.t.min() + pd.Timedelta(hours=6)) & (ev.t <= ev.t.min() + pd.Timedelta(hours=72))]
        if len(later):
            hl = hc = hp = nl = 0
            r, c = sim.rc(later.x.values, later.y.values); r -= i0; c -= j0
            for a, b in zip(r, c):
                sl = (slice(max(a - 12, 0), a + 13), slice(max(b - 12, 0), b + 13))
                nl += 1; hl += bool(Pl_f[sl].any()); hc += bool(Pc_f[sl].any()); hp += bool(Pp_f[sl].any())
            row.update(n_later=nl, hit_learn=hl, hit_circle=hc, hit_phys=hp)
        rows.append(row)
        if k % 50 == 0:
            print(k, len(ids), f'{time.time() - tt:.0f}s', flush=True)
    pd.DataFrame(rows).to_parquet(out)


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'build':
        build(sys.argv[2], sys.argv[3])
    elif mode == 'train':
        train(sys.argv[2], sys.argv[3])
    elif mode == 'score':
        score_(sys.argv[2], sys.argv[3], sys.argv[4])
