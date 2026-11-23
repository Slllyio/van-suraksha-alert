"""Fair comparison at fixed leads (audit, Oct 15): same fires (multi-satellite events with a grown outline), same truth, forecasts issued at
each VIIRS pass k with only the detections up to that pass, horizons 6/12/24/48 h, several forecast-area budgets.
Truths per issue time: (a) detections of any satellite in the next h hours (hit = forecast pixel within 240 m), counted only when the box had
at least one overpass in the window; (b) the final grown outline; (c) the fuel thread's mid-fire S2/Landsat snapshot of burned-so-far
(timing/chips, inside the raster scar only) where one falls inside 48 h of the issue time.
Methods: pers (distance from all known detections = persistence at any area), circ (distance from the latest pass), dist (LightGBM on
five distances + lead), phys (Rothermel restart from every known detection, ERA5-Land HINDCAST weather, no scar snapping, ranked by arrival),
lr (4j learned restart, polygon end head, lead set to the horizon), lrh (same features, one head per horizon), lrp (lrh + physics arrival
and reach), lfoot (4i learned footprint from the first pass, k = 1 only).
  build k/n rows.parquet       lattice rows (LAT 8) with features, physics, horizon labels, overpass counts
  train rows.parquet mdir      LOSO heads: dist, dist_scar, lrh_<h>, lrp_<h>, lrp_scar
  score mdir k/n out.parquet   per (fire, pass, truth, method, budget) hits / Sorensen / precision / recall; + out_cal.parquet lattice
                               probabilities and labels for calibration
"""
import os
os.environ.setdefault('SCAR_GROWN', '1'); os.environ.setdefault('GROWN_STORE', 'grown_scars_viirs.pkl')
for _k in ('BARRIERS', 'FAR_SIDE', 'PHYS_BARRIERS', 'PREBURN_POLY'):      # EVENTS_FILE is honoured (forward test: events_viirs_2526.parquet)
    os.environ.pop(_k, None)
import numpy as np, pandas as pd, sys, json, time, glob
from scipy import ndimage
import sim, score, grown
import footprint as fp
import foot_restart as fr
CHIP_PAD = 100      # fuel thread's chips index the burn rasters without this grid's 100-pixel pad (checked: chip scar overlaps burn_end 100% at +100, 11-16% at 0)
SNAP_ONLY = os.environ.get('SNAP_ONLY') == '1'; SNAPNEW_M = 450.0   # photo-only rerun; 'new ground' = >450 m from every known dot (spread review)
RING_M = 600.0; HOR = [6, 12, 24, 48]; BUD_HA = [10, 25, 50, 100, 200]; HIT = 12; NEW_M = 400.0; LAT_BUILD = 8; LAT_CAL = 4
DIST = ['d_all', 'd_last', 'd_first', 'd_cent_all', 'd_cent_last', 'lead_h']
FEATS_H = [f for f in fr.FEATS if f != 'lead_h']; PHYS = ['t_phys', 'reach']
CFG = dict(fp.CFG, ign_snap=False, ign_all=True)
V = pd.read_parquet(f"{sim.DATA}/{os.environ.get('EVENTS_FILE', 'events_viirs.parquet')}")
_ops = V.groupby(['season', 'satellite', 'overpass']).t.min().reset_index()
OPS = {s: np.sort(d.t.values) for s, d in _ops.groupby('season')}      # pass times over the box (any fire detected), per season
VS = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet')
_m = V[V.sensor == 'viirs-snpp'][['latitude', 'longitude', 't', 'event']].merge(VS[['latitude', 'longitude', 't', 'event']].rename(columns={'event': 'snpp'}), on=['latitude', 'longitude', 't'])
SNPP2MULTI = _m.groupby('snpp').event.agg(lambda s: s.mode().iloc[0])
TIMING = '/mnt/project-files/fuel-map/ratapani/timing'
MID = pd.read_parquet(f'{TIMING}/midscar.parquet'); MID = MID[MID.status == 'ok'].copy(); MID['multi'] = MID.event.map(SNPP2MULTI)


