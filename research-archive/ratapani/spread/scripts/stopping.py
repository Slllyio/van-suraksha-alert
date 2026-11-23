"""Audit item 3: is the fire still active, and still advancing into new ground? Fire-level, at every issue time (pass k) of the fair
table, for horizons 6/12/24/48 h. Labels from the detections that followed, counted only when the box had an overpass in the window:
y_any = any detection of this fire within h, y_new = a detection more than 400 m from everything known. Features: the fair table's
fire-level features (passes so far, elapsed time, FRP, day/night, weather at the pass, run so far) plus the lattice means of dryness, fuel,
leaf fall, forest share and of the physics' reach and arrival. LOSO LightGBM; AUC and Brier against climatology, by elapsed time.
"No detection" is kept apart from "fire out": the miss rate of an overpass between two detections of the same fire (the fire was burning
and the pass did not see it) is measured from the detection record itself, by day/night and FRP.
Gating: what a forecast budget saves if no map is issued when P(any detection within 24 h) is below a threshold, against the hits lost
(uses fair_score rows: lrh_24 at the persistence budget).
  python3 stopping.py 'data/fair_rows_[0-3].parquet' 'data/fair_score_[0-3].parquet' out.json
"""
import numpy as np, pandas as pd, sys, json, glob
import lightgbm as lgb
from sklearn.metrics import roc_auc_score
HOR = [6, 12, 24, 48]
FIRE = ['k', 'n_prev', 'n_last', 'elapsed_h', 'frp_last', 'frp_all', 'night_last', 'doy', 'ext_all', 'ws', 'rh', 'm1', 'temp', 'run_so_far']
MEANS = ['lean', 'rf1', 'lf', 'forest', 'reach', 't_phys', 'd_prev', 'nburn_hist']
V = pd.read_parquet('/tmp/claude-0/spread/data/events_viirs.parquet')


def steps_table(pat):
    d = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(pat))], ignore_index=True)
    g = d.groupby(['event', 'season', 'step'])
    t = g[FIRE].first()
    for c in MEANS:
        t[f'm_{c}'] = g[c].mean()
    t['n_rows'] = g.size()
    for h in HOR:
        t[f'nop_h{h}'] = g[f'nop_h{h}'].first(); t[f'ndet_h{h}'] = g[f'ndet_h{h}'].first(); t[f'nnew_h{h}'] = g[f'nnew_h{h}'].first()
    return t.reset_index()


def miss_rate():
    """overpasses of the box between a fire's first and last detection at which the fire was not detected"""
    ops = V.groupby(['season', 'satellite', 'overpass']).t.min().reset_index()
    rows = []
    for e, g in V.groupby('event'):
        if g.overpass.nunique() < 2:
            continue
        s = int(g.season.iloc[0]); t0, t1 = g.t.min(), g.t.max()
        o = ops[(ops.season == s) & (ops.t > t0 + pd.Timedelta(minutes=5)) & (ops.t < t1 - pd.Timedelta(minutes=5))]
        seen = set(zip(g.satellite, g.overpass))
        for _, r in o.iterrows():
            rows.append(dict(event=e, season=s, satellite=r.satellite, t=r.t, night=r.t.hour < 12, detected=(r.satellite, r.overpass) in seen,
                             frp_max=float(g.frp.max()), n_det=len(g), span_h=(t1 - t0).total_seconds() / 3600))
    m = pd.DataFrame(rows)
    out = dict(n_passes=len(m), n_fires=int(m.event.nunique()), miss_rate=float(1 - m.detected.mean()))
    out['by_daynight'] = {('night' if k else 'day'): float(1 - v.detected.mean()) for k, v in m.groupby('night')}
    out['by_satellite'] = {k: float(1 - v.detected.mean()) for k, v in m.groupby('satellite')}
    m['frp_bin'] = pd.cut(m.frp_max, [0, 5, 15, 50, 1e9], labels=['<5 MW', '5-15', '15-50', '>50'])
    out['by_frp_max'] = {str(k): float(1 - v.detected.mean()) for k, v in m.groupby('frp_bin', observed=True)}
    return out


