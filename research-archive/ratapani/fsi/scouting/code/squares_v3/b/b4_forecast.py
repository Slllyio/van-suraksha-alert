"""B step 4: forecast tests in Ratapani with seasons held out. Do per-fire speeds beat class speeds?

Every forecast is issued at a VIIRS pass time t_i and uses only detections and pairs finished by t_i. Speeds:
  same   = one speed for all fires (flat class model, other seasons)
  class  = class mean (forest type, month, size/FRP/age of the fire's own looks), other seasons
  fire   = class x the fire's posterior factor from ITS pairs finished by t_i (b_post shrinkage, tau and DE from other seasons)
(a) Burned by the next mid-fire photo (~10:30 IST; 340 photos; issue = last VIIRS look >= 2 h before). Photo pixels lie
    inside the final scar; a pixel is forecast burned if its distance to the nearest pre-issue VIIRS footprint (scan x track
    box) is <= R. R = v x clock hours (issue -> photo) [+120 m: part A's centre-behind-front shift]. Baselines: persistence
    (R = 0), 600 m ring (within 600 m of the pre-issue points), dot kernel (sum exp(-d/400 m) exp(-dt/12 h) >= threshold,
    threshold fitted on the other seasons), blend map built from pre-issue looks + continuity's 15 m/h tail (walking
    distance replaced by straight distance) [= same speed 15 m/h], and the blend reconstruction from ALL looks (not a
    forecast; reference only). Scores: pixel accuracy, burned-share error, AUC where a score exists.
(b) Next VIIRS pass. (i) Where: at each look slot, the next slot >= 6 h later; reach R = 375 m + v x clock hours from
    every point seen so far, speeds scaled so all methods have the same mean reach (equal area budget). Capture of all /
    NEW (> 400 m from all earlier) next-pass points. Plus the 600 m ring around the latest slot and the dot kernel at the
    same area as the class method (area on a 50 m grid). (ii) How many: the first VIIRS pass that VIEWED the fire >= 6 h
    after issue (silent passes count as 0; r19_track viewing passes). Poisson regression on log(issue count), day/night of
    target, target pixel width, gap, then + log(class speed) / + log(per-fire speed); held-out deviance and AUC of
    "flags at all".
(c) Final scar size (v2 outline, ha) from the first 24 h of detections (fires with a look after 24 h): log-linear fits on
    the other seasons using the 600 m ring area, the dot-kernel (400 m) area, and the growth term
    L_last x v x (median remaining clock hours of other-season fires). Held-out R2 of log area.
95% ranges: bootstrap over fires. Out: results/b4_*.json/csv, fig_b4_forecast.png"""
import sys, os, json, pickle
import numpy as np, pandas as pd
from scipy.spatial import cKDTree
from sklearn.metrics import roc_auc_score
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b_lib import *
from b_post import models, ratapani_meta, de_of, default_rows
from b1_hier import load, class_mean, nuisance
rng = np.random.default_rng(31)
IST = pd.Timedelta(hours=5.5)
def habs(t): return ((pd.to_datetime(pd.Series(t)) + IST) - pd.Timestamp('2017-01-01')).dt.total_seconds().values / 3600

# ------------------------------------------------------------------ per-pair pieces for posteriors at any issue time
def pair_pieces():
    O, _ = load(); P = O[O.fire_rt >= 0].copy(); M = models(); out = []
    meta = ratapani_meta().set_index('fire')
    for s, g in P.groupby(P.fire_rt.map(meta.season)):
        if s not in M: continue
        for lab, cmk in [('class', 'cm'), ('same', 'cmf')]:
            cm = M[s][cmk]; mu = class_mean(g, cm); m = mu * g.K.values; w = 1 / g.sig2.values; yc = g.y.values - nuisance(g, cm)
            out.append(pd.DataFrame(dict(fire=g.fire_rt.values, tB=g.tB.values, lab=lab, a=w * yc * m, b=w * m * m, mu=mu)))
    return pd.concat(out, ignore_index=True)