def n_ops(s, t, h):
    o = OPS[s]; t = np.datetime64(t)
    return int(((o > t + np.timedelta64(60, 's')) & (o <= t + np.timedelta64(int(h * 3600), 's'))).sum())


def dets_in(ev_full, t, h):
    return ev_full[(ev_full.t > t + pd.Timedelta(seconds=60)) & (ev_full.t <= t + pd.Timedelta(hours=h))]


def det_mask(sub, shape, win):
    m = np.zeros(shape, bool)
    if len(sub):
        r, c = sim.rc(sub.x.values, sub.y.values); r -= win[0]; c -= win[2]
        ok = (r >= 0) & (r < shape[0]) & (c >= 0) & (c < shape[1]); m[r[ok], c[ok]] = True
        m = ndimage.binary_dilation(m, structure=np.ones((2 * HIT + 1, 2 * HIT + 1)))
    return m


def new_dets(sub, known):
    if not len(sub):
        return sub
    dmn = np.array([np.hypot(known.x.values - x, known.y.values - y).min() for x, y in zip(sub.x, sub.y)])
    return sub[dmn > NEW_M]


def physics(known, wx, win):
    """Rothermel restart from every detection so far (100 m discs at their times), run 48 h past the issue time. Hindcast weather."""
    t0 = known.t.min().floor('h'); hours = int(np.ceil((known.t.max() - t0).total_seconds() / 3600)) + 48
    o = sim.run_event(known, wx, dict(CFG, win=win), hours=hours, scar_fn=None)
    t_issue = (known.t.max() - o['t0']).total_seconds() / 60
    tph = (o['T'] - t_issue) / 60.0
    reach = np.isfinite(tph)
    return np.where(reach, tph, 96.0).astype(np.float32), reach.astype(np.float32)


def step_labels(ev_full, known, t_issue, shape, win, s):
    lab = {}
    for h in HOR:
        sub = dets_in(ev_full, t_issue, h); new = new_dets(sub, known)
        lab[h] = dict(sub=sub, new=new, n_op=n_ops(s, t_issue, h), mask=det_mask(sub, shape, win))
    return lab


def build(k_n, out):
    fr.LAT = LAT_BUILD
    v, ids = fr.events(k_n); wx = {}; rows = []; tt = time.time()
    for q, e in enumerate(ids):
        st = fr.fire_setup(v[v.event == e])
        if st is None:
            continue
        ev, passes, win, S = st; s = int(ev.season.iloc[0]); ev_full = V[V.event == e].sort_values('t')
        if S.sum() < 25:
            continue
        if s not in wx:
            wx.clear(); wx[s] = sim.load_weather(s)
        F, B, cid = fr.fire_static(ev, win)
        for k in range(1, len(passes) + 1):
            X, yn, ys, m = fr.step_rows(ev, passes, k, F, B, cid, S, win, wx[s], True)
            mask, known = m['mask'], m['known']; t_issue = known.t.max()
            tph, reach = physics(known, wx[s], win)
            d = pd.DataFrame(X, columns=fr.FEATS); d['t_phys'] = tph[mask]; d['reach'] = reach[mask]; d['y_scar'] = ys
            lab = step_labels(ev_full, known, t_issue, S.shape, win, s)
            for h in HOR:
                d[f'y_h{h}'] = lab[h]['mask'][mask].astype(np.int8); d[f'nop_h{h}'] = lab[h]['n_op']; d[f'ndet_h{h}'] = len(lab[h]['sub']); d[f'nnew_h{h}'] = len(lab[h]['new'])
            d['event'] = e; d['season'] = s; d['step'] = k; d['n_pass'] = len(passes)
            rows.append(d)
        if q % 25 == 0:
            print(q, len(ids), f'{time.time() - tt:.0f}s', flush=True)
    d = pd.concat(rows, ignore_index=True); d.to_parquet(out); print('rows', len(d), 'steps', d.groupby(['event', 'step']).ngroups)


