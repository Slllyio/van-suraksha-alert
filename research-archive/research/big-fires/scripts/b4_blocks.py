"""Step 4: every satellite's detections as real-size blocks, and what they add over VIIRS alone (Akkshay, 16 Oct 18:01Z).

Detections on each fire's scar (v2 union), each drawn as its true footprint block:
  VIIRS (S-NPP, NOAA-20, NOAA-21): scan x track km rectangle (375 m at nadir, wider toward the swath edge)
  MODIS (Terra ~10:30/22:30, Aqua ~13:30/01:30 local): scan x track km rectangle (1 km+)
  Sentinel-2 / Landsat hot pixels (scar thread's af_scan, ~10:30 local): 30 m square
For every 30 m pixel of the fire box: block arrival time = time of the first block covering it.
Per fire: number of distinct look times, gap between looks, scar share covered, and the advance of new burning beyond
everything burning before (rate m/h, bearing). Done twice: VIIRS blocks only, and all sensors.
Out: results/blocks_fires.csv, results/blocks_steps.csv, results/blocks_cache.pkl (per fire grids for the photo test)
"""
import glob, os, pickle
import numpy as np, pandas as pd
import pyproj
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.ndimage import distance_transform_edt

ROOT = '/mnt/project-files'
R = f'{ROOT}/research/big-fires/results'
RES = 30.0
F = pd.read_csv(f'{R}/fires.csv')
A = pd.read_csv(f'{R}/fire_alerts.csv', parse_dates=['t'])
S = pickle.load(open(f'{R}/fire_scars.pkl', 'rb'))
F['big'] = (F.area_ha >= 200) & (F.n_looks >= 4) & (F.n_viirs >= 10) & ~F.still_at_edge
SEL = F[(F.n_looks >= 2) & (F.area_ha >= 50) & ~F.still_at_edge]   # big fires + smaller comparison set (also used by the photo test)
tp = pyproj.Transformer.from_crs(4326, 32643, always_xy=True).transform

hp = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(f'{ROOT}/fire-alert-scars/out/af/af_*.csv'))], ignore_index=True)
hp['t'] = pd.to_datetime(hp.date + ' ' + hp.time_utc)
hp['x'], hp['y'] = tp(hp.lon.values, hp.lat.values)
hp['date'] = pd.to_datetime(hp.date)

def blocks_for(f):
    poly = S[f.fire]
    a = A[A.fire == f.fire].copy()
    d0, d1 = pd.Timestamp(f.date0) - pd.Timedelta(days=1), pd.Timestamp(f.date1) + pd.Timedelta(days=2)
    a['kind'] = np.where(a.sat == 'modis', 'modis', 'viirs')
    a['hw'] = a.scan.fillna(0.375 if True else 1) * 500
    a['hh'] = a.track.fillna(0.375) * 500
    a.loc[a.kind == 'modis', 'hw'] = a.loc[a.kind == 'modis', 'scan'].fillna(1.0) * 500
    a.loc[a.kind == 'modis', 'hh'] = a.loc[a.kind == 'modis', 'track'].fillna(1.0) * 500
    x0, y0, x1, y1 = poly.bounds
    h = hp[(hp.x > x0 - 300) & (hp.x < x1 + 300) & (hp.y > y0 - 300) & (hp.y < y1 + 300) & (hp.date >= d0) & (hp.date <= d1)]
    h = h[[poly.buffer(100).contains(__import__('shapely').geometry.Point(xx, yy)) for xx, yy in zip(h.x, h.y)]] if len(h) else h
    h = h.assign(kind='hotpix', hw=RES / 2, hh=RES / 2, sat=h.sensor if len(h) else [])
    return pd.concat([a[['t', 'x', 'y', 'kind', 'hw', 'hh', 'sat']], h[['t', 'x', 'y', 'kind', 'hw', 'hh', 'sat']]], ignore_index=True).sort_values('t')

def grid_for(poly, pad=1500):
    x0, y0, x1, y1 = poly.bounds
    tr = from_origin(x0 - pad, y1 + pad, RES, RES)
    shp = (int((y1 - y0 + 2 * pad) / RES) + 1, int((x1 - x0 + 2 * pad) / RES) + 1)
    return tr, shp, rasterize([(poly, 1)], out_shape=shp, transform=tr).astype(bool)