class Speeds:
    def __init__(self):
        self.Pp = pair_pieces(); self.M = models(); meta = ratapani_meta()
        self.meta = meta.set_index('fire'); self.mu0 = {}
        for s, m in meta.groupby('season'):
            if s not in self.M: continue
            dr = default_rows(m)
            for lab, cmk in [('class', 'cm'), ('same', 'cmf')]:
                v = pd.Series(class_mean(dr, self.M[s][cmk]), index=dr.fire).groupby(level=0).mean()
                for f, x in v.items(): self.mu0[(f, lab)] = x
        self.g = {k: g.sort_values('tB') for k, g in self.Pp.groupby(['fire', 'lab'])}
    def get(self, fire, t_issue):
        """dict same / class / fire speeds (m/h daily mean) and the reliability B, using pairs with tB <= t_issue"""
        s = int(self.meta.season[fire]); M = self.M[s]
        out = {'same': self.mu0[(fire, 'same')], 'class': self.mu0[(fire, 'class')], 'B': 0.0, 'n_pairs': 0}
        g = self.g.get((fire, 'class'))
        if g is not None:
            k = np.searchsorted(g.tB.values, np.datetime64(t_issue), side='right')
            if k > 0:
                a, b = g.a.values[:k].sum(), g.b.values[:k].sum(); out['class'] = float(g.mu.values[:k].mean())
                s2e = (1 / b) * de_of(k, M['de'])[0]; B = M['tau2'] / (M['tau2'] + s2e)
                out['B'] = float(B); out['n_pairs'] = int(k); out['fire'] = out['class'] * (1 + B * (a / b - 1))
        out.setdefault('fire', out['class'])
        gs = self.g.get((fire, 'same'))
        if gs is not None:
            k = np.searchsorted(gs.tB.values, np.datetime64(t_issue), side='right')
        return out

def foot_dist(X, Y, d):
    h = np.radians(d.heading.values); us = np.c_[np.cos(h), -np.sin(h)]; ut = np.c_[np.sin(h), np.cos(h)]
    dx = X[:, None] - d.x.values[None]; dy = Y[:, None] - d.y.values[None]
    a = np.abs(dx * us[None, :, 0] + dy * us[None, :, 1]) - d.scan_m.values[None] / 2
    b = np.abs(dx * ut[None, :, 0] + dy * ut[None, :, 1]) - d.track_m.values[None] / 2
    return np.hypot(np.maximum(a, 0), np.maximum(b, 0)).min(1)

def kernel(X, Y, d, t):
    dd = np.hypot(X[:, None] - d.x.values[None], Y[:, None] - d.y.values[None])
    dt = np.abs((pd.Timestamp(t) - d.t).dt.total_seconds().values / 3600)
    return (np.exp(-dd / 400) * np.exp(-dt / 12)[None]).sum(1)

def auc(y, s): return roc_auc_score(y, s) if 0 < y.sum() < len(y) else np.nan

def boot_diff(df, a, b, w=None, n=1000):
    f = df.fire.values; u = np.unique(f); ix = {q: np.where(f == q)[0] for q in u}
    x = df[a].values - df[b].values; ww = np.ones(len(df)) if w is None else df[w].values; ok = np.isfinite(x)
    x, ww = np.where(ok, x, 0), np.where(ok, ww, 0); v = []
    for _ in range(n):
        k = np.concatenate([ix[q] for q in rng.choice(u, len(u))]); v.append(np.sum(x[k] * ww[k]) / np.sum(ww[k]))
    return [round(float(np.sum(x * ww) / np.sum(ww)), 4), round(float(np.quantile(v, .025)), 4), round(float(np.quantile(v, .975)), 4)]