def train(rows, mdir):
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score
    os.makedirs(mdir, exist_ok=True)
    d = pd.concat([pd.read_parquet(f) for f in rows.split(',')], ignore_index=True)
    print('rows', len(d), 'fires', d.event.nunique(), 'steps', d.groupby(['event', 'step']).ngroups, flush=True)
    params = dict(objective='binary', learning_rate=0.05, num_leaves=63, min_child_samples=300, feature_fraction=0.8, bagging_fraction=0.7, bagging_freq=1,
                  lambda_l2=5.0, num_threads=4, verbose=-1)
    rep = {}
    def fit(name, feats, dd, lab, s, cat):
        tr, te = (dd, dd.iloc[:0]) if s == 'all' else (dd[dd.season != s], dd[dd.season == s])
        m = lgb.train(params, lgb.Dataset(tr[feats], tr[lab], categorical_feature=cat), num_boost_round=200)
        m.save_model(f'{mdir}/{name}_{s}.txt')
        if len(te) and 0 < te[lab].sum() < len(te):
            rep[f'{name}_{s}'] = dict(n=len(te), auc=round(roc_auc_score(te[lab], m.predict(te[feats])), 4), base=round(float(te[lab].mean()), 4))
            print(name, s, rep[f'{name}_{s}'], flush=True)
        return m
    # distance-only, horizons stacked with lead_h = h (rows with at least one overpass in the window)
    st = []
    for h in HOR:
        q = d[d[f'nop_h{h}'] >= 1][DIST[:-1] + [f'y_h{h}', 'season']].copy(); q['lead_h'] = float(h); q['y'] = q[f'y_h{h}']; st.append(q.drop(columns=[f'y_h{h}']))
    st = pd.concat(st, ignore_index=True)
    for s in fr._seasons():
        fit('dist', DIST, st, 'y', s, [])
        fit('dist_scar', DIST[:-1], d, 'y_scar', s, [])
    del st
    for h in HOR:
        dd = d[d[f'nop_h{h}'] >= 1]
        for s in fr._seasons():
            m = fit(f'lrh_{h}', FEATS_H, dd, f'y_h{h}', s, ['wc'])
            m2 = fit(f'lrp_{h}', FEATS_H + PHYS, dd, f'y_h{h}', s, ['wc'])
        rep[f'lrh_{h}_importance'] = pd.Series(m.feature_importance('gain'), index=FEATS_H).sort_values(ascending=False).round(1).head(20).to_dict()
        rep[f'lrp_{h}_importance'] = pd.Series(m2.feature_importance('gain'), index=FEATS_H + PHYS).sort_values(ascending=False).round(1).head(20).to_dict()
    for s in fr._seasons():
        m = fit('lrp_scar', FEATS_H + PHYS, d, 'y_scar', s, ['wc'])
    rep['lrp_scar_importance'] = pd.Series(m.feature_importance('gain'), index=FEATS_H + PHYS).sort_values(ascending=False).round(1).head(20).to_dict()
    json.dump(rep, open(f'{mdir}/train_report.json', 'w'), indent=1)


def snapshots(e, ev_full, win, shape):
    """fuel thread's burned-by-scene-time chips for this fire, mapped to the window: list of (T, burned, known) masks (inside the raster scar only)"""
    out = []
    for _, r in MID[MID.multi == e].iterrows():
        f = glob.glob(f'{TIMING}/chips/{r.event}_{r.scene[:40]}.npz')
        if not f:
            continue
        z = np.load(f[0]); bym, ok = z['bym'], z['ok']; ci0, cj0 = int(z['i0']) + CHIP_PAD, int(z['j0']) + CHIP_PAD   # chips use the unpadded raster grid
        B_ = np.zeros(shape, bool); O_ = np.zeros(shape, bool)
        a0, a1 = max(ci0, win[0]), min(ci0 + bym.shape[0], win[1]); b0, b1 = max(cj0, win[2]), min(cj0 + bym.shape[1], win[3])
        if a1 <= a0 or b1 <= b0:
            continue
        B_[a0 - win[0]:a1 - win[0], b0 - win[2]:b1 - win[2]] = bym[a0 - ci0:a1 - ci0, b0 - cj0:b1 - cj0]
        O_[a0 - win[0]:a1 - win[0], b0 - win[2]:b1 - win[2]] = ok[a0 - ci0:a1 - ci0, b0 - cj0:b1 - cj0]
        out.append((pd.Timestamp(r['T']), B_, O_, r.scene))
    return out