def arrival(b, tr, shp):
    """first time each pixel is covered by a block (hours since epoch; inf = never)"""
    T = np.full(shp, np.inf)
    for r in b.itertuples():
        c0 = int((r.x - r.hw - tr[2]) / RES); c1 = int(np.ceil((r.x + r.hw - tr[2]) / RES))
        r0 = int((tr[5] - (r.y + r.hh)) / RES); r1 = int(np.ceil((tr[5] - (r.y - r.hh)) / RES))
        c0, r0 = max(c0, 0), max(r0, 0); c1, r1 = min(c1, shp[1]), min(r1, shp[0])
        if c1 <= c0 or r1 <= r0: continue
        th = r.t.value / 3.6e12
        T[r0:r1, c0:c1] = np.minimum(T[r0:r1, c0:c1], th)
    return T

def slots(b):
    """distinct look times: detections within 2 h of the previous one share a look"""
    s = (b.t.diff() > pd.Timedelta(hours=2)).cumsum()
    return s.values

fires_out, steps_out, cache = [], [], {}
for _, f in SEL.iterrows():
    b = blocks_for(f)
    if not len(b): continue
    tr, shp, scar = grid_for(S[f.fire])
    rec = dict(fire=f.fire, big=f.big, area_ha=f.area_ha, n_hotpix=int((b.kind == 'hotpix').sum()), n_modis=int((b.kind == 'modis').sum()),
               n_viirs=int((b.kind == 'viirs').sum()))
    cache[f.fire] = dict(tr=tr, shp=shp, blocks=b)
    for mode, bb in [('viirs', b[b.kind == 'viirs']), ('all', b)]:
        bb = bb.sort_values('t').reset_index(drop=True)
        if not len(bb): continue
        bb['slot'] = slots(bb)
        st = bb.groupby('slot').t.agg(['min', 'max'])
        rec[f'{mode}_looks'] = len(st)
        gaps = st['min'].diff().dt.total_seconds().dropna() / 3600
        rec[f'{mode}_gap_med'] = gaps.median() if len(gaps) else np.nan
        T = arrival(bb, tr, shp)
        rec[f'{mode}_cover'] = np.isfinite(T[scar]).mean()
        # advance of each look beyond everything covered before it
        for s, g in bb.groupby('slot'):
            tprev = g.t.min().value / 3.6e12 - 1e-6
            before = np.isfinite(T) & (T < tprev)
            if not before.any(): continue
            cur = arrival(g, tr, shp); newpx = np.isfinite(cur) & ~before
            if newpx.sum() == 0: continue
            dist = distance_transform_edt(~before) * RES
            dn = dist[newpx]
            if dn.max() <= 0: continue
            last_t = T[before].max()   # most recent burning before this look
            dt = tprev - last_t
            rr, cc = np.where(newpx & (dist > 0))
            br, bc = np.where(before)
            if not len(rr): continue
            # bearing from the latest-burning ground to the new ground beyond it
            lr, lc = np.where(before & (T >= last_t - 2))
            vx = (cc.mean() - lc.mean()) * RES; vy = -(rr.mean() - lr.mean()) * RES
            steps_out.append(dict(fire=f.fire, big=f.big, mode=mode, t=g.t.min(), kinds='+'.join(sorted(g.kind.unique())),
                                  dt_h=dt, adv_max=dn.max(), adv_med=np.median(dn[dn > 0]), new_ha=newpx.sum() * RES * RES / 1e4,
                                  bearing=np.degrees(np.arctan2(vx, vy)) % 360, move=np.hypot(vx, vy)))
    fires_out.append(rec)
pd.DataFrame(fires_out).to_csv(f'{R}/blocks_fires.csv', index=False)
pd.DataFrame(steps_out).to_csv(f'{R}/blocks_steps.csv', index=False)
pickle.dump(cache, open(f'{R}/blocks_cache.pkl', 'wb'))
Bf = pd.DataFrame(fires_out)
print(Bf.groupby('big')[['n_viirs', 'n_modis', 'n_hotpix', 'viirs_looks', 'all_looks', 'viirs_gap_med', 'all_gap_med', 'viirs_cover', 'all_cover']].median().round(2))