# ------------------------------------------------------------------ (a) photos
def test_photos(D, SP):
    PH = pickle.load(open(f'{R17}/photos.pkl', 'rb')); rows = []
    for ph in PH:
        f = ph['fire']; T = pd.Timestamp(ph['T']); d = D[(D.fire == f) & (D.t <= T - pd.Timedelta(hours=2))]
        if not len(d) or f not in SP.meta.index: continue
        ti = d.t.max(); ck = float(clock_between(habs([ti]), habs([T]))[0])
        X, Y, y = ph['X'], ph['Y'], ph['y'].astype(int); fd = foot_dist(X, Y, d)
        dp = np.hypot(X[:, None] - d.x.values[None], Y[:, None] - d.y.values[None]).min(1); kz = kernel(X, Y, d, ti)
        sp = SP.get(f, ti)
        r = dict(fire=f, season=ph['season'], event=ph['event'], scene=ph['scene'], n_px=len(y), obs=y.mean(), clock_h=ck, gap_h=(T - ti).total_seconds() / 3600,
                 B=sp['B'], n_pairs=sp['n_pairs'], v_same=sp['same'], v_class=sp['class'], v_fire=sp['fire'])
        preds = {'persistence': fd <= 0, 'ring600': dp <= 600, 'tail15': fd <= 15 * ck}
        for k in ['same', 'class', 'fire']:
            preds[k] = fd <= sp[k] * ck; preds[k + '+120m'] = fd <= sp[k] * ck + 120
        for m, p in preds.items(): r[f'acc_{m}'] = (p == y).mean(); r[f'frac_{m}'] = p.mean()
        r['auc_distance'] = auc(y, -fd); r['auc_kernel'] = auc(y, kz)
        # the class-speed reach as a ranking on its own pixels is just -distance; per-fire factors cannot change a ranking
        r['kz'] = kz; r['y'] = y
        rows.append(r)
    R = pd.DataFrame(rows)
    # kernel threshold fitted on other seasons (max pixel accuracy)
    thr = np.quantile(np.concatenate(R.kz.values), np.linspace(0.01, .99, 60))
    acc_k = np.zeros(len(R)); frac_k = np.zeros(len(R))
    for s in R.season.unique():
        tr = R[R.season != s]; best = max(thr, key=lambda q: np.mean([((kz >= q) == y).mean() for kz, y in zip(tr.kz, tr.y)]))
        for i in np.where(R.season == s)[0]: acc_k[i] = ((R.kz.iloc[i] >= best) == R.y.iloc[i]).mean(); frac_k[i] = (R.kz.iloc[i] >= best).mean()
    R['acc_kernel'] = acc_k; R['frac_kernel'] = frac_k
    T6 = pd.read_csv(f'{V2}/tracking/results/t6_photos_grid12.csv')[['event', 'scene', 'acc_blend', 'frac_blend']]
    R = R.merge(T6.rename(columns={'acc_blend': 'acc_blend_all_looks', 'frac_blend': 'frac_blend_all_looks'}), on=['event', 'scene'], how='left')
    R = R.drop(columns=['kz', 'y']); R.to_csv(f'{OUT}/b4a_photos.csv', index=False)
    meth = ['persistence', 'ring600', 'kernel', 'tail15', 'same', 'class', 'fire', 'same+120m', 'class+120m', 'fire+120m', 'blend_all_looks']
    res = dict(photos=len(R), fires=int(R.fire.nunique()), median_gap_h=round(float(R.gap_h.median()), 1), median_clock_h=round(float(R.clock_h.median()), 1),
               photos_with_pairs_before=int((R.n_pairs > 0).sum()), median_B=round(float(R.B.median()), 4), max_B=round(float(R.B.max()), 3))
    res['scores'] = {m: dict(acc=round(float(R[f'acc_{m}'].mean()), 4), burned_share_err=round(float((R[f'frac_{m}'] - R.obs).mean()), 4)) for m in meth if f'acc_{m}' in R}
    res['auc'] = dict(distance=round(float(R.auc_distance.mean()), 4), kernel=round(float(R.auc_kernel.mean()), 4))
    res['acc_fire_minus_class'] = boot_diff(R, 'acc_fire', 'acc_class'); res['acc_class_minus_same'] = boot_diff(R, 'acc_class', 'acc_same')
    res['acc_class_minus_persistence'] = boot_diff(R, 'acc_class', 'acc_persistence'); res['acc_class_minus_ring600'] = boot_diff(R, 'acc_class', 'acc_ring600')
    res['acc_class_minus_kernel'] = boot_diff(R, 'acc_class', 'acc_kernel')
    res['acc_fire_minus_class_photos_with_B_gt_0.05'] = boot_diff(R[R.B > .05], 'acc_fire', 'acc_class') if (R.B > .05).sum() > 5 else None
    return res

