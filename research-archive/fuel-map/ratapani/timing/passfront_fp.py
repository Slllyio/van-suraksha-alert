"""passfront.py redone with each VIIRS detection as its pixel footprint (scan x track) clipped to the scar:
front at a pass = farthest scar pixel (walking distance from the first-pass points) inside any footprint seen so far.
Checked against 194 mid-fire S2/Landsat scenes: footprint far edge is unbiased (median -22 m, |err| 128 m);
the centre point lags the true front by ~380 m."""
import numpy as np, pandas as pd, rasterio, glob
from scipy import ndimage
from skimage.graph import MCP_Geometric
B = '/mnt/project-files/research/ratapani-burn-labels/rasters/burn_{}.tif'
cls = np.load('cls20.npy')
v = pd.read_parquet('/mnt/project-files/ratapani/spread/results/events_viirs.parquet'); v = v[v.t.dt.month <= 6]
fr = []
for f in glob.glob('/mnt/project-files/fire-alert-scars/alerts/viirs-*.csv'):
    a = pd.read_csv(f)
    if 'latitude' in a: fr.append(a[['latitude', 'longitude', 'acq_date', 'acq_time', 'scan', 'track']])
a = pd.concat(fr); a['t'] = pd.to_datetime(a.acq_date + ' ' + a.acq_time.astype(str).str.zfill(4), format='%Y-%m-%d %H%M')
a['k'] = a.latitude.round(5).astype(str) + a.longitude.round(5).astype(str) + a.t.astype(str)
v['k'] = v.latitude.round(5).astype(str) + v.longitude.round(5).astype(str) + v.t.astype(str)
v = v.merge(a.drop_duplicates('k')[['k', 'scan', 'track']], on='k', how='left'); print('footprint matched', v.scan.notna().mean().round(3))
v[['scan', 'track']] = v[['scan', 'track']].fillna(0.4)
np_ = v.groupby('event').overpass.nunique(); v = v[v.event.isin(np_[np_ >= 2].index)]
with rasterio.open(B.format(2017)) as s: TR = s.transform
rows = []
for yr in range(2017, 2025):
    with rasterio.open(B.format(yr)) as s: be, bs = s.read(1), s.read(2)
    for e, ev in v[v.season == yr].groupby('event'):
        d0, d1 = ev.t.min().dayofyear, ev.t.max().dayofyear
        r, c = rasterio.transform.rowcol(TR, ev.x.values, ev.y.values); r, c = np.array(r), np.array(c)
        if (r < 150).any() or (c < 150).any() or (r >= be.shape[0] - 150).any() or (c >= be.shape[1] - 150).any(): continue
        i0, j0 = r.min() - 150, c.min() - 150; i1, j1 = r.max() + 150, c.max() + 150
        m = (be[i0:i1, j0:j1] > -999) & (be[i0:i1, j0:j1] >= d0 - 2) & (bs[i0:i1, j0:j1] <= d1 + 2)
        lab, n = ndimage.label(m, structure=np.ones((3, 3)))
        if n == 0: continue
        rr, cc = r - i0, c - j0
        near = np.zeros(m.shape, bool); near[rr, cc] = True; near = ndimage.binary_dilation(near, iterations=20)
        keep = np.unique(lab[near & m]); keep = keep[keep > 0]; S = np.isin(lab, keep)
        if S.sum() < 50: continue
        dist, (iy, ix) = ndimage.distance_transform_edt(~S, return_indices=True)
        ok = dist[rr, cc] * 20 <= 400
        ev = ev[ok]; rr, cc = rr[ok], cc[ok]
        if ev.overpass.nunique() < 2: continue
        passes = sorted(ev.overpass.unique()); f0 = (ev.overpass == passes[0]).values
        G, _ = MCP_Geometric(np.where(S, 1.0, np.inf)).find_costs(list(zip(iy[rr[f0], cc[f0]], ix[rr[f0], cc[f0]])))
        G = np.where(S & np.isfinite(G), G * 20, np.nan)
        cx = (ev.x.values - (TR.c + j0 * 20)) / 20 - 0.5; cy = ((TR.f - i0 * 20) - ev.y.values) / 20 - 0.5
        hw, hh = ev.scan.values * 25 + 0.5, ev.track.values * 25 + 0.5
        def fpmax(idx):
            best = 0.0
            for k in idx:
                ys, ye = int(max(cy[k] - hh[k], 0)), int(min(cy[k] + hh[k], S.shape[0] - 1)) + 1
                xs, xe = int(max(cx[k] - hw[k], 0)), int(min(cx[k] + hw[k], S.shape[1] - 1)) + 1
                sub = G[ys:ye, xs:xe]
                if np.isfinite(sub).any(): best = max(best, np.nanmax(sub))
            return best
        cl = cls[i0:i1, j0:j1]
        front = fpmax(np.where(f0)[0]); tprev = ev.t[f0].min(); ext = np.nanmax(G)
        for p in passes[1:]:
            idx = np.where((ev.overpass == p).values)[0]; g = ev.iloc[idx]
            dt = (g.t.min() - tprev).total_seconds() / 3600
            if dt < 3: continue
            newf = max(front, fpmax(idx)); band = S & (G > front) & (G <= newf)
            comp = np.bincount(cl[band], minlength=5) / max(band.sum(), 1)
            rows.append(dict(event=e, season=yr, t_a=tprev, t_b=g.t.min(), dt_h=dt, night_b=(g.daynight == 'N').any(), front_a=front, front_b=newf,
                             adv_mh=(newf - front) / dt, area_ha_per_h=band.sum() * 0.04 / dt, scar_ha=S.sum() * 0.04, scar_extent_m=ext, front0=fpmax(np.where(f0)[0]),
                             c1=comp[1], c2=comp[2], c3=comp[3], c4=comp[4], month=g.t.min().month))
            front, tprev = newf, g.t.min()
d = pd.DataFrame(rows); d.to_parquet('passfront_fp.parquet')
print(len(d), 'intervals', d.event.nunique(), 'fires'); print('first footprint already reaches (m), median', d.groupby('event').front0.first().median().round(0), 'of extent', d.groupby('event').scar_extent_m.first().median().round(0))
print(d[['adv_mh', 'area_ha_per_h']].describe(percentiles=[.25, .5, .75, .9]).round(1))
d['dom'] = d[['c1', 'c2', 'c3', 'c4']].values.argmax(1) + 1
print(d.groupby('dom').adv_mh.agg(['size', 'median']).round(1)); print(d.groupby('night_b').adv_mh.agg(['size', 'median']).round(1)); print(d.groupby('season').adv_mh.agg(['size', 'median']).round(1))
print('share of intervals with zero advance', (d.adv_mh == 0).mean().round(2))
