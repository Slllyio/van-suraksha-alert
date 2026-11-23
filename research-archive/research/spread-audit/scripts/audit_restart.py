"""Spread audit, learned restart (ratapani/spread/scripts/foot_restart.py, imported read only).
For every forecast step of the polygon-truth run (SCAR_GROWN=1, lrg_models) this re-scores the saved models and adds:
  - reproduction: the learned and persistence hit counts recomputed from the saved models (compare to results/lrg_score_*.parquet)
  - baseline 'last': the same area taken nearest the LATEST pass only (persistence uses every detection so far equally)
  - leak checks on the learned model at the same area:
      'honest_prev': same-season earlier burns limited to scars whose label could be confirmed before the fire (the burn-label
                     rule needs the NBR drop to persist 25 days, so a scar dated d is only final at d + 25)
      'nolean'     : the lean dryness score removed (lean, dlean set to missing)
Usage: SPREAD_DATA=... SCAR_GROWN=1 GROWN_STORE=grown_scars_viirs.pkl python3 audit_restart.py k/n out.parquet"""
import sys, os, time
sys.dont_write_bytecode = True; os.environ.setdefault('NUMBA_CACHE_DIR', '/tmp/sa/numba_cache')   # leave the spread folder untouched
sys.path.insert(0, '/mnt/project-files/ratapani/spread/scripts')
import numpy as np, pandas as pd
import foot_restart as fr
from foot_restart import sim, score, fp, FEATS
import lightgbm as lgb

MDIR = '/mnt/project-files/ratapani/spread/results/lrg_models'
CONFIRM = 25


def main(k_n, out):
    M = {s: lgb.Booster(model_file=f'{MDIR}/next_{s}.txt') for s in range(2017, 2025)}
    v, ids = fr.events(k_n); wx = {}; rows = []; tt = time.time()
    ix = {f: FEATS.index(f) for f in FEATS}
    for q, e in enumerate(ids):
        st = fr.fire_setup(v[v.event == e])
        if st is None:
            continue
        ev, passes, win, S = st; s = int(ev.season.iloc[0]); i0, i1, j0, j1 = win
        if s not in wx:
            wx.clear(); wx[s] = sim.load_weather(s)
        F, B, cid = fr.fire_static(ev, win)
        d0 = ev.t.min().dayofyear
        be = fp.burn_end(s)[i0:i1, j0:j1]
        prev_all = (be > -999) & (be < d0 - 1)
        prev_ok = (be > -999) & (be + CONFIRM < d0 - 1)
        dprev_h = fp.edt(prev_ok)
        n_prev_px, n_prev_unconf = int(prev_all.sum()), int((prev_all & ~prev_ok).sum())
        for k in range(1, len(passes)):
            X, yn, ys, m = fr.step_rows(ev, passes, k, F, B, cid, S, win, wx[s], False)
            mask, d_all, target, known, last = m['mask'], m['d_all'], m['target'], m['known'], m['last']
            pn = np.zeros(S.shape, np.float32); pn[mask] = M[s].predict(X)
            # honest same-season burns: d_prev and its difference from the latest pass centroid
            cl = (last.x.mean(), last.y.mean()); rc_, cc_ = sim.rc(np.array([cl[0]]), np.array([cl[1]]))
            ri = int(np.clip(rc_[0] - i0, 0, S.shape[0] - 1)); ci = int(np.clip(cc_[0] - j0, 0, S.shape[1] - 1))
            Xh = X.copy(); Xh[:, ix['d_prev']] = dprev_h[mask]; Xh[:, ix['dd_prev']] = dprev_h[mask] - dprev_h[ri, ci]
            ph = np.zeros(S.shape, np.float32); ph[mask] = M[s].predict(Xh)
            Xl = X.copy(); Xl[:, ix['lean']] = np.nan; Xl[:, ix['dlean']] = np.nan
            pl = np.zeros(S.shape, np.float32); pl[mask] = M[s].predict(Xl)
            dl = np.full(S.shape, np.inf); dl[mask] = X[:, ix['d_last']]
            top = lambda sc, nn: score.topn(-sc, mask, nn)
            Pm = mask & (d_all <= fr.PERS); n_p = int(Pm.sum())
            dmn = np.array([np.hypot(known.x.values - x, known.y.values - y).min() for x, y in zip(target.x, target.y)]); new = target[dmn > 400]
            row = dict(event=e, season=s, k=k, lead_h=float(X[0, ix['lead_h']]), n_target=len(target), n_new=len(new), area_pers=n_p,
                       n_prev_px=n_prev_px, n_prev_unconf=n_prev_unconf)
            for nm, A in [('pers', Pm), ('learn', top(pn, n_p)), ('last', top(-dl, n_p)), ('honest_prev', top(ph, n_p)), ('nolean', top(pl, n_p))]:
                row[f'hit_{nm}'] = fr.hits(target, A, win); row[f'hitnew_{nm}'] = fr.hits(new, A, win) if len(new) else 0
            rows.append(row)
        if q % 25 == 0:
            print(q, len(ids), f'{time.time() - tt:.0f}s', flush=True)
    pd.DataFrame(rows).to_parquet(out)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
