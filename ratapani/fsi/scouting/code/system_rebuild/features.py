"""Square-day feature tables for the pooled all-MP model (round 22).
For a season y, `season_iter(y, cfg)` walks the days 1 Jan..2 Jun on the full 500 m MP grid and yields, for every issue
day t (13 Feb..30 May), the feature matrix of all union cells U (418,642 squares in any division grid), the point label
(fire on t+1 or t+2, type 0, likely control burns dropped, targets 15 Feb..31 May) and, if asked, a footprint soft label.

Baseline feature set ('B0', a stand-in for the PC model; PC's own feature code is not in this container):
  live fires (type 0, 3 satellites): fire square-days in boxes of radius 0/1/3/7/15/50 cells over 1-30 days, days since
  the last fire in radius 0/1/3/7, season-to-date counts; division share of squares burning today / last 7 days;
  history (5 prior seasons, 15 Feb-31 May fire days): counts at radius 0/1/3/7, years burned at 0/1, last season at 1,
  mean day-of-year of past fires; early (1 Jan-14 Feb) burns this season at 0/1; calendar: day of year, division
  day-of-year fire rate (prior seasons, 7-day smoothed), history x rate; dryness (HLS NDVI/NDMI/NBR latest 10-day step,
  change since 2 Jan, clear %); division id (categorical).
Options in cfg switch on the satellite/GIS layers (see each block)."""
import numpy as np, pandas as pd
from scipy.ndimage import uniform_filter
import common as C

RADII = (0, 1, 3, 7, 10, 15, 50)
WINS = {0: (1, 2, 3, 7, 30), 1: (1, 2, 3, 7, 30), 3: (1, 3, 7, 14), 7: (1, 3, 7), 10: (7,), 15: (1, 7), 50: (1, 7)}
DSL_R = (0, 1, 3, 7)
_CACHE = {}


