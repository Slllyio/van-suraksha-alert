"""Front advance between VIIRS passes along each fire's own burn scar (S-NPP + NOAA-20 + NOAA-21).
Per fire: snap detections (<=400 m) to scar pixels, geodesic distance inside the scar from the first-pass pixels,
front of pass k = farthest snapped detection so far. Per interval (>=3 h): front advance (m/h), area newly enclosed
(scar pixels whose geodesic distance falls between the two fronts) per hour, and its fuel-class mix."""
import numpy as np, pandas as pd, rasterio
from scipy import ndimage
from skimage.graph import MCP_Geometric
B = '/mnt/project-files/research/ratapani-burn-labels/rasters/burn_{}.tif'
cls = np.load('cls20.npy')
ds = lambda a: a.astype(np.float32).reshape(1674, 2, 3772, 2).mean((1, 3))
SL = ds(np.load('../static10.npz')['slope']); LF = np.load('../leaffall.npz'); LF = {m: ds(LF[k]) for m, k in [(12,'m12'),(1,'m01'),(2,'m02'),(3,'m03'),(4,'m04')]}
TP = ds(np.load('../teakprob2.npy'))
last = np.full((1674, 3772), -1, np.int16)
v = pd.read_parquet('/mnt/project-files/ratapani/spread/results/events_viirs.parquet'); v = v[v.t.dt.month <= 6]
np_ = v.groupby('event').overpass.nunique(); v = v[v.event.isin(np_[np_ >= 2].index)]
with rasterio.open(B.format(2017)) as s: TR = s.transform
rows = []
for yr in range(2017, 2025):
    with rasterio.open(B.format(yr)) as s: be, bs = s.read(1), s.read(2)
    ysb_all = np.where(last >= 0, yr - last, 9).clip(max=9)
    for e, ev in v[v.season == yr].groupby('event'):
        d0, d1 = ev.t.min().dayofyear, ev.t.max().dayofyear
        r, c = rasterio.transform.rowcol(TR, ev.x.values, ev.y.values); r, c = np.array(r), np.array(c)
        if (r < 0).any() or (c < 0).any() or (r >= be.shape[0]).any() or (c >= be.shape[1]).any(): continue
        i0, j0 = max(r.min() - 150, 0), max(c.min() - 150, 0); i1, j1 = r.max() + 150, c.max() + 150
        m = (be[i0:i1, j0:j1] > -999) & (be[i0:i1, j0:j1] >= d0 - 2) & (bs[i0:i1, j0:j1] <= d1 + 2)
        lab, n = ndimage.label(m, structure=np.ones((3, 3)))
        if n == 0: continue
        rr, cc = r - i0, c - j0
        near = np.zeros(m.shape, bool); near[rr, cc] = True; near = ndimage.binary_dilation(near, iterations=20)
        keep = np.unique(lab[near & m]); keep = keep[keep > 0]; S = np.isin(lab, keep)
        if S.sum() < 50: continue                                      # >= 2 ha
        dist, (iy, ix) = ndimage.distance_transform_edt(~S, return_indices=True)
        dsnap = dist[rr, cc] * 20; sy, sx = iy[rr, cc], ix[rr, cc]
        ev = ev.assign(sy=sy, sx=sx, dsnap=dsnap); ev = ev[ev.dsnap <= 400]
        if ev.overpass.nunique() < 2: continue
        passes = sorted(ev.overpass.unique()); p0 = ev[ev.overpass == passes[0]]
        cost = np.where(S, 1.0, np.inf); mcp = MCP_Geometric(cost)
        G, _ = mcp.find_costs(list(zip(p0.sy, p0.sx))); G = np.where(np.isfinite(G), G * 20, np.nan)
        cl = cls[i0:i1, j0:j1]
        front, tprev = 0.0, p0.t.min()
        ext = np.nanmax(G)
        for p in passes[1:]:
            g = ev[ev.overpass == p]; dk = np.nanmax(G[g.sy, g.sx])
            if not np.isfinite(dk): continue
            dt = (g.t.min() - tprev).total_seconds() / 3600
            if dt < 3: continue
            newf = max(front, dk); band = S & (G > front) & (G <= newf)
            comp = np.bincount(cl[band], minlength=5) / max(band.sum(), 1)
            mo = g.t.min().month; lf = LF[min(mo, 4)] if mo != 12 else LF[12]
            sub = lambda A: float(A[i0:i1, j0:j1][band].mean()) if band.any() else np.nan
            extra = dict(slope=sub(SL), leaffall=sub(lf), teak=sub(TP), ysb=sub(ysb_all), ysb1=float((ysb_all[i0:i1, j0:j1][band] == 1).mean()) if band.any() else np.nan)
            rows.append(dict(**extra, event=e, season=yr, t_a=tprev, t_b=g.t.min(), dt_h=dt, night_b=(g.daynight == 'N').any(), front_a=front, front_b=newf,
                             adv_mh=(newf - front) / dt, area_ha_per_h=band.sum() * 0.04 / dt, scar_ha=S.sum() * 0.04, scar_extent_m=ext,
                             c1=comp[1], c2=comp[2], c3=comp[3], c4=comp[4], n_det_b=len(g), snap_med=g.dsnap.median(), month=g.t.min().month))
            front, tprev = newf, g.t.min()
    last[be > -999] = yr
d = pd.DataFrame(rows); d.to_parquet('passfront2.parquet')
print(len(d), 'intervals from', d.event.nunique(), 'fires'); print(d[['dt_h', 'adv_mh', 'area_ha_per_h']].describe(percentiles=[.25, .5, .75, .9]).round(2))