# ------------------------------------------------------------------ (b) next pass
def disc_area(pts, R, cell=50.0):
    """area (ha) of the union of discs of radius R (array per point or scalar) around pts"""
    R = np.broadcast_to(np.asarray(R, float), (len(pts),))
    x0, y0 = pts[:, 0].min() - R.max(), pts[:, 1].min() - R.max(); x1, y1 = pts[:, 0].max() + R.max(), pts[:, 1].max() + R.max()
    gx, gy = np.meshgrid(np.arange(x0, x1, cell), np.arange(y0, y1, cell)); G = np.c_[gx.ravel(), gy.ravel()]
    if len(G) > 4e6: cell *= 2; return disc_area(pts, R, cell)
    tr = cKDTree(pts); dd, j = tr.query(G, k=min(len(pts), 8))
    dd = np.atleast_2d(dd.T).T if dd.ndim == 1 else dd; j = np.atleast_2d(j.T).T if j.ndim == 1 else j
    inside = (dd <= R[j]).any(1); return inside.sum() * cell * cell / 1e4, (G, inside, cell)

def test_nextpass(D, SP, PV):
    D = D.sort_values('t'); rows = []; cnt = []
    PV = PV[PV.kind == 'viirs'].sort_values('t')
    for f, g in D.groupby('fire'):
        if f not in SP.meta.index: continue
        g = g.copy(); g['slot'] = (g.t.diff().dt.total_seconds().fillna(1e9) > 2 * 3600).cumsum()
        sl = g.groupby('slot').t.agg(['min', 'max'])
        for k in sl.index:
            ti = sl.loc[k, 'max']; seen = g[g.t <= ti]; cur = g[g.slot == k]
            sp = SP.get(f, ti)
            # (ii) count at the first viewing pass >= 6 h later
            nv = PV[(PV.t >= ti + pd.Timedelta(hours=6)) & (PV.t <= ti + pd.Timedelta(hours=30))]
            if len(nv):
                pv = nv.iloc[0]; n_next = int((g.pass_key == pv.pass_key).sum())
                cnt.append(dict(fire=f, season=int(SP.meta.season[f]), ti=ti, n_cur=cur.groupby('pass_key').size().mean(), n_seen=len(seen),
                                dn_target=pv.daynight, w_target=pv.scan_m, gap_h=(pv.t - ti).total_seconds() / 3600,
                                clock_h=float(clock_between(habs([ti]), habs([pv.t]))[0]), v_same=sp['same'], v_class=sp['class'], v_fire=sp['fire'], B=sp['B'], n_next=n_next))
            # (i) where: next slot >= 6 h later
            nxt = sl[(sl['min'] >= ti + pd.Timedelta(hours=6)) & (sl['min'] <= ti + pd.Timedelta(hours=36))]
            if not len(nxt): continue
            k2 = nxt.index[0]; N = g[(g.slot == k2)]; N = N[N.pass_key == N.pass_key.iloc[0]]
            S = seen[['x', 'y']].values; NN = N[['x', 'y']].values
            d = np.hypot(NN[:, 0, None] - S[None, :, 0], NN[:, 1, None] - S[None, :, 1]).min(1)
            dlat = np.hypot(NN[:, 0, None] - cur.x.values[None], NN[:, 1, None] - cur.y.values[None]).min(1)
            ck = float(clock_between(habs([ti]), habs([N.t.iloc[0]]))[0])
            rows.append(dict(fire=f, season=int(SP.meta.season[f]), ti=ti, clock_h=ck, d=d, dlat=dlat, new=d > 400, n=len(d), nnew=int((d > 400).sum()),
                             S=S, C=cur[['x', 'y']].values, ST=seen.t.values, NN=NN, v_same=sp['same'], v_class=sp['class'], v_fire=sp['fire'], B=sp['B']))
    R = pd.DataFrame(rows); C = pd.DataFrame(cnt)
    # equal mean reach: R = 375 + c_m * v_m * clock, c_m so that mean reach = 375 + 15 m/h * mean clock hours
    budget = 375 + 15.0 * R.clock_h.mean(); res = dict(forecasts=len(R), fires=int(R.fire.nunique()), mean_reach_m=round(budget, 1))
    reach = {'fixed': np.full(len(R), budget)}
    for m in ['same', 'class', 'fire']:
        raw = R[f'v_{m}'].values * R.clock_h.values; reach[m] = 375 + raw * (budget - 375) / raw.mean()
    for m, rr in reach.items():
        R[f'cap_{m}'] = [(d <= x).mean() for d, x in zip(R.d, rr)]; R[f'capn_{m}'] = [(d[nw] <= x).mean() if nw.any() else np.nan for d, nw, x in zip(R.d, R.new, rr)]
    R['cap_ring600'] = [(d <= 600).mean() for d in R.dlat]; R['capn_ring600'] = [(d[nw] <= 600).mean() if nw.any() else np.nan for d, nw in zip(R.dlat, R.new)]
    # areas and the kernel at equal area (subsample for speed)
    areas = {m: [] for m in ['class', 'fire', 'ring600']}; capk = np.full(len(R), np.nan); capkn = np.full(len(R), np.nan)
    for i, r in enumerate(R.itertuples()):
        a_c, (G, ins, cell) = disc_area(r.S, reach['class'][i]); areas['class'].append(a_c)
        areas['fire'].append(disc_area(r.S, reach['fire'][i])[0]); areas['ring600'].append(disc_area(r.C, 600.0)[0])
        sc = (np.exp(-cKDTree(r.S).query(G, k=min(len(r.S), 16))[0] / 400.0)).reshape(len(G), -1).sum(1)
        q = np.quantile(sc, 1 - ins.mean()); keep = sc >= q
        tg = cKDTree(G[keep]); dd, _ = tg.query(r.NN); hit = dd <= cell * 0.75
        capk[i] = hit.mean(); capkn[i] = hit[r.new].mean() if r.new.any() else np.nan
    R['cap_kernel'] = capk; R['capn_kernel'] = capkn
    for m in areas: R[f'area_{m}'] = areas[m]
    def wm(col, w): x = R[col].values; ww = R[w].values; ok = np.isfinite(x); return round(float(np.sum(x[ok] * ww[ok]) / np.sum(ww[ok])), 4)
    res['capture_all'] = {m: wm(f'cap_{m}', 'n') for m in ['fixed', 'same', 'class', 'fire', 'ring600', 'kernel']}
    res['capture_new'] = {m: wm(f'capn_{m}', 'nnew') for m in ['fixed', 'same', 'class', 'fire', 'ring600', 'kernel']}
    res['mean_area_ha'] = {m: round(float(np.mean(areas[m])), 1) for m in areas}
    res['fire_minus_class_all'] = boot_diff(R, 'cap_fire', 'cap_class', 'n'); res['fire_minus_class_new'] = boot_diff(R.fillna({'capn_fire': 0, 'capn_class': 0}), 'capn_fire', 'capn_class', 'nnew')
    res['class_minus_same_all'] = boot_diff(R, 'cap_class', 'cap_same', 'n'); res['class_minus_fixed_all'] = boot_diff(R, 'cap_class', 'cap_fixed', 'n')
    res['kernel_minus_class_all'] = boot_diff(R, 'cap_kernel', 'cap_class', 'n')
    res['forecasts_with_B_gt_0.05'] = int((R.B > .05).sum())
    R.drop(columns=['d', 'dlat', 'new', 'S', 'C', 'ST', 'NN']).to_csv(f'{OUT}/b4b_nextpass_where.csv', index=False)
    # (ii) counts: Poisson GLM, leave one season out
    import statsmodels.api as sm
    C['night'] = (C.dn_target == 'N').astype(float); C['lw'] = np.log(C.w_target / 375); C['ln'] = np.log(C.n_cur); C['lg'] = np.log(C.gap_h)
    for m in ['same', 'class', 'fire']: C[f'lv_{m}'] = np.log(np.clip(C[f'v_{m}'] * C.clock_h, 1, None))
    specs = {'persistence (count x day/night ratio)': None, 'base': ['ln', 'night', 'lw', 'lg'], '+ same speed': ['ln', 'night', 'lw', 'lg', 'lv_same'],
             '+ class speed': ['ln', 'night', 'lw', 'lg', 'lv_class'], '+ per-fire speed': ['ln', 'night', 'lw', 'lg', 'lv_fire']}
    pr = {k: np.zeros(len(C)) for k in specs}
    for s in C.season.unique():
        tr, te = C[C.season != s], C[C.season == s]
        ratio = {dn: tr[tr.dn_target == dn].n_next.mean() / tr[tr.dn_target == dn].n_cur.mean() for dn in 'DN'}
        pr['persistence (count x day/night ratio)'][te.index] = te.n_cur.values * te.dn_target.map(ratio).values
        for k, cols in specs.items():
            if cols is None: continue
            mdl = sm.GLM(tr.n_next, sm.add_constant(tr[cols]), family=sm.families.Poisson()).fit()
            pr[k][te.index] = mdl.predict(sm.add_constant(te[cols], has_constant='add'))
    y = C.n_next.values; out = {}
    for k, mu in pr.items():
        mu = np.clip(mu, 1e-6, None); dev = 2 * np.sum(np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / mu), 0) - (y - mu))
        out[k] = dict(deviance_per_forecast=round(float(dev / len(y)), 4), auc_flags_at_all=round(float(roc_auc_score(y > 0, mu)), 4),
                      mae=round(float(np.abs(mu - y).mean()), 3))
        C[f'pred_{k}'] = mu
    C['dev_class'] = 2 * (np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / C['pred_+ class speed']), 0) - (y - C['pred_+ class speed']))
    C['dev_fire'] = 2 * (np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / C['pred_+ per-fire speed']), 0) - (y - C['pred_+ per-fire speed']))
    C['dev_base'] = 2 * (np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / C['pred_base']), 0) - (y - C['pred_base']))
    res['counts'] = dict(forecasts=len(C), fires=int(C.fire.nunique()), share_silent=round(float((C.n_next == 0).mean()), 3), models=out,
                         deviance_fire_minus_class=boot_diff(C, 'dev_fire', 'dev_class'), deviance_class_minus_base=boot_diff(C, 'dev_class', 'dev_base'))
    C.to_csv(f'{OUT}/b4b_nextpass_counts.csv', index=False)
    return res

