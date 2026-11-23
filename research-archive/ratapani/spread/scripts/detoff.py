"""Where do VIIRS detections sit relative to the mapped burn scar, and does the ERA5 wind explain the offset?
Per detection: distance and direction to the nearest pixel of the event's matched scar, to the nearest burn label of
the season (any date window), WorldCover class under the point, pixel size (scan x track), day/night, wind at that hour.
Usage: detoff.py out.parquet [event_id]"""
import numpy as np, pandas as pd, sys
from scipy import ndimage
import sim, score
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); v = v[v.t.dt.month <= 6]
if len(sys.argv) > 2:
    v = v[v.event == int(sys.argv[2])]
rows, wx = [], {}
pad = 150   # 3 km
for e, ev in v.groupby('event'):
    ev = ev.sort_values('t'); s = int(ev.season.iloc[0])
    if s not in wx:
        wx.clear(); wx[s] = sim.load_weather(s)
    r, c = sim.rc(ev.x.values, ev.y.values)
    i0, i1 = max(r.min() - pad, 0), min(r.max() + pad, sim.NY); j0, j1 = max(c.min() - pad, 0), min(c.max() + pad, sim.NX)
    o = dict(win=(i0, i1, j0, j1), season=s)
    S, _ = score.scar_footprint(o, ev)
    be = sim.G[f'burn_end_{s}'][i0:i1, j0:j1]; bs = sim.G[f'burn_start_{s}'][i0:i1, j0:j1]
    anyb = be > -999
    wc = sim.WC[i0:i1, j0:j1]
    if S.sum() < 125:   # need a mapped scar >= 5 ha
        continue
    dS, (iS, jS) = ndimage.distance_transform_edt(~S, return_indices=True)
    dA, (iA, jA) = ndimage.distance_transform_edt(~anyb, return_indices=True)
    ys, xs = np.nonzero(S); cx, cy = xs.mean(), ys.mean()
    passes = sorted(ev.overpass.unique())
    W, P = wx[s]; pid = P.index[np.argmin(np.hypot(P.x - ev.x.mean(), P.y - ev.y.mean()))]
    for _, d in ev.iterrows():
        rr, cc = sim.rc(np.array([d.x]), np.array([d.y])); rr = int(rr[0] - i0); cc = int(cc[0] - j0)
        rr = min(max(rr, 0), S.shape[0] - 1); cc = min(max(cc, 0), S.shape[1] - 1)
        # offset from the detection to the nearest scar pixel (east, north) in metres
        ox, oy = (jS[rr, cc] - cc) * sim.RES, -(iS[rr, cc] - rr) * sim.RES
        oax, oay = (jA[rr, cc] - cc) * sim.RES, -(iA[rr, cc] - rr) * sim.RES
        th = d.t.floor('h')
        w = W[pid].loc[th] if th in W[pid].index else None
        waz = float(w.waz) if w is not None else np.nan; ws = float(w.ws) if w is not None else np.nan
        off_az = (np.degrees(np.arctan2(ox, oy)) + 360) % 360 if (ox or oy) else np.nan
        cen_az = (np.degrees(np.arctan2(cx - cc, -(cy - rr))) + 360) % 360
        rows.append(dict(event=e, season=s, t=d.t, pass_idx=passes.index(d.overpass), n_pass=len(passes), daynight=d.daynight,
                         scan=d.scan, track=d.track, frp=d.frp, conf=d.confidence, wc=int(wc[rr, cc]),
                         inside=bool(S[rr, cc]), dist_scar=float(dS[rr, cc] * sim.RES), off_x=ox, off_y=oy, off_az=off_az,
                         dist_any=float(dA[rr, cc] * sim.RES), any_bs=int(bs[iA[rr, cc], jA[rr, cc]]), any_be=int(be[iA[rr, cc], jA[rr, cc]]),
                         doy=d.t.dayofyear, cen_az=cen_az, cen_d=float(np.hypot(cx - cc, cy - rr) * sim.RES),
                         wind_az=waz, wind_ms=ws, scar_px=int(S.sum())))
d = pd.DataFrame(rows); d.to_parquet(sys.argv[1]); print('detections', len(d), 'fires', d.event.nunique())
