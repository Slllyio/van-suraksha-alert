"""If the forecast were headed in a known direction, how much better would its outline match the scar?
Footprint = the scar-area set of nearest burnable pixels under an anisotropic distance from the first-pass detection
pixels (each snapped to the nearest burnable pixel): the detection sits at the rear focus of a fire ellipse, distance
along the heading divided by k (forward stretch) and multiplied by 2 against it (backing). k = 1 is the plain circle.
Headings: oracle (first detections -> scar centroid) and the cues in rundir.parquet.
Usage: headtest2.py rundir.parquet out.parquet [k/n]"""
import numpy as np, pandas as pd, sys
from scipy import ndimage
import sim, score
rd = pd.read_parquet(sys.argv[1]).set_index('event')
k_, n_ = map(int, sys.argv[3].split('/')) if len(sys.argv) > 3 else (0, 1)
v = pd.read_parquet(f'{sim.DATA}/viirs_events.parquet'); v = v[v.t.dt.month <= 6]
HEADS = ['run_az', 'mom_az', 'vill_az', 'burn_az', 'fuel_az', 'edge_az', 'road_az', 'load_az', 'wind_az', 'down_az']
rows = []; wx = {}
for e, ev in list(v.groupby('event'))[k_::n_]:
    if e not in rd.index:
        continue
    ev = ev.sort_values('t'); s = int(ev.season.iloc[0])
    if s not in wx:
        wx.clear(); wx[s] = sim.load_weather(s)
    o = sim.run_event(ev, wx[s], dict(fuel='rfuel', wind=False, pad_m=4000), hours=1, scar_fn=score.scar_footprint)
    S, B, (i0, i1, j0, j1) = o['S'], o['burnable'], o['win']
    n = int(S.sum())
    if n < 125:
        continue
    first = ev[ev.overpass == ev.overpass.min()]
    r, c = sim.rc(first.x.values, first.y.values); r -= i0; c -= j0
    # snap each first-pass detection to the nearest burnable pixel within 400 m
    _, (ir, ic) = ndimage.distance_transform_edt(~B, return_indices=True)
    pts = []
    for a, b in zip(np.clip(r, 0, B.shape[0] - 1), np.clip(c, 0, B.shape[1] - 1)):
        ii, jj = ir[a, b], ic[a, b]
        if np.hypot(ii - a, jj - b) * sim.RES <= 400:
            pts.append((ii, jj))
    pts = list(set(pts))
    if not pts:
        continue
    yy, xx = np.mgrid[0:S.shape[0], 0:S.shape[1]]
    row = dict(event=e, season=s, scar_px=n, n_pts=len(pts))
    for k in (1.0, 2.0, 3.0):
        for hd in (['none'] if k == 1.0 else HEADS):
            a = rd.loc[e, hd] if hd != 'none' else np.nan
            if hd != 'none' and not np.isfinite(a):
                row[f'sor_{hd}_k{k:.0f}'] = np.nan; continue
            ax, ay = (np.sin(np.radians(a)), np.cos(np.radians(a))) if hd != 'none' else (0.0, 1.0)
            d = np.full(S.shape, np.inf)
            for i, j in pts:
                dx, dy = (xx - j).astype(float), -(yy - i).astype(float)
                along = dx * ax + dy * ay; across = -dx * ay + dy * ax
                if k > 1:
                    along = np.where(along > 0, along / k, along * 2.0)
                d = np.minimum(d, np.hypot(along, across))
            row[f'sor_{hd}_k{k:.0f}'] = score.soren(score.topn(d, B, n), S)
    rows.append(row)
pd.DataFrame(rows).to_parquet(sys.argv[2]); print('done', len(rows))
