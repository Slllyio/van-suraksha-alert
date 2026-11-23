"""Restart-from-every-pass evaluation (C-DAC slide 24 design; Xu et al. 2022). For fires seen on >= 2 VIIRS
passes within 48 h: forecast each pass's detections from (a) a free run started at the first pass and
(b) a run restarted with every detection up to the previous pass, each at its own time. Baselines: an
equal-area circle around the same ignition pixels, and plain persistence (375 m around previous detections).
Usage: restart.py cfgjson out.parquet [k/n]"""
import numpy as np, pandas as pd, sys, json
from scipy import ndimage
import sim, score
from engine import arrival, OFFS

cfg = json.loads(sys.argv[1]); cfg['return_fields'] = True
k_, n_ = map(int, sys.argv[3].split('/')) if len(sys.argv) > 3 else (0, 1)
HOURS = cfg.get('hours', 48); strict = int(cfg.get('strict', 0))
v = pd.read_parquet(cfg.get('events_file', f'{sim.DATA}/viirs_events.parquet')); v = v[v.t.dt.month <= 6]
ids = [e for e, g in v.groupby('event') if g.overpass.nunique() >= 2][k_::n_]
evs = v.groupby('event'); rows = []; wx = {}


def hits(sub, A, win):
    r, c = sim.rc(sub.x.values, sub.y.values); r -= win[0]; c -= win[2]
    return sum(bool(A[max(a - 12, 0):a + 13, max(b - 12, 0):b + 13].any()) for a, b in zip(r, c))


for e in ids:
    ev = evs.get_group(e).sort_values('t'); s = int(ev.season.iloc[0])
    ev = ev[ev.t <= ev.t.min() + pd.Timedelta(hours=HOURS - 1)]
    passes = sorted(ev.overpass.unique())
    if len(passes) < 2:
        continue
    if s not in wx:
        wx.clear(); wx[s] = sim.load_weather(s)
    o = sim.run_event(ev, wx[s], cfg, hours=HOURS, scar_fn=score.scar_footprint)
    B, S, win, t0 = o['burnable'], o['S'], o['win'], o['t0']
    Rh, Dh, Eh = o['Rh'], o['Dh'], o['Eh']

    def circle(ig, n):
        d = ndimage.distance_transform_edt(~ig) * sim.RES if ig.any() else np.full(B.shape, np.inf)
        dv = np.sort(d[B]); r = dv[min(max(n - 1, 0), len(dv) - 1)] if len(dv) else 0
        return B & (d <= r)

    def run(dets, tmax):
        ig, tg = sim.ignition_mask(dets, S, B, win, cfg, t0); ii, jj = np.nonzero(ig)
        T = arrival(Rh, Dh, Eh, B, ii.astype(np.int64), jj.astype(np.int64), tg[ii, jj], sim.RES, tmax, OFFS, strict) if len(ii) else np.full(B.shape, np.inf)
        return ig, T

    for k in range(1, len(passes)):
        target = ev[ev.overpass == passes[k]]; prev = ev[ev.overpass <= passes[k - 1]]
        tk = (target.t.min() - t0).total_seconds() / 60
        # new ground: target detections more than 400 m from every earlier detection
        dmin = np.array([np.hypot(prev.x.values - x, prev.y.values - y).min() for x, y in zip(target.x, target.y)])
        new = target[dmin > 400]
        A_free = o['T'] <= tk
        ig_rs, T_rs = run(prev, tk + 1); A_rs = T_rs <= tk
        C_free, C_rs = circle(o['ig'], int(A_free.sum())), circle(ig_rs, int(A_rs.sum()))
        P_rs = B & (ndimage.distance_transform_edt(~ig_rs) * sim.RES <= 375)
        row = dict(event=e, season=s, k=k, n_pass=len(passes), lead_h=(tk - (prev.t.max() - t0).total_seconds() / 60) / 60,
                   n_target=len(target), n_new=len(new), n_prev=len(prev), scar_px=int(S.sum()),
                   area_free=int(A_free.sum()), area_rs=int(A_rs.sum()), area_pers=int(P_rs.sum()))
        for nm, A in [('free', A_free), ('rs', A_rs), ('cfree', C_free), ('crs', C_rs), ('pers', P_rs)]:
            row[f'hit_{nm}'] = hits(target, A, win); row[f'hitnew_{nm}'] = hits(new, A, win) if len(new) else 0
        rows.append(row)
    # final footprint against the scar: free run vs restart with every detection
    if S.sum() >= 25 and rows and rows[-1]['event'] == e:
        tend = (ev.t.max() - t0).total_seconds() / 60 + 720
        ig_all, T_all = run(ev, tend)
        rows[-1].update(sor_free_end=score.soren(o['T'] <= tend, S), sor_rs_end=score.soren(T_all <= tend, S),
                        area_free_end=int((o['T'] <= tend).sum()), area_rs_end=int((T_all <= tend).sum()))
pd.DataFrame(rows).to_parquet(sys.argv[2])
print('done', len(rows))