def main(rows_pat, score_pat, out):
    t = steps_table(rows_pat); res = dict(n_steps=len(t), n_fires=int(t.event.nunique()))
    feats = FIRE + [f'm_{c}' for c in MEANS]
    params = dict(objective='binary', learning_rate=0.05, num_leaves=15, min_child_samples=20, feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, num_threads=4, verbose=-1)
    t['elapsed_bin'] = pd.cut(t.elapsed_h, [-1, 6, 12, 24, 48], labels=['0-6', '6-12', '12-24', '24-48'])
    for h in HOR:
        q = t[t[f'nop_h{h}'] >= 1].copy()
        for lab, src in [('any', f'ndet_h{h}'), ('new', f'nnew_h{h}')]:
            y = (q[src] > 0).astype(int).values; p = np.full(len(q), np.nan); clim = np.full(len(q), np.nan); m = None
            for s in sorted(q.season.unique()):
                tr, te = (q.season != s) & (q.season <= 2024), q.season == s      # 2025-26 (forward test) scored by a 2017-24 model
                if y[tr].sum() == 0 or y[tr].sum() == tr.sum():
                    continue
                m = lgb.train(params, lgb.Dataset(q.loc[tr, feats], y[tr]), num_boost_round=200)
                p[te] = m.predict(q.loc[te, feats]); clim[te] = y[tr].mean()
            ok = np.isfinite(p); r = dict(n=int(ok.sum()), base=float(y[ok].mean()), auc=float(roc_auc_score(y[ok], p[ok])) if 0 < y[ok].sum() < ok.sum() else None,
                                           brier=float(np.mean((p[ok] - y[ok]) ** 2)), brier_clim=float(np.mean((clim[ok] - y[ok]) ** 2)))
            r['by_elapsed'] = {str(k): dict(n=int(len(v)), base=float((v[src] > 0).mean()), p_mean=float(p[ok][(q[ok].elapsed_bin == k).values].mean()) if ((q[ok].elapsed_bin == k).sum()) else None) for k, v in q[ok].groupby('elapsed_bin', observed=True)}
            if m is not None:
                imp = pd.Series(m.feature_importance('gain'), index=feats).sort_values(ascending=False); r['importance'] = imp.round(0).head(8).to_dict()
            res[f'h{h}_{lab}'] = r; q[f'p_{lab}_h{h}'] = p
            print(h, lab, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k not in ('by_elapsed', 'importance')}, flush=True)
        if h == 24:
            t = t.merge(q[['event', 'step', 'p_any_h24']], on=['event', 'step'], how='left')
    res['miss_rate_given_active'] = miss_rate(); print('miss rate', res['miss_rate_given_active'], flush=True)
    res['grouping_rule'] = 'events_multi.py: S-NPP + NOAA-20 + NOAA-21 + MODIS detections linked within 1.2 km and 30 h (single linkage); steps = passes of fires with 2+ passes and a grown outline'
    # re-detection by the time of day of the latest detection (FSI thread: a silent pass after a night detection means more)
    rd = {}
    for h in HOR:
        q = t[t[f'nop_h{h}'] >= 1]
        rd[f'h{h}'] = {('night_last' if k else 'day_last'): dict(n=int(len(v)), redetected=float((v[f'ndet_h{h}'] > 0).mean())) for k, v in q.groupby(q.night_last > 0.5)}
    res['redetection_by_last_daynight'] = rd; print('redetection by last day/night', rd['h24'], flush=True)
    # gating the 24 h forecast on P(any detection within 24 h)
    sc = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(score_pat))], ignore_index=True)
    sc = sc[(sc.truth == 'h24') & (sc.method == 'lrh_24') & (sc.budget == 'pers')].merge(t[['event', 'step', 'p_any_h24']].rename(columns={'step': 'k'}), on=['event', 'k'], how='inner')
    sc = sc[sc.p_any_h24.notna()]
    if len(sc):
        g = {}
        for thr in [0.1, 0.2, 0.3, 0.5]:
            keep = sc.p_any_h24 >= thr
            g[str(thr)] = dict(steps_issued=float(keep.mean()), area_share=float(sc.n_px[keep].sum() / sc.n_px.sum()), hits_kept=float(sc.hit[keep].sum() / max(sc.hit.sum(), 1)),
                               dets_in_skipped=int(sc.n_det[~keep].sum()), dets_total=int(sc.n_det.sum()))
        res['gating_lrh24_pers_budget'] = g; print('gating', g, flush=True)
    json.dump(res, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
