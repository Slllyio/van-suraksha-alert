"""Per-pixel table for a learned spread correction: physics arrival time + geometry + fuel + weather,
label = pixel in the event's 20 m burn scar. Usage: hybrid_data.py cfgjson out.parquet k/n"""
import numpy as np, pandas as pd, sys, json
from scipy import ndimage
import sim, score
cfg = json.loads(sys.argv[1]); k_, n_ = map(int, sys.argv[3].split('/'))
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); v = v[(v.season <= 2024) & (v.t.dt.month <= 6)]
evs = v.groupby('event'); ids = sorted(evs.groups)[k_::n_]
rng = np.random.default_rng(k_); out = []; wx = {}
for e in ids:
    ev = evs.get_group(e).sort_values('t'); s = int(ev.season.iloc[0])
    if s not in wx:
        wx.clear(); wx[s] = sim.load_weather(s)
    o = sim.run_event(ev, wx[s], cfg, hours=48, scar_fn=score.scar_footprint)
    S = o['S']
    if S.sum() < 25 or o['ig'].sum() == 0:
        continue
    i0, i1, j0, j1 = o['win']; T, dist, B, ig = o['T'], o['dist'], o['burnable'], o['ig']
    yy, xx = np.mgrid[i0:i1, j0:j1]
    ci, cj = np.nonzero(ig); ci, cj = ci.mean() + i0, cj.mean() + j0
    bearing = np.arctan2(xx - cj, -(yy - ci))
    W, P = wx[s]; pid = P.index[np.argmin(np.hypot(P.x - ev.x.mean(), P.y - ev.y.mean()))]
    w = W[pid].loc[o['t0']: o['t0'] + pd.Timedelta(hours=23)]
    u = (w.ws * np.sin(np.radians(w.waz))).mean(); vv = (w.ws * np.cos(np.radians(w.waz))).mean()
    wind_al = (np.sin(bearing) * u + np.cos(bearing) * vv)
    el = sim.ELEV[i0:i1, j0:j1]; el0 = el[ig].mean()
    nb_dist = ndimage.distance_transform_edt(B) * sim.RES
    bfrac = ndimage.uniform_filter(B.astype(float), 11)
    prev = sim.G.get(f'burn_end_{s-1}') if f'burn_end_{s-1}' in sim.G.files else None
    burned_prev = (prev[i0:i1, j0:j1] > -999) if prev is not None else np.zeros(B.shape, bool)
    tmin = T - (ev.t.min() - o['t0']).total_seconds() / 60
    sel = (dist <= 4000)
    neg = sel & ~S & (rng.random(S.shape) < 0.15)
    take = (sel & S) | neg
    df = pd.DataFrame(dict(event=e, season=s, label=S[take].astype(np.int8), w=np.where(S[take], 1.0, 1 / 0.15),
        dist=dist[take], t_phys=np.where(np.isfinite(tmin[take]), tmin[take], 1e5), wind_al=wind_al[take],
        dz=el[take] - el0, slope=sim.SLOPE[i0:i1, j0:j1][take], wc=sim.WC[i0:i1, j0:j1][take],
        burnable=B[take], nb_dist=nb_dist[take], bfrac=bfrac[take], burned_prev=burned_prev[take],
        n_det=len(ev), doy=ev.t.min().dayofyear, rh_min=w.rh.min(), m1_min=w.m1.min(), ws_mean=w.ws.mean(),
        scar_px=int(S.sum()), n_sel=int(sel.sum())))
    out.append(df)
pd.concat(out).to_parquet(sys.argv[2])