def score_(mdir, k_n, out):
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score
    def load(name, d=None):
        d = d or mdir
        try:
            m = {s: lgb.Booster(model_file=f'{d}/{name}_{s}.txt') for s in range(2017, 2025)}
        except Exception:
            return None
        return fr._Fallback(m, lgb.Booster(model_file=f'{d}/{name}_all.txt')) if os.path.exists(f'{d}/{name}_all.txt') else m
    LR = {h: load(h, os.environ.get('LRG_MODELS', f'{sim.DATA}/lrg_models')) for h in ['next', 'scar']}        # env overrides: smoke tests
    LF = load('loso', os.environ.get('FOOT_MODELS', f'{sim.DATA}/foot_models_grown'))
    M = {nm: load(nm) for nm in ['dist', 'dist_scar', 'lrp_scar'] + [f'lrh_{h}' for h in HOR] + [f'lrp_{h}' for h in HOR]}
    v, ids = fr.events(k_n); wx = {}; rows = []; cal = []; tt = time.time()
    bud_px = [int(b / 0.04) for b in BUD_HA]
    # checkpoint (container restarts lost two runs on Oct 15): resume from <out>.part*.parquet and the done-event list
    pr, pc, pdn = out + '.part_rows.parquet', out + '.part_cal.parquet', out + '.part_done.json'
    prev_rows, prev_cal, done = [], [], set()
    if os.path.exists(pdn):
        done = set(json.load(open(pdn))); prev_rows = [pd.read_parquet(pr)] if os.path.exists(pr) else []; prev_cal = [pd.read_parquet(pc)] if os.path.exists(pc) else []
        print('resuming, fires already scored', len(done), flush=True)
    def ckpt():
        R_ = pd.concat(prev_rows + [pd.DataFrame(rows)], ignore_index=True) if rows or prev_rows else pd.DataFrame()
        C_ = pd.concat(prev_cal + cal, ignore_index=True) if cal or prev_cal else pd.DataFrame()
        R_.to_parquet(pr + '.tmp'); os.replace(pr + '.tmp', pr); C_.to_parquet(pc + '.tmp'); os.replace(pc + '.tmp', pc)
        json.dump(sorted(int(x) for x in done), open(pdn + '.tmp', 'w')); os.replace(pdn + '.tmp', pdn)
    for q, e in enumerate(ids):
        if int(e) in done:
            continue
        if q % 10 == 0 and q:
            ckpt()
        done.add(int(e))
        st = fr.fire_setup(v[v.event == e])
        if st is None:
            continue
        ev, passes, win, S = st; s = int(ev.season.iloc[0]); ev_full = V[V.event == e].sort_values('t')
        if S.sum() < 25:
            continue
        if s not in wx:
            wx.clear(); wx[s] = sim.load_weather(s)
        F, B, cid = fr.fire_static(ev, win)
        snaps = snapshots(e, ev_full, win, S.shape)
        if SNAP_ONLY and not snaps:
            continue
        yy, xx = np.mgrid[win[0]:win[1], win[2]:win[3]]; lat = (yy % LAT_CAL == 0) & (xx % LAT_CAL == 0)
        p_lfoot = None
        for k in range(1, len(passes) + 1):
            X, yn, ys, m = fr.step_rows(ev, passes, k, F, B, cid, S, win, wx[s], False)
            mask, d_all, known, last = m['mask'], m['d_all'], m['known'], m['last']; t_issue = known.t.max()
            d_last = np.full(S.shape, np.inf)
            for a, b in zip(last.x.values, last.y.values):
                yy_, xx_ = np.mgrid[win[0]:win[1], win[2]:win[3]]
                d_last = np.minimum(d_last, np.hypot(sim.X0 + xx_ * sim.RES + sim.RES / 2 - a, sim.Y0 - yy_ * sim.RES - sim.RES / 2 - b))
            tph, reach = physics(known, wx[s], win)
            Xd = pd.DataFrame(X, columns=fr.FEATS); Xd['t_phys'] = tph[mask]; Xd['reach'] = reach[mask]
            R = {'pers': -d_all, 'circ': -d_last, 'phys': -tph, 'ring': -np.abs(d_last - RING_M)}   # ring: spread review's no-learning rule (600 m from the latest pass)
            def put(vals):
                a = np.zeros(S.shape, np.float32); a[mask] = vals; return a
            Xh = Xd.copy()
            for h in HOR:
                Xh['lead_h'] = float(h)
                R[f'lr_{h}'] = put(LR['next'][s].predict(Xh[fr.FEATS]))
                if M['dist']: R[f'dist_{h}'] = put(M['dist'][s].predict(Xh[DIST]))
                if M[f'lrh_{h}']: R[f'lrh_{h}'] = put(M[f'lrh_{h}'][s].predict(Xh[FEATS_H]))
                if M[f'lrp_{h}']: R[f'lrp_{h}'] = put(M[f'lrp_{h}'][s].predict(Xh[FEATS_H + PHYS]))
            R['lr_end'] = put(LR['scar'][s].predict(Xd[fr.FEATS]))
            if M['dist_scar']: R['dist_end'] = put(M['dist_scar'][s].predict(Xd[DIST[:-1]]))
            if M['lrp_scar']: R['lrp_end'] = put(M['lrp_scar'][s].predict(Xd[FEATS_H + PHYS]))
            if k == 1:
                Xf, yf, mf = fp.fire_features(ev, wx[s]); pf = np.zeros(mf['mask'].shape, np.float32); pf[mf['mask']] = LF[s].predict(Xf)
                if pf.shape == S.shape:
                    p_lfoot = pf; R['lfoot'] = pf
            elif p_lfoot is not None:
                R['lfoot'] = p_lfoot              # the first-pass footprint, unchanged, as a reference at later passes
            lab = step_labels(ev_full, known, t_issue, S.shape, win, s)
            n_pers = int((mask & (d_all <= fr.PERS)).sum())
            base = dict(event=e, season=s, k=k, n_pass=len(passes), n_known=len(known), elapsed_h=(t_issue - ev.t.min()).total_seconds() / 3600,
                        scar_px=int(S.sum()), n_mask=int(mask.sum()), area_pers=n_pers)
            def methods_for(truth):
                if truth == 'end':
                    return ['pers', 'circ', 'ring', 'phys', 'lr_end', 'dist_end', 'lrp_end', 'lfoot']
                if truth == 'snap':
                    return ['pers', 'circ', 'ring', 'phys', 'lr_24', 'lrh_24', 'lrp_24', 'dist_24', 'lfoot']
                return ['pers', 'circ', 'ring', 'phys', f'lr_{truth}', f'lrh_{truth}', f'lrp_{truth}', f'dist_{truth}', 'lfoot']
            for h in ([] if SNAP_ONLY else HOR):
                L = lab[h]
                if L['n_op'] == 0:
                    continue
                for meth in methods_for(h):
                    if meth not in R:
                        continue
                    for bname, n in [(f'{b}ha', px) for b, px in zip(BUD_HA, bud_px)] + [('pers', n_pers)]:
                        A = score.topn(-R[meth], mask, n)
                        rows.append(dict(base, truth=f'h{h}', method=meth, budget=bname, n_px=int(A.sum()), n_op=L['n_op'], n_det=len(L['sub']), n_new=len(L['new']),
                                         hit=fr.hits(L['sub'], A, win) if len(L['sub']) else 0, hitnew=fr.hits(L['new'], A, win) if len(L['new']) else 0))
            n_s = int(S.sum())
            for meth in ([] if SNAP_ONLY else methods_for('end')):
                if meth not in R:
                    continue
                for bname, n in [(f'{b}ha', px) for b, px in zip(BUD_HA, bud_px)] + [('pers', n_pers), ('truth', n_s)]:
                    A = score.topn(-R[meth], mask, n); inter = int((A & S).sum())
                    rows.append(dict(base, truth='end', method=meth, budget=bname, n_px=int(A.sum()), n_truth=n_s, inter=inter, sor=score.soren(A, S),
                                     prec=inter / max(int(A.sum()), 1), rec=inter / max(n_s, 1)))
            for (T, Bm, Om, scene) in snaps:
                lead = (T - t_issue).total_seconds() / 3600
                if not (0 < lead <= 48):
                    continue
                known_ok = Om & mask
                if known_ok.sum() < 25:
                    continue
                for tname, Bt, Mt in [('snap', Bm, mask), ('snapnew', Bm & (d_all > SNAPNEW_M), mask & (d_all > SNAPNEW_M))]:   # snapnew: rank only ground beyond 450 m
                  nb = int((Bt & known_ok & Mt).sum())
                  if nb == 0:
                    continue
                  for meth in methods_for('snap'):
                    if meth not in R:
                        continue
                    for bname, n in [(f'{b}ha', px) for b, px in zip(BUD_HA, bud_px)] + [('pers', n_pers), ('truth', nb)]:
                        A = score.topn(-R[meth], Mt, n); Ak = A & known_ok; inter = int((Ak & Bt).sum())
                        rows.append(dict(base, truth=tname, method=meth, budget=bname, lead_h=lead, scene=scene, n_px=int(A.sum()), n_known_ok=int(known_ok.sum()),
                                         n_truth=nb, inter=inter, prec=inter / max(int(Ak.sum()), 1), rec=inter / nb, sor=2 * inter / max(int(Ak.sum()) + nb, 1)))
            # calibration lattice: probabilities and labels
            cm = mask & lat & (not SNAP_ONLY)
            c = dict(event=np.full(int(cm.sum()), e), season=s, k=k, d_all=d_all[cm].astype(np.float32), d_last=d_last[cm].astype(np.float32), t_phys=tph[cm], y_end=S[cm].astype(np.int8))
            for h in HOR:
                c[f'y_h{h}'] = lab[h]['mask'][cm].astype(np.int8); c[f'nop_h{h}'] = lab[h]['n_op']
                for meth in [f'lr_{h}', f'lrh_{h}', f'lrp_{h}', f'dist_{h}']:
                    if meth in R: c[f'p_{meth}'] = R[meth][cm]
            for meth in ['lr_end', 'lrp_end', 'dist_end', 'lfoot']:
                if meth in R: c[f'p_{meth}'] = R[meth][cm]
            cal.append(pd.DataFrame(c))
        if q % 25 == 0:
            print(q, len(ids), f'{time.time() - tt:.0f}s', flush=True)
    pd.concat(prev_rows + [pd.DataFrame(rows)], ignore_index=True).to_parquet(out); pd.concat(prev_cal + cal, ignore_index=True).to_parquet(out.replace('.parquet', '_cal.parquet'))
    for f in (pr, pc, pdn):
        if os.path.exists(f): os.remove(f)
    print('rows', len(rows))


if __name__ == '__main__':
    {'build': lambda: build(sys.argv[2], sys.argv[3]), 'train': lambda: train(sys.argv[2], sys.argv[3]), 'score': lambda: score_(sys.argv[2], sys.argv[3], sys.argv[4])}[sys.argv[1]]()