# ------------------------------------------------------------------ (c) final scar size
def test_final(D, SP, G):
    F = pd.read_csv(f'{ROOT}/research/big-fires/results/fires.csv').set_index('fire'); rows = []
    for f, g in D.groupby('fire'):
        if f not in SP.meta.index or f not in F.index: continue
        g = g.sort_values('t'); t0 = g.t.min(); ti = t0 + pd.Timedelta(hours=24)
        if g.t.max() <= ti + pd.Timedelta(hours=6): continue          # fires still burning after the first day only
        seen = g[g.t <= ti]; sp = SP.get(f, ti)
        gl = G[(G.fire == f) & (G.kind == 'viirs') & (G.t <= ti)].sort_values('t')
        L_last = float(gl.L_m.iloc[-1]) if len(gl) else 150.0
        rows.append(dict(fire=f, season=int(SP.meta.season[f]), A_final=F.area_ha[f], edge=bool(F.still_at_edge[f]), n_seen=len(seen),
                         ring600=disc_area(seen[['x', 'y']].values, 600.0)[0], kern400=disc_area(seen[['x', 'y']].values, 400.0)[0],
                         L_last=L_last, v_same=sp['same'], v_class=sp['class'], v_fire=sp['fire'], B=sp['B'],
                         hours_left=(g.t.max() - ti).total_seconds() / 3600))
    R = pd.DataFrame(rows); y = np.log(R.A_final.values)
    specs = {'ring 600 m': ['ring600'], 'dot kernel 400 m': ['kern400'], 'ring + line x same speed': ['ring600', 'g_same'],
             'ring + line x class speed': ['ring600', 'g_class'], 'ring + line x per-fire speed': ['ring600', 'g_fire'],
             'ring + line only': ['ring600', 'L_last'], 'ring + per-fire speed only': ['ring600', 'v_fire']}
    pred = {k: np.zeros(len(R)) for k in specs}
    for s in R.season.unique():
        tr, te = (R.season != s).values, (R.season == s).values
        Dm = np.median(R.hours_left.values[tr]) * 1.0          # remaining duration known only from other seasons
        for m in ['same', 'class', 'fire']: R.loc[:, f'g_{m}'] = R.L_last * R[f'v_{m}'] * Dm / 1e4
        for k, cols in specs.items():
            X = np.c_[np.ones(len(R)), np.log(np.clip(R[cols].values, 1e-3, None))]
            b = np.linalg.lstsq(X[tr], y[tr], rcond=None)[0]; pred[k][te] = X[te] @ b
    res = dict(fires=len(R), median_final_ha=round(float(R.A_final.median()), 1))
    for k, p in pred.items():
        e = y - p; R[f'e2_{k}'] = e ** 2
        res[k] = dict(heldout_r2_log=round(float(1 - np.mean(e ** 2) / np.var(y)), 3), median_abs_factor=round(float(np.exp(np.median(np.abs(e)))), 2))
    res['e2_per_fire_minus_class'] = boot_diff(R, 'e2_ring + line x per-fire speed', 'e2_ring + line x class speed')
    res['e2_class_minus_ring'] = boot_diff(R, 'e2_ring + line x class speed', 'e2_ring 600 m')
    res['e2_line_only_minus_ring'] = boot_diff(R, 'e2_ring + line only', 'e2_ring 600 m')
    res['note'] = 'blend map not applicable: it is drawn inside the final outline, so it cannot forecast the outline size'
    R.to_csv(f'{OUT}/b4c_final.csv', index=False)
    return res

if __name__ == '__main__':
    D = pd.read_parquet(f'{TRACK}/det.parquet'); D = D[(D.fire >= 0) & (D.kind == 'viirs') & (D.type.fillna(0) != 2)].copy()
    SP = Speeds(); G = pd.read_parquet(f'{SC}/line_pass.parquet'); PV = pd.read_parquet(f'{TRACK}/passes.parquet')
    which = sys.argv[1:] or ['a', 'b', 'c']; res = {}
    if os.path.exists(f'{OUT}/b4_forecast.json'): res = json.load(open(f'{OUT}/b4_forecast.json'))
    if 'a' in which: res['a_photos'] = test_photos(D, SP); print(json.dumps(res['a_photos'], indent=1))
    if 'c' in which: res['c_final'] = test_final(D, SP, G); print(json.dumps(res['c_final'], indent=1))
    if 'b' in which: res['b_nextpass'] = test_nextpass(D, SP, PV); print(json.dumps(res['b_nextpass'], indent=1))
    json.dump(res, open(f'{OUT}/b4_forecast.json', 'w'), indent=1, default=str)