def base():
    if 'U' not in _CACHE:
        U = C.union_cells(); G = C.grids_active()
        home = np.full(len(U), -1, np.int16); names = sorted(G)
        for k, nm in enumerate(names):
            r, c = G[nm]; idx = np.searchsorted(U, r * C.W + c); home[idx[home[idx] < 0]] = k
        Uf = np.unique(np.concatenate([r * C.W + c for r, c in C.grids().values()]))
        _CACHE['fidx'] = np.searchsorted(Uf, U)   # position of active cells in the full 87-division union (looks/static files)
        _CACHE.update(U=U, ur=(U // C.W).astype(np.int32), uc=(U % C.W).astype(np.int32), home=home, divnames=names)
    return _CACHE


def box(a, r):
    if r == 0: return a
    return np.round(uniform_filter(a, 2 * r + 1, mode='constant') * (2 * r + 1) ** 2, 3)


def dup_index():
    """det_all indices of same-pass duplicate detections (second member of each pair, s2_looks.py)."""
    if 'dup' not in _CACHE:
        import os
        fn = C.SC + 'dup_det_all.parquet'
        if not os.path.exists(fn):
            g = pd.read_parquet(C.SC + 'det_geom.parquet', columns=['sat', 'utc', 'latitude', 'longitude'])
            d = pd.read_parquet(C.SC + 'dup_det.parquet').det.values; g = g.loc[d]
            a = C.load_det()[['sat', 'utc', 'latitude', 'longitude']].reset_index()
            m = a.merge(g, on=['sat', 'utc', 'latitude', 'longitude'])
            m[['index']].to_parquet(fn)
        _CACHE['dup'] = pd.read_parquet(fn)['index'].values
    return _CACHE['dup']


def det_filter(v, cfg, live=True):
    v = v[v.type == 0]
    if cfg.get('drop_low') and live: v = v[v.confidence != 'l']
    if cfg.get('dedup'): v = v[~v.index.isin(dup_index())]
    if cfg.get('sats'): v = v[v.sat.isin(cfg['sats'])]
    return v


def grid_rc(v, cfg):
    """row/col of detections, optionally after removing per-satellite geolocation offsets (static-site calibration,
    squares_v2_pooled.md: relative to S-NPP; NOAA-20 day +52 E / -93 N, night -20 E / +79 N; NOAA-21 day -57 E / -25 N,
    night +27 E / -44 N, metres)."""
    if not cfg.get('offsets'): return v.row.values, v.col.values
    off = {('jpss1', 'D'): (52, -93), ('jpss1', 'N'): (-20, 79), ('noaa21', 'D'): (-57, -25), ('noaa21', 'N'): (27, -44)}
    dx = np.array([off.get((s, d), (0, 0))[0] for s, d in zip(v.sat.values, v.daynight.values)])
    dy = np.array([off.get((s, d), (0, 0))[1] for s, d in zip(v.sat.values, v.daynight.values)])
    x = v.x.values - dx; y = v.y.values - dy
    return np.floor((C.Y1 - y) / C.S).astype(int), np.floor((x - C.X0) / C.S).astype(int)


def raster_days(v, days, cfg, weight=None):
    """(n_days, H, W) float32 grid of fire square-days (binary) or footprint weights if cfg['fp'] (capped at 1)."""
    di = pd.Series(np.arange(len(days)), index=days)
    v = v[v.ld.isin(days)]
    R = np.zeros((len(days), C.H, C.W), np.float32)
    if len(v) == 0: return R
    if cfg.get('fp_feats') and weight is not None:
        fp = weight  # DataFrame of (det index, row, col, w) footprint fractions
        f = fp[fp.det.isin(v.index)]
        dd = di[v.ld.loc[f.det].values].values
        ok = (f.row.values >= 0) & (f.row.values < C.H) & (f.col.values >= 0) & (f.col.values < C.W)
        np.add.at(R, (dd[ok], f.row.values[ok], f.col.values[ok]), f.w.values[ok].astype(np.float32))
        np.minimum(R, 1, out=R)
    else:
        r, c = grid_rc(v, cfg); ok = (r >= 0) & (r < C.H) & (c >= 0) & (c < C.W)
        R[di[v.ld.values[ok]].values, r[ok], c[ok]] = 1
    return R


def history(y, cfg, V, fpw=None):
    """Prior-season (y-5..y-1, >=2014) 15 Feb-31 May fire-day counts (type 0, ctrl dropped) on the full grid."""
    yrs = [p for p in range(y - 5, y) if p >= 2014]
    out = []; tot = []
    for p in yrs:
        v = V[(V.season == p) & (V.type == 0) & ~V.ctrl]
        if cfg.get('dedup'): v = v[~v.index.isin(dup_index())]
        if cfg.get('hist_snpp'): v = v[v.sat == 'snpp']
        md = v.ld.dt.month * 100 + v.ld.dt.day; v = v[(md >= 215) & (md <= 531)]
        if cfg.get('offsets'):
            r_, c_ = grid_rc(v, cfg); v = v.assign(row=r_, col=c_)
        if cfg.get('fp_feats') and fpw is not None:   # footprint weights, capped at 1 per square-day
            f = fpw[fpw.det.isin(v.index)]; f = f.assign(ld=v.ld.loc[f.det].values).groupby(['row', 'col', 'ld']).w.sum().clip(upper=1).reset_index()
            f = f[(f.row >= 0) & (f.row < C.H) & (f.col >= 0) & (f.col < C.W)]
            hd = np.zeros((C.H, C.W), np.float32); dsum = np.zeros((C.H, C.W), np.float32)
            np.add.at(hd, (f.row.values, f.col.values), f.w.values.astype(np.float32)); np.add.at(dsum, (f.row.values, f.col.values), (f.w * f.ld.dt.dayofyear).values.astype(np.float32))
            v = v.drop_duplicates(['row', 'col', 'ld']); v = v[(v.row >= 0) & (v.row < C.H) & (v.col >= 0) & (v.col < C.W)]
            out.append((p, hd, dsum, v)); tot.append(hd.sum()); continue
        v = v.drop_duplicates(['row', 'col', 'ld'])
        hd = np.zeros((C.H, C.W), np.float32); dsum = np.zeros((C.H, C.W), np.float32)
        ok = (v.row >= 0) & (v.row < C.H) & (v.col >= 0) & (v.col < C.W); v = v[ok]
        np.add.at(hd, (v.row.values, v.col.values), 1); np.add.at(dsum, (v.row.values, v.col.values), v.ld.dt.dayofyear.values.astype(np.float32))
        out.append((p, hd, dsum, v)); tot.append(hd.sum())
    if cfg.get('hist_norm'):   # per-season normalisation: each prior season scaled to the mean season total
        m = np.mean(tot)
        out = [(p, hd * (m / max(t, 1)), ds, v) for (p, hd, ds, v), t in zip(out, tot)]
    return out


def season_iter(y, cfg, V, static=None, looks=None, fpw=None, need_fp_label=False):
    B = base(); U, ur, uc, home = B['U'], B['ur'], B['uc'], B['home']; nU = len(U); ndiv = len(B['divnames'])
    days = pd.date_range(f'{y}-01-01', f'{y}-06-02'); nd = len(days)
    Vy = V[V.season == y]
    vl = det_filter(Vy, cfg)
    FR = raster_days(vl, days, cfg, fpw)
    # live box sums at U, cumulative over days
    CS = {}; BOXD = {}
    for r in RADII:
        a = np.empty((nd, nU), np.float32)
        for d in range(nd): a[d] = box(FR[d], r)[ur, uc]
        BOXD[r] = a if r in DSL_R else None
        CS[r] = np.vstack([np.zeros((1, nU), np.float32), np.cumsum(a, 0)])
    EXTRA = {}
    if cfg.get('conf_feats') or cfg.get('frp_feats'):
        di0 = pd.Series(np.arange(nd), index=days); q = vl[vl.ld.isin(days)]
        r_, c_ = grid_rc(q, cfg); okq = (r_ >= 0) & (r_ < C.H) & (c_ >= 0) & (c_ < C.W); q = q[okq]; r_, c_ = r_[okq], c_[okq]; dq = di0[q.ld.values].values
        if cfg.get('conf_feats'):
            HI = np.zeros((nd, C.H, C.W), np.float32); HI[dq[q.confidence.values != 'l'], r_[q.confidence.values != 'l'], c_[q.confidence.values != 'l']] = 1
            for r in (0, 1, 3):
                a = np.stack([box(HI[d], r)[ur, uc] for d in range(nd)]); EXTRA[f'hi_r{r}'] = np.vstack([np.zeros((1, nU), np.float32), np.cumsum(a, 0)])
            del HI
        if cfg.get('frp_feats'):
            FS = np.zeros((nd, C.H, C.W), np.float32); np.add.at(FS, (dq, r_, c_), q.frp.values.astype(np.float32))
            FM = np.zeros((nd, C.H, C.W), np.float32); np.maximum.at(FM, (dq, r_, c_), q.frp.values.astype(np.float32))
            from scipy.ndimage import maximum_filter as _mf
            for r in (1, 3):
                a = np.stack([box(FS[d], r)[ur, uc] for d in range(nd)]); EXTRA[f'frps_r{r}'] = np.vstack([np.zeros((1, nU), np.float32), np.cumsum(a, 0)])
            EXTRA['frpmax_r1'] = np.stack([_mf(FM[d], 3)[ur, uc] for d in range(nd)])
            del FS, FM
    if cfg.get('nsat_feat'):
        EXTRA['nsat'] = np.array([Vy[Vy.ld == dd].sat.nunique() for dd in days], np.float32)
    # division activity (share of division U-cells burning)
    ncell = np.bincount(home, minlength=ndiv).astype(np.float32)
    divday = np.stack([np.bincount(home, weights=(BOXD[0][d] > 0), minlength=ndiv) / np.maximum(ncell, 1) for d in range(nd)])
    divcs = np.vstack([np.zeros((1, ndiv)), np.cumsum(divday, 0)])
    # targets (point labels; type 0 any confidence, all satellites, ctrl dropped, 15 Feb-31 May)
    vt = Vy[(Vy.type == 0) & ~Vy.ctrl]; md = vt.ld.dt.month * 100 + vt.ld.dt.day; vt = vt[(md >= 215) & (md <= 531)]
    FT = np.zeros((nd, nU), bool); di = pd.Series(np.arange(nd), index=days); idx = np.searchsorted(U, vt.row.values * C.W + vt.col.values)
    ok = (idx < nU) & (U[np.minimum(idx, nU - 1)] == vt.row.values * C.W + vt.col.values) & vt.ld.isin(days).values
    FT[di[vt.ld.values[ok]].values, idx[ok]] = True
    FTs = None
    if need_fp_label and fpw is not None:
        f = fpw[fpw.det.isin(vt.index)]; ld = vt.ld.loc[f.det].values
        ii = np.searchsorted(U, f.row.values * C.W + f.col.values); okk = (ii < nU) & (U[np.minimum(ii, nU - 1)] == f.row.values * C.W + f.col.values) & pd.Index(ld).isin(days)
        FTs = np.zeros((nd, nU), np.float32); np.add.at(FTs, (di[ld[okk]].values, ii[okk]), f.w.values[okk]); np.minimum(FTs, 1, out=FTs)
    # history
    H_ = history(y, cfg, V, fpw)
    hd = sum(h for _, h, _, _ in H_) if H_ else np.zeros((C.H, C.W), np.float32)
    ds = sum(d for _, _, d, _ in H_) if H_ else np.zeros((C.H, C.W), np.float32)
    hist = {f'h_r{r}': box(hd, r)[ur, uc] for r in (0, 1, 3, 7)}
    hist['hy_r0'] = sum((h > 0).astype(np.float32) for _, h, _, _ in H_)[ur, uc] if H_ else np.zeros(nU, np.float32)
    hist['hy_r1'] = sum((box(h, 1) > 0.5).astype(np.float32) for _, h, _, _ in H_)[ur, uc] if H_ else np.zeros(nU, np.float32)
    hist['hlast_r1'] = box(H_[-1][1], 1)[ur, uc] if H_ else np.zeros(nU, np.float32)
    b3 = box(hd, 3); hist['h_doy'] = np.where(b3[ur, uc] > 0, box(ds, 3)[ur, uc] / np.maximum(b3[ur, uc], 1e-6), np.nan).astype(np.float32)
    # division day-of-year climatology (share of the division's U cells burning that day, prior seasons, 7-day smooth)
    rate = np.zeros((ndiv, 367)); cnt = np.zeros(367)
    for p, h, _, v in H_:
        ii = np.searchsorted(U, v.row.values * C.W + v.col.values); okk = (ii < nU) & (U[np.minimum(ii, nU - 1)] == v.row.values * C.W + v.col.values)
        np.add.at(rate, (home[ii[okk]], v.ld.dt.dayofyear.values[okk]), 1)
        dd = pd.date_range(f'{p}-02-15', f'{p}-05-31').dayofyear; cnt[dd] += 1
    rate = rate / np.maximum(cnt, 1) / np.maximum(ncell, 1)[:, None]
    rate = pd.DataFrame(rate.T).rolling(7, center=True, min_periods=1).mean().values.T
    # dryness
    dz = np.load(C.P + f'ratapani/mp_grid/dryness/mp_dry_{y}.npz'); dcell = dz['cells']; X = dz['X'].astype(np.float32)
    X[(X == -9999) | (np.abs(X) > 10000)] = np.nan
    steps = pd.DatetimeIndex(dz['steps']); di_ = np.searchsorted(U, dcell); okd = (di_ < nU) & (U[np.minimum(di_, nU - 1)] == dcell)
    DRY = np.full((len(steps), nU, 4), np.nan, np.float32); DRY[:, di_[okd]] = X[:, okd]
    # early burns this season (1 Jan-14 Feb), radius 0/1
    eidx = days < pd.Timestamp(f'{y}-02-15')
    early0 = (BOXD[0][eidx] > 0).sum(0).astype(np.float32); early1 = (BOXD[1][eidx] > 0).sum(0).astype(np.float32)
    last = {r: np.full(nU, -999.0, np.float32) for r in DSL_R}
    names = None
    for d in range(nd):
        for r in DSL_R: last[r] = np.where(BOXD[r][d] > 0, d, last[r])
        dt = days[d]; mdd = dt.month * 100 + dt.day
        if not (213 <= mdd <= 530): continue
        F = {}
        for r, ws in WINS.items():
            for w in ws: F[f'f_r{r}_w{w}'] = CS[r][d + 1] - CS[r][max(0, d + 1 - w)]
        for r in (0, 1, 7): F[f'std_r{r}'] = CS[r][d + 1]
        for r in DSL_R: F[f'dsl_r{r}'] = np.minimum(d - last[r], 200).astype(np.float32)
        F['div_today'] = divday[d][home].astype(np.float32); F['div_w7'] = (divcs[d + 1] - divcs[max(0, d - 6)])[home].astype(np.float32)
        F.update(hist); F['early_r0'] = early0; F['early_r1'] = early1
        doy = dt.dayofyear; F['doy'] = np.full(nU, doy, np.float32)
        F['div_rate'] = rate[home, doy].astype(np.float32); F['calhist'] = (hist['h_r1'] * F['div_rate']).astype(np.float32)
        k = max(0, np.searchsorted(steps, dt, side='right') - 1)
        for j, nm in enumerate(('ndvi', 'ndmi', 'nbr', 'clear')): F[nm] = DRY[k, :, j]
        F['d_ndmi'] = DRY[k, :, 1] - DRY[0, :, 1]; F['d_ndvi'] = DRY[k, :, 0] - DRY[0, :, 0]
        F['div'] = home.astype(np.float32)
        for r in (0, 1, 3):
            if f'hi_r{r}' in EXTRA:
                for w in (1, 3, 7): F[f'hi_r{r}_w{w}'] = EXTRA[f'hi_r{r}'][d + 1] - EXTRA[f'hi_r{r}'][max(0, d + 1 - w)]
        for r in (1, 3):
            if f'frps_r{r}' in EXTRA:
                for w in (1, 3, 7): F[f'frps_r{r}_w{w}'] = EXTRA[f'frps_r{r}'][d + 1] - EXTRA[f'frps_r{r}'][max(0, d + 1 - w)]
        if 'frpmax_r1' in EXTRA:
            F['frpmax_r1_w1'] = EXTRA['frpmax_r1'][d]; F['frpmax_r1_w3'] = EXTRA['frpmax_r1'][max(0, d - 2):d + 1].max(0)
        if 'nsat' in EXTRA:
            F['nsat_w1'] = np.full(nU, EXTRA['nsat'][d], np.float32); F['nsat_w7'] = np.full(nU, EXTRA['nsat'][max(0, d - 6):d + 1].mean(), np.float32)
        if static is not None:
            for nm, a in static.items(): F[nm] = a
        if looks is not None:
            for nm, a in looks.day(d).items(): F[nm] = a
            g = looks.good_cs
            for r in (0, 1, 3):
                lr = last[r].astype(int); since = np.where(lr >= 0, g[d + 1] - g[np.clip(lr + 1, 0, nd), np.arange(nU)], g[d + 1])
                F[f'goodlooks_since_r{r}'] = np.minimum(since, 400).astype(np.float32)
            e7 = F['lk_eff7']
            F['f_r1_w7_perlook'] = F['f_r1_w7'] / np.maximum(e7, 0.1); F['f_r3_w7_perlook'] = F['f_r3_w7'] / np.maximum(e7, 0.1)
            F['f_r0_w7_perlook'] = F['f_r0_w7'] / np.maximum(e7, 0.1)
        if names is None: names = list(F)
        X_ = np.empty((nU, len(names)), np.float32)
        for j, nm in enumerate(names): X_[:, j] = F[nm]
        yl = FT[d + 1] | FT[d + 2]
        ys = np.maximum(FTs[d + 1], FTs[d + 2]) if FTs is not None else None
        yield dict(t=dt, X=X_, y=yl, ys=ys, names=names)
