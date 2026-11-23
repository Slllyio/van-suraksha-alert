"""Spread audit, learned footprint (ratapani/spread/scripts/footprint.py, imported read only), polygon truth (SCAR_GROWN=1,
results/foot_models_grown). Per fire, Sorensen at the polygon's area for:
  orig   : the saved model as scored by the spread thread (reproduction check against foot_score_grown2_*)
  wxp    : forecast-time weather. footprint.py feeds the physics arrival time (48 h of ERA5-Land after the first detection)
           and the 24 h mean wind after it; here every hour after the first detection is replaced by the same hour of the
           24 h before it (a persistence weather forecast), physics re-run, features rebuilt.
  honest : wxp + same-season earlier burns only once their label could be final (burn-label rule: drop must persist 25 days,
           so a scar dated d counts from d + 25), in the features AND in the physics' consumed-fuel mask.
  circle : equal-area distance baseline (unchanged by either change).
Usage: SPREAD_DATA=... SCAR_GROWN=1 python3 audit_footprint.py k/n out.parquet"""
import sys, os, time
sys.dont_write_bytecode = True; os.environ.setdefault('NUMBA_CACHE_DIR', '/tmp/sa/numba_cache')   # leave the spread folder untouched
sys.path.insert(0, '/mnt/project-files/ratapani/spread/scripts')
import numpy as np, pandas as pd
import footprint as fp
from footprint import sim, score
import lightgbm as lgb

MDIR = '/mnt/project-files/ratapani/spread/results/foot_models_grown'
CONFIRM = 25
_G0 = sim.G


class ShiftG(dict):
    """sim.G with every burn_end_<y> moved CONFIRM days later (valid pixels only)"""
    def __missing__(self, k):
        a = _G0[k]
        if k.startswith('burn_end_'):
            a = np.where(a > -999, a + CONFIRM, a).astype(a.dtype)
        self[k] = a
        return a


def persist_wx(wx, t_first, hours=72):
    W, P = wx; th = t_first.floor('h'); W2 = {}
    for pid, w in W.items():
        w = w.copy(); idx = w.index
        fut = (idx >= th) & (idx < th + pd.Timedelta(hours=hours))
        src = th - pd.Timedelta(hours=24) + pd.to_timedelta(((idx[fut] - th) / pd.Timedelta(hours=1)).astype(int) % 24, unit='h')
        ok = src.isin(idx)
        vals = w.loc[src[ok]].values
        w.loc[idx[fut][ok]] = vals
        W2[pid] = w
    return W2, P


def sor_at(X, meta, model):
    S, mask, d_near = meta['S'], meta['mask'], meta['d_near']
    p = np.zeros(S.shape, np.float32); p[mask] = model.predict(X); n = int(S.sum())
    return score.soren(score.topn(-p, mask, n), S), score.soren(score.topn(d_near, mask, n), S), int(round(float(p[mask].sum())))


def main(k_n, out):
    models = {s: lgb.Booster(model_file=f'{MDIR}/loso_{s}.txt') for s in range(2017, 2025)}
    v, ids = fp.events(k_n); wx = {}; rows = []; tt = time.time()
    for q, e in enumerate(ids):
        ev = v[v.event == e].sort_values('t'); s = int(ev.season.iloc[0])
        if s not in wx:
            wx.clear(); wx[s] = sim.load_weather(s)
        row = dict(event=e, season=s)
        sim.G = _G0; fp._BE.clear()
        X, y, meta = fp.fire_features(ev, wx[s])
        row['scar_px'] = int(meta['S'].sum())
        row['sor_orig'], row['sor_circle'], row['npred_orig'] = sor_at(X, meta, models[s])
        wp = persist_wx(wx[s], ev.t.min())
        X, y, meta = fp.fire_features(ev, wp)
        row['sor_wxp'], _, row['npred_wxp'] = sor_at(X, meta, models[s])
        sim.G = ShiftG(); fp._BE.clear()
        X, y, meta = fp.fire_features(ev, wp)
        row['sor_honest'], row['sor_circle_h'], row['npred_honest'] = sor_at(X, meta, models[s])
        sim.G = _G0; fp._BE.clear()
        rows.append(row)
        if q % 25 == 0:
            print(q, len(ids), f'{time.time() - tt:.0f}s', flush=True)
    pd.DataFrame(rows).to_parquet(out)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
